import logging
from uuid import uuid4
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from granix_backend.parsing.delivery_parser import DeliveryReportParser
from granix_backend.services.customer_service import CustomerService
from granix_backend.optimization.route_optimizer import optimize_route, get_street_level_route

# Configurar logger para delivery_service.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def process_delivery_report_data(raw_ocr_text: str) -> dict:
    """
    Procesa un informe de reparto, guarda ítems, optimiza la ruta y genera la lista de carga LIFO.
    """
    db = firestore.client()
    parser = DeliveryReportParser()
    customer_service = CustomerService()
    
    parsed_data = parser.parse_delivery_report_text(raw_ocr_text)
    delivery_items = parsed_data.get('delivery_items', [])

    if not delivery_items:
        return parsed_data

    processed_items = []
    # 1. Guardar/actualizar clientes y guardar cada delivery_item individualmente
    for item in delivery_items:
        address = item.get('delivery_address')
        if not address or address == 'No encontrado':
            continue

        item['address'] = address
        customer_data = customer_service.upsert_customer(item, 'delivery_report')
        
        # Asignar datos del cliente y coordenadas si están disponibles
        if customer_data and customer_data.get('id'):
            item['customer_id'] = customer_data['id']
            if customer_data.get('coordinates'):
                item['coordinates'] = customer_data['coordinates']

        # Verificar si la geocodificación falló
        coordinates = item.get('coordinates')
        if not coordinates or coordinates.get('latitude') is None or coordinates.get('longitude') is None:
            item['status'] = 'review_required'
            item['error_notes'] = "Error de geocodificación. Requiere revisión manual."
        else:
            item['status'] = 'pending_link'

        # Preparar un documento limpio para Firestore
        delivery_item_doc = {
            'delivery_address': address,
            'commercial_entity': item.get('commercial_entity'),
            'packages': item.get('packages'),
            'delivery_instructions': item.get('delivery_instructions'),
            'customer_id': item.get('customer_id'),
            'createdAt': firestore.SERVER_TIMESTAMP,
            'status': item['status']
        }
        if 'error_notes' in item:
            delivery_item_doc['error_notes'] = item['error_notes']

        delivery_item_id = uuid4().hex
        db.collection('delivery_items').document(delivery_item_id).set(delivery_item_doc)
        logger.info(f"Guardado delivery_item {delivery_item_id} para la dirección '{address}' con estado '{item['status']}'")
        processed_items.append(item)

    # 2. Optimizar la ruta de entrega, excluyendo los que requieren revisión
    valid_stops_for_optimization = [
        item for item in processed_items 
        if item.get('status') != 'review_required' and 'coordinates' in item and item['coordinates'].get('latitude') is not None
    ]
    
    if valid_stops_for_optimization:
        logger.info(f"Iniciando optimización de ruta para {len(valid_stops_for_optimization)} paradas.")
        optimized_route = optimize_route(valid_stops_for_optimization)
        parsed_data['optimized_route'] = optimized_route

        if optimized_route:
            street_level_polyline = get_street_level_route(optimized_route)
            parsed_data['street_level_polyline'] = street_level_polyline
            
            # --- Lógica de Carga LIFO Refactorizada ---
            logger.info("Generando lista de carga LIFO a partir de la ruta optimizada.")
            optimized_loading_list = optimized_route[::-1]
            
            addresses = [stop['address'] for stop in optimized_loading_list if 'address' in stop]
            
            if addresses:
                delivery_items_ref = db.collection('delivery_items')
                # La consulta ahora puede buscar items que están listos para ser vinculados o ya vinculados
                delivery_query = delivery_items_ref.where(filter=FieldFilter('delivery_address', 'in', addresses))
                
                delivery_items_map = {doc.to_dict()['delivery_address']: doc.to_dict() for doc in delivery_query.stream()}
                
                for stop in optimized_loading_list:
                    stop_address = stop.get('address')
                    linked_item = delivery_items_map.get(stop_address)
                    
                    if linked_item:
                        stop['client_name'] = linked_item.get('client_name', 'No encontrado')
                        stop['product_items'] = linked_item.get('product_items', [])
                    else:
                        stop['client_name'] = 'Datos de factura no vinculados'
                        stop['product_items'] = []
            
            parsed_data['optimized_loading_list'] = optimized_loading_list
            # --- FIN de la Lógica Refactorizada ---

        else:
            parsed_data['street_level_polyline'] = []
            parsed_data['optimized_loading_list'] = []
    else:
        logger.warning("No hay paradas con coordenadas suficientes para optimizar la ruta.")
        parsed_data['optimized_route'] = []
        parsed_data['street_level_polyline'] = []
        parsed_data['optimized_loading_list'] = []

    return parsed_data

