import os
import tempfile
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
import cloudinary
import cloudinary.uploader
from werkzeug.utils import secure_filename
from uuid import uuid4
from PIL import Image
import pytesseract
from datetime import datetime
import re
from geopy.geocoders import Nominatim
from pdf2image import convert_from_path
from contextlib import contextmanager
import io
import logging

# Configurar logger para services.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Dirección de respaldo para geocodificación fallida
DEFAULT_START_ADDRESS = "Mendoza y Wilde, Rosario, Santa Fe, Argentina"

# Carga variables de entorno desde .env si existe
load_dotenv()

# Configurar Cloudinary (se asume que las variables de entorno ya están cargadas)
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)
logger.info("Cloudinary configurado en services.py.")

# Inicializar Firebase Admin SDK si aún no está inicializado
try:
    firebase_admin.get_app() # Check if app is already initialized
except ValueError:
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if cred_path:
        cred_path = cred_path.strip().strip('\'').strip('"')

    if cred_path and os.path.isfile(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin inicializado correctamente en services.py.")
    else:
        logger.warning(
            "FIREBASE_CREDENTIALS_PATH no está definida o el archivo no existe. "
            "Se omite la inicialización de Firebase por ahora en services.py."
        )
except Exception as e:
    logger.error(f"Error al inicializar Firebase Admin en services.py: {e}")


@contextmanager
def temp_file_path(suffix=""):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd) # Close the file descriptor immediately
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)

def cleanup_temp_file(file_path: str) -> None:
    """
    Elimina un archivo temporal de forma segura.
    
    :param file_path: Ruta del archivo a eliminar
    """
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"Archivo temporal eliminado: {file_path}")
    except Exception as e:
        logger.warning(f"Error eliminando archivo temporal {file_path}: {e}")

