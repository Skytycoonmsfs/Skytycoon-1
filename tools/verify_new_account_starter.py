#!/usr/bin/env python3
"""Prüft Neukonto-Startwerte (Server PG + API-Register-Schema)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = (os.environ.get("SKYTYCOON_HEALTH_BASE") or "https://skytycoon.info").rstrip("/")
STARTER = 50_000.0


def _post(path: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "SkyTycoon-Verify/1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            j = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            j = {"raw": raw[:200]}
        return int(exc.code), j


def main() -> int:
    print("=== Neukonto-Check ===")
    print(f"Server: {BASE}")
    code, j = _post(
        "/api/v1/auth/register",
        {
            "email": f"verify_{os.getpid()}@example.invalid",
            "pilot_name": f"VerifyPilot{os.getpid() % 10000}",
            "password": "Test-Only-Not-Real-12!",
            "selected_language": "de",
        },
    )
    print(f"POST /api/v1/auth/register -> HTTP {code}")
    if code == 409:
        print("  (E-Mail/Pilot schon vergeben — erwartbar bei Wiederholung)")
    elif code not in (200, 201):
        print("  Antwort:", j)
        return 1
    else:
        print("  Registrierung OK (frisches Konto angelegt).")

    from skytycoon_profile_cloud import pg_create_fresh_portal_account

    try:
        from server_backend import get_db_connection
    except ImportError as exc:
        print("PG-Check übersprungen (server_backend nur auf IONOS):", exc)
        return 0

    test_em = f"local_pg_{os.getpid()}@example.invalid"
    ok, msg = pg_create_fresh_portal_account(
        email=test_em,
        pilot_name="PgVerifyPilot",
        hardware_id=f"web-verify-{os.getpid()}",
        get_db_connection=get_db_connection,
        selected_language="de",
    )
    print(f"pg_create_fresh_portal_account -> ok={ok} msg={msg}")
    if not ok:
        return 1
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT credits, money, xp, license_status
                FROM users WHERE lower(trim(email)) = %s LIMIT 1;
                """,
                (test_em.lower(),),
            )
            row = cur.fetchone()
        if not row:
            print("PG: Benutzer nicht gefunden")
            return 1
        cred = float(row[0] or 0) + float(row[1] or 0)
        xp = float(row[2] or 0)
        print(f"PG: credits+money={cred:.0f} xp={xp:.0f} status={row[3]}")
        if abs(cred - STARTER) > 1.0 or xp > 0.01:
            print("FEHLER: Startwerte nicht 50.000 / 0 XP")
            return 1
        print("OK: Server-Neukonto = 50.000 CR, 0 XP")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
