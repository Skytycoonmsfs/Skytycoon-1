# -*- coding: utf-8 -*-
"""Sovereign Profile Cloud Sync — PostgreSQL + Pack/Verify (ohne main.py)."""
from __future__ import annotations

import base64
import json
import os
import secrets
import time
from typing import Any

import requests

try:
    from psycopg2.extras import DictCursor
except ImportError:  # pragma: no cover
    DictCursor = None  # type: ignore[misc, assignment]

DISCORD_BOT_TOKEN = (os.environ.get("SKYTYCOON_DISCORD_BOT_TOKEN") or "").strip()
DISCORD_ADMIN_CHANNEL = (os.environ.get("SKYTYCOON_DISCORD_ADMIN_CHANNEL_ID") or "").strip()


def pack_profile_blob(payload: dict[str, Any]) -> str:
    import zlib

    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")


def unpack_profile_blob(blob: str) -> dict[str, Any]:
    import zlib

    if not (blob or "").strip():
        return {}
    try:
        raw = zlib.decompress(base64.b64decode(blob.encode("ascii")))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def discord_admin_alert(title: str, description: str) -> None:
    if not DISCORD_BOT_TOKEN or not DISCORD_ADMIN_CHANNEL:
        return
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{DISCORD_ADMIN_CHANNEL}/messages",
            headers={
                "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "embeds": [
                    {
                        "title": title[:256],
                        "description": description[:4000],
                        "color": 0xE53935,
                    }
                ]
            },
            timeout=12,
        )
    except Exception:
        pass


def sovereign_verify_license(
    *,
    license_key: str,
    hardware_id: str,
    pilot_name: str = "",
    password: str = "",
    verify_password,
    verify_license_keys_password_for_hid,
) -> tuple[bool, str, str]:
    """Returns (ok, hid64, error_code)."""
    import sqlite3

    lk = (license_key or "").strip().upper()
    hid = (hardware_id or "").strip()[:128]
    hid64 = hid[:64]
    if not lk or not hid64:
        return False, "", "missing_fields"
    if not lk.startswith("ST-"):
        return False, "", "bad_key_format"
    from server_backend import SERVER_DB_PATH, USER_DB_PATH

    conn = sqlite3.connect(str(SERVER_DB_PATH))
    try:
        row = None
        for cand in (lk, license_key.strip()):
            row = conn.execute(
                """
                SELECT status, hardware_id, pilot_name, customer_email,
                       password_salt, password_hash
                FROM license_keys WHERE license_key = ?;
                """,
                (cand,),
            ).fetchone()
            if row:
                break
        if not row:
            return False, "", "key_invalid"
        st, bound, pname, email, salt, ph = row
        st = str(st or "")
        bound = str(bound or "").strip()[:128]
        if st == "banned":
            return False, "", "banned"
        if st not in ("unused", "activated"):
            return False, "", "key_invalid"
        if st == "activated" and bound:
            try:
                from server_backend import _hwid_accounts_match

                em_chk = str(email or "").strip().lower()[:200]
                if not _hwid_accounts_match(bound, hid, em_chk):
                    conn.execute(
                        "UPDATE license_keys SET hardware_id = ? WHERE license_key = ?;",
                        (hid, cand or lk),
                    )
                    conn.commit()
            except Exception:
                if bound[:64] != hid64:
                    return False, "", "hardware_mismatch"
        if password and salt and ph:
            if not verify_password(str(salt), str(ph), password):
                return False, "", "bad_password"
        elif password and verify_license_keys_password_for_hid(hid64, password):
            pass
        elif st == "unused":
            pass
        else:
            return False, "", "auth_required"
        if st == "unused":
            salt_n, ph_n = ("", "")
            if password:
                from server_backend import _password_hash_store

                salt_n, ph_n = _password_hash_store(password)
            conn.execute(
                """
                UPDATE license_keys SET status = 'activated', hardware_id = ?,
                pilot_name = COALESCE(NULLIF(?, ''), pilot_name),
                password_salt = CASE WHEN ? != '' THEN ? ELSE password_salt END,
                password_hash = CASE WHEN ? != '' THEN ? ELSE password_hash END
                WHERE license_key = ?;
                """,
                (hid, pilot_name, salt_n, salt_n, ph_n, ph_n, cand or lk),
            )
            conn.commit()
        return True, hid64, ""
    finally:
        conn.close()


