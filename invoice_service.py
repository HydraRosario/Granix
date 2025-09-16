import os
import re
from datetime import datetime
from uuid import uuid4
from geopy.geocoders import Nominatim
import logging

from shared_utils import extract_text_from_image, upload_image_to_cloudinary, save_invoice_data

# Configurar logger para invoice_service.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Dirección de respaldo para geocodificación fallida
DEFAULT_START_ADDRESS = "Mendoza y Wilde, Rosario, Santa Fe, Argentina"

def geocode_address(address_string: str) -> dict:
    """
    Geocodifica una dirección usando Nominatim con un enfoque robusto.

    :param address_string: Dirección a geocodificar
    :return: Diccionario con latitude y longitude
    """
    geolocator = Nominatim(user_agent="granix-backend/1.0")
    
    # Usar la dirección por defecto si la dirección proporcionada es None o vacía
    if not address_string:
        logger.warning("Dirección vacía proporcionada para geocodificación. Usando dirección por defecto.")
        address_string = DEFAULT_START_ADDRESS

    city = "Rosario"
    if "25 De Mayo" in address_string:
        city = "Ibarlucea"

    try:
        # Construir una única cadena de consulta
        full_query = f"{address_string}, {city}, Santa Fe, Argentina"
        location = geolocator.geocode(full_query, country_codes='ar', timeout=10)
        
        if location:
            return {
                "latitude": location.latitude,
                "longitude": location.longitude
            }
        else:
            logger.warning(f"Nominatim no pudo geocodificar la dirección: {full_query}. Usando dirección por defecto.")
            # Si Nominatim no encuentra la dirección, usar la dirección por defecto
            default_query = f"{DEFAULT_START_ADDRESS}, Rosario, Santa Fe, Argentina"
            location = geolocator.geocode(default_query, country_codes='ar', timeout=10)
            if location:
                return {
                    "latitude": location.latitude,
                    "longitude": location.longitude
                }
            else:
                logger.error(f"Fallo la geocodificación de la dirección por defecto: {DEFAULT_START_ADDRESS}")
                return {"latitude": None, "longitude": None} # Fallback final
    except Exception as e:
        logger.error(f"Error en geocodificación con Nominatim para '{address_string}': {e}. Usando dirección por defecto.")
        # En caso de error, intentar geocodificar la dirección por defecto
        try:
            default_query = f"{DEFAULT_START_ADDRESS}, Rosario, Santa Fe, Argentina"
            location = geolocator.geocode(default_query, country_codes='ar', timeout=10)
            if location:
                return {
                    "latitude": location.latitude,
                    "longitude": location.longitude
                }
            else:
                logger.error(f"Fallo la geocodificación de la dirección por defecto: {DEFAULT_START_ADDRESS}")
                return {"latitude": None, "longitude": None} # Fallback final
        except Exception as e_default:
            logger.error(f"Error catastrófico al geocodificar la dirección por defecto: {e_default}")
            return {"latitude": None, "longitude": None} # Fallback final

def _process_invoice_image_data(image_path: str) -> dict:
    """
    Procesa una imagen de factura: OCR, parseo, subida a Cloudinary, geocodificación y guardado en Firestore.
    """
    raw_ocr_text = extract_text_from_image(image_path)
    parsed_data = parse_invoice_text(raw_ocr_text)
    
    client_street_address = parsed_data.get("address", "Dirección no encontrada")
    client_name = parsed_data.get("client_name", "Cliente no encontrado")
    total_amount = parsed_data.get("total_amount")
    product_items = parsed_data.get("product_items", [])

    cloudinary_url = upload_image_to_cloudinary(image_path)
    
    coordinates = geocode_address(client_street_address)

    invoice_id = uuid4().hex
    firestore_data = {
        "cloudinaryImageUrl": cloudinary_url,
        "uploadedAt": datetime.now(),
        "rawOcrText": raw_ocr_text,
        "parsedData": parsed_data,
        "location": {
            "address": parsed_data["address"],
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"]
        },
        "status": "processed",
        "processedAt": datetime.now(),
        "invoiceNumber": parsed_data.get("invoice_number", "No encontrado") # New field
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