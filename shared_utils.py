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
from pdf2image import convert_from_path
from contextlib import contextmanager
import io
import logging
from geopy.geocoders import Nominatim

# Configurar logger para shared_utils.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Carga variables de entorno desde .env si existe
load_dotenv()

# Dirección de respaldo para geocodificación fallida
DEFAULT_START_ADDRESS = "Mendoza y Wilde, Rosario, Santa Fe, Argentina"

# Configurar Cloudinary (se asume que las variables de entorno ya están cargadas)
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)
logger.info("Cloudinary configurado en shared_utils.py.")

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
        logger.info("Firebase Admin inicializado correctamente en shared_utils.py.")
    else:
        logger.warning(
            "FIREBASE_CREDENTIALS_PATH no está definida o el archivo no existe. "
            "Se omite la inicialización de Firebase por ahora en shared_utils.py."
        )
except Exception as e:
    logger.error(f"Error al inicializar Firebase Admin en shared_utils.py: {e}")

def geocode_address(address_string: str) -> dict:
    """
    Geocodifica una dirección usando Nominatim con un enfoque robusto.
    Se utiliza un viewbox para Rosario para mejorar la precisión.

    :param address_string: Dirección a geocodificar
    :return: Diccionario con latitude y longitude
    """
    geolocator = Nominatim(user_agent="granix-backend/1.0")
    
    # Coordenadas del viewbox para Rosario, Argentina: [(sur, oeste), (norte, este)]
    # Esto ayuda a Nominatim a priorizar resultados dentro de esta área.
    ROSARIO_VIEWBOX = [(-33.016, -60.75), (-32.85, -60.6)]

    # Usar la dirección por defecto si la dirección proporcionada es None o vacía
    if not address_string:
        logger.warning("Dirección vacía proporcionada para geocodificación. Usando dirección por defecto.")
        address_string = DEFAULT_START_ADDRESS

    # --- Normalización de Direcciones ---
    # Reemplaza nombres de calles comunes o ambiguos por su versión completa para mejorar la precisión.
    normalized_address = address_string
    if re.search(r'^\s*Andrade\b', address_string, re.IGNORECASE):
        normalized_address = re.sub(r'Andrade', 'Olegario Victor Andrade', address_string, count=1, flags=re.IGNORECASE)
        logger.info(f"Dirección normalizada: '{address_string}' -> '{normalized_address}'")

    city = "Rosario"
    if "25 De Mayo" in normalized_address:
        city = "Ibarlucea"

    try:
        full_query = f"{normalized_address}, {city}, Santa Fe, Argentina"
        # Geocodificar con viewbox para Rosario y bounded=True para limitar los resultados a esa caja.
        location = geolocator.geocode(
            full_query, 
            country_codes='ar', 
            timeout=10, 
            viewbox=ROSARIO_VIEWBOX, 
            bounded=True
        )
        
        if location:
            return {
                "latitude": location.latitude,
                "longitude": location.longitude
            }
        else:
            logger.warning(f"Nominatim no pudo geocodificar la dirección: {full_query}. Intentando sin viewbox.")
            # Si falla, intentar sin el viewbox como fallback
            location = geolocator.geocode(full_query, country_codes='ar', timeout=10)
            if location:
                return {
                    "latitude": location.latitude,
                    "longitude": location.longitude
                }
            logger.error(f"Fallo total de geocodificación para: {full_query}")
            return {"latitude": None, "longitude": None}

    except Exception as e:
        logger.error(f"Error en geocodificación con Nominatim para '{address_string}': {e}.")
        return {"latitude": None, "longitude": None} # Fallback final

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