def sovereign_profile_pull_pg(
    hid: str,
    *,
    get_db_connection,
    email: str = "",
    pilot_name: str = "",
) -> dict[str, Any]:
    hk = (hid or "").strip()[:128]
    hid64 = hk[:64]
    em = (email or "").strip().lower()[:200]
    pilot = (pilot_name or "").strip()[:120]
    out: dict[str, Any] = {
        "hardware_id": hk,
        "credits": 0.0,
        "xp": 0.0,
        "reputation": 72.0,
        "level": 1,
        "fuel_storage": 0,
        "fuel_max_capacity": 50_000,
        "fleet": [],
        "branches": [],
        "simconnect": {},
    }
    if not hk or get_db_connection is None:
        return out
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            u = None
            if em and "@" in em:
                cur.execute(
                    """
                    SELECT hardware_id, username, email, credits, money, xp, reputation,
                           license_status, fuel_storage, fuel_max_capacity, level,
                           branches_json, ratings_json, selected_language
                    FROM users
                    WHERE lower(trim(email)) = %s
                    LIMIT 1;
                    """,
                    (em,),
                )
                u = cur.fetchone()
            if not u:
                cur.execute(
                    """
                    SELECT hardware_id, username, email, credits, money, xp, reputation,
                           license_status, fuel_storage, fuel_max_capacity, level,
                           branches_json, ratings_json, selected_language
                    FROM users
                    WHERE hardware_id = %s
                    LIMIT 1;
                    """,
                    (hk,),
                )
                u = cur.fetchone()
            if u:
                out["hardware_id"] = str(u.get("hardware_id") or hk)
                out["username"] = str(u.get("username") or "")
                out["pilot_name"] = out["username"] or pilot
                out["email"] = str(u.get("email") or em)
                out["credits"] = float(u.get("credits") or u.get("money") or 0)
                out["xp"] = float(u.get("xp") or 0)
                out["reputation"] = float(u.get("reputation") or 72)
                out["level"] = max(1, int(u.get("level") or 1))
                out["fuel_storage"] = int(u.get("fuel_storage") or 0)
                out["fuel_max_capacity"] = max(50_000, int(u.get("fuel_max_capacity") or 50_000))
                bj = u.get("branches_json")
                if isinstance(bj, str) and bj.strip():
                    try:
                        out["branches"] = json.loads(bj)
                    except json.JSONDecodeError:
                        pass
                elif isinstance(bj, list):
                    out["branches"] = bj
            owner_user = str(out.get("username") or pilot or hk).strip()
            owner_em = str(out.get("email") or em).strip()
            cur.execute(
                """
                SELECT aircraft_id, aircraft_model, status, current_location,
                       engine_1_health, airframe_condition, fuel_gallons
                FROM fleet
                WHERE owner_username = %s
                   OR lower(trim(owner_username)) = lower(trim(%s))
                   OR (%s <> '' AND lower(trim(owner_username)) = lower(trim(%s)))
                ORDER BY id ASC LIMIT 120;
                """,
                (owner_user, owner_user, owner_em, owner_em),
            )
            fleet_rows = []
            for r in cur.fetchall() or []:
                fleet_rows.append(
                    {
                        "aircraft_id": r.get("aircraft_id"),
                        "aircraft_model": str(r.get("aircraft_model") or ""),
                        "status": str(r.get("status") or ""),
                        "location": str(r.get("current_location") or ""),
                        "engine_1_health": float(r.get("engine_1_health") or 100),
                        "airframe_condition": float(r.get("airframe_condition") or 100),
                        "fuel_gallons": float(r.get("fuel_gallons") or 0),
                    }
                )
            out["fleet"] = fleet_rows
            out["fleet_data"] = fleet_rows
    finally:
        conn.close()
    return out


def cloud_save_plausibility(body: dict[str, Any]) -> tuple[bool, str]:
    try:
        credits = float(body.get("credits", 0) or 0)
        flight_min = float(
            body.get("flight_minutes", body.get("flight_time_min", 0)) or 0
        )
    except (TypeError, ValueError):
        return True, ""
    if credits > 99_000_000:
        return False, "credits_cap"
    if flight_min < 3.0 and credits > 750_000:
        return False, "credits_vs_time"
    if flight_min > 0 and credits / max(flight_min, 0.1) > 250_000:
        return False, "credits_per_minute"
    return True, ""


def pg_create_fresh_portal_account(
    *,
    email: str,
    pilot_name: str,
    hardware_id: str,
    get_db_connection,
    selected_language: str = "de",
) -> tuple[bool, str]:
    """Neues PostgreSQL-Konto — strikt getrennt pro E-Mail."""
    from server_backend import (
        _pg_ensure_users_portal_columns,
        _pg_rollback,
        pg_commit,
        pg_execute,
        pg_fetchone,
    )

    em = (email or "").strip().lower()[:200]
    pilot = (pilot_name or "").strip()[:160] or em.split("@", 1)[0][:120]
    hid = (hardware_id or "").strip()[:128]
    if not em or "@" not in em or not hid:
        return False, "bad_input"
    lang = (selected_language or "de").strip().lower()[:8]
    if lang not in ("de", "en"):
        lang = "de"
    conn = get_db_connection()
    try:
        _pg_ensure_users_portal_columns(conn)
        if pg_fetchone(
            conn,
            "SELECT 1 FROM users WHERE lower(trim(email)) = %s LIMIT 1;",
            (em,),
        ):
            return False, "email_taken"
        if pg_fetchone(
            conn,
            """
            SELECT 1 FROM users
            WHERE lower(trim(username)) = lower(trim(%s))
              AND lower(trim(COALESCE(email, ''))) IS DISTINCT FROM %s
            LIMIT 1;
            """,
            (pilot, em),
        ):
            return False, "username_taken"
        try:
            pg_execute(
                conn,
                """
                INSERT INTO users (
                    hardware_id, username, email, money, credits, xp,
                    license_status, selected_language
                ) VALUES (%s, %s, %s, 50000, 50000, 0, 'portal_free', %s);
                """,
                (hid, pilot, em, lang),
            )
        except Exception:
            _pg_rollback(conn)
            pg_execute(
                conn,
                """
                INSERT INTO users (
                    hardware_id, username, email, money, credits, xp, license_status
                ) VALUES (%s, %s, %s, 50000, 50000, 0, 'portal_free');
                """,
                (hid, pilot, em),
            )
        pg_commit(conn)
        return True, hid
    except Exception as exc:
        _pg_rollback(conn)
        msg = str(exc).strip()
        if "current transaction is aborted" in msg.lower():
            return False, "register_db_retry"
        return False, msg[:400]
    finally:
        try:
            conn.close()
        except Exception:
            pass


