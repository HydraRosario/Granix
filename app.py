import os
from flask import Flask
from flask_cors import CORS

from routes import transport_bp

def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(transport_bp)
    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") in ("1", "true", "True")
    app.run(host="0.0.0.0", port=port, debug=debug)