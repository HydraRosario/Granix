import os
from flask import Blueprint, jsonify, request, current_app
from werkzeug.utils import secure_filename
from pdf2image import convert_from_path

from invoice_service import geocode_address, _process_invoice_image_data
from delivery_service import parse_delivery_report_text
from shared_utils import _extract_text_from_pdf, extract_text_from_image, temp_file_path

transport_bp = Blueprint('transport_bp', __name__)

@transport_bp.get("/")
def root():
    return "¡Backend Granix Funcionando!", 200

@transport_bp.get("/healthz")
def healthz():
    return jsonify(status="ok"), 200

@transport_bp.get("/geocode")
def geocode_endpoint():
    address = request.args.get("address")
    if not address:
        return jsonify(error="Parámetro 'address' es requerido."), 400
    
    coordinates = geocode_address(address)
    return jsonify(coordinates), 200

@transport_bp.post("/process_invoice")
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
        current_app.logger.exception("Error procesando factura")
        return jsonify(error="Error al procesar la factura"), 500

@transport_bp.post("/process_delivery_report")
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
        current_app.logger.exception("Error procesando informe de entrega")
        return jsonify(error="Error al procesar el informe de entrega"), 500
