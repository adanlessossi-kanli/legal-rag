import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

_DB_PATH = Path(settings.upload_dir) / "metadata.db"
_JSON_PATH = Path(settings.upload_dir) / "metadata.json"

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS documents (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'processing',
                content_hash TEXT
            )"""
        )
        _local.conn = conn
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS documents (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'processing',
                content_hash TEXT
            )"""
        )


def _migrate_from_json() -> None:
    if not _JSON_PATH.exists() or _DB_PATH.exists():
        return
    try:
        data = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
        _init_db()
        with _get_conn() as conn:
            for doc_id, info in data.items():
                conn.execute(
                    "INSERT OR IGNORE INTO documents (id, name, uploaded_at, chunk_count, status) VALUES (?, ?, ?, ?, ?)",
                    (doc_id, info["name"], info.get("uploaded_at", ""), info.get("chunk_count", 0), info.get("status", "ready")),
                )
        _JSON_PATH.rename(_JSON_PATH.with_suffix(".json.bak"))
        logger.info("Migrated metadata from JSON to SQLite")
    except Exception:
        logger.exception("Failed to migrate metadata from JSON")


_migrate_from_json()
_init_db()


def save_document(doc_id: str, name: str, chunk_count: int, status: str, content_hash: str = "") -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO documents (id, name, uploaded_at, chunk_count, status, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, name, datetime.now(timezone.utc).isoformat(), chunk_count, status, content_hash),
        )


def get_all_documents() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM documents").fetchall()
    return [dict(r) for r in rows]


def get_document(doc_id: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def delete_document(doc_id: str) -> bool:
    with _get_conn() as conn:
        cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return cursor.rowcount > 0


def update_status(doc_id: str, status: str) -> None:
    with _get_conn() as conn:
        conn.execute("UPDATE documents SET status = ? WHERE id = ?", (status, doc_id))


def find_by_hash(content_hash: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE content_hash = ?", (content_hash,)).fetchone()
    return dict(row) if row else None
