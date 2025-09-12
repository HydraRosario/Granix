import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import storage
from werkzeug.utils import secure_filename
from uuid import uuid4
from PIL import Image
import pytesseract

# Carga variables de entorno desde .env si existe
load_dotenv()


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

    @app.post("/upload-invoice")
    def upload_invoice():
        """Endpoint para subir una imagen de factura a Firebase Storage."""
        if "file" not in request.files:
            return jsonify(error="No se encontró el archivo en 'file'"), 400

        file_obj = request.files["file"]
        if not file_obj or file_obj.filename == "":
            return jsonify(error="Archivo inválido o nombre vacío"), 400

        try:
            public_url = upload_image_to_storage(file_obj)
            return jsonify(url=public_url), 200
        except ValueError as ve:
            return jsonify(error=str(ve)), 500
        except Exception as e:
            app.logger.exception("Error subiendo archivo a Storage")
            return jsonify(error="Error al subir la imagen"), 500

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

    return app


# Instancia global de la app para correr con `python app.py`
app = create_app()


if __name__ == "__main__":
    # Permitir configurar el puerto por env var
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") in ("1", "true", "True")
    app.run(host="0.0.0.0", port=port, debug=debug)
