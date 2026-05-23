# -*- coding: utf-8 -*-
"""GSX Auto-Cabin: asynchrones Menü → Catering → Boarding (SimConnect), ohne GUI-Block."""

from __future__ import annotations

import threading
import time
from typing import Any

_GSX_MENU_EVENTS: tuple[str, ...] = (
    "FSDT_GSX_MENU_OPEN",
    "K:FSDT_GSX_MENU_OPEN",
    "GSX_MENU_OPEN",
)
_GSX_CATERING: tuple[str, ...] = (
    "FSDT_GSX_CATERING_REQUEST",
    "FSDT_GSX_REQUEST_CATERING",
    "GSX_CATERING_REQUEST",
)
_GSX_BOARDING: tuple[str, ...] = (
    "FSDT_GSX_BOARDING_REQUEST",
    "FSDT_GSX_REQUEST_BOARDING",
    "GSX_BOARDING_REQUEST",
)

_last_chain_ts = 0.0
_chain_lock = threading.Lock()
_CHAIN_COOLDOWN_S = 50.0


def _send_simconnect_event(sm: Any, event_name: str, data: int = 1) -> bool:
    if sm is None:
        return False
    for cand in (event_name, event_name.upper(), f"K:{event_name}"):
        try:
            ev = sm.map_to_sim_event(cand.encode("ascii"))
        except (AttributeError, UnicodeEncodeError, TypeError, ValueError):
            ev = None
        if ev is None:
            continue
        try:
            if sm.send_event(ev, data):
                return True
        except (AttributeError, TypeError, ValueError):
            pass
    return False


def _set_lvar(aq: Any, name: str, value: float) -> None:
    if aq is None:
        return
    try:
        aq.set(name, float(value))
    except Exception:
        pass


def _run_gsx_chain(win: Any) -> None:
    sm = getattr(win, "_sm", None)
    aq = getattr(win, "_aq", None)
    for ev in _GSX_MENU_EVENTS:
        if _send_simconnect_event(sm, ev, 1):
            break
    _set_lvar(aq, "L:FSDT_GSX_MENU_OPEN", 1.0)
    time.sleep(0.45)
    for ev in _GSX_CATERING:
        if _send_simconnect_event(sm, ev, 1):
            break
    _set_lvar(aq, "L:FSDT_GSX_CATERING_REQUEST", 1.0)
    time.sleep(0.55)
    for ev in _GSX_BOARDING:
        if _send_simconnect_event(sm, ev, 1):
            break
    _set_lvar(aq, "L:FSDT_GSX_BOARDING_REQUEST", 1.0)
    play = getattr(win, "_play_cabin_soundboard_announcement", None)
    if callable(play):
        try:
            play("welcome_boarding")
        except Exception:
            pass


def trigger_gsx_menu_catering_boarding_async(win: Any) -> None:
    global _last_chain_ts
    with _chain_lock:
        now = time.time()
        if now - _last_chain_ts < _CHAIN_COOLDOWN_S:
            return
        _last_chain_ts = now
    threading.Thread(
        target=_run_gsx_chain,
        args=(win,),
        name="skytycoon-gsx-auto-cabin",
        daemon=True,
    ).start()


def tick_auto_cabin_audio(win: Any) -> None:
    """
    Aus main.py Sim-Poll (~21901): bei GSX-Boarding State 4 einmalig Kette starten.
    Kein pygame — nur SimConnect + optional Platin-QSoundEffect-Ansage.
    """
    stb = getattr(win, "_gsx_boarding_state", None)
    if stb != 4:
        return
    job = getattr(win, "_active_job", None)
    if not job or str(job.get("typ") or "") != "PAX":
        return
    if getattr(win, "_sky_auto_cabin_chain_armed", False):
        return
    win._sky_auto_cabin_chain_armed = True
    trigger_gsx_menu_catering_boarding_async(win)
    if stb not in (4, 6):
        win._sky_auto_cabin_chain_armed = False
