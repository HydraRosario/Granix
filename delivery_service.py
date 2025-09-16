import logging
from delivery_parser import DeliveryReportParser

# Configurar logger para delivery_service.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def parse_delivery_report_text(raw_ocr_text: str) -> dict:
    """
    Extrae datos estructurados del texto OCR de un informe de reparto.
    """
    parser = DeliveryReportParser()
    return parser.parse_delivery_report_text(raw_ocr_text)
