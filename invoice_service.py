import os
import re
from datetime import datetime
from uuid import uuid4
import logging
from customer_service import CustomerService
from shared_utils import extract_text_from_image, upload_image_to_cloudinary, save_invoice_data

# Configurar logger para invoice_service.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def _process_invoice_image_data(image_path: str) -> dict:
    """
    Procesa una imagen de factura: OCR, parseo, subida a Cloudinary, geocodificación y guardado en Firestore.
    """
    raw_ocr_text = extract_text_from_image(image_path)
    parsed_data = parse_invoice_text(raw_ocr_text)
    
    client_name = parsed_data.get("client_name", "Cliente no encontrado")
    total_amount = parsed_data.get("total_amount")
    product_items = parsed_data.get("product_items", [])

    cloudinary_url = upload_image_to_cloudinary(image_path)
    
    # --- Integración con CustomerService ---
    customer_service = CustomerService()
    customer_data = customer_service.upsert_customer(parsed_data, 'invoice')
    
    coordinates = {"latitude": None, "longitude": None}
    if customer_data and customer_data.get('coordinates'):
        coordinates = customer_data['coordinates']

    invoice_id = uuid4().hex
    firestore_data = {
        "cloudinaryImageUrl": cloudinary_url,
        "uploadedAt": datetime.now(),
        "rawOcrText": raw_ocr_text,
        "parsedData": parsed_data,
        "location": {
            "address": parsed_data.get("address", "No encontrado"),
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"]
        },
        "status": "processed",
        "processedAt": datetime.now(),
        "invoiceNumber": parsed_data.get("invoice_number", "No encontrado")
    }
    save_invoice_data(invoice_id, firestore_data)
    logger.info(f"[Invoice:{invoice_id}] Procesamiento completo para la factura.")
    
    formatted_total_amount = f'$ {total_amount:,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".") if total_amount is not None else None
    
    return {
        "invoice_id": invoice_id,
        "url": cloudinary_url,
        "raw_ocr_text": raw_ocr_text,
        "product_items": product_items,
        "total_amount": formatted_total_amount,
        "client_name": client_name,
        "parsed_data": parsed_data,
        "coordinates": coordinates,
        "status": "processed"
    }

def parse_invoice_text(raw_ocr_text: str) -> dict:
    """
    Extrae datos estructurados del texto OCR de una factura de forma robusta.

    :param raw_ocr_text: Texto crudo del OCR
    :return: Diccionario con datos estructurados
    """
    client_name = "Cliente no encontrado"
    address = "Dirección no encontrada"
    total_amount = None
    product_items = []
    invoice_number = "No encontrado" # New field

    # --- EXTRACCIÓN DE NÚMERO DE FACTURA ---
    invoice_number_pattern = r'(?:Factura|FACTURA)\s*N[°.]?\s*(\d{4}-\d{8})'
    match_invoice_number = re.search(invoice_number_pattern, raw_ocr_text)
    if match_invoice_number:
        invoice_number = match_invoice_number.group(1)

    # --- EXTRACCIÓN DE NOMBRE DE CLIENTE Y DIRECCIÓN ---
    # Patrón para capturar el nombre del cliente y la dirección por separado
    client_address_pattern = r'Sr/Sres\.\s*Cliente[^\n]+\n(.*?)\s*Ven\.:[^\n]*\n(.*?)\s*Transp\.:'
    match_client_address = re.search(client_address_pattern, raw_ocr_text, re.DOTALL)

    if match_client_address:
        try:
            client_name = match_client_address.group(1).strip()
            address = match_client_address.group(2).strip().replace('\n', ' ')
            # Limpieza adicional de la dirección
            address = re.sub(r'(?<![a-zA-Z])N[\u00b0*\s]+\s*', ' ', address, flags=re.IGNORECASE).strip()
            address = address.replace('?', '').strip()
            address = re.sub(r'\s{2,}', ' ', address).strip()
            address = address.title()
        except IndexError:
            pass

    # --- EXTRACCIÓN DE MONTO TOTAL ---
    total_amount_pattern = r'IMPORTE TOTAL\s+\$[\s]*([\d.,]+)'
    match_total = re.search(total_amount_pattern, raw_ocr_text)
    if match_total:
        try:
            total_amount = float(match_total.group(1).replace('.', '').replace(',', '.'))
        except (ValueError, IndexError):
            pass

    # --- EXTRACCIÓN DE ÍTEMS DE PRODUCTO ---
    # 1. Aislar el bloque de la tabla de productos
    product_block_pattern = r'Articulo\s+Cantidad\s+Descripci.n[\s\S]+?(?=Subtotal|IMPORTE TOTAL)'
    product_block_match = re.search(product_block_pattern, raw_ocr_text, re.DOTALL)
    
    product_table_text = ""
    if product_block_match:
        product_table_text = product_block_match.group(0)

    # 2. Usar un regex más estricto para las líneas de producto dentro del bloque
    product_line_pattern = r'^(\d{4,5})\s+(\d+)\s+(.+?)\s+([\d.,]+(?:,\d{2})?)\s+([\d.,]+(?:,\d{2})?)$'

    for line in product_table_text.split('\n'):
        line_match = re.match(product_line_pattern, line.strip())
        if line_match:
            try:
                product_code = line_match.group(1)
                quantity = int(line_match.group(2))
                description = line_match.group(3).strip()
                item_total = float(line_match.group(5).replace('.', '').replace(',', '.'))

                product_items.append({
                    "product_code": product_code,
                    "quantity": quantity,
                    "description": description,
                    "item_total": item_total,
                })
            except (ValueError, IndexError):
                pass

    return {
        "client_name": client_name,
        "address": address,
        "total_amount": total_amount,
        "product_items": product_items,
        "invoice_number": invoice_number,
    }

def process_invoices(image_paths: list) -> list:
    """
    Procesa una lista de rutas de imágenes de facturas.
    """
    processed_invoices = []
    for image_path in image_paths:
        try:
            result = _process_invoice_image_data(image_path)
            processed_invoices.append(result)
        except Exception as e:
            logger.error(f"Error procesando la factura {image_path}: {e}")
            processed_invoices.append({
                "invoice_id": None,
                "url": None,
                "raw_ocr_text": "",
                "product_items": [],
                "total_amount": None,
                "client_name": "Error en procesamiento",
                "parsed_data": {},
                "coordinates": {"latitude": None, "longitude": None},
                "status": "error"
            })
    return processed_invoices
