import sqlite3
from datetime import UTC, datetime

from flask import current_app, g


SCHEMA = """
CREATE TABLE IF NOT EXISTS qa_review (
    record_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    override_question TEXT,
    override_answer TEXT,
    admin_notes TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT,
    query_text TEXT,
    matched_question TEXT,
    matched_answer TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
