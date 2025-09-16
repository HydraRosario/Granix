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
from geopy.geocoders import Nominatim
from flask_cors import CORS # Importa CORS
from pdf2image import convert_from_path
from contextlib import contextmanager
import io

# Dirección de respaldo para geocodificación fallida
DEFAULT_START_ADDRESS = "Mendoza y Wilde, Rosario, Santa Fe, Argentina"

# Carga variables de entorno desde .env si existe
load_dotenv()

@contextmanager
def temp_file_path(suffix=""):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd) # Close the file descriptor immediately
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)

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
        firebase_admin.get_app() # Check if app is already initialized
    except ValueError:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if cred_path:
            cred_path = cred_path.strip().strip('\'').strip("\"")

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

    def _extract_text_from_pdf(pdf_path: str) -> str:
        """
        Extrae texto de un PDF convirtiendo cada página a imagen y aplicando OCR.
        """
        poppler_path = os.getenv("POPPLER_PATH")
        if not poppler_path:
            app.logger.error("POPPLER_PATH no está configurado en las variables de entorno.")
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
            app.logger.error(f"Error al subir a Cloudinary: {e}")
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
        app.logger.info(f"[Invoice:{invoice_id}] Datos guardados en Firestore para invoice_id: {invoice_id}")

    def geocode_address(address_string: str) -> dict:
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
        app.logger.info(f"[Invoice:{invoice_id}] Procesamiento completo para la factura.")
        
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
                address = re.sub(r'(?<![a-zA-Z])N[\u00b0*\s]+', ' ', address, flags=re.IGNORECASE).strip()
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

        # Regex to capture each delivery item line
        # Fa P0298-00668316 GARCIA OSCAR Artigas N° 395, Rosario 4
        # (Fa|Re) (InvoiceNumber) (CommercialEntity) (DeliveryAddress) (Bultos)
        item_pattern = re.compile(
            r'(Fa|Re)\s+([A-Z0-9-]+)\s+([^,]+?)\s+([^0-9]+?)\s+(\d+)'
        )

        # Regex to capture summary at the end
        summary_pattern = re.compile(
            r'Cantidad de Facturas:\s*(\d+)\s+Cantidad de Remitos:\s*(\d+)\s+Bultos:\s*(\d+)'
        )

        lines = raw_ocr_text.split('\n')
        for line in lines:
            item_match = item_pattern.search(line)
            if item_match:
                item_type = item_match.group(1)
                invoice_number = item_match.group(2)
                commercial_entity = item_match.group(3).strip()
                delivery_address = item_match.group(4).strip()
                packages = int(item_match.group(5))

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

    @app.post("/process_invoice")
    def process_invoice():
        """
        Endpoint para subir y procesar una imagen o PDF de factura.
        """
        if "file" not in request.files:
            return jsonify(error="No se encontró el archivo en 'file'"), 400

        file_obj = request.files["file"]
        if not file_obj or file_obj.filename == "":
            return jsonify(error="Archivo inválido o nombre vacío"), 400

        filename = secure_filename(file_obj.filename)
        results = []

        try:
            with temp_file_path(suffix=filename) as temp_path:
                file_obj.save(temp_path)

                is_pdf = file_obj.mimetype == 'application/pdf' or filename.lower().endswith(".pdf")

                if is_pdf:
                    poppler_path = os.getenv("POPPLER_PATH")
                    if not poppler_path:
                        return jsonify(error="La ruta a Poppler no está configurada en las variables de entorno."), 500
                    
                    images = convert_from_path(temp_path, poppler_path=poppler_path)
                    for i, image in enumerate(images):
                        with temp_file_path(suffix=f"_page_{i+1}.png") as img_temp_path:
                            image.save(img_temp_path, 'PNG')
                            results.append(_process_invoice_image_data(img_temp_path))
                elif file_obj.mimetype.startswith('image/') or filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    results.append(_process_invoice_image_data(temp_path))
                else:
                    return jsonify(error="Tipo de archivo no soportado. Solo se aceptan PDF o imágenes."), 400

            return jsonify(results), 200

        except ValueError as ve:
            return jsonify(error=str(ve)), 500
        except Exception as _:
            app.logger.exception("Error procesando factura")
            return jsonify(error="Error al procesar la factura"), 500 # Use os.unlink directly as NamedTemporaryFile with delete=False was used

    @app.post("/process_delivery_report")
    def process_delivery_report():
        """
        Endpoint para subir y procesar un informe de entrega, extrayendo solo el texto OCR
        y la información estructurada del informe.
        """
        if "file" not in request.files:
            return jsonify(error="No se encontró el archivo en 'file'"), 400

        file_obj = request.files["file"]
        if not file_obj or file_obj.filename == "":
            return jsonify(error="Archivo inválido o nombre vacío"), 400

        filename = secure_filename(file_obj.filename)
        raw_ocr_text = ""

        try:
            with temp_file_path(suffix=filename) as temp_path:
                file_obj.save(temp_path)

                is_pdf = file_obj.mimetype == 'application/pdf' or filename.lower().endswith(".pdf")

                if is_pdf:
                    raw_ocr_text = _extract_text_from_pdf(temp_path)
                elif file_obj.mimetype.startswith('image/') or filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    raw_ocr_text = extract_text_from_image(temp_path)
                else:
                    return jsonify(error="Tipo de archivo no soportado. Solo se aceptan PDF o imágenes."), 400

            parsed_report_data = parse_delivery_report_text(raw_ocr_text)

            return jsonify({
                "raw_ocr_text": raw_ocr_text,
                "parsed_report_data": parsed_report_data
            }), 200

        except ValueError as ve:
            return jsonify(error=str(ve)), 500
        except Exception as _:
            app.logger.exception("Error procesando informe de entrega")
            return jsonify(error="Error al procesar el informe de entrega"), 500

    return app


# Instancia global de la app para correr con `python app.py`
app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") in ("1", "true", "True")
    app.run(host="0.0.0.0", port=port, debug=debug)