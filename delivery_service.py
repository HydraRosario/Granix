import logging
from delivery_parser import DeliveryReportParser
from customer_service import CustomerService
from route_optimizer import optimize_route

# Configurar logger para delivery_service.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def parse_delivery_report_text(raw_ocr_text: str) -> dict:
    """
    Extrae y enriquece los datos de un informe de reparto y optimiza la ruta de entrega.
    """
    # 1. Parsear el texto crudo del OCR
    parser = DeliveryReportParser()
    parsed_data = parser.parse_delivery_report_text(raw_ocr_text)
    delivery_items = parsed_data.get('delivery_items', [])

    if not delivery_items:
        return parsed_data

    # 2. Enriquecer los datos de cada parada con información del cliente y coordenadas
    customer_service = CustomerService()
    for item in delivery_items:
        # La dirección se usa como clave para el cliente
        item['address'] = item.get('delivery_address')
        customer_data = customer_service.upsert_customer(item, 'delivery_report')
        if customer_data and customer_data.get('coordinates'):
            item['coordinates'] = customer_data['coordinates']

    # 3. Optimizar la ruta con las paradas que tienen coordenadas válidas
    # El optimizador necesita una lista de diccionarios con claves 'address' y 'coordinates'
    valid_stops_for_optimization = [item for item in delivery_items if 'coordinates' in item and item['coordinates'].get('latitude') is not None]
    
    if valid_stops_for_optimization:
        logger.info(f"Iniciando optimización de ruta para {len(valid_stops_for_optimization)} paradas.")
        optimized_route = optimize_route(valid_stops_for_optimization)
        parsed_data['optimized_route'] = optimized_route
    else:
        logger.warning("No hay paradas con coordenadas suficientes para optimizar la ruta.")
        parsed_data['optimized_route'] = []

    # 4. Devolver todos los datos procesados
    return parsed_data
