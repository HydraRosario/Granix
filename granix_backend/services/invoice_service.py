import re
from datetime import datetime, timedelta
from uuid import uuid4
import logging
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter, And
from granix_backend.services.customer_service import CustomerService
from granix_backend.utils.shared_utils import extract_text_from_image, upload_image_to_cloudinary, save_invoice_data

# Configurar logger para invoice_service.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def _link_to_delivery_by_address(invoice_id: str, address: str, client_name: str, product_items: list, invoice_date: datetime):
    """
    Busca un delivery_item por dirección dentro de una ventana de tiempo y lo actualiza.
    Esta función denormaliza los datos para simplificar las consultas de carga.
    """
    if not address or address == "Dirección no encontrada":
        logger.warning(f"Dirección inválida para la factura {invoice_id}. No se puede vincular.")
        return

    db = firestore.client()
    delivery_items_ref = db.collection('delivery_items')

    # Busca el item de delivery más antiguo con estado 'pending_link' para la misma dirección.
    # Esto permite vincular facturas a repartos de días anteriores.
    # NOTA: Esta consulta requiere un índice compuesto en Firestore.
    # Firestore proporcionará un enlace para crearlo en el mensaje de error si es necesario.
    query = (
        delivery_items_ref.where(filter=And([
            FieldFilter("delivery_address", "==", address),
            FieldFilter("status", "==", "pending_link")
        ]))
        .order_by("createdAt")
        .limit(1)
    )
    
    docs = query.stream()
    
    try:
        doc = next(docs)
        logger.info(f"Vinculando factura {invoice_id} con delivery_item {doc.id} por dirección y tiempo.")
        
        doc.reference.update({
            'invoice_id': invoice_id,
            'client_name': client_name,
            'product_items': product_items,
            'status': 'linked',
            'linkedAt': firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Vinculación por dirección y tiempo exitosa: {doc.id} -> {invoice_id}")

    except StopIteration:
        logger.warning(f"No se encontró un delivery_item pendiente para la dirección '{address}' en la ventana de tiempo. Se omite la vinculación.")
    except Exception as e:
        logger.error(f"Error al vincular por dirección y tiempo para '{address}': {e}")

def _process_invoice_image_data(image_path: str) -> dict:
    """
    Procesa una imagen de factura: OCR, parseo, subida a Cloudinary, guardado y vinculación.
    """
    processing_time = datetime.now()
    raw_ocr_text = extract_text_from_image(image_path)
    parsed_data = parse_invoice_text(raw_ocr_text)
    
    client_name = parsed_data.get("client_name", "Cliente no encontrado")
    address = parsed_data.get("address", "Dirección no encontrada")
    total_amount = parsed_data.get("total_amount")
    product_items = parsed_data.get("product_items", [])

    cloudinary_url = upload_image_to_cloudinary(image_path)
    
    customer_service = CustomerService()
    customer_data = customer_service.upsert_customer(parsed_data, 'invoice')
    
    coordinates = {"latitude": None, "longitude": None}
    if customer_data and customer_data.get('coordinates'):
        coordinates = customer_data['coordinates']

    invoice_id = uuid4().hex
    firestore_data = {
        "cloudinaryImageUrl":cloudinary_url,
        "uploadedAt": processing_time,
        "rawOcrText": raw_ocr_text,
        "parsedData": parsed_data,
        "location": {
            "address": address,
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"]
        },
        "status": "processed",
        "processedAt": processing_time
    }
    save_invoice_data(invoice_id, firestore_data)
    logger.info(f"[Invoice:{invoice_id}] Procesamiento completo para la factura.")

    # --- Lógica de Vinculación por Dirección y Tiempo ---
    _link_to_delivery_by_address(
        invoice_id=invoice_id,
        address=address,
        client_name=client_name,
        product_items=product_items,
        invoice_date=processing_time
    )
    
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
    Extrae datos estructurados del texto OCR de una factura.
    """
    client_name = "Cliente no encontrado"
    address = "Dirección no encontrada"
    total_amount = None
    product_items = []

    client_address_pattern = r'Sr/Sres\.\s*Cliente[^\n]+\n(.*?)\s*Ven\.:[^\n]*\n(.*?)\s*Transp\.:'
    match_client_address = re.search(client_address_pattern, raw_ocr_text, re.DOTALL)

    if match_client_address:
        try:
            client_name = match_client_address.group(1).strip()
            address = match_client_address.group(2).strip().replace('\n', ' ')
            address = re.sub(r'(?<![a-zA-Z])N[\u00b0*\s]+\s*', ' ', address, flags=re.IGNORECASE).strip()
            address = address.replace('?', '').strip()
            address = re.sub(r'\s{2,}', ' ', address).strip()
            address = address.title()
        except IndexError:
            pass

    total_amount_pattern = r'IMPORTE TOTAL\s+\$[\s]*([\d.,]+)'
    match_total = re.search(total_amount_pattern, raw_ocr_text)
    if match_total:
        try:
            total_amount = float(match_total.group(1).replace('.', '').replace(',', '.'))
        except (ValueError, IndexError):
            pass

    product_block_pattern = r'Articulo\s+Cantidad\s+Descripci.n[\s\S]+?(?=Subtotal|IMPORTE TOTAL)'
    product_block_match = re.search(product_block_pattern, raw_ocr_text, re.DOTALL)
    
    product_table_text = ""
    if product_block_match:
        product_table_text = product_block_match.group(0)

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