def _extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extrae texto de un PDF convirtiendo cada página a imagen y aplicando OCR.
    """
    poppler_path = os.getenv("POPPLER_PATH")
    if not poppler_path:
        logger.error("POPPLER_PATH no está configurado en las variables de entorno.")
        raise ValueError("La ruta a Poppler no está configurada.")

    images = convert_from_path(pdf_path, poppler_path=poppler_path)
    full_text = []
    for i, image in enumerate(images):
        # Save image to a BytesIO object instead of a temporary file
        with io.BytesIO() as image_bytes_io:
            image.save(image_bytes_io, format='PNG')
            image_bytes_io.seek(0) # Rewind to the beginning of the stream
            full_text.append(extract_text_from_image(image_bytes_io))
    return "\n".join(full_text)

def upload_image_to_cloudinary(file_obj) -> str:
    """
    Sube un archivo de imagen a Cloudinary y retorna la URL segura.

    :param file_obj: objeto FileStorage o ruta a un archivo
    :return: URL segura del archivo subido
    :raises: Exception en caso de error de subida
    """
    try:
        upload_result = cloudinary.uploader.upload(
            file_obj,
            folder="granix-invoices"
        )
        return upload_result['secure_url']
    except Exception as e:
        logger.error(f"Error al subir a Cloudinary: {e}")
        raise

def save_invoice_data(invoice_id: str, data: dict) -> None:
    """
    Guarda datos de factura en Firestore.
    
    :param invoice_id: ID del documento
    :param data: Datos a guardar
    :raises: ValueError si Firestore no está configurado
    """
    # Usar get_app() para verificar si Firebase está inicializado
    try:
        firebase_admin.get_app()
    except ValueError:
        raise ValueError("Firebase Admin no está inicializado.")
    
    db = firestore.client()
    doc_ref = db.collection('invoices').document(invoice_id)
    doc_ref.set(data)
    logger.info(f"[Invoice:{invoice_id}] Datos guardados en Firestore para invoice_id: {invoice_id}")

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

def parse_delivery_report_text(raw_ocr_text: str) -> dict:
    """
    Extrae datos estructurados del texto OCR de un informe de reparto.
    """
    delivery_items = []
    total_invoices = 0
    total_remitos = 0
    total_packages_summary = 0

    # Regex to capture Type, InvoiceNumber, and the rest of the line
    item_line_pattern = re.compile(
        r'(Fa|Re)\s+([A-Z0-9-]+)\s+(.*)'
    )

    # Regex to capture summary at the end
    summary_pattern = re.compile(
        r'Cantidad de Facturas:\s*(\d+)\s+Cantidad de Remitos:\s*(\d+)\s+Bultos:\s*(\d+)'
    )

    lines = raw_ocr_text.split('\n')
    for line in lines:
        item_match = item_line_pattern.search(line)
        if item_match:
            item_type = item_match.group(1)
            invoice_number = item_match.group(2)
            rest_of_line = item_match.group(3).strip()

            # Extract packages from the end of rest_of_line
            packages_match = re.search(r'(\d+)$', rest_of_line)
            packages = 0
            if packages_match:
                packages = int(packages_match.group(1))
                rest_of_line_without_packages = rest_of_line[:-len(packages_match.group(0))].strip()
            else:
                rest_of_line_without_packages = rest_of_line

            commercial_entity = "No encontrado"
            delivery_address = "No encontrado"

            # Updated address pattern:
            # - Starts with a capitalized word (street name)
            # - Followed by optional "N°" or "N" (case-insensitive)
            # - Followed by a number
            # - Followed by optional additional address details, including "Rosario"
            # This pattern aims to capture the entire address part.
            address_pattern = re.compile(
                r'([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s]*?\s+(?:N[°.]?\s*\d+|\d+)(?:,\s*[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s]*)*)',
                re.IGNORECASE
            )

            address_match = address_pattern.search(rest_of_line_without_packages)

            if address_match:
                # Extract the potential address part
                potential_address = address_match.group(0).strip()

                # Separate commercial entity and delivery address
                commercial_entity = rest_of_line_without_packages[:address_match.start()].strip()
                delivery_address = potential_address

                # --- Clean and format commercial_entity ---
                commercial_entity = commercial_entity.upper()
                # Remove standalone numbers or line prefixes from commercial_entity
                commercial_entity = re.sub(r'\b\d+\b', '', commercial_entity).strip() # Remove standalone numbers
                commercial_entity = re.sub(r'^\s*\d+\s*', '', commercial_entity).strip() # Remove leading numbers/prefixes

                # --- Clean and format delivery_address ---
                # Remove "N" or "N°" between street and number
                delivery_address = re.sub(r'\s+N[°.]?\s*', ' ', delivery_address, flags=re.IGNORECASE)

                # Format to title case, ensuring "Rosario" remains "Rosario"
                delivery_address_parts = []
                for part in delivery_address.split(','):
                    part = part.strip()
                    if part.lower() == "rosario":
                        delivery_address_parts.append("Rosario")
                    else:
                        delivery_address_parts.append(part.title())
                delivery_address = ", ".join(delivery_address_parts)

            else:
                # Fallback if address pattern not found
                commercial_entity = rest_of_line_without_packages.upper()
                # Apply cleaning for standalone numbers even in fallback
                commercial_entity = re.sub(r'\b\d+\b', '', commercial_entity).strip()
                commercial_entity = re.sub(r'^\s*\d+\s*', '', commercial_entity).strip()

            delivery_items.append({
                "type": item_type,
                "invoice_number": invoice_number,
                "commercial_entity": commercial_entity,
                "delivery_address": delivery_address,
                "packages": packages
            })
        
        summary_match = summary_pattern.search(line)
        if summary_match:
            total_invoices = int(summary_match.group(1))
            total_remitos = int(summary_match.group(2))
            total_packages_summary = int(summary_match.group(3))

    return {
        "delivery_items": delivery_items,
        "total_invoices": total_invoices,
        "total_remitos": total_remitos,
        "total_packages_summary": total_packages_summary
    }

def extract_text_from_image(image_input) -> str:
    """
    Extrae texto usando Tesseract a través de pytesseract.
    """
    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    lang = os.getenv("TESSERACT_LANG", "spa+eng")

    img = None
    if isinstance(image_input, Image.Image):
        img = image_input
    elif isinstance(image_input, (str, os.PathLike)):
        img = Image.open(image_input)
    else:
        try:
            data = image_input.read() if hasattr(image_input, "read") else image_input
            from io import BytesIO
            img = Image.open(BytesIO(data))
        except Exception as e:
            raise ValueError("Entrada de imagen no válida.") from e

    try:
        img = img.convert("L")
        # Add binarization step
        img = img.point(lambda x: 0 if x < 180 else 255, '1')
    except Exception:
        pass

    text = pytesseract.image_to_string(img, lang=lang)
    return text
