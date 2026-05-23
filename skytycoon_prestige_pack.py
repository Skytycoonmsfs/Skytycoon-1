# -*- coding: utf-8 -*-
"""Type-Ratings, Prestige-Ränge und Pax-Radar — PostgreSQL-Pool (skytycoon_pg)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TYPE_RATING_CLASS_MODELS: dict[str, tuple[str, ...]] = {
    "a320": (
        "Fenix A320",
        "FlyByWire A32NX",
        "Airbus A319 CEO",
        "Airbus A320neo",
        "Airbus A330-900",
        "Airbus A350-900",
    ),
    "b737": (
        "Boeing 737-700",
        "PMDG 737-800",
        "PMDG 737-900",
        "Boeing 777-300ER",
        "PMDG 777",
        "Boeing 787-10",
        "MD-82",
        "Bombardier CRJ900",
        "Dash 8 Q400",
    ),
    "ga": ("Cessna 172 Skyhawk", "Concorde (Study Level)"),
}

TYPE_RATING_MODULE_BY_CLASS: dict[str, str] = {
    "a320": "type_rating_a320",
    "b737": "type_rating_b737",
    "ga": "type_rating_ga",
}

MODULE_COSTS: dict[str, int] = {
    "type_rating_a320": 3500,
    "type_rating_b737": 2800,
    "type_rating_ga": 400,
    "mod_casino": 0,
}

RANK_MILESTONES: tuple[tuple[float, str], ...] = (
    (0.0, "Cadet"),
    (500.0, "First Officer"),
    (2500.0, "Captain"),
    (8000.0, "Senior Captain"),
    (20000.0, "Global Tycoon"),
)


def _hid64(hardware_id: str) -> str:
    return str(hardware_id or "").strip()[:64]


def _pg_conn():
    from skytycoon_pg import get_db_connection

    return get_db_connection()


def pg_has_module(hardware_id: str, module_key: str) -> bool:
    hid = _hid64(hardware_id)
    mk = str(module_key or "").strip()
    if not hid or not mk:
        return False
    try:
        from skytycoon_pg import pg_fetchone

        conn = _pg_conn()
        try:
            for sql in (
                """
                SELECT 1 FROM pilot_addon_modules
                WHERE hardware_id = %s AND module_key = %s
                  AND COALESCE(active, 1) = 1
                LIMIT 1;
                """,
                """
                SELECT 1 FROM user_modules
                WHERE hardware_id = %s AND module_key = %s
                LIMIT 1;
                """,
            ):
                try:
                    row = pg_fetchone(conn, sql, (hid, mk))
                    if row:
                        return True
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
        finally:
            conn.close()
    except Exception:
        return False
    return False


def pg_buy_module(hardware_id: str, module_key: str) -> tuple[bool, str]:
    hid = _hid64(hardware_id)
    mk = str(module_key or "").strip()
    cost = int(MODULE_COSTS.get(mk, 5000))
    if not hid or not mk:
        return False, "hardware_id oder module_key fehlt."
    try:
        from skytycoon_pg import pg_fetchone

        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT credits FROM users WHERE hardware_id = %s LIMIT 1;",
                    (hid,),
                )
                row = cur.fetchone()
                cred = float(row["credits"] or 0) if row else 0.0
                if cost > 0 and cred < cost:
                    return False, "Zu wenig Credits auf dem Server-Konto."
                if cost > 0:
                    cur.execute(
                        "UPDATE users SET credits = credits - %s WHERE hardware_id = %s;",
                        (cost, hid),
                    )
                ts = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    """
                    INSERT INTO pilot_addon_modules (
                        hardware_id, module_key, active, credits_spent, unlocked_at
                    ) VALUES (%s, %s, 1, %s, %s)
                    ON CONFLICT (hardware_id, module_key) DO UPDATE SET
                        active = 1,
                        credits_spent = EXCLUDED.credits_spent,
                        unlocked_at = EXCLUDED.unlocked_at;
                    """,
                    (hid, mk, float(cost), ts),
                )
                conn.commit()
        finally:
            conn.close()
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def pg_user_profile_row(hardware_id: str) -> dict[str, Any]:
    hid = _hid64(hardware_id)
    out: dict[str, Any] = {
        "credits": 0.0,
        "fuel_vouchers": 0,
        "prestige_level": 0,
        "total_miles": 0.0,
    }
    if not hid:
        return out
    try:
        from skytycoon_pg import pg_fetchone

        conn = _pg_conn()
        try:
            row = pg_fetchone(
                conn,
                """
                SELECT credits, COALESCE(fuel_vouchers, 0) AS fuel_vouchers,
                       COALESCE(prestige_level, 0) AS prestige_level,
                       COALESCE(total_miles, 0) AS total_miles
                FROM users WHERE hardware_id = %s LIMIT 1;
                """,
                (hid,),
            )
            if row:
                out["credits"] = float(row.get("credits") or 0)
                out["fuel_vouchers"] = int(row.get("fuel_vouchers") or 0)
                out["prestige_level"] = int(row.get("prestige_level") or 0)
                out["total_miles"] = float(row.get("total_miles") or 0)
        finally:
            conn.close()
    except Exception:
        pass
    return out


def resolve_rank(miles: float, prestige_level: int = 0) -> dict[str, Any]:
    m = max(0.0, float(miles or 0))
    pl = max(0, int(prestige_level or 0))
    name = RANK_MILESTONES[0][1]
    next_name = ""
    next_miles = 0.0
    progress = 100.0
    for i, (threshold, rank_name) in enumerate(RANK_MILESTONES):
        if m >= threshold:
            name = rank_name
        if i + 1 < len(RANK_MILESTONES):
            nxt_thr, nxt_name = RANK_MILESTONES[i + 1]
            if m < nxt_thr:
                next_name = nxt_name
                next_miles = nxt_thr
                span = max(1.0, nxt_thr - threshold)
                progress = min(100.0, max(0.0, ((m - threshold) / span) * 100.0))
                break
    return {
        "rank_name": name,
        "prestige_level": pl,
        "miles": m,
        "next_rank": next_name,
        "next_rank_miles": next_miles,
        "progress_pct": progress,
    }


def _casino_max_bet(hardware_id: str) -> int:
    if pg_has_module(_hid64(hardware_id), "mod_casino"):
        return 250_000
    return 50_000


def fetch_pax_radar_pg(hardware_id: str, *, limit: int = 24) -> dict[str, Any]:
    """Optional: Pax-Feedback-Zeilen aus PostgreSQL (Radar-Ergänzung)."""
    hid = _hid64(hardware_id)
    out: dict[str, Any] = {"comments": [], "avg_stars": 0.0}
    if not hid:
        return out
    try:
        from skytycoon_pg import pg_fetchall

        conn = _pg_conn()
        try:
            rows = pg_fetchall(
                conn,
                """
                SELECT stars, multiplier, comment_text
                FROM pax_feedback
                WHERE hardware_id = %s
                ORDER BY created_ts DESC NULLS LAST
                LIMIT %s;
                """,
                (hid, int(limit)),
            )
            comments = []
            stars_sum = 0.0
            n = 0
            for r in rows or []:
                st = int(r.get("stars") or 5)
                mult = float(r.get("multiplier") or 1.0)
                txt = str(r.get("comment_text") or r.get("comment") or "").strip()
                comments.append({"stars": st, "multiplier": mult, "comment": txt})
                stars_sum += st
                n += 1
            out["comments"] = comments
            out["avg_stars"] = (stars_sum / n) if n else 0.0
        finally:
            conn.close()
    except Exception:
        pass
    return out
