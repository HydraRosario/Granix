import os
import tempfile
from flask import Flask, jsonify, request
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
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from geopy.geocoders import Nominatim
from flask_cors import CORS # Importa CORS
from pdf2image import convert_from_path

# Dirección de respaldo para geocodificación fallida
DEFAULT_START_ADDRESS = "Mendoza y Wilde, Rosario, Santa Fe, Argentina"

# Carga variables de entorno desde .env si existe
load_dotenv()

@dataclass
class Location:
    """Modelo de datos para ubicaciones"""
    name: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class OrderItem:
    """Modelo de datos para items de pedido"""
    product_code: str
    description: str
    quantity: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None


@dataclass
class Order:
    """Modelo de datos para pedidos"""
    order_id: str
    items: List[OrderItem]
    total_amount: float
    order_date: Optional[datetime] = None


@dataclass
class Delivery:
    """Modelo de datos para entregas"""
    delivery_id: str
    order: Order
    location: Location
    status: str
    cloudinary_image_url: str
    raw_ocr_text: str
    uploaded_at: datetime
    processed_at: Optional[datetime] = None


def create_app() -> Flask:
    """
    Crea e inicializa la aplicación Flask y, si es posible, inicializa Firebase Admin SDK
    usando la ruta del archivo de credenciales indicada en la variable de entorno
    GOOGLE_APPLICATION_CREDENTIALS.
    """
    app = Flask(__name__)
    CORS(app) # Inicializa CORS en la aplicación

    # Configurar Cloudinary
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    )
    app.logger.info("Cloudinary configurado.")

    # Inicializar Firebase Admin SDK si aún no está inicializado
    try:
        if not firebase_admin._apps:
            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            if cred_path:
                cred_path = cred_path.strip().strip('\'').strip("'")

            if cred_path and os.path.isfile(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                app.logger.info("Firebase Admin inicializado correctamente.")
            else:
                app.logger.warning(
                    "FIREBASE_CREDENTIALS_PATH no está definida o el archivo no existe. "
                    "Se omite la inicialización de Firebase por ahora."
                )
    except Exception as e:
        app.logger.error(f"Error al inicializar Firebase Admin: {e}")

    @app.get("/")
    def root():
        return "¡Backend Granix Funcionando!", 200

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok"), 200

    @app.get("/geocode")
    def geocode_endpoint():
        address = request.args.get("address")
        if not address:
            return jsonify(error="Parámetro 'address' es requerido."), 400
        
        coordinates = geocode_address(address)
        return jsonify(coordinates), 200

    def cleanup_temp_file(file_path: str) -> None:
        """
        Elimina un archivo temporal de forma segura.
        
        :param file_path: Ruta del archivo a eliminar
        """
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                app.logger.info(f"Archivo temporal eliminado: {file_path}")
        except Exception as e:
            app.logger.warning(f"Error eliminando archivo temporal {file_path}: {e}")

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
            app.logger.error(f"Error al subir a Cloudinary: {e}")
            raise

    def save_invoice_data(invoice_id: str, data: Dict[str, Any]) -> None:
        """
        Guarda datos de factura en Firestore.
        
        :param invoice_id: ID del documento
        :param data: Datos a guardar
        :raises: ValueError si Firestore no está configurado
        """
        if not firebase_admin._apps:
            raise ValueError("Firebase Admin no está inicializado.")
        
        db = firestore.client()
        doc_ref = db.collection('invoices').document(invoice_id)
        doc_ref.set(data)
        app.logger.info(f"Datos guardados en Firestore para invoice_id: {invoice_id}")

    def geocode_address(address_string: str) -> Dict[str, Optional[float]]:
        """
        Geocodifica una dirección usando Nominatim con un enfoque robusto.

        :param address_string: Dirección a geocodificar
        :return: Diccionario con latitude y longitude
        """
        geolocator = Nominatim(user_agent="granix-backend/1.0")
        
        # Usar la dirección por defecto si la dirección proporcionada es None o vacía
        if not address_string:
            app.logger.warning("Dirección vacía proporcionada para geocodificación. Usando dirección por defecto.")
            address_string = DEFAULT_START_ADDRESS

        try:
            # Construir una única cadena de consulta
            full_query = f"{address_string}, Rosario, Santa Fe, Argentina"
            location = geolocator.geocode(full_query, country_codes='ar', timeout=10)
            
            if location:
                return {
                    "latitude": location.latitude,
                    "longitude": location.longitude
                }
            else:
                app.logger.warning(f"Nominatim no pudo geocodificar la dirección: {full_query}. Usando dirección por defecto.")
                # Si Nominatim no encuentra la dirección, usar la dirección por defecto
                default_query = f"{DEFAULT_START_ADDRESS}, Rosario, Santa Fe, Argentina"
                location = geolocator.geocode(default_query, country_codes='ar', timeout=10)
                if location:
                    return {
                        "latitude": location.latitude,
                        "longitude": location.longitude
                    }
                else:
                    app.logger.error(f"Fallo la geocodificación de la dirección por defecto: {DEFAULT_START_ADDRESS}")
                    return {"latitude": None, "longitude": None} # Fallback final
        except Exception as e:
            app.logger.error(f"Error en geocodificación con Nominatim para '{address_string}': {e}. Usando dirección por defecto.")
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
                    app.logger.error(f"Fallo la geocodificación de la dirección por defecto: {DEFAULT_START_ADDRESS}")
                    return {"latitude": None, "longitude": None} # Fallback final
            except Exception as e_default:
                app.logger.error(f"Error catastrófico al geocodificar la dirección por defecto: {e_default}")
                return {"latitude": None, "longitude": None} # Fallback final

    def parse_invoice_text(raw_ocr_text: str) -> Dict[str, Any]:
        """
        Extrae datos estructurados del texto OCR de una factura de forma robusta.

        :param raw_ocr_text: Texto crudo del OCR
        :return: Diccionario con datos estructurados
        """
        address = None
        total_amount = None

        # --- EXTRACCIÓN DE DIRECCIÓN ---
        # Intento 1: Buscar "Dirección:" (ignorando mayúsculas/minúsculas y acentos)
        address_pattern1 = re.search(r'Direcci[oó]n:\s*(.+)', raw_ocr_text, re.IGNORECASE)
        if address_pattern1:
            address = address_pattern1.group(1).strip()
        else:
            # Intento 2: Buscar patrones de calle más generales (ej. "Calle XXXXX")
            address_pattern2 = re.search(r'(?:Calle|Av\.|Avenida)\s+([^,\n]+)', raw_ocr_text, re.IGNORECASE)
            if address_pattern2:
                address = address_pattern2.group(1).strip()

        # --- EXTRACCIÓN DE MONTO TOTAL ---
        # Buscar "Total:", "Total a pagar:", "$" seguido de un número
        total_pattern = re.search(r'(?:Total|Total a pagar):?\s*\$?\s*([\d\.,]+)', raw_ocr_text, re.IGNORECASE)
        if total_pattern:
            # Reemplazar comas por puntos para una conversión a float consistente
            try:
                total_amount = float(total_pattern.group(1).replace(',', '.'))
            except (ValueError, IndexError):
                total_amount = None # En caso de que la conversión a float falle

        # --- EXTRACCIÓN DE ÍTEMS (MOCKUP/EJEMPLO) ---
        items = [
            {"product_code": "MOCK_PROD_1", "description": "Producto de Prueba Uno", "quantity": 10},
            {"product_code": "MOCK_PROD_2", "description": "Producto de Prueba Dos", "quantity": 5}
        ]

        return {
            "address": address,
            "total_amount": total_amount,
            "items": items,
            "extraction_confidence": "low" if not address and not total_amount else "medium"
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
        except Exception:
            pass

        text = pytesseract.image_to_string(img, lang=lang)
        return text

    @app.post("/process_invoice")
    def process_invoice():
        """
        Endpoint para subir y procesar una imagen de factura.
        """
        if "file" not in request.files:
            return jsonify(error="No se encontró el archivo en 'file'"), 400

        file_obj = request.files["file"]
        if not file_obj or file_obj.filename == "":
            return jsonify(error="Archivo inválido o nombre vacío"), 400

        filename = secure_filename(file_obj.filename)
        temp_path = None
        results = []

        try:
            # Guardar temporalmente
            with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as temp_file:
                file_obj.save(temp_file.name)
                temp_path = temp_file.name

            if file_obj.mimetype == 'application/pdf':
                images = convert_from_path(temp_path, poppler_path=r"C:\Users\HHHES\Documents\poppler\poppler-25.07.0\Library\bin")
                for i, image in enumerate(images):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_page_{i+1}.png") as img_temp_file:
                        image.save(img_temp_file.name, 'PNG')
                        img_temp_path = img_temp_file.name
                    
                    # Procesar cada imagen
                    raw_ocr_text = extract_text_from_image(img_temp_path)

                    # --- EXTRACCIÓN DE ÍTEMS DE PRODUCTO ---
                    product_items = []
                    product_pattern = r'(\d+)\s+(\d+)\s+(.+?)\s+([\d.]+)\s+([\d,.]+)'
                    
                    header_match = re.search(r'Artículo\s+Cantidad\s+Descripción\s+Precio\s+Importe', raw_ocr_text, re.IGNORECASE)
                    text_to_search_items = raw_ocr_text
                    if header_match:
                        text_to_search_items = raw_ocr_text[header_match.end():]

                    match_item = re.search(product_pattern, text_to_search_items)
                    
                    if match_item:
                        try:
                            product_code = match_item.group(1)
                            quantity = int(match_item.group(2))
                            description = match_item.group(3).strip()
                            unit_price = float(match_item.group(4).replace(',', '.'))
                            total_price = float(match_item.group(5).replace(',', '.'))

                            product_items.append({
                                "product_code": product_code,
                                "quantity": quantity,
                                "description": description,
                                "unit_price": unit_price,
                                "total_price": total_price,
                            })
                        except (ValueError, IndexError):
                            pass # Ignorar si el parseo falla

                    # --- EXTRACCIÓN DE MONTO TOTAL ---
                    total_amount = None
                    total_amount_pattern = r'IMPORTE TOTAL\s+\$[\s]*([\d.,]+)'
                    match_total = re.search(total_amount_pattern, raw_ocr_text)
                    if match_total:
                        try:
                            total_amount = float(match_total.group(1).replace('.', '').replace(',', '.'))
                        except (ValueError, IndexError):
                            pass

                    # --- EXTRACCIÓN DE DIRECCIÓN DEL CLIENTE ---
                    client_street_address = "Dirección no encontrada"
                    address_pattern = r'SPORTELLI GUSTAVO\.\s*(.*?)\s*Transp\.:\s*(.*?)\s*\((\d+)\)\s*ROSARIO'
                    match_address = re.search(address_pattern, raw_ocr_text, re.DOTALL)
                    if match_address:
                        try:
                            street_and_number = match_address.group(1).strip().replace('\n', ' ')
                            client_street_address = street_and_number
                        except IndexError:
                            pass

                    cloudinary_url = upload_image_to_cloudinary(img_temp_path)
                    parsed_data = parse_invoice_text(raw_ocr_text)
                    if product_items:
                        parsed_data['items'] = product_items
                    if total_amount is not None:
                        parsed_data['total_amount'] = total_amount
                    if client_street_address != "Dirección no encontrada":
                        parsed_data['address'] = client_street_address
                    
                    # --- GEOCODIFICACIÓN ---
                    full_address = f'{client_street_address}, Rosario, Santa Fe, Argentina'
                    geolocator = Nominatim(user_agent="granix-backend/1.0")
                    location = geolocator.geocode(full_address, country_codes='ar', timeout=10)
                    coordinates = {"latitude": None, "longitude": None}
                    if location:
                        coordinates["latitude"] = location.latitude
                        coordinates["longitude"] = location.longitude
                    
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
                        "processedAt": datetime.now()
                    }
                    save_invoice_data(invoice_id, firestore_data)
                    
                    formatted_total_amount = f'$ {total_amount:,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".") if total_amount is not None else None
                    
                    results.append({
                        "invoice_id": invoice_id,
                        "url": cloudinary_url,
                        "raw_ocr_text": raw_ocr_text,
                        "product_items": product_items,
                        "total_amount": formatted_total_amount,
                        "parsed_data": parsed_data,
                        "coordinates": coordinates,
                        "status": "processed"
                    })
                    cleanup_temp_file(img_temp_path)
            else:
                # Procesar como imagen única
                raw_ocr_text = extract_text_from_image(temp_path)

                # --- EXTRACCIÓN DE ÍTEMS DE PRODUCTO ---
                product_items = []
                product_pattern = r'(\d+)\s+(\d+)\s+(.+?)\s+([\d.]+)\s+([\d,.]+)'
                
                header_match = re.search(r'Artículo\s+Cantidad\s+Descripción\s+Precio\s+Importe', raw_ocr_text, re.IGNORECASE)
                text_to_search_items = raw_ocr_text
                if header_match:
                    text_to_search_items = raw_ocr_text[header_match.end():]

                match_item = re.search(product_pattern, text_to_search_items)
                
                if match_item:
                    try:
                        product_code = match_item.group(1)
                        quantity = int(match_item.group(2))
                        description = match_item.group(3).strip()
                        unit_price = float(match_item.group(4).replace(',', '.'))
                        total_price = float(match_item.group(5).replace(',', '.'))

                        product_items.append({
                            "product_code": product_code,
                            "quantity": quantity,
                            "description": description,
                            "unit_price": unit_price,
                            "total_price": total_price,
                        })
                    except (ValueError, IndexError):
                        pass # Ignorar si el parseo falla

                # --- EXTRACCIÓN DE MONTO TOTAL ---
                total_amount = None
                total_amount_pattern = r'IMPORTE TOTAL\s+\$[\s]*([\d.,]+)'
                match_total = re.search(total_amount_pattern, raw_ocr_text)
                if match_total:
                    try:
                        total_amount = float(match_total.group(1).replace('.', '').replace(',', '.'))
                    except (ValueError, IndexError):
                        pass

                # --- EXTRACCIÓN DE DIRECCIÓN DEL CLIENTE ---
                client_street_address = "Dirección no encontrada"
                address_pattern = r'SPORTELLI GUSTAVO\.\s*(.*?)\s*Transp\.:\s*(.*?)\s*\((\d+)\)\s*ROSARIO'
                match_address = re.search(address_pattern, raw_ocr_text, re.DOTALL)
                if match_address:
                    try:
                        street_and_number = match_address.group(1).strip().replace('\n', ' ')
                        client_street_address = street_and_number
                    except IndexError:
                        pass

                cloudinary_url = upload_image_to_cloudinary(temp_path)
                parsed_data = parse_invoice_text(raw_ocr_text)
                if product_items:
                    parsed_data['items'] = product_items
                if total_amount is not None:
                    parsed_data['total_amount'] = total_amount
                if client_street_address != "Dirección no encontrada":
                    parsed_data['address'] = client_street_address

                # --- GEOCODIFICACIÓN ---
                full_address = f'{client_street_address}, Rosario, Santa Fe, Argentina'
                geolocator = Nominatim(user_agent="granix-backend/1.0")
                location = geolocator.geocode(full_address, country_codes='ar', timeout=10)
                coordinates = {"latitude": None, "longitude": None}
                if location:
                    coordinates["latitude"] = location.latitude
                    coordinates["longitude"] = location.longitude

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
                    "processedAt": datetime.now()
                }
                save_invoice_data(invoice_id, firestore_data)

                formatted_total_amount = f'$ {total_amount:,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".") if total_amount is not None else None

                results.append({
                    "invoice_id": invoice_id,
                    "url": cloudinary_url,
                    "raw_ocr_text": raw_ocr_text,
                    "product_items": product_items,
                    "total_amount": formatted_total_amount,
                    "parsed_data": parsed_data,
                    "coordinates": coordinates,
                    "status": "processed"
                })

            return jsonify(results), 200

        except ValueError as ve:
            return jsonify(error=str(ve)), 500
        except Exception as e:
            app.logger.exception("Error procesando factura")
            return jsonify(error="Error al procesar la factura"), 500
        finally:
            if temp_path:
                cleanup_temp_file(temp_path)

    return app


# Instancia global de la app para correr con `python app.py`
app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") in ("1", "true", "True")
    app.run(host="0.0.0.0", port=port, debug=debug)