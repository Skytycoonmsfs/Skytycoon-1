# -*- coding: utf-8 -*-
"""SkyTycoon Desktop — PostgreSQL (skytycoon_prod, DictCursor)."""

from __future__ import annotations

import os
import threading
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import DictCursor
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]
    DictCursor = None  # type: ignore[assignment,misc]

_PG_LOCK = threading.Lock()
_PG_READY = False

PG_DSN = (os.environ.get("SKYTYCOON_POSTGRES_DSN") or "").strip()
PG_HOST = (os.environ.get("SKYTYCOON_PG_HOST") or "127.0.0.1").strip()
PG_PORT = (os.environ.get("SKYTYCOON_PG_PORT") or "5432").strip()
PG_DATABASE = (os.environ.get("SKYTYCOON_PG_DATABASE") or "skytycoon_prod").strip()
PG_USER = (os.environ.get("SKYTYCOON_PG_USER") or "sky_admin").strip()
PG_PASSWORD = (os.environ.get("SKYTYCOON_PG_PASSWORD") or "").strip()


def pg_available() -> bool:
    return psycopg2 is not None


def _probe_connection() -> bool:
    if not pg_available():
        return False
    try:
        conn = _open_connection()
        conn.close()
        return True
    except Exception:
        return False


def _open_connection():
    if not pg_available():
        raise RuntimeError("psycopg2 nicht installiert — pip install psycopg2-binary")
    if PG_DSN:
        return psycopg2.connect(PG_DSN, cursor_factory=DictCursor, connect_timeout=10)
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
        cursor_factory=DictCursor,
        connect_timeout=10,
    )


def get_db_connection():
    """Neue Verbindung mit DictCursor (Aufrufer schließt)."""
    global _PG_READY
    with _PG_LOCK:
        if not _PG_READY and not _probe_connection():
            raise RuntimeError(
                "PostgreSQL nicht erreichbar — SKYTYCOON_PG_* oder "
                "SKYTYCOON_POSTGRES_DSN prüfen."
            )
        _PG_READY = True
    return _open_connection()


def pg_execute(sql: str, params: Any = None) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return int(cur.rowcount)
    finally:
        conn.close()


def pg_fetchone(sql: str, params: Any = None) -> Any:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def pg_fetchall(sql: str, params: Any = None) -> list[Any]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()
