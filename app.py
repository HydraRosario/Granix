import os
import tempfile
import requests
from flask import Flask, jsonify, request
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import storage
from firebase_admin import firestore
from werkzeug.utils import secure_filename
from uuid import uuid4
from PIL import Image
import pytesseract
from datetime import datetime
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from geopy.geocoders import Nominatim

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
    original_image_url: str
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

    # Inicializar Firebase Admin SDK si aún no está inicializado
    try:
        if not firebase_admin._apps:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            # Permitir que la ruta esté entrecomillada en .env
            if cred_path:
                cred_path = cred_path.strip().strip('"').strip("'")

            bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET_NAME")
            options = {}
            if bucket_name:
                options["storageBucket"] = bucket_name
            if cred_path and os.path.isfile(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, options or None)
                app.logger.info("Firebase Admin inicializado correctamente.")
            else:
                # Intentar inicializar sin credenciales explícitas (ADC), si hay opciones
                try:
                    firebase_admin.initialize_app(options=options or None)
                    app.logger.warning(
                        "Inicializado Firebase Admin usando credenciales por defecto (ADC)."
                    )
                except Exception:
                    app.logger.warning(
                        "GOOGLE_APPLICATION_CREDENTIALS no está definida o el archivo no existe. "
                        "Se omite la inicialización de Firebase por ahora."
                    )
    except Exception as e:
        # No bloquear el arranque de Flask, pero registrar el error
        app.logger.error(f"Error al inicializar Firebase Admin: {e}")

    @app.get("/")
    def root():
        return "¡Backend Granix Funcionando!", 200

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok"), 200

    def download_image_temporarily(firebase_url: str) -> str:
        """
        Descarga una imagen desde Firebase Storage a un archivo temporal.
        
        :param firebase_url: URL pública de Firebase Storage
        :return: Ruta local del archivo temporal
        :raises: Exception en caso de error de descarga
        """
        try:
            # Crear archivo temporal
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_path = temp_file.name
            temp_file.close()
            
            # Descargar la imagen
            response = requests.get(firebase_url, timeout=30)
            response.raise_for_status()
            
            # Guardar en archivo temporal
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            
            app.logger.info(f"Imagen descargada temporalmente en: {temp_path}")
            return temp_path
            
        except Exception as e:
            app.logger.error(f"Error descargando imagen: {e}")
            # Limpiar archivo temporal si se creó
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

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

    def upload_image_to_storage(file_storage, *, folder_prefix: str = "invoices/raw") -> str:
        """
        Sube un archivo de imagen a Firebase Storage y retorna la URL pública.

        :param file_storage: objeto FileStorage recibido desde request.files
        :param folder_prefix: carpeta destino dentro del bucket
        :return: URL pública del archivo subido
        :raises: ValueError en caso de configuración faltante
        """
        if not firebase_admin._apps:
            raise ValueError("Firebase Admin no está inicializado. Configure GOOGLE_APPLICATION_CREDENTIALS.")

        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("Falta variable FIREBASE_STORAGE_BUCKET_NAME en el entorno.")

        bucket = storage.bucket(bucket_name)

        filename = secure_filename(file_storage.filename or "invoice")
        unique_id = uuid4().hex
        destination_path = f"{folder_prefix}/{unique_id}_{filename}"

        blob = bucket.blob(destination_path)
        # Generar token para descarga vía Firebase Storage
        download_token = uuid4().hex
        # Subir desde memoria, preservando el content_type cuando sea posible, y agregando token como metadato
        blob.upload_from_string(
            file_storage.read(),
            content_type=file_storage.mimetype,
            predefined_acl=None,
        )
        # Establecer metadata de token para Firebase Storage
        blob.metadata = blob.metadata or {}
        blob.metadata["firebaseStorageDownloadTokens"] = download_token
        blob.patch()

        # Construir URL de descarga estilo Firebase
        from urllib.parse import quote
        encoded_path = quote(destination_path, safe="")
        bucket_name = blob.bucket.name
        download_url = (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}?alt=media&token={download_token}"
        )
        return download_url

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
        Geocodifica una dirección usando Nominatim.
        
        :param address_string: Dirección a geocodificar
        :return: Diccionario con latitude y longitude
        """
        try:
            geolocator = Nominatim(user_agent="granix-backend/1.0")
            location = geolocator.geocode(address_string, timeout=10)
            
            if location:
                return {
                    "latitude": location.latitude,
                    "longitude": location.longitude
                }
            else:
                app.logger.warning(f"No se pudo geocodificar la dirección: {address_string}")
                return {"latitude": None, "longitude": None}
        except Exception as e:
            app.logger.error(f"Error en geocodificación: {e}")
            return {"latitude": None, "longitude": None}

    def parse_invoice_text(raw_ocr_text: str) -> Dict[str, Any]:
        """
        Extrae datos estructurados del texto OCR de una factura.
        
        :param raw_ocr_text: Texto crudo del OCR
        :return: Diccionario con datos estructurados
        """
        # Patrones regex simples para extracción
        address_patterns = [
            r'(?i)direcci[óo]n[:\s]+(.+?)(?:\n|$)',
            r'(?i)calle[:\s]+(.+?)(?:\n|$)',
            r'(?i)domicilio[:\s]+(.+?)(?:\n|$)',
            r'\d+\s+[A-Za-záéíóúñ\s]+\d{4,5}'  # Patrón genérico de dirección
        ]
        
        total_patterns = [
            r'(?i)total[:\s]+\$?(\d+(?:[,.]?\d+)*)',
            r'(?i)importe[:\s]+\$?(\d+(?:[,.]?\d+)*)',
            r'\$(\d+(?:[,.]?\d+)*)',
        ]
        
        # Buscar dirección
        address = None
        for pattern in address_patterns:
            match = re.search(pattern, raw_ocr_text)
            if match:
                address = match.group(1).strip()
                break
        
        # Buscar total
        total_amount = None
        for pattern in total_patterns:
            match = re.search(pattern, raw_ocr_text)
            if match:
                amount_str = match.group(1).replace(',', '.')
                try:
                    total_amount = float(amount_str)
                    break
                except ValueError:
                    continue
        
        # Simular items (para MVP)
        items = [
            {
                "product_code": "PROD001",
                "description": "Producto ejemplo extraído",
                "quantity": 1,
                "unit_price": total_amount or 0.0,
                "total_price": total_amount or 0.0
            }
        ]
        
        return {
            "address": address or "Dirección no encontrada",
            "total_amount": total_amount or 0.0,
            "items": items,
            "extraction_confidence": "low" if not address and not total_amount else "medium"
        }

    def extract_text_from_image(image_input) -> str:
        """
        Extrae texto usando Tesseract a través de pytesseract.

        Acepta:
        - Ruta a imagen (str u os.PathLike)
        - Objeto PIL.Image.Image
        - Bytes o file-like con .read()

        Usa variables de entorno opcionales:
        - TESSERACT_CMD: ruta al ejecutable de tesseract (Windows)
        - TESSERACT_LANG: idiomas para OCR (por defecto 'spa+eng')
        """
        # Configurar ubicación del binario Tesseract si se provee
        tesseract_cmd = os.getenv("TESSERACT_CMD")
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        lang = os.getenv("TESSERACT_LANG", "spa+eng")

        img = None
        # 1) Si es ya una imagen PIL
        if isinstance(image_input, Image.Image):
            img = image_input
        # 2) Si es una ruta
        elif isinstance(image_input, (str, os.PathLike)):
            img = Image.open(image_input)
        else:
            # 3) Intentar bytes o file-like
            try:
                data = image_input.read() if hasattr(image_input, "read") else image_input
                from io import BytesIO
                img = Image.open(BytesIO(data))
            except Exception as e:
                raise ValueError("Entrada de imagen no válida. Se espera ruta, PIL.Image, bytes o file-like.") from e

        # Normalización simple: pasar a escala de grises para mejorar OCR general
        try:
            img = img.convert("L")
        except Exception:
            pass

        # Ejecutar OCR
        text = pytesseract.image_to_string(img, lang=lang)
        return text

    @app.post("/upload-invoice")
    def upload_invoice():
        """
        Endpoint para subir y procesar una imagen de factura.
        
        Flujo completo:
        1. Subir imagen a Firebase Storage
        2. Descargar temporalmente para OCR
        3. Extraer texto con Tesseract
        4. Parsear datos estructurados
        5. Geocodificar dirección
        6. Guardar en Firestore
        7. Retornar datos procesados
        """
        if "file" not in request.files:
            return jsonify(error="No se encontró el archivo en 'file'"), 400

        file_obj = request.files["file"]
        if not file_obj or file_obj.filename == "":
            return jsonify(error="Archivo inválido o nombre vacío"), 400

        temp_path = None
        try:
            # 1. Subir a Firebase Storage
            public_url = upload_image_to_storage(file_obj)
            app.logger.info(f"Imagen subida a Storage: {public_url}")
            
            # 2. Descargar temporalmente
            temp_path = download_image_temporarily(public_url)
            
            # 3. Extraer texto con OCR
            raw_ocr_text = extract_text_from_image(temp_path)
            app.logger.info(f"OCR completado, texto extraído: {len(raw_ocr_text)} caracteres")
            
            # 4. Parsear datos estructurados
            parsed_data = parse_invoice_text(raw_ocr_text)
            
            # 5. Geocodificar dirección
            coordinates = geocode_address(parsed_data["address"])
            
            # 6. Preparar datos para Firestore
            invoice_id = uuid4().hex
            firestore_data = {
                "originalImageUrl": public_url,
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
            
            # 7. Guardar en Firestore
            save_invoice_data(invoice_id, firestore_data)
            
            # 8. Respuesta completa
            response_data = {
                "invoice_id": invoice_id,
                "url": public_url,
                "raw_ocr_text": raw_ocr_text,
                "parsed_data": parsed_data,
                "coordinates": coordinates,
                "status": "processed"
            }
            
            return jsonify(response_data), 200
            
        except ValueError as ve:
            return jsonify(error=str(ve)), 500
        except Exception as e:
            app.logger.exception("Error procesando factura")
            return jsonify(error="Error al procesar la factura"), 500
        finally:
            # Limpiar archivo temporal
            if temp_path:
                cleanup_temp_file(temp_path)

    return app


# Instancia global de la app para correr con `python app.py`
app = create_app()


if __name__ == "__main__":
    # Permitir configurar el puerto por env var
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") in ("1", "true", "True")
    app.run(host="0.0.0.0", port=port, debug=debug)