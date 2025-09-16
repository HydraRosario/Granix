import logging
from delivery_parser import DeliveryReportParser
from customer_service import CustomerService

# Configurar logger para delivery_service.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def parse_delivery_report_text(raw_ocr_text: str) -> dict:
    """
    Extrae datos estructurados del texto OCR de un informe de reparto,
    y enriquece los datos con información del cliente desde la base de datos de clientes.
    """
    parser = DeliveryReportParser()
    parsed_data = parser.parse_delivery_report_text(raw_ocr_text)

    customer_service = CustomerService()

    for item in parsed_data.get('delivery_items', []):
        customer_data = customer_service.upsert_customer(item, 'delivery_report')
        if customer_data and customer_data.get('coordinates'):
            item['coordinates'] = customer_data['coordinates']

    return parsed_data