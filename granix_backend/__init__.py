import os
from flask import Flask
from flask_cors import CORS

from granix_backend.api.routes import transport_bp

def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(transport_bp)
    return app
