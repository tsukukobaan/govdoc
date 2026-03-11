"""Shared database connection for all scripts.

Connects to Turso (remote libSQL) when TURSO_DATABASE_URL is set,
otherwise falls back to local dev.db (sqlite3).

Usage:
    from db import connect_db

    conn = connect_db()
    conn.execute("SELECT ...")
    conn.commit()
    conn.close()
"""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "dev.db"

_is_turso = False


def is_turso() -> bool:
    """Return True if using remote Turso database."""
    return _is_turso


def connect_db(row_factory: bool = False):
    """Connect to database.

    Uses Turso if TURSO_DATABASE_URL env var is set, otherwise local dev.db.

    Args:
        row_factory: If True, rows are accessible by column name (dict-like).
    """
    global _is_turso
    turso_url = os.environ.get("TURSO_DATABASE_URL")

    if turso_url:
        import libsql_experimental

        auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
        conn = libsql_experimental.connect(turso_url, auth_token=auth_token)
        if row_factory:
            conn.row_factory = libsql_experimental.Row
        _is_turso = True
        return conn
    else:
        import sqlite3

        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH), timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        if row_factory:
            conn.row_factory = sqlite3.Row
        _is_turso = False
        return conn
