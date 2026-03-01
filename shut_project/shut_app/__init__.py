from flask import Flask

from .blueprints.admin import admin_bp
from .blueprints.public import public_bp
from .config import Config
from .db import init_app as init_db_app
from .services.qa_engine import QAEngine


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Config.TEMPLATE_DIR),
        static_folder=str(Config.STATIC_DIR),
    )
    app.config.from_object(Config)
    app.config["UPLOADS_DIR"].mkdir(parents=True, exist_ok=True)

    init_db_app(app)
    app.extensions["qa_engine"] = QAEngine(app.config["QA_DATA_FILE"])

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    return app
