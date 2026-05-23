# -*- coding: utf-8 -*-
"""
Meilenstein 216 — 14-Säulen-Wirtschaftsimperium (Erweiterung).
Registriert Webseiten + APIs am FastAPI-App-Objekt ohne bestehenden Code zu löschen.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette import status as http_status

# Lazy import von server_backend nach App-Start (vermeidet Zirkel beim Modul-Load).
_SB_MODULE: Any = None


def _get_sb():
    global _SB_MODULE
    if _SB_MODULE is None:
        import server_backend as sb_mod

        _SB_MODULE = sb_mod
    return _SB_MODULE


M216_MODULE_CATALOG: dict[str, dict[str, Any]] = {
    "mod_jobs": {"id": 2, "credits": 12500, "path": "/market/jobs", "de": "Live-Flugbörse", "en": "Live job board"},
    "mod_alliance": {"id": 3, "credits": 15000, "path": "/alliance/hub", "de": "Allianz-Zentrale", "en": "Alliance hub"},
    "mod_hangar": {"id": 4, "credits": 11000, "path": "/fleet/hangar", "de": "Web-Hangar", "en": "Web hangar"},
    "mod_dispatcher": {"id": 5, "credits": 9000, "path": "/flight/dispatcher", "de": "Live-Boarding", "en": "Live boarding"},
    "mod_banking": {"id": 6, "credits": 14000, "path": "/bank/loans", "de": "P2P-Banking", "en": "P2P banking"},
    "mod_auctions": {"id": 7, "credits": 13000, "path": "/werft/auctions", "de": "Gebrauchtwerft", "en": "Used aircraft yard"},
    "mod_dispatch": {"id": 8, "credits": 16000, "path": "/market/dispatch", "de": "SimBrief-Zentrale", "en": "SimBrief center"},
    "mod_radar": {"id": 9, "credits": 8000, "path": "/market/radar", "de": "Live-Radar", "en": "Live radar"},
    "mod_license_shop": {"id": 10, "credits": 0, "path": "/market/license_shop", "de": "Credit-Marktplatz", "en": "Credit marketplace"},
    "mod_properties": {"id": 11, "credits": 22000, "path": "/market/properties", "de": "HQ & Immobilien", "en": "HQ & properties"},
    "mod_academy": {"id": 12, "credits": 10500, "path": "/market/academy", "de": "Crew-Training", "en": "Crew training"},
    "mod_weather": {"id": 13, "credits": 7500, "path": "/market/weather", "de": "Premium-Wetter", "en": "Premium weather"},
    "mod_msfs": {"id": 14, "credits": 25000, "path": "/market/msfs_link", "de": "SimConnect-Pipeline", "en": "SimConnect pipeline"},
}

M216_SHOP_MODULES = (
    "mod_jobs",
    "mod_alliance",
    "mod_hangar",
    "mod_dispatcher",
    "mod_banking",
    "mod_auctions",
    "mod_dispatch",
    "mod_radar",
    "mod_properties",
    "mod_academy",
    "mod_weather",
    "mod_msfs",
)


def _m216_lang(request: Request) -> str:
    return _get_sb()._web_lang(request)


def _m216_hid(request: Request) -> str:
    bridge = _get_sb()._desktop_bridge_hid_from_request(request)
    if bridge:
        return bridge
    return str(_get_sb()._web_session_hardware_id(request) or "").strip()[:64]


def _m216_require_web_session(request: Request) -> str:
    hid = _m216_hid(request)
    if not hid:
        raise HTTPException(status_code=401, detail="login_required")
    return hid


def _m216_addon_active(hid: str, module_key: str) -> bool:
    if module_key == "mod_license_shop":
        return True
    if module_key in ("mod_weather", "mod_radar") and hid:
        return True
    conn = sqlite3.connect(str(_get_sb().SERVER_DB_PATH))
    try:
        row = conn.execute(
            """
            SELECT active FROM pilot_addon_modules
            WHERE hardware_id = ? AND module_key = ? AND active = 1;
            """,
            (hid[:64], module_key),
        ).fetchone()
        return bool(row and int(row[0]) == 1)
    finally:
        conn.close()


def _m216_user_credits(hid: str) -> float:
    conn = sqlite3.connect(str(_get_sb().USER_DB_PATH))
    try:
        row = conn.execute(
            "SELECT credits FROM users WHERE hardware_id = ?;", (hid[:64],)
        ).fetchone()
        return float(row[0] or 0) if row else 0.0
    finally:
        conn.close()


def _m216_page(
    request: Request, template: str, *, require_module: str | None = None, **ctx: Any
):
    hid = _m216_hid(request)
    if not hid:
        return RedirectResponse("/login", status_code=http_status.HTTP_303_SEE_OTHER)
    if require_module and not _m216_addon_active(hid, require_module):
        return RedirectResponse(
            "/market/license_shop", status_code=http_status.HTTP_303_SEE_OTHER
        )
    ctx.setdefault("pilot_credits", _m216_user_credits(hid))
    ctx.setdefault("module_unlocked", _m216_list_unlocked(hid))
    return _get_sb()._web_page_html(template, request, **ctx)


def build_shop_catalog(hid: str, lang: str) -> list[dict[str, Any]]:
    """Modul-Liste für Credit-Shop und Dashboard (alle freischaltbaren Module)."""
    catalog: list[dict[str, Any]] = []
    for key in M216_SHOP_MODULES:
        meta = dict(M216_MODULE_CATALOG[key])
        meta["key"] = key
        meta["title"] = meta["de"] if lang == "de" else meta["en"]
        meta["owned"] = _m216_addon_active(hid, key)
        catalog.append(meta)
    return catalog


def _m216_list_unlocked(hid: str) -> list[str]:
    conn = sqlite3.connect(str(_get_sb().SERVER_DB_PATH))
    try:
        cur = conn.execute(
            """
            SELECT module_key FROM pilot_addon_modules
            WHERE hardware_id = ? AND active = 1;
            """,
            (hid[:64],),
        )
        return [str(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()


def _m216_admin_password_ok(pw: str) -> bool:
    expected = (
        os.environ.get("SKYTYCOON_ADMIN_COMMANDER_PASSWORD")
        or os.environ.get("ADMIN_COMMANDER_PASSWORD")
        or ""
    ).strip()
    if not expected:
        return False
    return (pw or "").strip() == expected


def register(app: Any) -> None:
    """Alle M216-Routen an die bestehende FastAPI-App hängen."""

    @app.get("/market/license_shop", response_class=HTMLResponse, response_model=None)
    async def m216_license_shop(request: Request):
        hid = _m216_hid(request)
        if not hid:
            return RedirectResponse("/login", status_code=http_status.HTTP_303_SEE_OTHER)
        lang = _m216_lang(request)
        catalog = build_shop_catalog(hid, lang)
        return _get_sb()._web_page_html(
            "market/license_shop.html",
            request,
            catalog=catalog,
            pilot_credits=_m216_user_credits(hid),
            module_unlocked=_m216_list_unlocked(hid),
        )

    @app.post("/api/v1/licenses/buy")
    async def m216_licenses_buy(
        request: Request, body: dict[str, Any] = Body(default_factory=dict)
    ) -> JSONResponse:
        hid = _m216_require_web_session(request)
        module_key = str(body.get("module_key") or "").strip()
        meta = M216_MODULE_CATALOG.get(module_key)
        if not meta or module_key not in M216_SHOP_MODULES:
            return JSONResponse(
                {"status": "error", "message": "unknown_module"}, status_code=400
            )
        if _m216_addon_active(hid, module_key):
            return JSONResponse(
                {"status": "success", "message": "already_owned", "module_key": module_key}
            )
        cost = float(meta.get("credits") or 0)
        uconn = sqlite3.connect(str(_get_sb().USER_DB_PATH))
        sconn = sqlite3.connect(str(_get_sb().SERVER_DB_PATH))
        try:
            uconn.execute("BEGIN IMMEDIATE")
            sconn.execute("BEGIN IMMEDIATE")
            row = uconn.execute(
                "SELECT credits FROM users WHERE hardware_id = ?;", (hid,)
            ).fetchone()
            bal = float(row[0] or 0) if row else 0.0
            if bal < cost:
                uconn.rollback()
                sconn.rollback()
                return JSONResponse(
                    {"status": "error", "message": "insufficient_credits"},
                    status_code=400,
                )
            uconn.execute(
                "UPDATE users SET credits = credits - ? WHERE hardware_id = ?;",
                (cost, hid),
            )
            sconn.execute(
                """
                INSERT INTO pilot_addon_modules (
                    hardware_id, module_key, active, credits_spent, unlocked_at
                ) VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(hardware_id, module_key) DO UPDATE SET
                    active = 1,
                    credits_spent = excluded.credits_spent,
                    unlocked_at = excluded.unlocked_at;
                """,
                (
                    hid,
                    module_key,
                    cost,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            uconn.commit()
            sconn.commit()
            title = meta.get("de") or module_key
            _get_sb()._append_server_live_ticker(
                f"🛒 {title} per Credits freigeschaltet (Pilot {_get_sb()._pilot_display_name_for_hid(hid)[:24]})"
            )
        except sqlite3.Error as exc:
            uconn.rollback()
            sconn.rollback()
            return JSONResponse(
                {"status": "error", "message": str(exc)}, status_code=500
            )
        finally:
            uconn.close()
            sconn.close()
        return JSONResponse(
            {
                "status": "success",
                "module_key": module_key,
                "credits_remaining": _m216_user_credits(hid),
            }
        )

    @app.get("/admin/commander/licenses", response_class=HTMLResponse, response_model=None)
    async def m216_admin_commander_licenses(request: Request):
        return _get_sb()._web_page_html("admin/commander_licenses.html", request)

    @app.post("/api/v1/admin/commander/licenses/grant")
    async def m216_admin_grant_license(
        request: Request, body: dict[str, Any] = Body(default_factory=dict)
    ) -> JSONResponse:
        if not _m216_admin_password_ok(str(body.get("admin_password") or "")):
            return JSONResponse({"status": "error", "message": "auth_failed"}, status_code=403)
        hid = str(body.get("hardware_id") or "").strip()[:64]
        module_key = str(body.get("module_key") or "").strip()
        if not hid or module_key not in M216_MODULE_CATALOG:
            return JSONResponse({"status": "error", "message": "invalid_payload"}, status_code=400)
        conn = sqlite3.connect(str(_get_sb().SERVER_DB_PATH))
        try:
            conn.execute(
                """
                INSERT INTO pilot_addon_modules (
                    hardware_id, module_key, active, credits_spent, unlocked_at
                ) VALUES (?, ?, 1, 0, ?)
                ON CONFLICT(hardware_id, module_key) DO UPDATE SET active = 1;
                """,
                (hid, module_key, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return JSONResponse({"status": "success", "hardware_id": hid, "module_key": module_key})

    @app.get("/market/jobs", response_class=HTMLResponse, response_model=None)
    async def m216_jobs(request: Request):
        return _m216_page(request, "market/jobs.html", require_module="mod_jobs")

    @app.get("/alliance/hub", response_class=HTMLResponse, response_model=None)
    async def m216_alliance_hub(request: Request):
        return _m216_page(request, "alliance/hub.html", require_module="mod_alliance")

    @app.get("/fleet/hangar", response_class=HTMLResponse, response_model=None)
    async def m216_hangar(request: Request):
        return _m216_page(request, "fleet/hangar.html", require_module="mod_hangar")

    @app.get("/flight/dispatcher", response_class=HTMLResponse, response_model=None)
    async def m216_dispatcher(request: Request):
        return _m216_page(request, "flight/dispatcher.html", require_module="mod_dispatcher")

    @app.get("/bank/loans", response_class=HTMLResponse, response_model=None)
    async def m216_loans(request: Request):
        return _m216_page(request, "bank/loans.html", require_module="mod_banking")

    @app.get("/werft/auctions", response_class=HTMLResponse, response_model=None)
    async def m216_auctions(request: Request):
        return _m216_page(request, "werft/auctions.html", require_module="mod_auctions")

    @app.get("/market/dispatch", response_class=HTMLResponse, response_model=None)
    async def m216_dispatch(request: Request):
        return _m216_page(request, "market/dispatch.html", require_module="mod_dispatch")

    @app.get("/market/radar", response_class=HTMLResponse, response_model=None)
    async def m216_market_radar(request: Request):
        return _m216_page(request, "market/radar.html", require_module="mod_radar")

    @app.get("/market/properties", response_class=HTMLResponse, response_model=None)
    async def m216_properties(request: Request):
        return _m216_page(request, "market/properties.html", require_module="mod_properties")

    @app.get("/market/academy", response_class=HTMLResponse, response_model=None)
    async def m216_academy(request: Request):
        return _m216_page(request, "market/academy.html", require_module="mod_academy")

    @app.get("/market/weather", response_class=HTMLResponse, response_model=None)
    async def m216_weather(request: Request):
        return _m216_page(request, "market/weather.html", require_module="mod_weather")

    @app.get("/player/weather", response_class=HTMLResponse, response_model=None)
    async def m216_player_weather(request: Request):
        return _m216_page(request, "market/weather.html", require_module="mod_weather")

    @app.get("/player/radar", response_class=HTMLResponse, response_model=None)
    async def m216_player_radar(request: Request):
        return _m216_page(request, "market/radar.html", require_module="mod_radar")

    @app.get("/market/msfs_link", response_class=HTMLResponse, response_model=None)
    async def m216_msfs_link(request: Request):
        return _m216_page(request, "market/msfs_link.html", require_module="mod_msfs")

    @app.get("/api/v1/radar/live")
    def m216_radar_live_alias() -> JSONResponse:
        return _get_sb().web_radar_positions()

    @app.post("/api/v1/hangar/repair")
    async def m216_hangar_repair(
        request: Request, body: dict[str, Any] = Body(default_factory=dict)
    ) -> JSONResponse:
        hid = _m216_require_web_session(request)
        if not _m216_addon_active(hid, "mod_hangar"):
            return JSONResponse({"status": "error", "message": "module_locked"}, status_code=403)
        try:
            cost = float(body.get("cost_credits") or body.get("cost") or 2500)
            health_after = float(body.get("health_after") or body.get("health") or 100)
        except (TypeError, ValueError):
            return JSONResponse({"status": "error", "message": "bad_payload"}, status_code=400)
        cost = max(100.0, min(cost, 500000.0))
        health_after = max(0.0, min(health_after, 100.0))
        uconn = sqlite3.connect(str(_get_sb().USER_DB_PATH))
        try:
            uconn.execute("BEGIN IMMEDIATE")
            row = uconn.execute(
                "SELECT credits FROM users WHERE hardware_id = ?;", (hid,)
            ).fetchone()
            bal = float(row[0] or 0) if row else 0.0
            if bal < cost:
                uconn.rollback()
                return JSONResponse(
                    {"status": "error", "message": "insufficient_credits"}, status_code=400
                )
            uconn.execute(
                "UPDATE users SET credits = credits - ? WHERE hardware_id = ?;",
                (cost, hid),
            )
            uconn.commit()
        finally:
            uconn.close()
        _get_sb()._append_server_live_ticker(
            f"🔧 Hangar-Reparatur abgeschlossen ({int(health_after)}%) — "
            f"{_get_sb()._pilot_display_name_for_hid(hid)[:24]}"
        )
        return JSONResponse(
            {
                "status": "success",
                "credits_spent": cost,
                "health_after": health_after,
                "credits_remaining": _m216_user_credits(hid),
            }
        )
