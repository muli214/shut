import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
UPLOADS_DIR = DATA_DIR / "uploads"
QA_DATA_FILE = DATA_DIR / "qa_pairs.json"
DATABASE_PATH = DATA_DIR / "app.db"


class Config:
    SECRET_KEY = os.environ.get("SHUT_SECRET_KEY", "shut-dev-secret")
    ADMIN_USERNAME = os.environ.get("SHUT_ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("SHUT_ADMIN_PASSWORD", "change-me")
    DATA_DIR = DATA_DIR
    STATIC_DIR = STATIC_DIR
    TEMPLATE_DIR = TEMPLATE_DIR
    UPLOADS_DIR = UPLOADS_DIR
    QA_DATA_FILE = QA_DATA_FILE
    DATABASE_PATH = DATABASE_PATH