def pg_obliterate_account(
    *,
    hardware_id: str,
    username: str = "",
    release_license: bool = True,
    get_db_connection,
) -> bool:
    hk = (hardware_id or "").strip()[:128]
    un = (username or "").strip()[:160]
    if not hk:
        return False
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM active_flights WHERE hardware_id = %s OR substring(hardware_id from 1 for 64) = %s;",
                (hk, hk[:64]),
            )
            if un:
                cur.execute(
                    "DELETE FROM fleet WHERE lower(owner_username) = lower(%s);",
                    (un,),
                )
            cur.execute(
                """
                DELETE FROM fleet
                WHERE owner_username = %s
                   OR lower(owner_username) = lower(%s);
                """,
                (hk, un or hk),
            )
            cur.execute(
                "DELETE FROM users WHERE hardware_id = %s OR substring(hardware_id from 1 for 64) = %s;",
                (hk, hk[:64]),
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def pg_persist_cloud_profile(
    *,
    hardware_id: str,
    body: dict[str, Any],
    get_db_connection,
) -> bool:
    hk = (hardware_id or "").strip()[:128]
    if not hk:
        return False
    try:
        credits = float(body.get("credits", 0) or 0)
        xp = float(body.get("xp", 0) or 0)
        reputation = float(body.get("reputation", 72) or 72)
        level = max(1, int(body.get("level", 1) or 1))
        fuel_storage = int(body.get("fuel_storage", 0) or 0)
        fuel_cap = max(50_000, int(body.get("fuel_max_capacity", 50_000) or 50_000))
    except (TypeError, ValueError):
        return False
    branches = body.get("branches_json")
    if branches is None:
        branches = body.get("branches")
    bj = "[]"
    if isinstance(branches, list):
        bj = json.dumps(branches, ensure_ascii=False)[:400_000]
    elif isinstance(branches, str) and branches.strip():
        bj = branches[:400_000]
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (
                    hardware_id, username, money, credits, xp, reputation,
                    fuel_storage, fuel_max_capacity, level, branches_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (hardware_id) DO UPDATE SET
                    credits = EXCLUDED.credits,
                    money = EXCLUDED.credits,
                    xp = EXCLUDED.xp,
                    reputation = EXCLUDED.reputation,
                    fuel_storage = EXCLUDED.fuel_storage,
                    fuel_max_capacity = EXCLUDED.fuel_max_capacity,
                    level = EXCLUDED.level,
                    branches_json = EXCLUDED.branches_json;
                """,
                (
                    hk,
                    str(body.get("username") or body.get("pilot_name") or hk[:16])[:160],
                    credits,
                    credits,
                    xp,
                    reputation,
                    fuel_storage,
                    fuel_cap,
                    level,
                    bj,
                ),
            )
            fleet = body.get("fleet") or body.get("fleet_data") or []
            if isinstance(fleet, list):
                owner = str(body.get("username") or body.get("pilot_name") or hk)[:160]
                for ac in fleet[:120]:
                    if not isinstance(ac, dict):
                        continue
                    aid = str(ac.get("aircraft_id") or ac.get("id") or "")[:64]
                    model = str(ac.get("aircraft_model") or ac.get("model") or "")[:80]
                    if not model:
                        continue
                    cur.execute(
                        """
                        INSERT INTO fleet (
                            owner_username, aircraft_id, aircraft_model, status,
                            current_location, engine_1_health, airframe_condition, fuel_gallons
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING;
                        """,
                        (
                            owner,
                            aid or model[:32],
                            model,
                            str(ac.get("status") or "hangar")[:32],
                            str(ac.get("location") or ac.get("current_location") or "")[:8],
                            float(ac.get("engine_1_health", 100) or 100),
                            float(ac.get("airframe_condition", 100) or 100),
                            float(ac.get("fuel_gallons", 0) or 0),
                        ),
                    )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()
