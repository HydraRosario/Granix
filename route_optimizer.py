import logging
from math import radians, sin, cos, sqrt, atan2
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

from shared_utils import geocode_address

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

def optimize_route(addresses: list, depot_address: str = "Mendoza 8895, Rosario, Santa Fe, Argentina"):
    """
    Encuentra la ruta óptima para una lista de direcciones usando Google OR-Tools.
    Prioriza el uso de coordenadas existentes antes de llamar a la API de geocodificación.
    """
    if not addresses:
        return []

    # 1. Consolidar y obtener coordenadas para todas las ubicaciones
    all_locations = [{'address': depot_address, 'is_depot': True}] + addresses
    location_coords = []
    for loc in all_locations:
        # Prioriza las coordenadas existentes pasadas desde el servicio
        coords = loc.get('coordinates')
        
        # Si no hay coordenadas válidas, geocodifica como fallback
        if not coords or coords.get('latitude') is None:
            logger.info(f"Coordenadas no encontradas para '{loc['address']}', geocodificando...")
            coords = geocode_address(loc['address'])

        if coords and coords.get('latitude') is not None:
            loc['coordinates'] = coords
            location_coords.append(loc)
        else:
            logger.warning(f"No se pudieron obtener las coordenadas para la dirección: {loc['address']}. Se omitirá de la optimización.")

    if len(location_coords) < 2:
        logger.warning("No hay suficientes ubicaciones con coordenadas válidas para optimizar.")
        return addresses # Devuelve el orden original

    # 2. Construir la matriz de distancias
    num_locations = len(location_coords)
    distance_matrix = [[0] * num_locations for _ in range(num_locations)]
    for i in range(num_locations):
        for j in range(num_locations):
            if i != j:
                distance_matrix[i][j] = haversine_distance(location_coords[i]['coordinates'], location_coords[j]['coordinates'])

    # 3. Configurar y resolver el problema de enrutamiento (TSP) con OR-Tools
    manager = pywrapcp.RoutingIndexManager(num_locations, 1, 0)
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

    # 4. Extraer y devolver la ruta optimizada
    if solution:
        logger.info(f"Solución encontrada con una distancia total de: {solution.ObjectiveValue()} metros.")
        ordered_route = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            ordered_route.append(location_coords[node_index])
            index = solution.Value(routing.NextVar(index))
        ordered_route.append(location_coords[manager.IndexToNode(index)])
        
        # Devolver la lista sin el depósito al inicio y al final
        return ordered_route[1:-1]
    else:
        logger.error("No se encontró una solución para la optimización de la ruta.")
        return addresses