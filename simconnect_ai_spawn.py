"""MSFS SimConnect AICreateNonATCAircraft via ctypes (optional native spawn)."""
from __future__ import annotations

import ctypes
import math
from ctypes import POINTER, Structure, byref, c_char, c_double, c_uint32, c_void_p


class SIMCONNECT_DATA_INITPOSITION(Structure):
    _fields_ = [
        ("Latitude", c_double),
        ("Longitude", c_double),
        ("Altitude", c_double),
        ("Pitch", c_double),
        ("Bank", c_double),
        ("Heading", c_double),
        ("OnGround", c_uint32),
        ("Airspeed", c_uint32),
    ]


def _simconnect_dll(sm: object) -> ctypes.CDLL | None:
    for attr in ("_h", "hSimConnect", "handle", "simconnect_handle"):
        h = getattr(sm, attr, None)
        if h is not None:
            try:
                return ctypes.CDLL("SimConnect.dll")
            except OSError:
                pass
    try:
        return ctypes.CDLL("SimConnect.dll")
    except OSError:
        return None


def _extract_handle(sm: object) -> int | None:
    for attr in ("_h", "hSimConnect", "handle", "simconnect_handle", "dwHandle"):
        v = getattr(sm, attr, None)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return None


def ai_create_non_atc_aircraft(
    sm: object,
    container_title: str,
    tail_number: str,
    lat: float,
    lon: float,
    alt_ft: float,
    heading_deg: float = 0.0,
    on_ground: bool = True,
) -> bool:
    """
  Versucht ``AICreateNonATCAircraft`` (MSFS SimConnect SDK).
  Gibt True zurück, wenn der Aufruf ohne Exception durchlief.
    """
    if sm is None:
        return False
  # 1) Python-SimConnect-Wrapper-Methoden
    for name in (
        "AICreateNonATCAircraft",
        "ai_create_non_atc_aircraft",
        "create_ai_non_atc_aircraft",
    ):
        fn = getattr(sm, name, None)
        if callable(fn):
            try:
                fn(
                    container_title,
                    tail_number,
                    float(lat),
                    float(lon),
                    float(alt_ft),
                    float(heading_deg),
                    bool(on_ground),
                )
                return True
            except TypeError:
                try:
                    fn(container_title, tail_number, lat, lon, alt_ft)
                    return True
                except Exception:
                    pass
            except Exception:
                pass
    dll = _simconnect_dll(sm)
    h = _extract_handle(sm)
    if dll is None or h is None:
        return False
    try:
        create_fn = dll.SimConnect_AICreateNonATCAircraft
    except AttributeError:
        return False
    create_fn.argtypes = [
        c_void_p,
        c_char * 256,
        c_char * 32,
        c_uint32,
        POINTER(SIMCONNECT_DATA_INITPOSITION),
        c_uint32,
        c_uint32,
    ]
    create_fn.restype = ctypes.c_long
    pos = SIMCONNECT_DATA_INITPOSITION(
        float(lat),
        float(lon),
        float(alt_ft),
        0.0,
        0.0,
        float(heading_deg) % 360.0,
        1 if on_ground else 0,
        0,
    )
    ct = (container_title or "Airbus A320")[:255].encode("ascii", errors="replace")
    tn = (tail_number or "AI01")[:31].encode("ascii", errors="replace")
    buf_ct = ctypes.create_string_buffer(ct, 256)
    buf_tn = ctypes.create_string_buffer(tn, 32)
    try:
        hr = int(
            create_fn(
                c_void_p(h),
                buf_ct,
                buf_tn,
                0,
                byref(pos),
                0,
                0,
            )
        )
        return hr == 0
    except Exception:
        return False
