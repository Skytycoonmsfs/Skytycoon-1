# -*- coding: utf-8 -*-
"""Setzt online_network_enabled=1 in career.db (Cloud-Only-Start)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "career.db"


def main() -> None:
    if not DB.is_file():
        print(f"[FEHLER] Keine DB: {DB}")
        return
    conn = sqlite3.connect(str(DB))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('online_network_enabled', '1');"
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('ionos_server_url', 'https://skytycoon.info');"
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('ionos_api_base', 'https://skytycoon.info');"
        )
        conn.commit()
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key='online_network_enabled';"
        ).fetchone()
        print(f"[OK] online_network_enabled = {row[0] if row else '?'}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
