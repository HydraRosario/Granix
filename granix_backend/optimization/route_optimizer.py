import logging
import requests
import polyline
from math import radians, sin, cos, sqrt, atan2
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

from granix_backend.utils.shared_utils import geocode_address

# Configurar logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def haversine_distance(coord1, coord2):
    """
    Calcula la distancia de gran círculo entre dos puntos en la tierra (en metros).
    """
    R = 6371000  # Radio de la Tierra en metros
    lat1, lon1 = radians(coord1['latitude']), radians(coord1['longitude'])
    lat2, lon2 = radians(coord2['latitude']), radians(coord2['longitude'])

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return int(distance) # OR-Tools prefiere distancias enteras

def optimize_route(addresses: list):
    """
    Encuentra la ruta óptima para una lista de direcciones, comenzando y terminando
    en la dirección de la empresa (depósito). Utiliza Google OR-Tools para resolver
    el Problema del Viajante de Comercio (TSP).
    """
    if not addresses:
        return []

    # 1. Definir el depósito y obtener sus coordenadas.
    # Esta es la dirección fija de la empresa desde donde salen y a donde regresan los repartos.
    depot_address = "Mendoza 8195, Rosario, Santa Fe, Argentina"
    depot_coords = geocode_address(depot_address)

    if not depot_coords or depot_coords.get('latitude') is None:
        logger.error(f"No se pudieron obtener las coordenadas para el depósito: {depot_address}. No se puede optimizar la ruta.")
        return addresses

    depot_location = {'address': depot_address, 'coordinates': depot_coords, 'is_depot': True}

    # 2. Preparar la lista de todas las paradas (depósito + entregas).
    # El depósito se inserta al principio de la lista de ubicaciones.
    # Su índice (0) se usará para definir el inicio y fin de la ruta.
    all_locations = [depot_location] + addresses
    location_coords = []

    for i, loc in enumerate(all_locations):
        coords = loc.get('coordinates')
        # Si una dirección de entrega no tiene coordenadas, intenta geocodificarla.
        if (not coords or coords.get('latitude') is None) and not loc.get('is_depot'):
            logger.info(f"Coordenadas no encontradas para '{loc['address']}', geocodificando...")
            coords = geocode_address(loc['address'])

        if coords and coords.get('latitude') is not None:
            loc['coordinates'] = coords
            location_coords.append(loc)
        else:
            logger.warning(f"No se pudieron obtener las coordenadas para la dirección: {loc['address']}. Se omitirá.")

    if len(location_coords) < 2:
        logger.warning("No hay suficientes ubicaciones con coordenadas para optimizar. Se devuelve el orden original.")
        return addresses

    # 3. Construir la matriz de distancias entre todas las ubicaciones.
    num_locations = len(location_coords)
    distance_matrix = [[0] * num_locations for _ in range(num_locations)]
    for i in range(num_locations):
        for j in range(num_locations):
            if i != j:
                distance_matrix[i][j] = haversine_distance(
                    location_coords[i]['coordinates'],
                    location_coords[j]['coordinates']
                )

    # 4. Configurar y resolver el problema de enrutamiento con OR-Tools.
    # Se crea un gestor de índices de enrutamiento.
    # - num_locations: Total de paradas.
    # - 1: Número de vehículos (en este caso, una sola ruta).
    # - [0]: Nodo de inicio (índice 0, que corresponde al depósito).
    # - [0]: Nodo de fin (índice 0, forzando el regreso al depósito).
    manager = pywrapcp.RoutingIndexManager(num_locations, 1, [0], [0])
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    search_parameters.local_search_metaheuristic = (routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    search_parameters.time_limit.FromSeconds(5)

    logger.info("Resolviendo la ruta óptima con OR-Tools...")
    solution = routing.SolveWithParameters(search_parameters)

    # 5. Extraer y devolver la ruta optimizada.
    if solution:
        logger.info(f"Solución encontrada con una distancia total de: {solution.ObjectiveValue()} metros.")
        ordered_route = []
        index = routing.Start(0)
        # El primer nodo es el depósito, lo saltamos en el resultado final.
        index = solution.Value(routing.NextVar(index))
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            ordered_route.append(location_coords[node_index])
            index = solution.Value(routing.NextVar(index))
        
        # La ruta devuelta contiene solo las direcciones de entrega en el orden óptimo.
        return ordered_route
    else:
        logger.error("No se encontró una solución para la optimización de la ruta.")
        return addresses

def get_street_level_route(stops: list) -> list:
    """
    Obtiene una polilínea de ruta a nivel de calle desde OSRM para una lista de paradas.

    :param stops: Una lista de diccionarios de paradas, cada uno con una clave 'coordinates'.
    :return: Una lista de tuplas de coordenadas (lat, lon) que representan la polilínea.
    """
    if not stops or len(stops) < 2:
        logger.warning("Se necesitan al menos dos paradas para generar una ruta a nivel de calle.")
        return []

    # Formatear las coordenadas para la URL de la API de OSRM (lon,lat;lon,lat;...)
    coords_str = ";".join(
        f"{stop['coordinates']['longitude']},{stop['coordinates']['latitude']}" 
        for stop in stops if stop.get('coordinates')
    )

    # URL del servidor público de OSRM. Para producción, se recomienda un servidor propio.
    # Parámetros: overview=full (geometría detallada), geometries=polyline (formato codificado)
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=polyline"

    try:
        logger.info("Consultando a OSRM para obtener la ruta a nivel de calle...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()  # Lanza un error para respuestas 4xx/5xx
        
        data = response.json()

        if data.get('code') == 'Ok' and data.get('routes'):
            # Extraer la geometría de la primera ruta encontrada
            encoded_polyline = data['routes'][0]['geometry']
            
            # Decodificar la polilínea para obtener una lista de coordenadas [lat, lon]
            decoded_coords = polyline.decode(encoded_polyline)
            
            logger.info(f"Ruta a nivel de calle obtenida con {len(decoded_coords)} puntos.")
            return decoded_coords
        else:
            logger.error(f"OSRM no pudo encontrar una ruta. Respuesta: {data.get('message')}")
            return []

    except requests.exceptions.RequestException as e:
        logger.error(f"Error al contactar al servidor de OSRM: {e}")
        return []
    except Exception as e:
        logger.error(f"Error inesperado al procesar la respuesta de OSRM: {e}")
        return []