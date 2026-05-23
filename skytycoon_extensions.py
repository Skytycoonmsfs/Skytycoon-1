# -*- coding: utf-8 -*-
"""
SkyTycoon Pro — Platin-Injektion (modular, ohne Layout in main.py).

RAM-Cache + Hintergrund-Refresh alle 60s — kein API/psutil bei Tab-Wechsel.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import QEvent, QObject, QRunnable, QThreadPool, QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from skytycoon_theme import (
    MONO_TILE_STYLE,
    SKY_DARK_SCROLL_CSS,
    SKYTYCOON_UNIFIED_DARK_STYLE,
)

_PLATIN_GOLD_STYLE = SKYTYCOON_UNIFIED_DARK_STYLE
_PLATIN_GLOBAL_DARK_STYLE = SKYTYCOON_UNIFIED_DARK_STYLE

PLATIN_EXTENSIONS_FILE = Path(__file__).resolve()
PLATIN_PROJECT_ROOT = PLATIN_EXTENSIONS_FILE.parent
PLATIN_CYBER_COLORS = {
    "bg": "#0b0f19",
    "neon": "#00a2ff",
    "ice": "#8ac7ff",
}


def platin_project_root() -> Path:
    """Projektordner auf jedem PC — kein festes Laufwerk A:\\."""
    env = (os.environ.get("SKYTYCOON_PROJECT_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    return PLATIN_PROJECT_ROOT


def platin_swiss_backup_root() -> Path:
    """2h-ZIP auf dem Laufwerk des aktiven Entwickler-Projektordners."""
    env = (os.environ.get("SKYTYCOON_SWISS_BACKUP_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    root = platin_project_root()
    drive = root.drive or ""
    if drive:
        dest = Path(f"{drive}{os.sep}SkyTycoon_Backups")
    else:
        dest = root / "SkyTycoon_Backups"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        return dest
    except OSError:
        fallback = root / "_dev_backups"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _platin_bind_dynamic_project_roots(main_mod: Any) -> None:
    root = platin_project_root()
    bak = platin_swiss_backup_root()
    os.environ["SKYTYCOON_PROJECT_ROOT"] = str(root)
    os.environ["SKYTYCOON_SWISS_BACKUP_ROOT"] = str(bak)
    for mod in _runtime_main_modules():
        try:
            mod.BASE_DIR = root
        except Exception:
            pass
    try:
        main_mod.BASE_DIR = root
    except Exception:
        pass


def _platin_run_swiss_backup_zip() -> tuple[bool, str]:
    import admin_vault_core as avc

    proj = platin_project_root()
    bak = platin_swiss_backup_root()
    old_p, old_s = avc.PROJECT_ROOT_DEFAULT, avc.SWISS_BACKUP_ROOT
    avc.PROJECT_ROOT_DEFAULT = proj
    avc.SWISS_BACKUP_ROOT = bak
    try:
        return avc.run_swiss_sync_to_backup_root(proj)
    finally:
        avc.PROJECT_ROOT_DEFAULT = old_p
        avc.SWISS_BACKUP_ROOT = old_s

def _patch_simconnect_telemetry_regulation(main_mod: Any) -> None:
    """
    SimConnect: Hintergrund-Poll + GUI-Apply nur alle 2s — kein Label-/Phase-Flackern.
    """
    win_cls = getattr(main_mod, "MainWindow", None)
    th_cls = getattr(main_mod, "_SimConnectPollThread", None)
    if win_cls is None or getattr(win_cls, "_sky_sim_telemetry_patch", False):
        return
    poll_names = getattr(main_mod, "SIM_POLL_VAR_NAMES", ())
    if th_cls is not None and poll_names:

        def _run_sim_poll_slow(self: Any) -> None:
            while self._running:
                if self._aq is None:
                    break
                snap: dict[str, object] = {}
                try:
                    for name in poll_names:
                        snap[name] = self._aq.get(name)
                    self.snapshot_ready.emit(snap)
                except Exception as exc:
                    self.poll_error.emit(exc)
                self.msleep(SIMCONNECT_TELEMETRY_MS)

        th_cls.run = _run_sim_poll_slow

    orig_apply = win_cls._apply_sim_poll_snapshot

    def _apply_sim_poll_snapshot_throttled(self: Any) -> None:
        now = time.monotonic()
        last = float(getattr(self, "_platin_sim_gui_apply_mono", 0.0) or 0.0)
        if now - last < (SIMCONNECT_TELEMETRY_MS / 1000.0) - 0.02:
            return
        self._platin_sim_gui_apply_mono = now
        prev_title = str(getattr(self, "_platin_snap_title_key", "") or "")
        prev_phase = str(getattr(self, "_platin_snap_phase_key", "") or "")
        orig_apply(self)
        title_key = str(getattr(self, "_last_title", "") or "").strip()[:120]
        phase_key = str(
            getattr(getattr(self, "_phase", None), "value", "") or ""
        ).strip()
        lbl_ac = getattr(self, "label_aircraft", None)
        lbl_ph = getattr(self, "label_phase", None)
        if title_key == prev_title and lbl_ac is not None:
            stable_ac = getattr(self, "_platin_stable_ac_lbl", None)
            if stable_ac:
                try:
                    lbl_ac.setText(stable_ac)
                except RuntimeError:
                    pass
        elif lbl_ac is not None:
            try:
                self._platin_stable_ac_lbl = lbl_ac.text()
            except RuntimeError:
                pass
            self._platin_snap_title_key = title_key
        if phase_key == prev_phase and lbl_ph is not None:
            stable_ph = getattr(self, "_platin_stable_phase_lbl", None)
            if stable_ph:
                try:
                    lbl_ph.setText(stable_ph)
                except RuntimeError:
                    pass
        elif lbl_ph is not None:
            try:
                self._platin_stable_phase_lbl = lbl_ph.text()
            except RuntimeError:
                pass
            self._platin_snap_phase_key = phase_key

    win_cls._apply_sim_poll_snapshot = _apply_sim_poll_snapshot_throttled
    win_cls._sky_sim_telemetry_patch = True

GSX_TRIGGER_LVARS = {
    "catering": "L:FSDT_GSX_CATERING_REQUEST",
    "boarding": "L:FSDT_GSX_BOARDING_REQUEST",
    "deboarding": "L:FSDT_GSX_DEBOARDING_REQUEST",
    "refuel": "L:FSDT_GSX_REFUEL_REQUEST",
}
GSX_MENU_OPEN_SIM_EVENTS = (
    "FSDT_GSX_MENU_OPEN",
    "K:FSDT_GSX_MENU_OPEN",
    "GSX_MENU_OPEN",
)
GSX_START_HANDLING_SIM_EVENTS = (
    "FSDT_GSX_START",
    "FSDT_GSX_REQUEST",
    "GSX_START",
    "FSDT_GSX_OPEN_MENU",
)
GSX_NATIVE_SIM_EVENTS: dict[str, tuple[str, ...]] = {
    "catering": (
        "FSDT_GSX_CATERING_REQUEST",
        "FSDT_GSX_REQUEST_CATERING",
        "GSX_CATERING_REQUEST",
    ),
    "boarding": (
        "FSDT_GSX_BOARDING_REQUEST",
        "FSDT_GSX_REQUEST_BOARDING",
        "GSX_BOARDING_REQUEST",
    ),
    "deboarding": (
        "FSDT_GSX_DEBOARDING_REQUEST",
        "FSDT_GSX_REQUEST_DEBOARDING",
        "GSX_DEBOARDING_REQUEST",
    ),
    "refuel": (
        "FSDT_GSX_REFUEL_REQUEST",
        "FSDT_GSX_REQUEST_REFUEL",
        "GSX_REFUEL_REQUEST",
    ),
}
LOGOUT_META_KEYS = (
    "ionos_jwt",
    "license_activated",
    "license_key_installed",
    "pilot_display_name",
    "pilot_name",
    "portal_email",
    "cloud_password",
    "cloud_sync_password",
    "cloud_ever_synced_ok",
    "cloud_last_sync_ts",
    "drm_last_status",
    "drm_last_ok_ts",
    "platin_superadmin",
    "online_network_enabled",
)
GSX_POLL_LVARS = (
    "L:FSDT_GSX_BOARDING_STATE",
    "L:FSDT_GSX_NUM_PASSENGERS_BOARDED",
    "L:FSDT_GSX_BOARDING_PROGRESS",
)
GSX_POLL_MS = 3000
SIMCONNECT_TELEMETRY_MS = 2000
PLATIN_CABIN_DEFAULT_VOL = 75
PLATIN_MIN_REAL_AUDIO_BYTES = 45_000
PLATIN_BUILD = "20260526-online-login-v27"
PLATIN_HAUL_NM_THRESHOLD = 1500.0
_PLATIN_SPLASH_UPDATE_ONCE = True
_PLATIN_PREMAIN_AUTH_OK = False
# Kaltstart: keine Update-/Lizenz-Pop-ups bis Login erfolgreich (main.py unverändert).
_PLATIN_BLOCK_STARTUP_POPUPS = True
LOCAL_SESSION_FILENAME = "local_session.json"
LOCAL_SESSION_VERSION = 3
LOCAL_SESSION_MAX_AGE_SEC = 60 * 60 * 24 * 90
CABIN_CDN_BASES: tuple[str, ...] = (
    "https://skytycoon.info/static/cabin_sounds/",
    "https://skytycoon.info/assets/sounds/",
    "https://skytycoon.info/static/sounds/",
)
_HUB_TAB_IX_ATTRS: tuple[str, ...] = (
    "_hub_ix_career",
    "_hub_ix_alliance",
    "_hub_ix_dispatch",
    "_hub_ix_hangar",
    "_hub_ix_cabin",
    "_hub_ix_bank",
)
RADAR_HEARTBEAT_MS = 5000
_RADAR_DEFAULT_LAT = 50.0379
_RADAR_DEFAULT_LON = 8.5622
_CLOUD_API_FALLBACK = "https://skytycoon.info"
_CLOUD_API_FALLBACK_IP = "https://217.154.16.248"
GLOBAL_SUPERADMIN_EMAIL = "info@skytycoon.info"


def _is_local_api_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return (
        not u
        or "127.0.0.1" in u
        or "localhost" in u
        or u.startswith("http://0.0.0.0")
    )


def _resolve_production_api_base(main_mod: Any, db_path: Path) -> str:
    """Niemals localhost — immer skytycoon.info / IONOS-IP."""
    candidates: list[str] = []
    for key in ("SKYTYCOON_IONOS_SERVER_URL", "SKYTYCOON_IONOS_API_BASE"):
        candidates.append((os.environ.get(key) or "").strip())
    for meta_key in (
        "ionos_server_url",
        "ionos_api_base",
        "skytycoon_server_url",
        "SKYTYCOON_IONOS_SERVER_URL",
    ):
        try:
            candidates.append(str(main_mod.app_meta_get(db_path, meta_key, "") or "").strip())
        except Exception:
            pass
    try:
        cfg_path = Path(getattr(main_mod, "APP_ROOT", Path(db_path).parent)) / "config.json"
        if cfg_path.is_file():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                for ck in (
                    "ionos_server_url",
                    "ionos_api_base",
                    "server_url",
                    "api_base",
                ):
                    candidates.append(str(cfg.get(ck) or "").strip())
    except Exception:
        pass
    for raw in candidates:
        if raw and not _is_local_api_url(raw):
            return raw.rstrip("/")
    return _CLOUD_API_FALLBACK


def _simconnect_coord_float(v: object) -> float | None:
    """SimConnect PLANE LATITUDE/LONGITUDE als volles double (kein Integer-Cut)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (bytes, bytearray, memoryview)):
        try:
            import struct

            if len(v) >= 8:
                return struct.unpack("<d", v[:8])[0]
            if len(v) >= 4:
                return struct.unpack("<f", v[:4])[0]
        except (struct.error, TypeError, ValueError):
            return None
    if isinstance(v, (tuple, list)) and v:
        v = v[0]
    if hasattr(v, "value"):
        try:
            v = v.value
        except Exception:
            pass
    try:
        x = float(v)
    except (TypeError, ValueError):
        try:
            s = str(v).strip().replace(",", ".")
            if not s or s.lower() in ("nan", "none", "null", "-", "–"):
                return None
            x = float(s)
        except (TypeError, ValueError):
            return None
    if x != x:  # NaN
        return None
    if abs(x) > 1e8:
        return None
    if abs(x) > 90 and abs(x) <= 90000000:
        x = x / 1_000_000.0
    elif abs(x) > 180 and abs(x) <= 180000000:
        x = x / 1_000_000.0
    return float(x)


def _gps_coords_plausible(lat: float, lon: float) -> bool:
    """Nullpunkt/Afrika-Fehler vermeiden — nur echte SimConnect-GPS."""
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    if abs(lat) < 0.02 and abs(lon) < 0.02:
        return False
    return True


def _simconnect_latitude_longitude(win: Any) -> tuple[float | None, float | None]:
    """
    MSFS: PLANE LATITUDE = Breitengrad, PLANE LONGITUDE = Längengrad (niemals vertauscht).
    """
    latitude = _simconnect_coord_float(
        _read_sim_snapshot_field(win, "PLANE LATITUDE")
    )
    longitude = _simconnect_coord_float(
        _read_sim_snapshot_field(win, "PLANE LONGITUDE")
    )
    if latitude is None or longitude is None:
        return latitude, longitude
    lat_f = float(latitude)
    lon_f = float(longitude)
    # Heuristik EU/MSFS: vertauschte Achsen (z. B. lat≈8, lon≈50 statt lat≈50, lon≈8)
    if (
        abs(lat_f) < 25.0
        and abs(lon_f) > 28.0
        and abs(lon_f) <= 75.0
        and abs(lat_f) < abs(lon_f)
    ):
        lat_f, lon_f = lon_f, lat_f
    if not _gps_coords_plausible(lat_f, lon_f):
        return None, None
    return lat_f, lon_f


def _json_coord_number(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 7)


_AIRCRAFT_TITLE_ICAO_RULES: tuple[tuple[str, str], ...] = (
    (r"737[-\s]?8\d{2}|B738|737-800", "B738"),
    (r"737[-\s]?7\d{2}|B737", "B737"),
    (r"737[-\s]?9\d{2}|B739", "B739"),
    (r"777[-\s]?3\d{2}|B77W|777-300", "B77W"),
    (r"787[-\s]?9|B789", "B789"),
    (r"787[-\s]?8|B788", "B788"),
    (r"A320NEO|A20N|A320-2\d{3}N", "A20N"),
    (r"A321NEO|A21N", "A21N"),
    (r"A319|A319", "A319"),
    (r"A320|A320", "A320"),
    (r"A321|A321", "A321"),
    (r"A330-300|A333", "A333"),
    (r"A350-900|A359", "A359"),
    (r"A380", "A388"),
    (r"E175|E170", "E175"),
    (r"E190|E195", "E190"),
    (r"CRJ.?7|CRJ7", "CRJ7"),
    (r"DA62", "DA62"),
    (r"C172|Cessna 172", "C172"),
    (r"C208|Caravan", "C208"),
    (r"SF50|Vision Jet", "SF50"),
    (r"FENIX.*A320|A320.*FENIX", "A320"),
    (r"PMDG.*737", "B738"),
    (r"PMDG.*777", "B77W"),
    (r"FBW.*A32", "A320"),
    (r"ATR.?72", "AT72"),
    (r"DASH.?8|Q400", "DH8D"),
)


def _simconnect_title_to_icao(title: str, atc_model: str = "", atc_type: str = "") -> str:
    blob = " ".join(
        x for x in (title or "", atc_type or "", atc_model or "") if str(x).strip()
    ).upper()
    if not blob or blob in ("–", "-", "NONE"):
        return ""
    for pat, icao in _AIRCRAFT_TITLE_ICAO_RULES:
        if re.search(pat, blob, re.IGNORECASE):
            return icao
    m = re.search(r"\b([AB][0-9]{2,3}[A-Z]?)\b", blob)
    if m:
        return m.group(1)[:4]
    return (atc_model or "").strip().upper()[:4] or (title or "").strip()[:12]


def _read_sim_snapshot_field(win: Any, name: str) -> object:
    """Nur Snapshot-Buffer — kein aq.get() im GUI-Thread (verhindert Deadlock/Ping)."""
    buf = getattr(win, "_sim_snap_buffer", None) or {}
    if name in buf:
        return buf[name]
    return None


def _patch_main_cloud_api_urls(main_mod: Any, db_path: Path) -> None:
    """Erzwingt Produktions-API für FIDS, Leaflet-Feed und Radar-Heartbeat."""
    prod = _resolve_production_api_base(main_mod, db_path)
    if not getattr(main_mod, "_sky_cloud_api_patched", False):
        _orig_server = main_mod.ionos_server_url
        _orig_api = main_mod.ionos_api_base_url

        def ionos_server_url() -> str:
            u = (_orig_server() or "").strip().rstrip("/")
            return prod if _is_local_api_url(u) else (u or prod)

        def ionos_api_base_url() -> str:
            u = (_orig_api() or "").strip().rstrip("/")
            return prod if _is_local_api_url(u) else (u or prod)

        main_mod.ionos_server_url = ionos_server_url
        main_mod.ionos_api_base_url = ionos_api_base_url
        main_mod._sky_cloud_api_patched = True
    if not getattr(main_mod, "_sky_as_float_patched", False):
        _orig_float = main_mod._as_float

        def _as_float(v: object) -> float | None:
            hi = _simconnect_coord_float(v)
            if hi is not None:
                return hi
            return _orig_float(v)

        main_mod._as_float = _as_float
        main_mod._sky_as_float_patched = True

FUEL_TIER_LITERS = (150_000, 500_000, 2_000_000, 5_000_000, 25_000_000)
FUEL_TIER_COSTS = (150_000.0, 500_000.0, 2_000_000.0, 5_000_000.0, 25_000_000.0)
CACHE_REFRESH_MS = 180_000

GOLD_TILE_STYLE = MONO_TILE_STYLE


def _init_platin_ram_cache(win: Any) -> None:
    win._platin_cached_fuel = {
        "storage": 0,
        "cap": 50_000,
        "pct": 0,
        "txt": "—",
        "ready": False,
        "ts": 0.0,
    }
    win._platin_branches_applied_once = False


def _qt_widget_alive(widget: Any) -> bool:
    if widget is None:
        return False
    try:
        from shiboken6 import isValid

        return bool(isValid(widget))
    except Exception:
        try:
            widget.isVisible()
            return True
        except RuntimeError:
            return False


class _PlatinAsyncBus(QObject):
    fuel_status = Signal(int, int)
    fuel_upgrade_done = Signal(bool, str)
    branches_pull_done = Signal(bool, str)
    license_need_dialog = Signal()
    cloud_sync_done = Signal(bool, str)
    gsx_boarding_pct = Signal(int, int, float)
    logout_ui_ready = Signal()
    charter_api_done = Signal(object)
    charter_api_fail = Signal(str)
    pax_feedback_ready = Signal(object)
    p2p_board_ready = Signal(object)


class _FnRunnable(QRunnable):
    __slots__ = ("_fn",)

    def __init__(self, fn: Any) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        self._fn()


class _CharterApiRunnable(QRunnable):
    """Charter calculate/dispatch — blockiert die UI nicht (QThreadPool)."""

    __slots__ = ("_inj", "_path", "_payload")

    def __init__(
        self, injector: "_PlatinInjector", api_path: str, payload: dict[str, Any]
    ) -> None:
        super().__init__()
        self._inj = injector
        self._path = api_path
        self._payload = payload

    def run(self) -> None:
        inj = self._inj
        base = inj._api_base()
        body = dict(inj.m.build_ionos_cloud_sync_body(inj.db_path, pull_only=True))
        body.update(self._payload)
        headers = dict(inj._headers())
        headers.setdefault("Content-Type", "application/json")
        lang = (
            inj.m.app_meta_get(inj.db_path, "app_language", "")
            or inj.m.app_meta_get(inj.db_path, "ui_lang", "")
            or "de"
        )
        body.setdefault("ui_lang", lang)
        body.setdefault("selected_language", lang if lang in ("de", "en") else "de")
        try:
            r = requests.post(
                f"{base}{self._path}",
                json=body,
                headers=headers,
                timeout=14,
            )
            data = r.json() if r.content else {}
            if not isinstance(data, dict):
                data = {"ok": False, "detail": "bad_response"}
            if r.status_code >= 400 and not data.get("detail"):
                data["detail"] = f"HTTP {r.status_code}"
            inj._safe_bus_emit(
                inj._bus.charter_api_done,
                {"path": self._path, "data": data, "status": r.status_code},
            )
        except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
            inj._safe_bus_emit(inj._bus.charter_api_fail, str(exc))


class _RadarHeartbeatRunnable(QRunnable):
    """Blockierungsfreier 5s-FIDS-Funk → POST /api/v1/radar/heartbeat (QThreadPool)."""

    __slots__ = ("_inj",)

    def __init__(self, injector: "_PlatinInjector") -> None:
        super().__init__()
        self._inj = injector

    def run(self) -> None:
        inj = self._inj
        m = inj.m
        db = inj.db_path
        if m.app_meta_get(db, "license_activated", "0") != "1":
            return
        m.app_meta_set(db, "online_network_enabled", "1")
        base = inj._api_base()
        win = inj.win
        pilot = (
            str(getattr(win, "username", "") or "").strip()
            or str(getattr(win, "pilot_display_name", "") or "").strip()
            or m.app_meta_get(db, "pilot_display_name", "")
            or m.pilot_handle(db)
            or "Pilot"
        )
        hid = m.p2p_hardware_id(db)
        la, lo = _RADAR_DEFAULT_LAT, _RADAR_DEFAULT_LON
        alt, hdg, gs = 0.0, 0.0, 0.0
        cur_icao = "EDDF"
        if getattr(win, "simconnect_connected", False):
            la_v, lo_v = _simconnect_latitude_longitude(win)
            if la_v is not None and lo_v is not None:
                la, lo = float(la_v), float(lo_v)
                if hasattr(win, "_persist_last_radar_coords"):
                    try:
                        win._persist_last_radar_coords(la, lo)
                    except Exception:
                        pass
                if hasattr(win, "_last_plane_lat"):
                    win._last_plane_lat = la
                    win._last_plane_lon = lo
            alt = float(
                m._as_float(_read_sim_snapshot_field(win, "INDICATED ALTITUDE")) or 0.0
            )
            hdg = float(
                m._as_float(
                    _read_sim_snapshot_field(win, "PLANE HEADING DEGREES TRUE")
                )
                or 0.0
            )
            gs = float(
                m._as_float(_read_sim_snapshot_field(win, "AIRSPEED_INDICATED"))
                or m._as_float(_read_sim_snapshot_field(win, "GROUND VELOCITY"))
                or 0.0
            )
        elif hasattr(win, "_last_known_radar_coords"):
            try:
                la, lo = win._last_known_radar_coords()
            except Exception:
                pass
        if not _gps_coords_plausible(la, lo):
            if hasattr(win, "_last_plane_lat") and hasattr(win, "_last_plane_lon"):
                la2 = getattr(win, "_last_plane_lat", None)
                lo2 = getattr(win, "_last_plane_lon", None)
                if la2 is not None and lo2 is not None and _gps_coords_plausible(
                    float(la2), float(lo2)
                ):
                    la, lo = float(la2), float(lo2)
            if not _gps_coords_plausible(la, lo):
                return
        cur_icao = (
            str(getattr(win, "current_aircraft_icao", None) or "").strip().upper()[:4]
            or str(getattr(win, "_session_fuel_icao", None) or "EDDF").strip().upper()[:4]
            or "EDDF"
        )
        title_raw = str(
            _read_sim_snapshot_field(win, "TITLE")
            or getattr(win, "_last_title", "")
            or ""
        ).strip()
        atc_model = str(_read_sim_snapshot_field(win, "ATC MODEL") or "").strip()
        atc_type = str(_read_sim_snapshot_field(win, "ATC TYPE") or "").strip()
        icao_ac = _simconnect_title_to_icao(title_raw, atc_model, atc_type)
        if icao_ac:
            try:
                win.current_aircraft_icao = icao_ac
            except Exception:
                pass
        ac = (
            icao_ac
            or str(getattr(win, "current_aircraft_model", "") or "").strip()
            or title_raw
            or "B738"
        )[:120]
        if not ac or ac in ("—", "-", "None"):
            ac = "B738"
        pw = (m.cloud_password_get(db) or "").strip()
        headers = dict(inj._headers())
        headers.setdefault("Content-Type", "application/json")
        payload: dict[str, Any] = {
            "hardware_id": hid,
            "username": pilot,
            "pilot_name": pilot,
            "status": "ONLINE",
            "flight_phase": "AM GATE / PARKING",
            "flight_phase_key": "parked",
            "aircraft": ac,
            "aircraft_model": ac,
            "current_icao": cur_icao,
            "origin": "STANDBY",
            "destination": "STANDBY",
            "origin_icao": "STANDBY",
            "destination_icao": "STANDBY",
            "route": "STANDBY",
            "latitude": float(la),
            "longitude": float(lo),
            "lat": float(la),
            "lon": float(lo),
            "alt": alt,
            "altitude": alt,
            "hdg": hdg,
            "heading": hdg,
            "ground_speed": gs,
            "ts": time.time(),
        }
        if pw:
            payload["password"] = pw
        url = f"{base}/api/v1/radar/heartbeat"
        try:
            requests.post(url, json=payload, headers=headers, timeout=6)
        except requests.RequestException:
            return
        if getattr(win, "_platin_radar_session_init", False):
            return
        init_body = dict(payload)
        init_body["icao"] = cur_icao
        try:
            requests.post(
                f"{base}/api/v1/radar/initialize_session",
                json=init_body,
                headers=headers,
                timeout=6,
            )
            win._platin_radar_session_init = True
        except requests.RequestException:
            pass


class _PlatinCloseEventFilter(QObject):
    """QObject-Eventfilter für Cloud-Save beim Schließen (PySide6-konform)."""

    __slots__ = ("_injector",)

    def __init__(self, injector: "_PlatinInjector") -> None:
        super().__init__()
        self._injector = injector

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj is self._injector.win and event.type() == QEvent.Type.Close:
            self._injector._cloud_save_async()
        return False


PLATIN_CABIN_TTS_SCRIPTS: dict[str, dict[str, dict[str, str]]] = {
    "welcome_boarding": {
        "de": {
            "female": "Willkommen an Bord. Bitte nehmen Sie Ihren Sitzplatz ein.",
            "male": "Willkommen an Bord. Bitte nehmen Sie Ihren Sitzplatz ein.",
        },
        "en": {
            "female": "Welcome on board. Please take your seats.",
            "male": "Welcome on board. Please take your seats.",
        },
    },
    "safety_briefing": {
        "de": {
            "female": "Wir beginnen mit der Sicherheitsunterweisung. Achten Sie auf die Anzeigen.",
            "male": "Wir beginnen mit der Sicherheitsunterweisung. Achten Sie auf die Anzeigen.",
        },
        "en": {
            "female": "We will now begin the safety demonstration.",
            "male": "We will now begin the safety demonstration.",
        },
    },
    "seatbelt_on": {
        "de": {
            "female": "Bitte schnallen Sie sich an.",
            "male": "Bitte schnallen Sie sich an.",
        },
        "en": {
            "female": "Please fasten your seat belts.",
            "male": "Please fasten your seat belts.",
        },
    },
    "seatbelt_off": {
        "de": {
            "female": "Sie dürfen Ihre Gurte jetzt lösen.",
            "male": "Sie dürfen Ihre Gurte jetzt lösen.",
        },
        "en": {
            "female": "You may now unfasten your seat belts.",
            "male": "You may now unfasten your seat belts.",
        },
    },
    "takeoff": {
        "de": {
            "female": "Achtung, Start. Bitte bleiben Sie angeschnallt.",
            "male": "Achtung, Start. Bitte bleiben Sie angeschnallt.",
        },
        "en": {
            "female": "Attention, takeoff. Please remain seated.",
            "male": "Attention, takeoff. Please remain seated.",
        },
    },
    "cruise": {
        "de": {
            "female": "Wir haben unsere Reiseflughöhe erreicht.",
            "male": "Wir haben unsere Reiseflughöhe erreicht.",
        },
        "en": {
            "female": "We have reached our cruising altitude.",
            "male": "We have reached our cruising altitude.",
        },
    },
    "descent": {
        "de": {
            "female": "Wir beginnen mit dem Sinkflug.",
            "male": "Wir beginnen mit dem Sinkflug.",
        },
        "en": {
            "female": "We are beginning our descent.",
            "male": "We are beginning our descent.",
        },
    },
    "landing": {
        "de": {
            "female": "Achtung, Landung. Bitte schnallen Sie sich wieder an.",
            "male": "Achtung, Landung. Bitte schnallen Sie sich wieder an.",
        },
        "en": {
            "female": "Attention, landing. Please fasten your seat belts.",
            "male": "Attention, landing. Please fasten your seat belts.",
        },
    },
    "thank_you": {
        "de": {
            "female": "Vielen Dank, dass Sie mit uns geflogen sind.",
            "male": "Vielen Dank, dass Sie mit uns geflogen sind.",
        },
        "en": {
            "female": "Thank you for flying with us today.",
            "male": "Thank you for flying with us today.",
        },
    },
    "turbulence": {
        "de": {
            "female": "Es kann zu Turbulenzen kommen. Bitte bleiben Sie angeschnallt.",
            "male": "Es kann zu Turbulenzen kommen. Bitte bleiben Sie angeschnallt.",
        },
        "en": {
            "female": "We are expecting turbulence. Please remain seated.",
            "male": "We are expecting turbulence. Please remain seated.",
        },
    },
    "duty_free": {
        "de": {
            "female": "Unser Duty-Free-Service beginnt jetzt.",
            "male": "Unser Duty-Free-Service beginnt jetzt.",
        },
        "en": {
            "female": "Our duty free service is now available.",
            "male": "Our duty free service is now available.",
        },
    },
    "prepare_landing": {
        "de": {
            "female": "Bitte bereiten Sie sich auf die Landung vor.",
            "male": "Bitte bereiten Sie sich auf die Landung vor.",
        },
        "en": {
            "female": "Please prepare for landing.",
            "male": "Please prepare for landing.",
        },
    },
}


def _cabin_audio_is_real(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= PLATIN_MIN_REAL_AUDIO_BYTES
    except OSError:
        return False


def _tts_windows_generate_wav(text: str, dest: Path, *, gender: str = "female") -> bool:
    """Windows SAPI: echte Piloten-/Crew-Stimme ohne Extra-Pakete."""
    if not text.strip() or os.name != "nt":
        return False
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    safe = text.replace("'", "''").replace('"', '`"')[:500]
    g_hint = "Female" if str(gender).lower() not in ("male", "m", "man") else "Male"
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"try {{ $v = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Gender -eq "
        f"'[System.Speech.Synthesis.VoiceGender]::{g_hint}' }} | Select-Object -First 1; "
        f"if ($v) {{ $s.SelectVoice($v.VoiceInfo.Name) }} }} catch {{}}; "
        f"$s.SetOutputToWaveFile('{str(dest).replace(chr(39), chr(39)*2)}'); "
        f"$s.Speak('{safe}'); $s.Dispose();"
    )
    try:
        import subprocess

        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=90,
            check=False,
        )
        return proc.returncode == 0 and _cabin_audio_is_real(dest)
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def _ensure_platin_cabin_voice_files(main_mod: Any, roots: list[Path]) -> int:
    """Ersetzt Pieps-Platzhalter durch SAPI-Sprachansagen (DE/EN, 12 Keys)."""
    written = 0
    for key, langs in PLATIN_CABIN_TTS_SCRIPTS.items():
        for lo, genders in langs.items():
            for gender, phrase in genders.items():
                fname = f"{key}_{lo}_{gender}.wav"
                for root in roots:
                    dest = root / fname
                    if _cabin_audio_is_real(dest):
                        continue
                    if dest.is_file():
                        try:
                            dest.unlink()
                        except OSError:
                            pass
                    if _tts_windows_generate_wav(phrase, dest, gender=gender):
                        written += 1
                        for mirror in roots:
                            if mirror == root:
                                continue
                            try:
                                (mirror / fname).write_bytes(dest.read_bytes())
                            except OSError:
                                pass
                        break
    return written


def _license_required_bilingual_text() -> str:
    return (
        "LIZENZ ERFORDERLICH: Bitte gib deinen 16-stelligen SkyTycoon Aktivierungsschlüssel ein!\n\n"
        "LICENSE REQUIRED: Please enter your 16-character SkyTycoon activation key!"
    )


def _lock_six_main_hub_tabs(win: Any) -> None:
    tw = getattr(win, "tab_widget", None)
    if tw is None:
        return
    win._platin_hub_locked = True
    for attr in _HUB_TAB_IX_ATTRS:
        ix = getattr(win, attr, None)
        if isinstance(ix, int) and 0 <= ix < tw.count():
            tw.setTabEnabled(ix, False)


def _resolve_portal_email_from_login(
    pilot: str, login_json: dict[str, Any] | None
) -> str:
    """Was im Login-Feld steht (E-Mail) hat Vorrang vor alter Server-/Datei-E-Mail."""
    p = (pilot or "").strip().lower()
    if "@" in p:
        return p[:200]
    if not isinstance(login_json, dict):
        return ""
    em = str(
        login_json.get("email") or login_json.get("portal_email") or ""
    ).strip().lower()
    return em[:200] if "@" in em else ""


def _clear_stale_login_identity(main_mod: Any, db_path: Any) -> None:
    """Vor frischem Login: vorheriges Konto aus Session-Meta entfernen."""
    for key in (
        "portal_email",
        "career_bound_portal_email",
        "ionos_jwt",
        "platin_superadmin",
        "alliance_snapshot_json",
        "ionos_hardware_id",
        "econ_device_tag",
    ):
        try:
            main_mod.app_meta_set(db_path, key, "")
        except Exception:
            pass
    try:
        main_mod.cloud_password_set(db_path, "")
    except Exception:
        pass


def _platin_seal_login_session(
    main_mod: Any,
    db_path: Any,
    login_json: dict[str, Any],
    *,
    pilot: str = "",
    password: str = "",
) -> None:
    """Nach login_success: JWT/Passwort/Pilot bombenfest im RAM + SQLite behalten."""
    if not isinstance(login_json, dict):
        login_json = {}
    local_hid = _normalize_client_hwid(main_mod, db_path, force_os=False)
    _bind_server_hardware_id(main_mod, db_path, login_json, local_hid)
    _store_login_access_token(main_mod, db_path, login_json)
    tok = str(
        login_json.get("access_token")
        or login_json.get("session_token")
        or login_json.get("token")
        or ""
    ).strip()
    if tok:
        main_mod.app_meta_set(db_path, "ionos_jwt", tok[:4096])
    pw = (password or "").strip()
    if pw:
        main_mod.cloud_password_set(db_path, pw)
    pilot_n = (pilot or "").strip()
    em = _resolve_portal_email_from_login(pilot_n, login_json)
    srv_em = str(login_json.get("email") or login_json.get("portal_email") or "").strip().lower()
    if srv_em and "@" in srv_em:
        em = srv_em[:200]
    display = str(
        login_json.get("pilot_name")
        or login_json.get("display_name")
        or login_json.get("username")
        or ""
    ).strip()
    if not display and pilot_n and "@" not in pilot_n:
        display = pilot_n
    if not display and em and "@" in em:
        display = em.split("@", 1)[0]
    if display and "@" not in display:
        main_mod.app_meta_set(db_path, "pilot_display_name", display[:120])
        main_mod.app_meta_set(db_path, "pilot_name", display[:120])
    elif em and "@" in em:
        main_mod.app_meta_set(db_path, "pilot_display_name", em[:120])
        main_mod.app_meta_set(db_path, "pilot_name", em.split("@", 1)[0][:120])
    if em:
        main_mod.app_meta_set(db_path, "portal_email", em)
        main_mod.app_meta_set(db_path, "career_bound_portal_email", em)
    main_mod.app_meta_set(db_path, "online_network_enabled", "1")


def _platin_apply_cockpit_identity(win: Any, main_mod: Any, db_path: Any) -> None:
    """Cockpit-Labels: Portal-E-Mail + kanonische HWID (nicht alter Login-Name)."""
    if win is None:
        return
    try:
        em = (main_mod.app_meta_get(db_path, "portal_email", "") or "").strip()
        pilot = (main_mod.app_meta_get(db_path, "pilot_display_name", "") or "").strip()
        hid = _normalize_client_hwid(main_mod, db_path)
        line = em if "@" in em else (pilot or "—")
        if hasattr(win, "label_brand_pilot"):
            win.label_brand_pilot.setText(line)
        if hasattr(win, "label_career_pilot_line"):
            win.label_career_pilot_line.setText(f"👤 {line}")
        sb = win.statusBar() if hasattr(win, "statusBar") else None
        if sb is not None and hid:
            sb.showMessage(f"Portal: {line} · HWID {hid[:20]}…", 8000)
        if hasattr(win, "_apply_branded_window_title"):
            win._apply_branded_window_title()
    except Exception as exc:
        print(f"[SkyTycoon] Cockpit-Identity: {exc!s}", flush=True)


def _platin_instant_cockpit_open(win: Any) -> None:
    """Cockpit sofort sichtbar — kein GUI-Thread-Block nach Login."""
    if win is None:
        return
    _hide_platin_login_surface(win)
    try:
        win.show()
        win.raise_()
        win.activateWindow()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app is not None:
        try:
            app.processEvents()
        except RuntimeError:
            pass


def _purge_session_meta_db(main_mod: Any, db_path: Any) -> None:
    """Nur beim Logout / vor frischem Fremd-Login: Meta leeren (nicht nach login_success)."""
    for key in LOGOUT_META_KEYS:
        try:
            main_mod.app_meta_set(db_path, key, "")
        except Exception:
            pass
    try:
        main_mod.app_meta_set(db_path, "ionos_jwt", "")
    except Exception:
        pass
    try:
        main_mod.cloud_password_set(db_path, "")
    except Exception:
        pass


def _purge_session_ram_cache(win: Any, main_mod: Any, db_path: Any) -> None:
    """Logout: Meta + Remember-Me + RAM-Cache vollständig leeren."""
    _purge_session_meta_db(main_mod, db_path)
    _nuke_disk_local_session(main_mod, db_path)
    targets: list[Any] = []
    if win is not None:
        targets.append(win)
        try:
            p = win.parent()
            while p is not None:
                targets.append(p)
                p = p.parent()
        except RuntimeError:
            pass
    ram_attrs = (
        "session_token",
        "access_token",
        "ionos_jwt",
        "username",
        "pilot_display_name",
        "pilot_name",
        "portal_email",
        "_platin_cloud_sync_last_ok",
        "_platin_login_user",
        "_profile_cloud_last",
    )
    for obj in targets:
        for attr in ram_attrs:
            try:
                setattr(obj, attr, None)
            except Exception:
                pass
        try:
            obj._platin_fresh_cloud_sync = True
            obj._platin_radar_heartbeat_armed = False
            obj._platin_radar_session_init = False
        except Exception:
            pass


def _store_login_access_token(main_mod: Any, db_path: Any, payload: dict[str, Any]) -> None:
    tok = str(payload.get("access_token") or "").strip()
    if tok:
        main_mod.app_meta_set(db_path, "ionos_jwt", tok[:4096])


def _normalize_client_hwid(
    main_mod: Any, db_path: Any, *, force_os: bool = False
) -> str:
    """Saubere HWID (64 Zeichen). force_os=True: echte Windows-UUID vor Login erzwingen."""
    if force_os:
        for key in ("ionos_hardware_id", "econ_device_tag"):
            try:
                main_mod.app_meta_set(db_path, key, "")
            except Exception:
                pass
    try:
        if hasattr(main_mod, "ensure_ionos_hardware_id_from_os"):
            main_mod.ensure_ionos_hardware_id_from_os(db_path)
    except Exception:
        pass
    raw = main_mod.p2p_hardware_id(db_path)
    if isinstance(raw, dict):
        hid = str(
            raw.get("hardware_id")
            or raw.get("id")
            or raw.get("hwid")
            or ""
        ).strip()
    else:
        hid = str(raw or "").strip()
    if len(hid) >= 2 and hid[0] == hid[-1] and hid[0] in "\"'":
        hid = hid[1:-1].strip()
    return hid[:64] if hid and hid.lower() != "unknown" else hid[:64]


def _bind_server_hardware_id(
    main_mod: Any, db_path: Any, login_json: dict[str, Any] | None, fallback: str
) -> None:
    """Nach Login/Activate: Server-HWID (kanonisch) lokal speichern."""
    hid = str((login_json or {}).get("hardware_id") or fallback or "").strip()[:64]
    if hid and hid.lower() != "unknown":
        main_mod.ionos_bind_hardware_id(db_path, hid)


def _sterile_api_string(val: Any, *, max_len: int = 200) -> str:
    """Nur druckbare Zeichen — verhindert JSON-Fragmente im Login-Handshake."""
    if val is None or isinstance(val, (dict, list, tuple, bytes, bytearray)):
        return ""
    s = str(val)
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    s = "".join(ch for ch in s if ord(ch) >= 32 or ch in "\t")
    return s.strip()[:max_len]


def _app_data_dir(main_mod: Any, db_path: Any) -> Path:
    """Projektordner dynamisch — portabel für Co-Dev (BigMaq / Schweiz / DE)."""
    _ = db_path
    return platin_project_root()


def _local_session_path(main_mod: Any, db_path: Any) -> Path:
    return _app_data_dir(main_mod, db_path) / LOCAL_SESSION_FILENAME


def _session_crypto_key(main_mod: Any, db_path: Any) -> bytes:
    base = _app_data_dir(main_mod, db_path).resolve()
    raw = (
        f"skytycoon-platin-session-v{LOCAL_SESSION_VERSION}:"
        f"{base}:{main_mod.SKYTYCOON_APP_NAME}"
    ).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).digest()


def _session_encrypt(main_mod: Any, db_path: Any, plain: str) -> str:
    if not plain:
        return ""
    k = _session_crypto_key(main_mod, db_path)
    data = plain.encode("utf-8", errors="replace")
    x = bytes(b ^ k[i % len(k)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(x).decode("ascii")


def _session_decrypt(main_mod: Any, db_path: Any, blob: str) -> str:
    if not blob.strip():
        return ""
    try:
        raw = base64.urlsafe_b64decode(blob.encode("ascii"))
    except (ValueError, OSError):
        return ""
    k = _session_crypto_key(main_mod, db_path)
    p = bytes(b ^ k[i % len(k)] for i, b in enumerate(raw))
    return p.decode("utf-8", errors="replace")


def _clear_local_session_file(main_mod: Any, db_path: Any) -> None:
    """Physische local_session.json radikal entfernen (Remember-Me aus)."""
    candidates: list[Path] = []
    try:
        candidates.append(_local_session_path(main_mod, db_path))
    except Exception:
        pass
    try:
        root = _app_data_dir(main_mod, db_path)
        candidates.append(root / LOCAL_SESSION_FILENAME)
        candidates.append(Path(db_path).parent / LOCAL_SESSION_FILENAME)
    except Exception:
        pass
    seen: set[str] = set()
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        try:
            if p.is_file():
                os.remove(str(p))
        except OSError:
            try:
                if p.is_file():
                    p.unlink()
            except OSError:
                pass
    try:
        main_mod.app_meta_set(db_path, "platin_remember_login", "0")
    except Exception:
        pass


def _nuke_disk_local_session(main_mod: Any, db_path: Any) -> None:
    """Logout: RAM + SQLite-Meta + Festplatten-Session in einem Schritt."""
    _clear_local_session_file(main_mod, db_path)


def _apply_platin_global_dark_theme(win: Any) -> None:
    """Globales Platin Schwarz/Gold — verhindert Windows-Standard-Grau nach Tab-Injekt."""
    if win is None:
        return
    try:
        win.setStyleSheet(_PLATIN_GLOBAL_DARK_STYLE)
    except RuntimeError:
        pass
    for attr in ("tab_widget", "main_tab_widget"):
        tw = getattr(win, attr, None)
        if tw is None:
            continue
        try:
            tw.setStyleSheet(_PLATIN_GLOBAL_DARK_STYLE)
        except RuntimeError:
            pass


def _save_local_session(
    main_mod: Any,
    db_path: Any,
    *,
    username: str,
    password: str,
    access_token: str,
    portal_email: str,
    license_key: str = "",
) -> None:
    lk = _sterile_api_string(license_key, max_len=256)
    payload = {
        "v": LOCAL_SESSION_VERSION,
        "remember": True,
        "username": _sterile_api_string(username, max_len=120),
        "portal_email": _sterile_api_string(portal_email, max_len=200).lower(),
        "password_enc": _session_encrypt(main_mod, db_path, password),
        "access_token_enc": _session_encrypt(main_mod, db_path, access_token),
        "license_key_enc": _session_encrypt(main_mod, db_path, lk) if lk else "",
        "saved_ts": int(time.time()),
    }
    p = _local_session_path(main_mod, db_path)
    try:
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _load_local_session(main_mod: Any, db_path: Any) -> dict[str, Any] | None:
    p = _local_session_path(main_mod, db_path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        _clear_local_session_file(main_mod, db_path)
        return None
    if not isinstance(data, dict) or not data.get("remember"):
        return None
    ver = int(data.get("v") or 0)
    if ver not in (2, LOCAL_SESSION_VERSION):
        _clear_local_session_file(main_mod, db_path)
        return None
    saved_ts = int(data.get("saved_ts") or 0)
    if saved_ts and time.time() - saved_ts > LOCAL_SESSION_MAX_AGE_SEC:
        _clear_local_session_file(main_mod, db_path)
        return None
    pw = _session_decrypt(main_mod, db_path, str(data.get("password_enc") or ""))
    tok = _session_decrypt(main_mod, db_path, str(data.get("access_token_enc") or ""))
    if not pw and not tok:
        _clear_local_session_file(main_mod, db_path)
        return None
    lk = _session_decrypt(main_mod, db_path, str(data.get("license_key_enc") or ""))
    return {
        "username": str(data.get("username") or ""),
        "portal_email": str(data.get("portal_email") or ""),
        "password": pw,
        "access_token": tok,
        "license_key": lk,
    }


def _platin_persist_remember_me(
    dlg: Any, main_mod: Any, db_path: Any, login_json: dict[str, Any] | None = None
) -> None:
    cb = getattr(dlg, "_platin_remember_cb", None)
    remember = True if cb is None else bool(cb.isChecked())
    pilot = (
        getattr(dlg, "ed_login_name", None).text().strip()
        if getattr(dlg, "ed_login_name", None) is not None
        else ""
    )
    pw = (
        getattr(dlg, "ed_login_pw", None).text().strip()
        if getattr(dlg, "ed_login_pw", None) is not None
        else ""
    )
    j = login_json if isinstance(login_json, dict) else {}
    lk = ""
    if getattr(dlg, "ed_login_key", None) is not None:
        lk = dlg.ed_login_key.text().strip()
    if not lk:
        lk = str(j.get("license_key") or "").strip()
    if not lk:
        try:
            lk = (main_mod.app_meta_get(db_path, "license_key_installed", "") or "").strip()
        except Exception:
            lk = ""
    if remember and pilot and pw:
        em = _resolve_portal_email_from_login(pilot, j)
        tok = str(
            j.get("access_token") or j.get("token") or ""
        ).strip()
        if not tok:
            try:
                tok = (main_mod.app_meta_get(db_path, "ionos_jwt", "") or "").strip()
            except Exception:
                tok = ""
        _save_local_session(
            main_mod,
            db_path,
            username=pilot,
            password=pw,
            access_token=tok,
            portal_email=em if "@" in em else "",
            license_key=lk,
        )
        if lk:
            main_mod.app_meta_set(db_path, "license_key_installed", lk[:256])
        main_mod.app_meta_set(db_path, "platin_remember_login", "1")
    elif cb is not None and not remember:
        _clear_local_session_file(main_mod, db_path)
        main_mod.app_meta_set(db_path, "platin_remember_login", "0")


def _platin_login_accept(
    dlg: Any, main_mod: Any, db_path: Any, login_json: dict[str, Any] | None = None
) -> None:
    """Nach erfolgreichem Login: Remember-Me sichern, dann Dialog schließen."""
    payload = login_json
    if not isinstance(payload, dict):
        payload = getattr(dlg, "_platin_pending_login_json", None)
    if not isinstance(payload, dict):
        payload = {}
    if (
        str(payload.get("status", "")).lower() in ("login_success", "ok", "activated")
        or int(payload.get("has_license") or 0)
        or payload.get("auto_license_activated")
        or payload.get("hwid_slot_provisioned")
        or main_mod.app_meta_get(db_path, "license_activated", "0") == "1"
    ):
        main_mod.app_meta_set(db_path, "license_activated", "1")
    _platin_seal_login_session(
        main_mod,
        db_path,
        payload,
        pilot=(
            getattr(dlg, "ed_login_name", None).text().strip()
            if getattr(dlg, "ed_login_name", None) is not None
            else ""
        ),
        password=(
            getattr(dlg, "ed_login_pw", None).text().strip()
            if getattr(dlg, "ed_login_pw", None) is not None
            else ""
        ),
    )
    _platin_persist_remember_me(dlg, main_mod, db_path, payload)
    try:
        from platin_cloud_only import hydrate_platin_credentials_from_disk

        hydrate_platin_credentials_from_disk(main_mod)
    except Exception:
        pass
    parent = getattr(dlg, "parent_window", None) or dlg.parent()
    pilot_txt = ""
    if getattr(dlg, "ed_login_name", None) is not None:
        pilot_txt = dlg.ed_login_name.text().strip()
    em_login = _resolve_portal_email_from_login(pilot_txt, payload)
    if em_login and "@" in em_login:
        try:
            prof_login = {
                "credits": float(
                    payload.get("credits", main_mod.PORTAL_STARTER_CREDITS)
                    or main_mod.PORTAL_STARTER_CREDITS
                ),
                "xp": float(payload.get("xp", 0) or 0),
                "email": em_login,
            }
            if main_mod.portal_login_needs_local_starter_reset(
                db_path, em_login, prof_login
            ):
                main_mod.reset_local_career_to_starter_profile(db_path, prof_login)
                if parent is not None:
                    parent._platin_fresh_cloud_sync = True
            else:
                main_mod.app_meta_set(
                    db_path, "career_bound_portal_email", em_login[:200]
                )
        except Exception:
            pass
    try:
        main_mod.cloud_record_successful_server_contact(db_path)
    except Exception:
        pass
    dlg._platin_pending_login_json = None
    if parent is not None:
        parent._platin_license_trusted = True
        parent._platin_license_prompt_block_until = time.time() + 86400.0
        parent._platin_auth_gate_done = True
        _platin_apply_cockpit_identity(parent, main_mod, db_path)
        _platin_instant_cockpit_open(parent)
    sky_orig = getattr(type(dlg), "_sky_orig_accept", None)
    if callable(sky_orig):
        sky_orig(dlg)
    else:
        QDialog.accept(dlg)


def _prepare_startup_auth_remember_prefill(
    dlg: Any, main_mod: Any, db_path: Any
) -> bool:
    """Gespeicherte Session laden (Datei reicht — Meta-Flag optional)."""
    if not _local_session_path(main_mod, db_path).is_file():
        return False
    return _prefill_startup_auth_from_local_session(dlg, main_mod, db_path)


def _remember_me_label(main_mod: Any, db_path: Any) -> str:
    lg = (
        main_mod.app_meta_get(db_path, "ui_lang", "")
        or main_mod.app_meta_get(db_path, "selected_language", "")
        or "de"
    ).strip().lower()[:2]
    if lg == "en":
        return "🔓 Remember credentials & log in automatically"
    return "🔓 Zugangsdaten merken & automatisch anmelden"


_PLATIN_AUTH_ICE_STYLE = """
QDialog { background-color: #0b0f19; color: #eceff1; }
QTabWidget::pane { border: 1px solid #1a2a3d; border-radius: 8px; background: #0b0f19; }
QLineEdit {
    background-color: #05080f; color: #8ac7ff; border: 2px solid #00a2ff;
    border-radius: 8px; padding: 10px 12px; font-size: 14px; font-weight: 600;
    selection-background-color: #00a2ff; selection-color: #0b0f19;
}
QLineEdit:focus { border: 2px solid #8ac7ff; color: #ffffff; }
QPushButton {
    background-color: #00a2ff; color: #0b0f19; border: none;
    border-radius: 8px; padding: 12px 16px; font-weight: 800; font-size: 14px;
}
QPushButton:hover { background-color: #8ac7ff; color: #0b0f19; }
QPushButton#secondary {
    background-color: transparent; color: #8ac7ff;
    border: 2px solid #00a2ff; font-weight: 700;
}
QPushButton#secondary:hover { background-color: rgba(0, 162, 255, 0.2); }
QLabel { color: #cfd8dc; }
QCheckBox { color: #8ac7ff; font-weight: 700; }
QCheckBox::indicator {
    width: 18px; height: 18px; border: 2px solid #00a2ff; border-radius: 4px;
    background: #0b0f19;
}
QCheckBox::indicator:checked { background: #00a2ff; border-color: #8ac7ff; }
"""


def _patch_kill_offline_setup_wizard(main_mod: Any) -> None:
    """Offline-Setup (Cpt. Müller / Swiss SWR) — niemals mehr beim Kaltstart."""
    if getattr(main_mod, "_sky_setup_wizard_killed", False):
        return
    orig = getattr(main_mod, "run_first_run_wizard", None)
    if not callable(orig):
        return

    def run_first_run_wizard_platin(parent: Any = None) -> bool:
        path = getattr(main_mod, "DB_PATH", None)
        if path is not None:
            try:
                main_mod.app_meta_set(path, "setup_complete", "1")
                main_mod.app_meta_set(path, "setup_wizard_v2_done", "1")
                main_mod.app_meta_set(path, "platin_online_only_v1", "1")
            except OSError:
                pass
        print(
            "[SkyTycoon] Offline-Setup-Wizard blockiert — nur Online-Login (StartupAuthDialog).",
            flush=True,
        )
        return True

    main_mod.run_first_run_wizard = run_first_run_wizard_platin
    main_mod._sky_setup_wizard_killed = True


def _patch_startup_auth_iceblue_ui(main_mod: Any) -> None:
    """Eisblaues Online-Login: E-Mail, Passwort, Lizenzschlüssel, Remember Me."""
    dlg_cls = getattr(main_mod, "StartupAuthDialog", None)
    if dlg_cls is None or getattr(dlg_cls, "_platin_ice_auth_ui", False):
        return
    orig_i18n = dlg_cls._apply_startup_auth_i18n

    def _apply_startup_auth_i18n_ice(self: Any) -> None:
        orig_i18n(self)
        self.setStyleSheet(_PLATIN_AUTH_ICE_STYLE)
        self.setWindowTitle(
            main_mod.i18n_db(
                self._path,
                "startup.auth.title_online",
                "SkyTycoon Pro — Online-Anmeldung (Cloud)",
            )
        )
        if getattr(self, "ed_login_name", None) is not None:
            self.ed_login_name.setPlaceholderText(
                main_mod.i18n_db(
                    self._path,
                    "startup.auth.placeholder_email",
                    "✉️ E-Mail-Adresse / Portal-E-Mail",
                )
            )
        if getattr(self, "ed_login_pw", None) is not None:
            self.ed_login_pw.setPlaceholderText(
                main_mod.i18n_db(
                    self._path,
                    "startup.auth.placeholder_pw",
                    "🔑 Passwort / Master-Passwort",
                )
            )
        if getattr(self, "ed_login_key", None) is not None:
            self.ed_login_key.setVisible(True)
            self.ed_login_key.setPlaceholderText(
                main_mod.i18n_db(
                    self._path,
                    "startup.auth.placeholder_license",
                    "🎫 Lizenzschlüssel / Shop-Key (ST-AUTO-...)",
                )
            )
        if getattr(self, "lbl_login_key_hint", None) is not None:
            self.lbl_login_key_hint.setVisible(True)
            self.lbl_login_key_hint.setStyleSheet(
                "color:#8ac7ff;font-size:12px;font-weight:600;"
            )
            self.lbl_login_key_hint.setText(
                main_mod.i18n_db(
                    self._path,
                    "startup.auth.license_key_hint",
                    "Nach PayPal-Kauf: ST-AUTO-… hier eintragen — wird an PostgreSQL geprüft.",
                )
            )
        if getattr(self, "b_login_paste", None) is not None:
            self.b_login_paste.setVisible(True)
        if getattr(self, "b_login", None) is not None:
            self.b_login.setText(
                main_mod.i18n_db(
                    self._path,
                    "startup.auth.btn_login_cloud",
                    "🌐 Online anmelden (Cloud-Sync)",
                )
            )

    dlg_cls._apply_startup_auth_i18n = _apply_startup_auth_i18n_ice
    dlg_cls._platin_ice_auth_ui = True


def _inject_startup_auth_remember_checkbox(main_mod: Any) -> None:
    dlg_cls = getattr(main_mod, "StartupAuthDialog", None)
    if dlg_cls is None or getattr(dlg_cls, "_sky_remember_me_patch", False):
        return
    orig_init = dlg_cls.__init__

    def __init__(self: Any, db_path: Any, parent: Any = None) -> None:
        orig_init(self, db_path, parent)
        if getattr(self, "ed_login_key", None) is not None:
            self.ed_login_key.setVisible(True)
            if getattr(self, "b_login_paste", None) is not None:
                self.b_login_paste.setVisible(True)
            if getattr(self, "lbl_login_key_hint", None) is not None:
                self.lbl_login_key_hint.setVisible(True)
                self.lbl_login_key_hint.setText(
                    main_mod.i18n_db(
                        db_path,
                        "startup.auth.license_key_hint",
                        "Lizenzschlüssel (ST-XXXX-XXXX-XXXX) — beim ersten Start oder "
                        "nach Kauf hier eintragen.",
                    )
                )
        if getattr(self, "_platin_remember_cb", None) is not None:
            return
        cb = QCheckBox(_remember_me_label(main_mod, db_path))
        cb.setObjectName("platinRememberLogin")
        cb.setStyleSheet(
            "QCheckBox{color:#e8e8ec;font-weight:700;font-size:12px;spacing:8px;}"
            "QCheckBox::indicator{width:18px;height:18px;border:2px solid #3a3a42;"
            "border-radius:4px;background:#0b0b10;}"
            "QCheckBox::indicator:checked{background:#2c2c32;border-color:#e8e8ec;}"
        )
        self._platin_remember_cb = cb
        cb.setChecked(True)
        if _local_session_path(main_mod, db_path).is_file():
            cb.setChecked(True)
        elif main_mod.app_meta_get(db_path, "platin_remember_login", "0") == "0":
            cb.setChecked(False)
        lay = self.ed_login_pw.parentWidget().layout() if self.ed_login_pw else None
        inserted = False
        if lay is not None:
            ix = lay.indexOf(self.ed_login_pw)
            if ix >= 0:
                lay.insertWidget(ix + 1, cb)
                inserted = True
            else:
                lay.addWidget(cb)
                inserted = True
        if not inserted and getattr(self, "b_login", None) is not None:
            bl = self.b_login.parentWidget().layout() if self.b_login else None
            if bl is not None:
                bl.insertWidget(max(0, bl.indexOf(self.b_login)), cb)

    dlg_cls.__init__ = __init__

    orig_i18n = dlg_cls._apply_startup_auth_i18n

    def _apply_i18n_remember(self: Any) -> None:
        orig_i18n(self)
        cb = getattr(self, "_platin_remember_cb", None)
        if cb is not None:
            cb.setText(_remember_me_label(main_mod, self._path))

    dlg_cls._apply_startup_auth_i18n = _apply_i18n_remember
    dlg_cls._sky_remember_me_patch = True


def _prefill_startup_auth_from_local_session(dlg: Any, main_mod: Any, db_path: Any) -> bool:
    sess = _load_local_session(main_mod, db_path)
    if not sess:
        return False
    user = str(sess.get("portal_email") or sess.get("username") or "").strip()
    pw = str(sess.get("password") or "").strip()
    if user and getattr(dlg, "ed_login_name", None) is not None:
        dlg.ed_login_name.setText(user)
    if pw and getattr(dlg, "ed_login_pw", None) is not None:
        dlg.ed_login_pw.setText(pw)
    lk = str(sess.get("license_key") or "").strip()
    if lk and getattr(dlg, "ed_login_key", None) is not None:
        dlg.ed_login_key.setText(lk)
        dlg.ed_login_key.setVisible(True)
        main_mod.app_meta_set(db_path, "license_key_installed", lk[:256])
    cb = getattr(dlg, "_platin_remember_cb", None)
    if cb is not None:
        cb.setChecked(True)
    return bool(user and pw)


class _PlatinAutoLoginSettingsDialog(QDialog):
    """Goldenes Mini-Fenster: Auto-Login aktivieren/deaktivieren."""

    def __init__(self, win: Any, main_mod: Any, db_path: Any) -> None:
        super().__init__(win)
        self._m = main_mod
        self._db = db_path
        self.setWindowTitle(
            main_mod.i18n_db(
                db_path,
                "platin.autologin.title",
                "🔓 Automatische Anmeldung",
            )
        )
        self.setModal(True)
        self.resize(480, 220)
        self.setStyleSheet(_PLATIN_GOLD_STYLE)
        lay = QVBoxLayout(self)
        self._cb = QCheckBox(_remember_me_label(main_mod, db_path))
        self._cb.setChecked(main_mod.app_meta_get(db_path, "platin_remember_login", "0") == "1")
        lay.addWidget(self._cb)
        hint = QLabel(
            main_mod.i18n_db(
                db_path,
                "platin.autologin.hint",
                "Aktiv: Zugangsdaten verschlüsselt in local_session.json.\n"
                "Deaktiviert: Datei wird sofort gelöscht.",
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#90a4ae;font-size:12px;")
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch()
        ok = QPushButton(main_mod.i18n_db(db_path, "platin.autologin.save", "Speichern / Save"))
        ok.clicked.connect(self._save)
        row.addWidget(ok)
        lay.addLayout(row)

    def _save(self) -> None:
        if self._cb.isChecked():
            sess = _load_local_session(self._m, self._db)
            if not sess:
                QMessageBox.information(
                    self,
                    self._m.SKYTYCOON_APP_NAME,
                    self._m.i18n_db(
                        self._db,
                        "platin.autologin.need_login",
                        "Bitte einmal manuell anmelden und „Zugangsdaten merken“ aktivieren.",
                    ),
                )
                self._cb.setChecked(False)
                self._m.app_meta_set(self._db, "platin_remember_login", "0")
                self.accept()
                return
            self._m.app_meta_set(self._db, "platin_remember_login", "1")
        else:
            self._m.app_meta_set(self._db, "platin_remember_login", "0")
            _clear_local_session_file(self._m, self._db)
        self.accept()


def _inject_auto_login_settings_menu(win: Any, main_mod: Any, db_path: Any) -> None:
    if getattr(win, "_platin_autologin_menu", False):
        return
    mb = win.menuBar()
    if mb is None:
        return
    label_de = "🔓 Automatische Anmeldung verwalten"
    label_en = "🔓 Toggle Auto-Login"
    lg = (
        main_mod.app_meta_get(db_path, "ui_lang", "")
        or main_mod.app_meta_get(db_path, "selected_language", "")
        or "de"
    ).strip().lower()[:2]
    label = label_en if lg == "en" else label_de

    def _open() -> None:
        _PlatinAutoLoginSettingsDialog(win, main_mod, db_path).exec()

    act = QAction(label, win)
    act.triggered.connect(_open)
    inserted = False
    for existing in mb.actions():
        txt = existing.text() or ""
        if "Einstellungen" in txt or "Settings" in txt:
            mb.insertAction(existing, act)
            inserted = True
            break
    if not inserted:
        mb.insertAction(mb.actions()[0] if mb.actions() else None, act)
    win._platin_autologin_menu = True
    win._platin_act_autologin = act


def _prepare_startup_auth_dialog(dlg: Any, main_mod: Any) -> None:
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.resize(540, 480)
    try:
        dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    except Exception:
        pass
    if hasattr(dlg, "_apply_startup_auth_i18n"):
        dlg._apply_startup_auth_i18n()


def _run_modal_startup_auth(
    win: Any, main_mod: Any, db_path: Any, injector: Any
) -> bool:
    """Kaltstart: nur StartupAuthDialog — keine parallelen Pop-ups."""
    global _PLATIN_BLOCK_STARTUP_POPUPS
    dlg_cls = getattr(main_mod, "StartupAuthDialog", None)
    if dlg_cls is None:
        return False
    _PLATIN_BLOCK_STARTUP_POPUPS = True
    _hide_main_cockpit(win)
    _lock_six_main_hub_tabs(win)
    try:
        win.hide()
    except RuntimeError:
        pass
    dlg = dlg_cls(db_path, None)
    _prepare_startup_auth_dialog(dlg, main_mod)
    has_saved = _prepare_startup_auth_remember_prefill(dlg, main_mod, db_path)
    if has_saved and getattr(dlg, "b_login", None) is not None:

        def _auto_login() -> None:
            try:
                if dlg.isVisible():
                    dlg.b_login.click()
            except RuntimeError:
                pass

        QTimer.singleShot(600, _auto_login)
    accepted = dlg.exec() == QDialog.DialogCode.Accepted
    if accepted:
        pending = getattr(dlg, "_platin_pending_login_json", None)
        _platin_persist_remember_me(
            dlg,
            main_mod,
            db_path,
            pending if isinstance(pending, dict) else {},
        )
    try:
        dlg.deleteLater()
    except RuntimeError:
        pass
    if not accepted:
        return False
    _PLATIN_BLOCK_STARTUP_POPUPS = False
    win._platin_auth_gate_done = True
    win._platin_coldstart_login_complete = True
    injector._after_platin_login_success()
    injector._post_auth_bootstrap()
    return True


def _sterile_login_json(
    main_mod: Any,
    db_path: Any,
    username: str,
    password: str,
    *,
    license_key: str = "",
    portal_email: str = "",
) -> dict[str, str]:
    """Minimaler Login/cloud_sync-Body: username, password, pc_hardware_id (+ optional E-Mail)."""
    hid = _normalize_client_hwid(main_mod, db_path, force_os=True)
    pilot = _sterile_api_string(username, max_len=120)
    pw = _sterile_api_string(password, max_len=256)
    body: dict[str, str] = {
        "username": pilot,
        "pilot_name": pilot,
        "password": pw,
        "pc_hardware_id": hid,
        "hardware_id": hid,
        "incoming_pc_hardware_id": hid,
    }
    em = _sterile_api_string(portal_email, max_len=200).lower()
    if not em and "@" in pilot:
        em = pilot.lower()
    if em and "@" in em:
        body["email"] = em
        body["portal_email"] = em
    lk = _sterile_api_string(license_key, max_len=256)
    if lk:
        body["license_key"] = lk
    ui_lg = _sterile_api_string(
        main_mod.app_meta_get(db_path, "selected_language", "")
        or main_mod.app_meta_get(db_path, "ui_lang", "")
        or "de",
        max_len=8,
    ).lower()
    if ui_lg in ("de", "en"):
        body["selected_language"] = ui_lg
        body["ui_lang"] = ui_lg
    return body


def _desktop_auth_login_body(
    main_mod: Any, db_path: Any, pilot: str, pw: str, key: str = ""
) -> dict[str, Any]:
    return dict(
        _sterile_login_json(
            main_mod,
            db_path,
            pilot,
            pw,
            license_key=key,
            portal_email=pilot if "@" in str(pilot or "") else "",
        )
    )


def _apply_desktop_language(win: Any, db_path: str, main_mod: Any, lang: str) -> None:
    """Server-Sprache (de/en) sofort ins Cockpit — ohne main.py-Layout zu ändern."""
    lg = str(lang or "").strip().lower()[:8]
    if lg not in ("de", "en"):
        lg = str(main_mod.app_meta_get(db_path, "ui_lang", "de") or "de").strip().lower()[:8]
        if lg not in ("de", "en"):
            lg = "de"
    main_mod.app_meta_set(db_path, "ui_lang", lg)
    main_mod.app_meta_set(db_path, "selected_language", lg)
    if hasattr(win, "ui_lang"):
        win.ui_lang = lg
    load_tr = getattr(win, "load_translations", None)
    if callable(load_tr):
        try:
            load_tr(lg)
        except TypeError:
            try:
                load_tr()
            except Exception:
                pass
    apply_fn = getattr(win, "_apply_ui_language", None)
    if callable(apply_fn):
        try:
            apply_fn()
        except Exception:
            pass


def _force_main_tab_invisible(win: Any) -> None:
    """Logout: main_tab_widget hart unsichtbar — nur Login-Oberfläche."""
    tw = getattr(win, "tab_widget", None)
    if tw is not None:
        try:
            win.main_tab_widget = tw
        except Exception:
            pass
    mtw = getattr(win, "main_tab_widget", None)
    if mtw is not None:
        try:
            mtw.setVisible(False)
            mtw.setEnabled(False)
            mtw.hide()
        except RuntimeError:
            pass


def _hide_main_cockpit(win: Any) -> None:
    """Logout: Haupt-Cockpit (Tabs + Menü + ACARS) vollständig unsichtbar."""
    _force_main_tab_invisible(win)
    tw = getattr(win, "tab_widget", None)
    if tw is not None:
        try:
            win.main_tab_widget = tw
        except Exception:
            pass
    hidden: list[Any] = []

    def _hide_widget(w: Any) -> None:
        if w is None:
            return
        try:
            if w.isVisible():
                hidden.append(w)
            w.setVisible(False)
            w.setEnabled(False)
        except RuntimeError:
            pass

    for attr in (
        "main_tab_widget",
        "tab_widget",
        "central_host",
        "label_global_acars_ticker",
        "label_global_news_banner",
    ):
        _hide_widget(getattr(win, attr, None))
    cw = None
    try:
        cw = win.centralWidget()
    except RuntimeError:
        cw = None
    _hide_widget(cw)
    if cw is not None:
        lay = cw.layout()
        if lay is not None:
            for i in range(lay.count()):
                item = lay.itemAt(i)
                if item is None:
                    continue
                _hide_widget(item.widget())
    try:
        for tb in win.findChildren(QToolBar):
            _hide_widget(tb)
    except RuntimeError:
        pass
    mb = None
    try:
        mb = win.menuBar()
    except RuntimeError:
        mb = None
    _hide_widget(mb)
    sb = getattr(win, "statusBar", None)
    if callable(sb):
        try:
            _hide_widget(sb())
        except RuntimeError:
            pass
    win._sky_hidden_cockpit_widgets = hidden
    try:
        win.setStyleSheet("background-color:#050508;")
    except RuntimeError:
        pass


def _show_main_cockpit(win: Any) -> None:
    for w in getattr(win, "_sky_hidden_cockpit_widgets", None) or []:
        try:
            w.setEnabled(True)
            w.setVisible(True)
        except RuntimeError:
            pass
    win._sky_hidden_cockpit_widgets = []
    for attr in ("main_tab_widget", "tab_widget", "central_host"):
        tw = getattr(win, attr, None)
        if tw is not None:
            try:
                tw.setEnabled(True)
                tw.setVisible(True)
            except RuntimeError:
                pass
    cw = None
    try:
        cw = win.centralWidget()
    except RuntimeError:
        cw = None
    if cw is not None:
        try:
            cw.setEnabled(True)
            cw.setVisible(True)
        except RuntimeError:
            pass
    mb = None
    try:
        mb = win.menuBar()
    except RuntimeError:
        mb = None
    if mb is not None:
        try:
            mb.setEnabled(True)
            mb.setVisible(True)
        except RuntimeError:
            pass
    sb = getattr(win, "statusBar", None)
    if callable(sb):
        try:
            bar = sb()
            if bar is not None:
                bar.setEnabled(True)
                bar.setVisible(True)
        except RuntimeError:
            pass


class _PlatinLoginOverlay(QWidget):
    """Ersatz für fehlendes main.py login_widget — Vollbild-Login nach Logout."""

    def __init__(self, win: Any, main_mod: Any, db_path: Any, injector: Any) -> None:
        super().__init__(win)
        self._win = win
        self._m = main_mod
        self._db = db_path
        self._inj = injector
        self.setObjectName("platinLoginOverlay")
        self.setStyleSheet(
            "QWidget#platinLoginOverlay{background:#050508;}"
            "QLabel{color:#e8e8ec;font-weight:900;}"
            "QPushButton{background:#161618;color:#e8e8ec;border:2px solid #3a3a42;"
            "border-radius:10px;font-weight:800;padding:14px 28px;min-height:48px;}"
            "QPushButton:hover{background:#2c2c32;}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 48, 48, 48)
        lay.addStretch(1)
        title = QLabel("🔐 SkyTycoon Pro — Anmeldung")
        title.setStyleSheet("font-size:22px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        sub = QLabel(
            "Konto abgemeldet. Bitte erneut anmelden (Patrick.S / Portal-Konto)."
        )
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color:#90a4ae;font-weight:600;font-size:13px;")
        lay.addWidget(sub)
        lay.addSpacing(24)
        btn = QPushButton("▶ Anmelden / Login starten")
        btn.clicked.connect(self._open_auth_dialog)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(2)

    def _open_auth_dialog(self) -> None:
        _purge_session_ram_cache(self._win, self._m, self._db)
        dlg_cls = getattr(self._m, "StartupAuthDialog", None)
        if dlg_cls is None:
            return
        dlg = dlg_cls(self._db, self)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._inj._after_platin_login_success()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.setGeometry(self._win.rect())


def _ensure_platin_login_widget(
    win: Any, main_mod: Any, db_path: Any, injector: Any
) -> _PlatinLoginOverlay:
    ov = getattr(win, "_platin_login_overlay", None)
    if ov is None:
        ov = _PlatinLoginOverlay(win, main_mod, db_path, injector)
        win._platin_login_overlay = ov
    try:
        win.login_widget = ov
    except Exception:
        pass
    return ov


def _show_platin_login_surface(win: Any, main_mod: Any, db_path: Any, injector: Any) -> None:
    _hide_main_cockpit(win)
    _force_main_tab_invisible(win)
    try:
        win.show()
    except RuntimeError:
        pass
    ov = _ensure_platin_login_widget(win, main_mod, db_path, injector)
    ov.setGeometry(win.rect())
    ov.show()
    ov.raise_()
    ov.activateWindow()


def _hide_platin_login_surface(win: Any) -> None:
    ov = getattr(win, "_platin_login_overlay", None)
    if ov is not None:
        try:
            ov.hide()
        except RuntimeError:
            pass


def _unlock_six_main_hub_tabs(win: Any) -> None:
    tw = getattr(win, "tab_widget", None)
    if tw is None:
        return
    win._platin_hub_locked = False
    for attr in _HUB_TAB_IX_ATTRS:
        ix = getattr(win, attr, None)
        if isinstance(ix, int) and 0 <= ix < tw.count():
            tw.setTabEnabled(ix, True)


def _patch_startup_auth_portal_login(main_module: Any) -> None:
    """Portal-Konten: login_success ohne ST-Lizenz — kein fälschliches license_activated=1."""
    dlg_cls = getattr(main_module, "StartupAuthDialog", None)
    if dlg_cls is None or getattr(dlg_cls, "_sky_portal_login_patch", False):
        return
    orig = dlg_cls._do_login
    if not getattr(dlg_cls, "_sky_orig_accept", None):
        dlg_cls._sky_orig_accept = dlg_cls.accept

    def _accept_remember_me(self: Any) -> None:
        pending = getattr(self, "_platin_pending_login_json", None)
        _platin_persist_remember_me(
            self,
            main_module,
            self._path,
            pending if isinstance(pending, dict) else {},
        )
        self._platin_pending_login_json = None
        return dlg_cls._sky_orig_accept(self)

    dlg_cls.accept = _accept_remember_me

    def _do_login_portal_aware(self: Any) -> None:
        base = main_module.ionos_server_url()
        pilot = self.ed_login_name.text().strip()
        pw = self.ed_login_pw.text().strip()
        key = (
            self.ed_login_key.text().strip()
            if hasattr(self, "ed_login_key") and self.ed_login_key.isVisible()
            else ""
        )
        self._platin_fresh_login = True
        _clear_stale_login_identity(main_module, self._path)
        hid = _normalize_client_hwid(main_module, self._path, force_os=True)
        if not pilot or not pw or not hid:
            QMessageBox.warning(
                self,
                main_module.SKYTYCOON_APP_NAME,
                main_module._st_auth_tr(
                    self._path, "startup.auth.fill_all", "Bitte alle Felder ausfüllen."
                ),
            )
            return
        body = _desktop_auth_login_body(main_module, self._path, pilot, pw, key)
        parent_win = getattr(self, "parent_window", None) or self.parent()
        try:
            r = requests.post(
                f"{base}/api/v1/auth/login",
                json=body,
                timeout=20,
                headers={
                    "User-Agent": f"{main_module.SKYTYCOON_APP_NAME}/{main_module.APP_VERSION}",
                    "Content-Type": "application/json",
                },
                verify=main_module.auth_requests_verify_tls(),
            )
            j = r.json() if r.content else {}
        except Exception as exc:
            QMessageBox.warning(
                self,
                main_module.SKYTYCOON_APP_NAME,
                main_module._st_auth_tr(
                    self._path, "startup.auth.net_err", "Server nicht erreichbar: {e}"
                ).format(e=str(exc)),
            )
            return
        if isinstance(j, dict) and j.get("error") == "invalid JSON":
            QMessageBox.warning(
                self,
                main_module.SKYTYCOON_APP_NAME,
                "Server: Ungültige Anfrage (JSON). Bitte App neu starten oder Support.",
            )
            return
        st = str(j.get("status", ""))
        if st == "login_success" or j.get("portal_account") or j.get("is_superadmin"):
            self._platin_pending_login_json = j
        if st == "login_failed":
            detail = str(j.get("detail") or "").strip().lower()
            msg_fail = str(
                j.get("message")
                or main_module._st_auth_tr(
                    self._path,
                    "startup.auth.failed",
                    "Anmeldung fehlgeschlagen (Name, Passwort oder Hardware-ID).",
                )
            )
            if detail == "hwid_limit":
                msg_fail = str(
                    j.get("message")
                    or "Diese Hardware-ID ist bereits mit 3 Konten verknüpft."
                )
            QMessageBox.warning(self, main_module.SKYTYCOON_APP_NAME, msg_fail)
            return
        slot_ok = bool(
            j.get("hwid_slot_provisioned")
            or j.get("auto_license_activated")
            or int(j.get("has_license") or 0)
        )
        if st == "login_success" and slot_ok:
            _store_login_access_token(main_module, self._path, j)
            main_module.app_meta_set(self._path, "pilot_display_name", pilot[:120])
            main_module.app_meta_set(self._path, "pilot_name", pilot[:120])
            main_module.app_meta_set(self._path, "license_activated", "1")
            main_module.app_meta_set(self._path, "online_network_enabled", "1")
            lk_slot = str(j.get("license_key") or key or "").strip()
            if lk_slot:
                main_module.app_meta_set(
                    self._path, "license_key_installed", lk_slot[:256]
                )
            em_slot = _resolve_portal_email_from_login(pilot, j)
            if em_slot:
                main_module.app_meta_set(self._path, "portal_email", em_slot)
                main_module.app_meta_set(
                    self._path, "career_bound_portal_email", em_slot
                )
            if pw:
                main_module.cloud_password_set(self._path, pw)
            _bind_server_hardware_id(main_module, self._path, j, hid)
            try:
                cdb = main_module._conn(self._path)
                try:
                    cred = float(j.get("credits", 0) or 0)
                    xp_v = float(j.get("xp", 0) or 0)
                    cdb.execute(
                        "UPDATE pilot_stats SET credits = ?, xp = ? WHERE id = 1;",
                        (cred, xp_v),
                    )
                    cdb.commit()
                finally:
                    cdb.close()
            except Exception:
                pass
            lg_slot = str(j.get("selected_language") or j.get("ui_lang") or "de")
            if lg_slot in ("de", "en"):
                main_module.app_meta_set(self._path, "selected_language", lg_slot)
                main_module.app_meta_set(self._path, "ui_lang", lg_slot)
            if parent_win is not None:
                QTimer.singleShot(
                    0,
                    parent_win,
                    lambda w=parent_win, lg=lg_slot: _apply_desktop_language(
                        w, self._path, main_module, lg
                    ),
                )
            if parent_win is not None:
                inj = getattr(parent_win, "_platin_injector", None)
                if inj is not None:
                    parent_win._platin_fresh_cloud_sync = True
                    QTimer.singleShot(50, inj._cloud_sync_pull_async)
            _platin_login_accept(self, main_module, self._path, j)
            return
        if st == "license_required":
            em = _resolve_portal_email_from_login(pilot, j)
            if em:
                main_module.app_meta_set(self._path, "portal_email", em)
                main_module.app_meta_set(
                    self._path, "career_bound_portal_email", em
                )
            main_module.app_meta_set(self._path, "license_activated", "0")
            _bind_server_hardware_id(main_module, self._path, j, hid)
            if pw:
                main_module.cloud_password_set(self._path, pw)
            try:
                self.hide()
            except RuntimeError:
                pass
            lic_dlg = _PlatinLicenseDialog(parent_win, self._path, main_module)
            lic_dlg._lbl.setText(_license_required_bilingual_text())
            if lic_dlg.exec() == QDialog.DialogCode.Accepted:
                self._platin_pending_login_json = j
                _platin_login_accept(self, main_module, self._path, j)
            return
        if st == "login_success" and j.get("portal_account") and not int(j.get("has_license") or 0):
            _store_login_access_token(main_module, self._path, j)
            main_module.app_meta_set(self._path, "pilot_display_name", pilot[:120])
            main_module.app_meta_set(self._path, "license_activated", "0")
            main_module.app_meta_set(self._path, "drm_last_status", "portal_free")
            _bind_server_hardware_id(main_module, self._path, j, hid)
            if pw:
                main_module.cloud_password_set(self._path, pw)
            em = _resolve_portal_email_from_login(pilot, j)
            if em:
                main_module.app_meta_set(self._path, "portal_email", em)
                main_module.app_meta_set(
                    self._path, "career_bound_portal_email", em
                )
            try:
                credits_v = float(j.get("credits", 0))
                xp_v = float(j.get("xp", 0))
            except (TypeError, ValueError):
                credits_v = xp_v = None
            if credits_v is not None and xp_v is not None:
                try:
                    cdb = main_module._conn(self._path)
                    try:
                        cdb.execute(
                            "UPDATE pilot_stats SET credits = ?, xp = ? WHERE id = 1;",
                            (credits_v, xp_v),
                        )
                        cdb.commit()
                    finally:
                        cdb.close()
                except Exception:
                    pass
            lg_p = str(j.get("selected_language") or j.get("ui_lang") or "").strip().lower()[:8]
            if lg_p in ("de", "en"):
                main_module.app_meta_set(self._path, "selected_language", lg_p)
                main_module.app_meta_set(self._path, "ui_lang", lg_p)
            if parent_win is not None:
                inj = getattr(parent_win, "_platin_injector", None)
                if inj is not None:
                    parent_win._platin_fresh_cloud_sync = True
                    QTimer.singleShot(50, inj._cloud_sync_pull_async)
            _platin_login_accept(self, main_module, self._path, j)
            return
        if str(j.get("role", "")).upper() == "SUPERADMIN" or j.get("is_superadmin"):
            _store_login_access_token(main_module, self._path, j)
            main_module.app_meta_set(self._path, "portal_email", GLOBAL_SUPERADMIN_EMAIL)
            main_module.app_meta_set(self._path, "license_activated", "1")
            main_module.app_meta_set(self._path, "online_network_enabled", "1")
            main_module.app_meta_set(self._path, "platin_superadmin", "1")
            lk_sa = str(j.get("license_key") or key or "").strip()
            if lk_sa:
                main_module.app_meta_set(self._path, "license_key_installed", lk_sa[:256])
            if pw:
                main_module.cloud_password_set(self._path, pw)
            _bind_server_hardware_id(main_module, self._path, j, hid)
            lg_sa = str(j.get("selected_language") or j.get("ui_lang") or "de").strip().lower()[:8]
            if lg_sa in ("de", "en"):
                main_module.app_meta_set(self._path, "selected_language", lg_sa)
                main_module.app_meta_set(self._path, "ui_lang", lg_sa)
            _platin_login_accept(self, main_module, self._path, j)
            return
        if st == "login_success" and (
            int(j.get("has_license") or 0) or j.get("auto_license_activated")
        ):
            _store_login_access_token(main_module, self._path, j)
            main_module.app_meta_set(self._path, "license_activated", "1")
            lk_ok = str(j.get("license_key") or key or "").strip()
            if lk_ok:
                main_module.app_meta_set(
                    self._path, "license_key_installed", lk_ok[:256]
                )
            em_ok = _resolve_portal_email_from_login(pilot, j)
            if em_ok:
                main_module.app_meta_set(self._path, "portal_email", em_ok)
                main_module.app_meta_set(
                    self._path, "career_bound_portal_email", em_ok
                )
            if pw:
                main_module.cloud_password_set(self._path, pw)
            _bind_server_hardware_id(main_module, self._path, j, hid)
            lg_ok = str(j.get("selected_language") or j.get("ui_lang") or "de").strip().lower()[:8]
            if lg_ok in ("de", "en"):
                main_module.app_meta_set(self._path, "selected_language", lg_ok)
                main_module.app_meta_set(self._path, "ui_lang", lg_ok)
        if st == "login_success":
            _store_login_access_token(main_module, self._path, j)
            main_module.app_meta_set(self._path, "pilot_display_name", pilot[:120])
            main_module.app_meta_set(self._path, "pilot_name", pilot[:120])
            if pw:
                main_module.cloud_password_set(self._path, pw)
            _bind_server_hardware_id(main_module, self._path, j, hid)
            if (
                j.get("hwid_slot_provisioned")
                or j.get("auto_license_activated")
                or int(j.get("has_license") or 0)
            ):
                main_module.app_meta_set(self._path, "license_activated", "1")
                main_module.app_meta_set(self._path, "online_network_enabled", "1")
                lk_any = str(j.get("license_key") or key or "").strip()
                if lk_any:
                    main_module.app_meta_set(
                        self._path, "license_key_installed", lk_any[:256]
                    )
            lg_any = str(j.get("selected_language") or j.get("ui_lang") or "").strip().lower()[:8]
            if lg_any in ("de", "en"):
                main_module.app_meta_set(self._path, "selected_language", lg_any)
                main_module.app_meta_set(self._path, "ui_lang", lg_any)
            if parent_win is not None:
                _show_main_cockpit(parent_win)
                inj = getattr(parent_win, "_platin_injector", None)
                if inj is not None:
                    parent_win._platin_fresh_cloud_sync = True
                    QTimer.singleShot(50, inj._cloud_sync_pull_async)
            _platin_login_accept(self, main_module, self._path, j)
            return
        if st == "hardware_mismatch":
            rebind = self._try_pc_hardware_rebind_login(pilot, pw, key)
            if rebind:
                self._platin_pending_login_json = rebind
                _bind_server_hardware_id(main_module, self._path, rebind, hid)
                main_module.app_meta_set(self._path, "license_activated", "1")
                main_module.app_meta_set(self._path, "pilot_display_name", pilot[:120])
                if pw:
                    main_module.cloud_password_set(self._path, pw)
                _platin_login_accept(self, main_module, self._path, rebind)
                return
        main_module.app_meta_set(self._path, "ionos_jwt", "")
        return orig(self)

    dlg_cls._do_login = _do_login_portal_aware
    dlg_cls._sky_portal_login_patch = True


def _patch_update_check_once(main_mod: Any) -> None:
    """Update-Dialog nur beim Splash (vor Login) — niemals im Cockpit/Hauptmenü."""
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_sky_update_patch", False):
        return
    orig_schedule = win_cls._schedule_update_check
    orig_show = getattr(win_cls, "_show_update_available_dialog", None)

    def _schedule_update_check_patched(self: Any, force: bool = False) -> None:
        return

    def _show_update_available_dialog_patched(
        self: Any, remote: Any, dl: Any, extra_ln: Any, mandatory: Any, changelog: Any
    ) -> None:
        if getattr(self, "_platin_auth_gate_done", False) or _PLATIN_PREMAIN_AUTH_OK:
            return
        if getattr(self, "_platin_injector", None) is not None:
            return
        if callable(orig_show):
            return orig_show(self, remote, dl, extra_ln, mandatory, changelog)

    win_cls._schedule_update_check = _schedule_update_check_patched
    win_cls._show_update_available_dialog = _show_update_available_dialog_patched
    orig_net = win_cls._on_network_finished

    def _on_network_finished_patched(self: Any, reply: Any) -> None:
        try:
            kind = reply.property("kind")
        except RuntimeError:
            kind = None
        if kind == "update_check" and (
            getattr(self, "_platin_auth_gate_done", False) or _PLATIN_PREMAIN_AUTH_OK
        ):
            try:
                self._update_check_inflight = False
            except Exception:
                pass
            try:
                reply.deleteLater()
            except RuntimeError:
                pass
            return
        return orig_net(self, reply)

    win_cls._on_network_finished = _on_network_finished_patched
    win_cls._sky_update_patch = True


def _runtime_main_modules() -> list[Any]:
    """python main.py läuft als __main__ — Patches müssen dort landen, nicht nur import main."""
    import sys

    seen: list[int] = []
    out: list[Any] = []
    for name in ("__main__", "main"):
        mod = sys.modules.get(name)
        if mod is None or id(mod) in seen:
            continue
        seen.append(id(mod))
        out.append(mod)
    return out


def _install_platin_coldstart_guards() -> bool:
    """Splash-Update + Pre-DRM blockieren, bis Login fertig ist."""
    patched_any = False
    for main_mod in _runtime_main_modules():
        if getattr(main_mod, "_platin_coldstart_guards", False):
            patched_any = True
            continue
        if not getattr(main_mod, "check_for_updates", None):
            continue
        if not getattr(main_mod, "run_startup_update_gate", None):
            continue

        _orig_check = main_mod.check_for_updates
        _orig_gate = main_mod.run_startup_update_gate
        _orig_cloud = main_mod.run_startup_cloud_security_and_updates
        _orig_drm = main_mod.ionos_drm_gate_run

        def check_for_updates_platin(
            path: Any,
            parent: Any = None,
            global_cfg: Any = None,
            *,
            _oc: Any = _orig_check,
        ) -> bool:
            if _PLATIN_BLOCK_STARTUP_POPUPS:
                return True
            return _oc(path, parent, global_cfg)

        def run_startup_update_gate_platin(
            path: Any,
            parent: Any = None,
            global_cfg: Any = None,
            *,
            _og: Any = _orig_gate,
        ) -> bool:
            if _PLATIN_BLOCK_STARTUP_POPUPS:
                return True
            return _og(path, parent, global_cfg)

        def run_startup_cloud_security_platin(
            path: Any,
            parent: Any = None,
            *,
            network: bool = True,
            _mm: Any = main_mod,
            _oc: Any = _orig_check,
        ) -> tuple[bool, str]:
            cfg = _mm.fetch_global_config_merged(path, network=network)
            _mm.apply_global_config_cloud_to_meta(path, cfg)
            blocked, msg = _mm.is_launch_blocked_by_cloud_or_license(path, cfg)
            if blocked:
                return False, msg
            stale_b, stale_m = _mm.is_offline_cloud_stale_blocked(path)
            if stale_b:
                return False, stale_m
            global _PLATIN_SPLASH_UPDATE_ONCE, _PLATIN_BLOCK_STARTUP_POPUPS
            if _PLATIN_SPLASH_UPDATE_ONCE:
                _PLATIN_SPLASH_UPDATE_ONCE = False
                prev_block = _PLATIN_BLOCK_STARTUP_POPUPS
                _PLATIN_BLOCK_STARTUP_POPUPS = False
                try:
                    if not _oc(path, parent, cfg):
                        return False, _mm.i18n_db(
                            path,
                            "update.aborted",
                            "Start abgebrochen (Update erforderlich oder beendet).",
                        )
                finally:
                    _PLATIN_BLOCK_STARTUP_POPUPS = prev_block
                return True, ""
            if _PLATIN_BLOCK_STARTUP_POPUPS:
                return True, ""
            if not _oc(path, parent, cfg):
                return False, _mm.i18n_db(
                    path,
                    "update.aborted",
                    "Start abgebrochen (Update erforderlich oder beendet).",
                )
            return True, ""

        def ionos_drm_gate_platin(
            path: Any,
            *,
            _od: Any = _orig_drm,
        ) -> tuple[bool, str]:
            if _PLATIN_BLOCK_STARTUP_POPUPS:
                return True, "platin_deferred_login"
            return _od(path)

        main_mod.check_for_updates = check_for_updates_platin
        main_mod.run_startup_update_gate = run_startup_update_gate_platin
        main_mod.run_startup_cloud_security_and_updates = run_startup_cloud_security_platin
        main_mod.ionos_drm_gate_run = ionos_drm_gate_platin
        main_mod._platin_coldstart_guards = True
        patched_any = True
    return patched_any


def platin_prepare_coldstart() -> None:
    """Vor Splash/Update: Riegel auf __main__ + main (idempotent)."""
    global _PLATIN_BLOCK_STARTUP_POPUPS
    _PLATIN_BLOCK_STARTUP_POPUPS = True
    _install_platin_coldstart_guards()
    mods = _runtime_main_modules()
    if mods:
        _platin_bind_dynamic_project_roots(mods[0])
    _platin_apply_patches_to_runtime_modules()


def _run_standalone_startup_auth(main_mod: Any, db_path: Any) -> bool:
    """Login vor MainWindow — kein Splash-Freeze, kein Dialog-Stapel."""
    global _PLATIN_BLOCK_STARTUP_POPUPS, _PLATIN_PREMAIN_AUTH_OK
    dlg_cls = getattr(main_mod, "StartupAuthDialog", None)
    if dlg_cls is None:
        return False
    _PLATIN_BLOCK_STARTUP_POPUPS = True
    dlg = dlg_cls(db_path, None)
    _prepare_startup_auth_dialog(dlg, main_mod)
    has_saved = _prepare_startup_auth_remember_prefill(dlg, main_mod, db_path)
    if has_saved and getattr(dlg, "b_login", None) is not None:

        def _auto_login() -> None:
            try:
                if dlg.isVisible():
                    dlg.b_login.click()
            except RuntimeError:
                pass

        QTimer.singleShot(600, _auto_login)
    accepted = dlg.exec() == QDialog.DialogCode.Accepted
    if accepted:
        pending = getattr(dlg, "_platin_pending_login_json", None)
        _platin_persist_remember_me(
            dlg,
            main_mod,
            db_path,
            pending if isinstance(pending, dict) else {},
        )
    try:
        dlg.deleteLater()
    except RuntimeError:
        pass
    if not accepted:
        return False
    _PLATIN_BLOCK_STARTUP_POPUPS = False
    _PLATIN_PREMAIN_AUTH_OK = True
    return True


def platin_pre_mainwindow_login(db_path: Any) -> bool:
    """Einziges Fenster vor dem Cockpit-Aufbau."""
    mods = _runtime_main_modules()
    main_mod = mods[0] if mods else None
    if main_mod is None:
        try:
            import main as main_mod
        except Exception:
            return False
    platin_prepare_coldstart()
    _platin_apply_patches_to_runtime_modules()
    if _PLATIN_PREMAIN_AUTH_OK:
        return True
    return _run_standalone_startup_auth(main_mod, db_path)


def _patch_live_cabin_soundboard(main_mod: Any) -> None:
    """Ersetzt _play_key_qsound + play_key — Qt-Slots mit *args/**kwargs, pygame zuerst."""
    cls = getattr(main_mod, "LiveCabinSoundboard", None)
    if cls is None:
        return
    if getattr(cls, "_platin_audio_patch", False):
        return

    def _play_key_qsound_platin(self: Any, path: Any) -> bool:
        path_str = str(Path(path).resolve()).replace("\\", "/")
        vol = max(
            PLATIN_CABIN_DEFAULT_VOL / 100.0,
            float(getattr(self, "volume", 0.75) or 0.75),
        )

        def _fire() -> None:
            try:
                if self._qsfx.isLoaded():
                    self._qsfx.setVolume(vol)
                    self._qsfx.play()
            except RuntimeError:
                pass

        def _on_status(*args: Any, **kwargs: Any) -> None:
            _fire()
            try:
                self._qsfx.statusChanged.disconnect(_on_status)
            except (RuntimeError, TypeError):
                pass

        try:
            self._qsfx.stop()
            url = QUrl.fromLocalFile(path_str)
            if url.isEmpty():
                return False
            self._qsfx.setSource(url)
            self._qsfx.setVolume(vol)
            try:
                self._qsfx.statusChanged.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._qsfx.statusChanged.connect(_on_status)
            if self._qsfx.isLoaded():
                _fire()
                return True
            return True
        except Exception:
            return False

    def play_key_platin(self: Any, key: str) -> bool:
        path = self.resolve_path(key)
        if path is None or not path.is_file():
            return False
        if not _cabin_audio_is_real(path) and path.suffix.lower() == ".wav":
            lo = "en" if str(self.lang).lower().startswith("en") else "de"
            g = (
                "male"
                if str(self.gender).lower() in ("male", "m", "männlich", "man")
                else "female"
            )
            phrase = PLATIN_CABIN_TTS_SCRIPTS.get(key, {}).get(lo, {}).get(g, "")
            if phrase:
                _tts_windows_generate_wav(phrase, path, gender=g)
        pygame_mod = getattr(main_mod, "pygame", None)
        if pygame_mod is not None:
            if not getattr(self, "_ready", False):
                try:
                    self._init_mixer()
                except Exception:
                    pass
            if getattr(self, "_ready", False):
                try:
                    if self._current is not None:
                        try:
                            self._current.stop()
                        except Exception:
                            pass
                    snd = pygame_mod.mixer.Sound(str(path.resolve()))
                    snd.set_volume(vol := max(PLATIN_CABIN_DEFAULT_VOL / 100.0, float(self.volume or 0.75)))
                    snd.play()
                    self._current = snd
                    return True
                except Exception:
                    pass
        return _play_key_qsound_platin(self, path)

    cls._play_key_qsound = _play_key_qsound_platin
    cls.play_key = play_key_platin
    cls._platin_audio_patch = True


def _patch_gsx_start_handling(main_mod: Any) -> None:
    """GSX-Bodenabfertigung: SimConnect-Sequenz statt nur Cloud-Hinweis."""
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_platin_gsx_start_patch", False):
        return
    orig = win_cls._on_gsx_start_handling_clicked

    def _on_gsx_start_handling_patched(self: Any) -> None:
        inj = getattr(self, "_platin_injector", None)
        if inj is not None:
            inj._gsx_start_full_handling_async()
        orig(self)

    win_cls._on_gsx_start_handling_clicked = _on_gsx_start_handling_patched
    win_cls._platin_gsx_start_patch = True


def _patch_platin_meta_crash_shield(main_mod: Any) -> None:
    """app_meta / Cloud-Schema — verhindert GUI-Absturz bei leerer Session-DB."""
    if getattr(main_mod, "_platin_meta_crash_shield", False):
        return
    if not hasattr(main_mod, "init_database"):
        return
    try:
        from platin_cloud_only import (
            hydrate_platin_credentials_from_disk,
            install_platin_cloud_only,
            patch_mainwindow_cloud_guard,
            platin_meta_get_safe,
            platin_meta_set_safe,
        )

        install_platin_cloud_only(main_mod)
        patch_mainwindow_cloud_guard(main_mod)
    except Exception as exc:
        print(f"[SkyTycoon] Cloud-Only: {exc!s}", flush=True)

    def safe_app_meta_get(path: Any, key: str, default: str = "") -> str:
        try:
            from platin_cloud_only import (
                hydrate_platin_credentials_from_disk,
                platin_meta_get_safe,
            )

            hydrate_platin_credentials_from_disk(main_mod)
            return platin_meta_get_safe(main_mod, key, default)
        except Exception:
            return default

    def safe_app_meta_set(path: Any, key: str, value: str) -> None:
        try:
            from platin_cloud_only import platin_meta_set_safe

            platin_meta_set_safe(main_mod, key, value)
        except Exception:
            pass

    main_mod.app_meta_get = safe_app_meta_get
    main_mod.app_meta_set = safe_app_meta_set

    if hasattr(main_mod, "cloud_password_get"):
        _orig_cpw = main_mod.cloud_password_get

        def safe_cloud_password_get(path: Any) -> str:
            try:
                from platin_cloud_only import platin_meta_get_safe

                return (
                    platin_meta_get_safe(main_mod, "cloud_backup_password", "")
                    or platin_meta_get_safe(main_mod, "cloud_sync_password", "")
                    or _orig_cpw(path)
                )
            except Exception:
                return ""

        main_mod.cloud_password_get = safe_cloud_password_get

    if hasattr(main_mod, "ionos_auth_headers"):
        _orig_ionos = main_mod.ionos_auth_headers

        def safe_ionos_auth_headers(path: Any) -> dict[str, str]:
            try:
                from platin_cloud_only import platin_meta_get_safe

                tok = platin_meta_get_safe(main_mod, "ionos_jwt", "")
                if tok:
                    return {"Authorization": f"Bearer {tok}"}
                return _orig_ionos(path)
            except Exception:
                return {}

        main_mod.ionos_auth_headers = safe_ionos_auth_headers

    main_mod._platin_meta_crash_shield = True


def _patch_branding_live_stamp_flood_guard(main_mod: Any) -> None:
    """Verhindert Hunderttausende ✓ LIVE-Zeilen (GUI-Freeze/Absturz)."""
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None:
        return
    if getattr(win_cls, "_platin_stamp_flood_guard", False):
        return

    orig_stamp = win_cls._stamp_runtime_build_marker
    orig_title = win_cls._apply_branded_window_title
    orig_brand_ui = win_cls._refresh_branding_ui
    orig_brand = win_cls.update_airline_branding
    orig_logo = getattr(win_cls, "force_absolute_logo_render", None)

    def _stamp_runtime_build_marker_safe(self: Any) -> None:
        if getattr(self, "_platin_live_console_printed", False):
            return
        self._platin_live_console_printed = True
        try:
            orig_stamp(self)
        except Exception:
            pass

    def _apply_branded_window_title_safe(self: Any) -> None:
        now = time.monotonic()
        if now - float(getattr(self, "_platin_title_mono", 0.0) or 0.0) < 1.5:
            return
        self._platin_title_mono = now
        try:
            orig_title(self)
        except Exception:
            pass
        try:
            em = (
                main_mod.app_meta_get(main_mod.DB_PATH, "portal_email", "") or ""
            ).strip()
            if em and "@" in em and hasattr(self, "setWindowTitle"):
                airline = (
                    main_mod.app_meta_get(
                        main_mod.DB_PATH, "selected_airline_name", ""
                    )
                    or ""
                ).strip() or "Airline"
                self.setWindowTitle(f"{em} · SkyTycoon Pro – {airline}")
        except Exception:
            pass

    def _refresh_branding_ui_safe(self: Any) -> None:
        now = time.monotonic()
        if now - float(getattr(self, "_platin_brand_ui_mono", 0.0) or 0.0) < 0.6:
            return
        self._platin_brand_ui_mono = now
        try:
            orig_brand_ui(self)
        except Exception:
            pass
        try:
            _platin_apply_cockpit_identity(self, main_mod, main_mod.DB_PATH)
        except Exception:
            pass

    def update_airline_branding_safe(self: Any) -> None:
        now = time.monotonic()
        if now - float(getattr(self, "_platin_brand_mono", 0.0) or 0.0) < 0.6:
            return
        self._platin_brand_mono = now
        try:
            orig_brand(self)
        except Exception:
            pass

    def force_absolute_logo_render_safe(self: Any) -> None:
        now = time.monotonic()
        if now - float(getattr(self, "_platin_logo_mono", 0.0) or 0.0) < 0.35:
            return
        self._platin_logo_mono = now
        if callable(orig_logo):
            try:
                orig_logo(self)
            except Exception:
                pass

    win_cls._stamp_runtime_build_marker = _stamp_runtime_build_marker_safe
    win_cls._apply_branded_window_title = _apply_branded_window_title_safe
    win_cls._refresh_branding_ui = _refresh_branding_ui_safe
    win_cls.update_airline_branding = update_airline_branding_safe
    if callable(orig_logo):
        win_cls.force_absolute_logo_render = force_absolute_logo_render_safe
    win_cls._platin_stamp_flood_guard = True


def _patch_post_show_init_safe(main_mod: Any) -> None:
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_platin_post_show_patch", False):
        return
    orig = win_cls._run_post_show_init

    def _run_post_show_init_safe(self: Any) -> None:
        try:
            orig(self)
        except Exception as exc:
            print(f"[SkyTycoon] post_show_init abgefangen: {exc!s}", flush=True)

    win_cls._run_post_show_init = _run_post_show_init_safe
    win_cls._platin_post_show_patch = True


def _patch_platin_injector_ui_lang_safe() -> None:
    if getattr(_PlatinInjector, "_platin_ui_lang_patch", False):
        return
    orig = _PlatinInjector._ui_lang_en

    def _ui_lang_en_safe(self: Any) -> bool:
        try:
            return bool(orig(self))
        except Exception:
            return False

    _PlatinInjector._ui_lang_en = _ui_lang_en_safe
    _PlatinInjector._platin_ui_lang_patch = True


def patch_admin_commander_platin(win: Any | None = None) -> None:
    """Admin Commander: Cyber-Blue + Scroll-Dampfwalze (optional Fenster-Instanz)."""
    try:
        import Admin_Commander as ac_mod
    except ImportError:
        return
    ac_mod.apply_platin_cyber_blue_chrome(win)


def _platin_apply_patches_to_runtime_modules() -> list[Any]:
    """Alle Patches auf __main__ und import main (python main.py Duplikat-Modul)."""
    mods = _runtime_main_modules()
    for main_mod in mods:
        if not hasattr(main_mod, "init_database"):
            continue
        _platin_bind_dynamic_project_roots(main_mod)
        _patch_platin_meta_crash_shield(main_mod)
        _patch_branding_live_stamp_flood_guard(main_mod)
        _patch_post_show_init_safe(main_mod)
        _patch_platin_injector_ui_lang_safe()
        _patch_kill_offline_setup_wizard(main_mod)
        _patch_startup_auth_iceblue_ui(main_mod)
        _patch_startup_auth_portal_login(main_mod)
        _inject_startup_auth_remember_checkbox(main_mod)
        _patch_live_cabin_soundboard(main_mod)
        _patch_update_check_once(main_mod)
        _patch_fids_live_board_fetch(main_mod)
        _patch_cloud_jobs_gzip_nam(main_mod)
        _patch_job_board_charter_lazy(main_mod)
        _patch_premium_kundenkonto_dialog_logout(main_mod)
        _patch_gsx_start_handling(main_mod)
        _patch_profile_tab_hide_license(main_mod)
        _patch_job_board_haul_filters(main_mod)
        _patch_crew_refresh_safe(main_mod)
        from platin_career_layout import patch_career_original_layout

        patch_career_original_layout(main_mod)
        db = getattr(main_mod, "DB_PATH", None)
        if db is not None:
            _patch_main_cloud_api_urls(main_mod, db)
        _patch_simconnect_telemetry_regulation(main_mod)
    return mods


def _patch_profile_tab_hide_license(main_mod: Any) -> None:
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_platin_prof_license_patch", False):
        return
    orig = win_cls._refresh_profile_tab

    def _refresh_profile_tab_patched(self: Any) -> None:
        lic = getattr(self, "label_prof_license", None)
        if lic is not None:
            lic.hide()
        orig(self)
        if lic is not None:
            lic.hide()

    win_cls._refresh_profile_tab = _refresh_profile_tab_patched
    win_cls._platin_prof_license_patch = True


def _platin_scroll_wrap(content: QWidget) -> QWidget:
    shell = QWidget()
    outer = QVBoxLayout(shell)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet(SKY_DARK_SCROLL_CSS)
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)
    return shell


def _patch_job_board_haul_filters(main_mod: Any) -> None:
    """Kurz/Langstrecke 1500 NM, keine lokalen Aufträge in Cargo/Charter, Kabinen-Preview aus."""
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_platin_job_haul_patch", False):
        return
    orig_filtered = win_cls._filtered_jobs
    orig_tab_chg = win_cls._on_job_board_tab_changed
    orig_cabin = win_cls._refresh_cabin_preview
    orig_current = win_cls._current_job_filter

    def _job_tab_orig_index(win: Any, index: int) -> int:
        if getattr(win, "_platin_local_tab_removed", False) and index >= 3:
            return index + 1
        return index

    def _current_job_filter_platin(self: Any) -> str:
        if getattr(self, "_platin_short_haul_main_active", False):
            return main_mod.JOB_FILTER_ALL
        if not hasattr(self, "job_board_tabs"):
            return main_mod.JOB_FILTER_ALL
        idx = self.job_board_tabs.currentIndex()
        if getattr(self, "_platin_local_tab_removed", False):
            if idx == 0:
                return main_mod.JOB_FILTER_PAX
            if idx == 1:
                return main_mod.JOB_FILTER_CARGO
            if idx == 2:
                return main_mod.JOB_FILTER_HUBS
            return main_mod.JOB_FILTER_ALL
        return orig_current(self)

    def _filtered_jobs_platin(self: Any) -> list[dict]:
        jobs = orig_filtered(self)
        thr = PLATIN_HAUL_NM_THRESHOLD
        if getattr(self, "_platin_short_haul_main_active", False):
            return [
                j
                for j in jobs
                if float(j.get("dist_nm", 0) or 0) < thr
                and not j.get("local_pickup")
            ]
        if not hasattr(self, "job_board_tabs"):
            return jobs
        idx = self.job_board_tabs.currentIndex()
        if getattr(self, "_platin_local_tab_removed", False):
            if idx == 0:
                jobs = [
                    j
                    for j in jobs
                    if float(j.get("dist_nm", 0) or 0) >= thr
                    and str(j.get("typ", "")).upper() == "PAX"
                ]
            elif idx in (1, 4):
                jobs = [j for j in jobs if not j.get("local_pickup")]
                if idx == 1:
                    jobs = [
                        j
                        for j in jobs
                        if str(j.get("typ", "")).upper() in ("CARGO", "AIRCARGO")
                    ]
        else:
            if idx == 0:
                jobs = [
                    j
                    for j in jobs
                    if float(j.get("dist_nm", 0) or 0) >= thr
                    and str(j.get("typ", "")).upper() == "PAX"
                ]
            elif idx in (1, 5):
                jobs = [j for j in jobs if not j.get("local_pickup")]
        return jobs

    def _refresh_cabin_preview_platin(self: Any, job: Any = None) -> None:
        return

    def _on_job_board_tab_changed_platin(self: Any, index: int) -> None:
        orig_tab_chg(self, _job_tab_orig_index(self, index))

    win_cls._filtered_jobs = _filtered_jobs_platin
    win_cls._current_job_filter = _current_job_filter_platin
    win_cls._refresh_cabin_preview = _refresh_cabin_preview_platin
    win_cls._on_job_board_tab_changed = _on_job_board_tab_changed_platin
    win_cls._platin_job_haul_patch = True


def _patch_crew_refresh_safe(main_mod: Any) -> None:
    """news_timer → _refresh_crew_ui: gelöschtes QLabel (Tab-Rebuild) abfangen."""
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_platin_crew_class_patch", False):
        return
    orig = win_cls._refresh_crew_ui

    def _refresh_crew_ui_safe(self: Any) -> None:
        lbl = getattr(self, "label_crew_status", None)
        if lbl is None:
            return
        try:
            from shiboken6 import isValid

            if not isValid(lbl):
                return
        except Exception:
            try:
                _ = lbl.objectName()
            except RuntimeError:
                return
        try:
            orig(self)
        except RuntimeError:
            pass

    win_cls._refresh_crew_ui = _refresh_crew_ui_safe
    win_cls._platin_crew_class_patch = True


def _platin_reset_ui_flags(win: Any) -> None:
    """Neuer Build → UI-Injektionen erneut ausführen."""
    for attr in (
        "_platin_post_auth_boot_done",
        "_platin_run_armed",
        "_platin_hangar_restructured",
        "_platin_career_profit_done",
        "_platin_wallstreet_moved",
        "_platin_cabin_preview_nuked",
        "_platin_local_tab_removed",
        "_platin_scroll_armor_done",
        "_platin_hangar_layout_fix",
        "_platin_short_haul_tab_ix",
        "_platin_short_haul_tab_hook",
        "_platin_alliance_tabs",
        "_platin_p2p_market_page",
        "_platin_portal_btns",
        "_platin_gsx_remote",
        "_platin_gsx_start_patch",
        "_platin_career_layout_restored",
        "_platin_alliance_13_installed",
        "_platin_crew_layout_fixed",
        "_platin_zero_lazy_installed",
        "_platin_lazy_materialized",
        "_sky_jobs_gzip_patch",
        "_sky_charter_lazy_patch",
    ):
        try:
            delattr(win, attr)
        except AttributeError:
            setattr(win, attr, None if attr.endswith("_ix") else False)


def _platin_stamp_window_title(win: Any) -> None:
    try:
        base = str(win.windowTitle() or "")
        tag = f"· Platin {PLATIN_BUILD[-8:]}"
        if tag not in base:
            win.setWindowTitle(f"{base} {tag}".strip())
    except RuntimeError:
        pass


def _platin_nam_gzip_headers(req: Any) -> Any:
    """Accept-Encoding für kleinere Job-JSON-Pakete (QNAM dekomprimiert gzip)."""
    try:
        req.setRawHeader(b"Accept-Encoding", b"gzip, deflate")
    except (RuntimeError, AttributeError):
        pass
    return req


def _patch_cloud_jobs_gzip_nam(main_mod: Any) -> None:
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_sky_jobs_gzip_patch", False):
        return

    def _request_cloud_jobs_global_fallback_gzip(self: Any) -> None:
        if "dispatch" not in getattr(self, "_platin_lazy_materialized", set()):
            inj = getattr(self, "_platin_injector", None)
            if inj is not None:
                inj._ensure_lazy_vault()
                inj._lazy_materialize_dispatch()
        if getattr(self, "_cloud_jobs_fetch_inflight", False):
            return
        base = main_mod.ionos_api_base_url().strip().rstrip("/")
        if not base:
            return
        self._cloud_jobs_fetch_inflight = True
        if hasattr(self, "label_job_cloud_status"):
            self.label_job_cloud_status.setText(
                self._tr(
                    "job.cloud_global_loading",
                    "Lade weltweiten Cloud-Markt (Fallback)…",
                )
            )
        url = f"{base}/api/v1/jobs/available?current_icao=ALL"
        if getattr(self, "_platin_short_haul_main_active", False):
            url += "&haul=short"
        elif getattr(self, "_platin_long_haul_main_active", False):
            url += "&haul=long"
        from PySide6.QtNetwork import QNetworkRequest
        from PySide6.QtCore import QUrl

        req = _platin_nam_gzip_headers(QNetworkRequest(QUrl(url)))
        rep = self._nam.get(req)
        rep.setProperty("kind", "cloud_jobs_fetch")
        rep.setProperty("cloud_icao", "ALL")
        rep.setProperty("cloud_global_fallback", True)

    win_cls._request_cloud_jobs_global_fallback = _request_cloud_jobs_global_fallback_gzip
    win_cls._sky_jobs_gzip_patch = True


def _platin_lazy_placeholder(inj: Any, key: str) -> QWidget:
    w = QWidget()
    w.setObjectName(f"platinLazyShell_{key}")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(12, 24, 12, 24)
    tip = inj._tr(
        f"platin.lazy.{key}",
        "Tab wird beim ersten Öffnen geladen…",
    )
    lbl = QLabel(tip)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color:#8ac7ff;font-size:13px;font-weight:600;")
    lay.addStretch(1)
    lay.addWidget(lbl)
    lay.addStretch(1)
    return w


def _platin_lazy_take_from_scroll(scroll: QScrollArea) -> QWidget | None:
    if not isinstance(scroll, QScrollArea):
        return None
    child = scroll.widget()
    if child is None:
        return None
    scroll.takeWidget()
    return child


def _patch_job_board_charter_lazy(main_mod: Any) -> None:
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_sky_charter_lazy_patch", False):
        return
    orig = win_cls._on_job_board_tab_changed

    def _on_job_board_tab_changed_lazy(self: Any, index: int) -> None:
        if index == 4:
            inj = getattr(self, "_platin_injector", None)
            if inj is not None:
                inj._lazy_materialize_charter()
        orig(self, index)

    win_cls._on_job_board_tab_changed = _on_job_board_tab_changed_lazy
    win_cls._sky_charter_lazy_patch = True


def _patch_fids_live_board_fetch(main_mod: Any) -> None:
    """FIDS-Tafel: GET /api/v1/web/radar/positions von skytycoon.info (QThreadPool, kein Cache)."""
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_sky_fids_fetch_patch", False):
        return
    orig_fetch = win_cls.fetch_global_online_pilots_fids

    def fetch_global_online_pilots_fids_patched(self: Any) -> None:
        inj = getattr(self, "_platin_injector", None)
        if inj is not None:
            inj._fids_fetch_live_async()
            return
        orig_fetch(self)

    win_cls.fetch_global_online_pilots_fids = fetch_global_online_pilots_fids_patched
    win_cls._sky_fids_fetch_patch = True


def _patch_premium_kundenkonto_dialog_logout(main_mod: Any) -> None:
    """Logout-Button im Fenster „Kundenkonto“ (PremiumKundenkontoDialog)."""
    dlg_cls = getattr(main_mod, "PremiumKundenkontoDialog", None)
    if dlg_cls is None or getattr(dlg_cls, "_sky_logout_dialog_patch", False):
        return
    orig_build = dlg_cls._build_ui

    def _build_ui_with_logout(self: Any) -> None:
        orig_build(self)
        inj = getattr(self._mw, "_platin_injector", None)
        lay = self.layout()
        if lay is None or inj is None:
            return
        if getattr(self, "_platin_logout_btn", None) is not None:
            return
        default_lbl = "[ 🔓 Konto abmelden / Logout ]"
        btn = QPushButton(inj._tr("platin.auth.logout", default_lbl))
        btn.setObjectName("platinLogoutBtn")
        btn.setStyleSheet(
            "QPushButton#platinLogoutBtn { background:#161618; color:#e8e8ec; "
            "border:3px solid #3a3a42; font-weight:900; padding:14px 20px; "
            "border-radius:10px; min-height:44px; }"
            "QPushButton#platinLogoutBtn:hover { background:#2c2c32; }"
        )
        btn.clicked.connect(inj._on_logout_clicked)
        reg = getattr(self._mw, "_i18n_register", None)
        if callable(reg):
            reg(btn, "platin.auth.logout", default_lbl)
        self._platin_logout_btn = btn
        idx = max(0, lay.count() - 1)
        lay.insertWidget(idx, btn, alignment=Qt.AlignmentFlag.AlignHCenter)

    dlg_cls._build_ui = _build_ui_with_logout
    dlg_cls._sky_logout_dialog_patch = True


def inject_platin_features(main_window: Any) -> None:
    build_mismatch = getattr(main_window, "_platin_build", None) != PLATIN_BUILD
    if build_mismatch:
        main_window._platin_injected = False
        _platin_reset_ui_flags(main_window)
        for _m_reset in _runtime_main_modules():
            dlg_cls = getattr(_m_reset, "StartupAuthDialog", None)
            if dlg_cls is not None:
                dlg_cls._sky_portal_login_patch = False
                dlg_cls._sky_remember_me_patch = False
                dlg_cls._sky_orig_accept = None
            sb_cls = getattr(_m_reset, "LiveCabinSoundboard", None)
            if sb_cls is not None:
                sb_cls._platin_audio_patch = False
            win_cls = getattr(_m_reset, "MainWindow", None)
            if win_cls is not None:
                win_cls._sky_update_patch = False
                win_cls._platin_gsx_start_patch = False
                win_cls._platin_crew_class_patch = False

    print(
        f"[SkyTycoon] Platin {PLATIN_BUILD} — Karriere-CEO-Panel aktiv.",
        flush=True,
    )

    platin_prepare_coldstart()
    _install_platin_coldstart_guards()
    _platin_apply_patches_to_runtime_modules()
    _platin_stamp_window_title(main_window)

    if getattr(main_window, "_platin_injected", False) and not build_mismatch:
        _platin_apply_patches_to_runtime_modules()
        inj = getattr(main_window, "_platin_injector", None)
        if inj is not None:
            QTimer.singleShot(200, inj._force_reapply_ui_layouts)
        return

    main_window._platin_injected = True
    main_window._platin_build = PLATIN_BUILD
    _init_platin_ram_cache(main_window)
    _apply_platin_global_dark_theme(main_window)
    try:
        main_window.setStyleSheet(_PLATIN_GLOBAL_DARK_STYLE)
    except RuntimeError:
        pass
    inj = _PlatinInjector(main_window)
    main_window._platin_injector = inj
    _apply_platin_global_dark_theme(main_window)
    if _PLATIN_PREMAIN_AUTH_OK:
        main_window._platin_auth_gate_done = True
        main_window._platin_coldstart_login_complete = True
        main_window._platin_license_trusted = True
        main_window._platin_license_prompt_block_until = time.time() + 86400.0

    def _arm_platin_ui() -> None:
        if getattr(main_window, "_platin_run_armed", False):
            return
        main_window._platin_run_armed = True
        inj.run()

    # Cockpit-Injektion nach __init__ (tab_widget existiert dann).
    QTimer.singleShot(0, _arm_platin_ui)


def platin_gsx_simconnect_handling(main_window: Any) -> None:
    """GSX-Bodenabfertigung in MSFS (SimConnect) — aus main.py aufrufbar."""
    inj = getattr(main_window, "_platin_injector", None)
    if inj is None:
        inject_platin_features(main_window)
        inj = getattr(main_window, "_platin_injector", None)
    if inj is not None:
        inj._gsx_start_full_handling_async()


def platin_after_mainwindow_built(main_window: Any) -> None:
    """
    Von main.py NACH win.show() aufgerufen.
    Erzwingt Profit/Allianz/Kurzstrecke/P2P-Layout — ohne main.py-Layout-Umbau.
    """
    if main_window is None:
        return
    if not _qt_widget_alive(main_window):
        return
    inj = getattr(main_window, "_platin_injector", None)
    if inj is None:
        inject_platin_features(main_window)
        inj = getattr(main_window, "_platin_injector", None)
    if inj is None:
        return
    _platin_stamp_window_title(main_window)
    rm = getattr(main_window, "_remove_duplicate_main_tabs_after_career", None)
    if callable(rm):
        rm()
    if getattr(main_window, "_platin_after_build_hook_done", False):
        if not getattr(main_window, "_platin_career_profit_done", False):
            main_window._platin_post_auth_boot_done = False
            _platin_reset_ui_flags(main_window)
            inj._post_auth_bootstrap()
        else:
            inj._fix_hangar_hub_layout_expansion()
            inj._apply_global_scroll_armor()
        return
    main_window._platin_after_build_hook_done = True
    main_window._platin_post_auth_boot_done = False
    _platin_reset_ui_flags(main_window)
    if _PLATIN_PREMAIN_AUTH_OK or getattr(main_window, "_platin_auth_gate_done", False):
        main_window._platin_auth_gate_done = True
        main_window._platin_license_trusted = True
        inj._post_auth_bootstrap()
    print(
        f"[SkyTycoon] platin_after_mainwindow_built OK ({PLATIN_BUILD})",
        flush=True,
    )


class _PlatinInjector:
    def __init__(self, win: Any) -> None:
        self.win = win
        import main as m

        self.m = m
        try:
            from platin_cloud_only import ensure_platin_session_db

            ensure_platin_session_db(m)
        except Exception:
            pass
        self.db_path = m.DB_PATH
        self._bus = _PlatinAsyncBus(win)
        self._bus.fuel_status.connect(self._on_fuel_status)
        self._bus.fuel_upgrade_done.connect(self._on_fuel_upgrade_done)
        self._bus.branches_pull_done.connect(self._on_branches_pull_done)
        self._bus.license_need_dialog.connect(self._show_license_dialog)
        self._bus.cloud_sync_done.connect(self._on_cloud_sync_done)
        self._bus.gsx_boarding_pct.connect(self._on_gsx_boarding_pct)
        self._bus.logout_ui_ready.connect(self._finish_logout_ui)
        self._bus.charter_api_done.connect(self._on_charter_api_done)
        self._bus.charter_api_fail.connect(self._on_charter_api_fail)
        self._bus.pax_feedback_ready.connect(self._on_pax_feedback_ready)
        self._bus.p2p_board_ready.connect(self._on_p2p_board_ready)
        self._sync_busy = False
        self._cloud_save_armed = False
        self._last_graceful_save = False

    def _tr(self, key: str, default: str) -> str:
        tr = getattr(self.win, "_tr", None)
        if callable(tr):
            return tr(key, default)
        return self.m.i18n_db(self.db_path, key, default)

    def _pool(self) -> QThreadPool:
        return QThreadPool.globalInstance()

    def _api_base(self) -> str:
        u = (self.m.ionos_api_base_url() or "").strip().rstrip("/")
        if _is_local_api_url(u):
            return _resolve_production_api_base(self.m, self.db_path)
        return u or _resolve_production_api_base(self.m, self.db_path)

    def _headers(self) -> dict[str, str]:
        try:
            from platin_cloud_only import ensure_platin_session_db

            ensure_platin_session_db(self.m)
            self.db_path = self.m.DB_PATH
        except Exception:
            pass
        headers = {
            "User-Agent": f"{self.m.SKYTYCOON_APP_NAME}/{self.m.APP_VERSION}",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        tok = (self.m.app_meta_get(self.db_path, "ionos_jwt", "") or "").strip()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        return headers

    def _online(self) -> bool:
        return self.m.online_network_enabled(self.db_path)

    def _safe_bus_emit(self, signal: Signal, *args: Any) -> None:
        if not _qt_widget_alive(self.win):
            return
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    def run(self) -> None:
        _patch_main_cloud_api_urls(self.m, self.db_path)
        _apply_platin_global_dark_theme(self.win)
        QTimer.singleShot(0, self._coldstart_auth_gate)

    def _post_auth_bootstrap(self) -> None:
        """Cockpit-Injektionen gestaffelt — Hauptfenster sofort nutzbar."""
        if getattr(self.win, "_platin_post_auth_boot_done", False):
            return
        self.win._platin_post_auth_boot_done = True
        _unlock_six_main_hub_tabs(self.win)
        _show_main_cockpit(self.win)
        _inject_auto_login_settings_menu(self.win, self.m, self.db_path)
        self._wire_profile_branches_sync()
        self._wire_cloud_sync_engine()
        self._install_zero_delay_lazy_tabs()
        self._install_lazy_hub_hooks()
        self._arm_swiss_code_backup_timer()
        _apply_platin_global_dark_theme(self.win)
        QTimer.singleShot(0, self._post_auth_bootstrap_phase2a)
        QTimer.singleShot(140, self._post_auth_bootstrap_phase2b)
        QTimer.singleShot(380, self._post_auth_bootstrap_phase2c)
        QTimer.singleShot(1800, self._post_auth_bootstrap_phase3)

    def _post_auth_bootstrap_phase2a(self) -> None:
        if not _qt_widget_alive(self.win):
            return
        self.win.setUpdatesEnabled(False)
        try:
            self._relocate_kerosin_to_hangar()
        finally:
            self.win.setUpdatesEnabled(True)

    def _post_auth_bootstrap_phase2b(self) -> None:
        if not _qt_widget_alive(self.win):
            return
        self.win.setUpdatesEnabled(False)
        try:
            self._inject_bank_fuel_platin()
            self._fix_bank_tab_layout_spacing()
            self._inject_crew_platin_hint()
            self._patch_safe_crew_ui_refresh()
            self._nuke_cabin_preview_widgets()
            self._sanitize_job_board_tabs()
        finally:
            self.win.setUpdatesEnabled(True)

    def _post_auth_bootstrap_phase2c(self) -> None:
        if not _qt_widget_alive(self.win):
            return
        self.win.setUpdatesEnabled(False)
        try:
            self._fix_crew_hub_overlap()
            self._inject_gsx_remote_control()
            self._inject_logout_button()
            self._apply_global_scroll_armor()
        finally:
            self.win.setUpdatesEnabled(True)
        _platin_stamp_window_title(self.win)
        print(
            f"[SkyTycoon] Platin UI armiert: 13-Säulen-Allianz, Cyber-Blau, Crew-Layout ({PLATIN_BUILD}).",
            flush=True,
        )
        QTimer.singleShot(80, self._apply_bank_hub_tab_labels)
        QTimer.singleShot(1400, self._ensure_alliance_13_hub)

    def _force_reapply_ui_layouts(self) -> None:
        """Nach Extensions-Update ohne App-Neustart: Layout-Patches erneut."""
        if not _qt_widget_alive(self.win):
            return
        _platin_reset_ui_flags(self.win)
        self.win._platin_post_auth_boot_done = False
        self._post_auth_bootstrap()

    def _post_auth_bootstrap_phase3(self) -> None:
        if not _qt_widget_alive(self.win):
            return
        self._inject_pax_main_tab()
        self._hide_cabin_live_hub_tab()
        self._inject_p2p_lease_hangar()
        self._fix_hangar_hub_layout_expansion()
        finalize = getattr(self.win, "_finalize_main_tab_bar", None)
        if callable(finalize):
            finalize()
        else:
            resync = getattr(self.win, "_resync_main_tab_indices", None)
            if callable(resync):
                resync()
        self._apply_bank_hub_tab_labels()
        self._fix_crew_hub_overlap()
        if not getattr(self.win, "_platin_scroll_armor_done", False):
            self._apply_global_scroll_armor()
        if "dispatch" in getattr(self.win, "_platin_lazy_materialized", set()):
            self._patch_dispatch_eventradar_buttons()
            self._patch_charter_buttons_async()
        self._bootstrap_cabin_sounds()
        QTimer.singleShot(4500, self._cabin_audio_download_async)
        QTimer.singleShot(800, self._cloud_sync_pull_async)
        QTimer.singleShot(3000, self._background_sync_ram_cache)
        if getattr(self.win, "_platin_cache_timer", None) is None:
            self.win._platin_cache_timer = QTimer(self.win)
            self.win._platin_cache_timer.setInterval(CACHE_REFRESH_MS)
            self.win._platin_cache_timer.timeout.connect(self._background_sync_ram_cache)
            self.win._platin_cache_timer.start()
        if getattr(self.win, "_platin_sim_save_timer", None) is None:
            self.win._platin_sim_save_timer = QTimer(self.win)
            self.win._platin_sim_save_timer.setInterval(4000)
            self.win._platin_sim_save_timer.timeout.connect(
                self._check_sim_shutdown_cloud_save
            )
            self.win._platin_sim_save_timer.start()
        if getattr(self.win, "_platin_gsx_poll_timer", None) is None:
            self.win._platin_gsx_poll_timer = QTimer(self.win)
            self.win._platin_gsx_poll_timer.setInterval(GSX_POLL_MS)
            self.win._platin_gsx_poll_timer.timeout.connect(self._gsx_poll_async)
            self.win._platin_gsx_poll_timer.start()
        self._arm_radar_heartbeat_funk()
        self._arm_fids_live_refresh()
        self._arm_aircraft_label_sync()
        self._hook_sim_snapshot_for_aircraft()
        QTimer.singleShot(2200, self._post_startup_license_enforce)

    def _fix_bank_tab_layout_spacing(self) -> None:
        """Bank-Reiter: Abstände — verhindert überlappende Sektionen."""
        intro = getattr(self.win, "label_bank_intro_tab", None)
        page = intro.parentWidget() if intro is not None else None
        if page is None:
            return
        lay = page.layout()
        if lay is not None:
            lay.setSpacing(10)
            lay.setContentsMargins(8, 8, 8, 8)
        if getattr(self.win, "_platin_bank_scroll", False):
            return
        outer = page.parentWidget()
        outer_lay = outer.layout() if outer is not None else None
        if outer_lay is None:
            return
        ix = outer_lay.indexOf(page)
        if ix < 0:
            return
        outer_lay.removeWidget(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        outer_lay.insertWidget(ix, scroll)
        self.win._platin_bank_scroll = True

    def _run_background_update_check(self) -> None:
        """Update-UI nur Splash — Cockpit bleibt stumm."""
        return

    def _hook_sim_snapshot_for_aircraft(self) -> None:
        th = getattr(self.win, "_sim_poll_thread", None)
        if th is None or getattr(self.win, "_platin_sim_snap_hooked", False):
            return
        self.win._platin_sim_snap_hooked = True

        def _on_snap(snap: dict) -> None:
            if isinstance(snap, dict):
                self.win._sim_snap_buffer = snap

        try:
            th.snapshot_ready.connect(_on_snap)
        except (RuntimeError, TypeError):
            pass

    def _arm_aircraft_label_sync(self) -> None:
        if getattr(self.win, "_platin_ac_label_timer", None) is not None:
            try:
                self.win._platin_ac_label_timer.setInterval(SIMCONNECT_TELEMETRY_MS)
            except RuntimeError:
                pass
            return
        t = QTimer(self.win)
        t.setInterval(SIMCONNECT_TELEMETRY_MS)
        t.timeout.connect(self._refresh_aircraft_label_from_sim)
        t.start()
        self.win._platin_ac_label_timer = t
        QTimer.singleShot(SIMCONNECT_TELEMETRY_MS, self._refresh_aircraft_label_from_sim)

    def _refresh_aircraft_label_from_sim(self) -> None:
        lbl = getattr(self.win, "label_aircraft", None)
        if lbl is None:
            return
        title_raw = str(
            _read_sim_snapshot_field(self.win, "TITLE")
            or getattr(self.win, "_last_title", "")
            or ""
        ).strip()
        atc_model = str(_read_sim_snapshot_field(self.win, "ATC MODEL") or "").strip()
        atc_type = str(_read_sim_snapshot_field(self.win, "ATC TYPE") or "").strip()
        icao = _simconnect_title_to_icao(title_raw, atc_model, atc_type)
        if icao:
            try:
                self.win.current_aircraft_icao = icao
            except Exception:
                pass
        if title_raw and title_raw not in ("–", "– (noch keine Daten)"):
            try:
                self.win._last_title = title_raw[:120]
                self.win.current_aircraft_model = title_raw[:120]
            except Exception:
                pass
        if icao:
            display = f"{icao} — {title_raw[:72]}" if title_raw else icao
        elif title_raw and title_raw not in ("–", "– (noch keine Daten)"):
            display = self._tr(
                "sim.loaded_ac_fmt", "Geladenes Flugzeug (TITLE): {title}"
            ).format(title=title_raw[:96])
        else:
            return
        snap_key = f"{icao}|{title_raw[:96]}"
        if snap_key == str(getattr(self.win, "_platin_last_ac_snap_key", "")):
            return
        self.win._platin_last_ac_snap_key = snap_key
        if display == str(getattr(self.win, "_platin_last_ac_display", "")):
            return
        self.win._platin_last_ac_display = display
        try:
            lbl.setText(display)
            self.win._platin_stable_ac_lbl = display
        except RuntimeError:
            pass
        lbl_ph = getattr(self.win, "label_phase", None)
        if lbl_ph is not None:
            phase_val = str(
                getattr(getattr(self.win, "_phase", None), "value", "") or ""
            ).strip()
            if phase_val:
                phase_txt = f"Flugphase: {phase_val}"
                if phase_txt != str(getattr(self.win, "_platin_last_phase_display", "")):
                    self.win._platin_last_phase_display = phase_txt
                    try:
                        lbl_ph.setText(phase_txt)
                        self.win._platin_stable_phase_lbl = phase_txt
                    except RuntimeError:
                        pass

    def _arm_fids_live_refresh(self) -> None:
        if getattr(self.win, "_platin_zero_lazy_installed", False) and (
            "fids" not in getattr(self.win, "_platin_lazy_materialized", set())
        ):
            return
        if getattr(self.win, "_platin_fids_timer_armed", False):
            return
        self.win._platin_fids_timer_armed = True
        t_rot = getattr(self.win, "timer_fids_rotation", None)
        if t_rot is not None:
            try:
                t_rot.timeout.disconnect()
            except (RuntimeError, TypeError):
                pass
            t_rot.timeout.connect(self._fids_fetch_live_async)
        t_hb = getattr(self.win, "timer_fids_heartbeat", None)
        if t_hb is not None:
            try:
                t_hb.timeout.disconnect(self.win._post_fids_radar_heartbeat)
            except (RuntimeError, TypeError):
                pass
        QTimer.singleShot(800, self._fids_fetch_live_async)

    def _fids_fetch_live_async(self) -> None:
        if getattr(self.win, "_fids_fetch_inflight", False):
            return
        base = _CLOUD_API_FALLBACK.rstrip("/")
        self.win._fids_fetch_inflight = True
        if hasattr(self.win, "label_fids_status"):
            self.win.label_fids_status.setText(
                self._tr("fids.status_loading", "Lade weltweite Flugbewegungen…")
            )

        def _work() -> None:
            positions: list[Any] = []
            err_txt = ""
            try:
                url = f"{base.rstrip('/')}/api/v1/web/radar/positions"
                headers = {
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                    "Accept": "application/json",
                }
                headers.update(self.m.ionos_auth_headers(self.db_path))
                for hk in list(headers.keys()):
                    if hk.lower() in ("x-session-id", "x-cache-key", "if-none-match"):
                        headers.pop(hk, None)
                hid = self.m.p2p_hardware_id(self.db_path)
                em = (
                    self.m.app_meta_get(self.db_path, "portal_email", "")
                    or ""
                ).strip().lower()
                params: dict[str, Any] = {"_": int(time.time() * 1000)}
                if hid:
                    params["hardware_id"] = hid[:128]
                if em and "@" in em:
                    params["portal_email"] = em[:200]
                r = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=14,
                    verify=self.m.auth_requests_verify_tls(),
                )
                j = r.json() if r.content else {}
                if isinstance(j, dict):
                    raw = j.get("positions")
                    if isinstance(raw, list):
                        positions = raw
                    elif str(j.get("status", "")).lower() == "success":
                        raw2 = j.get("pilots")
                        if isinstance(raw2, list):
                            positions = raw2
            except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
                err_txt = str(exc)

            def _ui() -> None:
                self.win._fids_fetch_inflight = False
                if err_txt and hasattr(self.win, "label_fids_status"):
                    self.win.label_fids_status.setText(
                        self._tr(
                            "fids.status_err",
                            "Flugtafel: Server nicht erreichbar.",
                        )
                    )
                    return
                if hasattr(self.win, "_apply_fids_positions"):
                    self.win._apply_fids_positions(positions)

            QTimer.singleShot(0, self.win, _ui)

        self._pool().start(_FnRunnable(_work))

    def _arm_radar_heartbeat_funk(self) -> None:
        """Permanenter 5s-Live-Radar (FIDS + Discord) — läuft im QThreadPool, UI bleibt frei."""
        if getattr(self.win, "_platin_radar_heartbeat_armed", False):
            return
        self.win._platin_radar_heartbeat_armed = True
        self.win._platin_radar_session_init = getattr(
            self.win, "_platin_radar_session_init", False
        )
        self._radar_hb_timer = QTimer(self.win)
        self._radar_hb_timer.setInterval(RADAR_HEARTBEAT_MS)
        self._radar_hb_timer.timeout.connect(self._fire_radar_heartbeat_async)
        self._radar_hb_timer.start()
        QTimer.singleShot(0, self._fire_radar_heartbeat_async)

    def _fire_radar_heartbeat_async(self) -> None:
        if self.m.app_meta_get(self.db_path, "license_activated", "0") != "1":
            return
        self._pool().start(_RadarHeartbeatRunnable(self))

    def _inject_gsx_remote_control(self) -> None:
        old_host = getattr(self.win, "_platin_gsx_host", None)
        if old_host is not None:
            try:
                old_host.setParent(None)
                old_host.deleteLater()
            except RuntimeError:
                pass
            self.win._platin_gsx_host = None
            self.win._platin_gsx_remote = False
        if getattr(self.win, "_platin_gsx_remote", False):
            return
        anchor = getattr(self.win, "btn_gsx_start_handling", None)
        if anchor is None:
            hub = getattr(self.win, "_hub_leaf_gsx", None)
            if hub is not None:
                lay = hub.layout()
            else:
                return
        else:
            parent_w = anchor.parentWidget()
            lay = parent_w.layout() if parent_w else None
        if lay is None:
            return
        fr, fl = self._gold_frame(
            "platin.gsx.title",
            "🤖 GSX Pro Remote Control",
        )
        btn_row = QHBoxLayout()
        self.win._platin_gsx_btns: dict[str, QPushButton] = {}
        specs = (
            ("catering", "platin.gsx.catering", "🍽️ Catering"),
            ("boarding", "platin.gsx.boarding", "🧳 Boarding"),
            ("deboarding", "platin.gsx.deboarding", "🚌 Deboarding"),
            ("refuel", "platin.gsx.refuel", "⛽ Refuel"),
        )
        for key, i18n_k, default_lbl in specs:
            btn = QPushButton(self._tr(i18n_k, default_lbl))
            btn.setObjectName("platinBtn")
            btn.setStyleSheet(GOLD_TILE_STYLE)
            btn.clicked.connect(lambda _c=False, k=key: self._trigger_gsx_async(k))
            btn_row.addWidget(btn)
            self.win._platin_gsx_btns[key] = btn
        fl.addLayout(btn_row)
        self.win.label_platin_gsx_boarding = QLabel("—")
        self.win.label_platin_gsx_boarding.setStyleSheet("color:#90caf9;font-weight:700;")
        fl.addWidget(self.win.label_platin_gsx_boarding)
        self.win.prog_platin_gsx_boarding = QProgressBar()
        self.win.prog_platin_gsx_boarding.setRange(0, 100)
        self.win.prog_platin_gsx_boarding.setFormat(
            self._tr("platin.gsx.boarding_fmt", "Boarding %p %")
        )
        self.win.prog_platin_gsx_boarding.setStyleSheet(
            "QProgressBar { border:1px solid #3a3a42; height:22px; }"
            "QProgressBar::chunk { background:#42a5f5; }"
        )
        fl.addWidget(self.win.prog_platin_gsx_boarding)
        self.win._platin_gsx_host = fr
        if anchor is not None:
            idx = lay.indexOf(anchor)
            lay.insertWidget(idx + 1 if idx >= 0 else lay.count(), fr)
        else:
            lay.insertWidget(0, fr)
        self.win._platin_gsx_remote = True

    def _inject_logout_button(self) -> None:
        """Menüleiste → 👤 Kundenkonto → Logout (kein Profil-Tab nötig)."""
        if getattr(self.win, "_platin_logout_act", None) is not None:
            return
        menu_acc = getattr(self.win, "_menu_account", None)
        if menu_acc is None:
            mb = self.win.menuBar()
            if mb is not None:
                for act in mb.actions():
                    txt = (act.text() or "").lower()
                    if "kundenkonto" in txt or "account" in txt or "👤" in (act.text() or ""):
                        menu_acc = act.menu()
                        break
        if menu_acc is None:
            return
        default_lbl = "[ 🔓 Konto abmelden / Logout ]"
        act = QAction(self._tr("platin.auth.logout", default_lbl), self.win)
        act.setObjectName("platinLogoutAction")
        act.triggered.connect(self._on_logout_clicked)
        reg = getattr(self.win, "_i18n_register", None)
        if callable(reg):
            reg(act, "platin.auth.logout", default_lbl)
        menu_acc.addSeparator()
        menu_acc.addAction(act)
        self.win._platin_logout_act = act
        self.win._menu_account = menu_acc

    def _on_logout_clicked(self) -> None:
        title = self._tr("platin.auth.logout", "[ 🔓 Konto abmelden / Logout ]")
        msg = self._tr(
            "platin.auth.logout_confirm",
            "Pilot von der Live-Flugtafel entfernen und Konto abmelden?",
        )
        if (
            QMessageBox.question(self.win, title, msg)
            != QMessageBox.StandardButton.Yes
        ):
            return
        _nuke_disk_local_session(self.m, self.db_path)
        _purge_session_ram_cache(self.win, self.m, self.db_path)
        try:
            self.win.hide()
        except RuntimeError:
            pass
        parent = self.win
        tw = getattr(parent, "tab_widget", None)
        if tw is not None:
            try:
                parent.main_tab_widget = tw
            except Exception:
                pass
        mtw = getattr(parent, "main_tab_widget", None)
        if mtw is not None:
            try:
                mtw.setVisible(False)
                mtw.setEnabled(False)
                mtw.hide()
            except RuntimeError:
                pass
        _force_main_tab_invisible(self.win)
        _hide_main_cockpit(self.win)
        self._pool().start(_FnRunnable(self._logout_disconnect_work))

    def _logout_disconnect_work(self) -> None:
        _nuke_disk_local_session(self.m, self.db_path)
        _purge_session_ram_cache(self.win, self.m, self.db_path)
        base = self._api_base() or "https://skytycoon.info"
        try:
            body = dict(self.m.build_ionos_cloud_sync_body(self.db_path, pull_only=True))
            pilot = (
                str(getattr(self.win, "pilot_display_name", "") or "").strip()
                or self.m.app_meta_get(self.db_path, "pilot_display_name", "")
                or self.m.pilot_handle(self.db_path)
            )
            body["username"] = pilot
            body["pilot_name"] = pilot
            requests.post(
                f"{base.rstrip('/')}/api/v1/radar/disconnect",
                json=body,
                timeout=6,
                headers=self._headers(),
            )
        except requests.RequestException:
            pass
        self._safe_bus_emit(self._bus.logout_ui_ready)

    def _finish_logout_ui(self) -> None:
        _nuke_disk_local_session(self.m, self.db_path)
        _purge_session_ram_cache(self.win, self.m, self.db_path)
        _init_platin_ram_cache(self.win)
        _lock_six_main_hub_tabs(self.win)
        for tname in (
            "timer_fids_heartbeat",
            "radar_timer",
            "_gsx_poll_timer",
            "_cache_timer",
            "_radar_hb_timer",
            "_platin_ac_label_timer",
        ):
            t = getattr(self.win, tname, None) or getattr(self, tname, None)
            if t is not None and hasattr(t, "stop"):
                try:
                    t.stop()
                except RuntimeError:
                    pass
        self.win._platin_radar_heartbeat_armed = False
        self.win._platin_radar_session_init = False
        _show_platin_login_surface(self.win, self.m, self.db_path, self)
        dlg_cls = getattr(self.m, "StartupAuthDialog", None)
        if dlg_cls is None:
            _show_main_cockpit(self.win)
            return
        ov = _ensure_platin_login_widget(self.win, self.m, self.db_path, self)
        accepted = False
        while not accepted:
            dlg = dlg_cls(self.db_path, ov)
            dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                accepted = True
                break
            quit_msg = self._tr(
                "platin.auth.logout_abort",
                "Anmeldung abgebrochen. SkyTycoon Pro beenden?",
            )
            if (
                QMessageBox.question(
                    ov,
                    self._tr("platin.auth.logout", "Logout"),
                    quit_msg,
                )
                == QMessageBox.StandardButton.Yes
            ):
                self.win.close()
                return
        self._after_platin_login_success()

    def _after_platin_login_success(self) -> None:
        _platin_instant_cockpit_open(self.win)
        _show_main_cockpit(self.win)
        _unlock_six_main_hub_tabs(self.win)
        lang_meta = (
            self.m.app_meta_get(self.db_path, "selected_language", "")
            or self.m.app_meta_get(self.db_path, "ui_lang", "")
            or "de"
        )
        _apply_desktop_language(self.win, self.db_path, self.m, lang_meta)
        self._arm_radar_heartbeat_funk()
        if hasattr(self.win, "_arm_radar_after_login"):
            try:
                self.win._arm_radar_after_login()
            except Exception:
                pass
        self.win._platin_fresh_cloud_sync = True
        QTimer.singleShot(600, self._cloud_sync_pull_async)
        QTimer.singleShot(900, self._ensure_alliance_13_hub)
        QTimer.singleShot(2200, self._ensure_alliance_13_hub)

    def _apply_bank_hub_tab_labels(self) -> None:
        """Hub „Bank“ ohne main.py-Layout-Änderung (nur Tab-Titel)."""
        tw = getattr(self.win, "tab_widget", None)
        safe_ix = getattr(self.win, "_safe_tab_index", None)
        ix = safe_ix("_hub_ix_bank") if callable(safe_ix) else getattr(
            self.win, "_hub_ix_bank", -1
        )
        if tw is None or not isinstance(ix, int) or ix < 0 or ix >= tw.count():
            return
        en = self._ui_lang_en()
        tw.setTabText(
            ix,
            "🏦 Bank" if en else "🏦 Bank",
        )
        sub = (getattr(self.win, "_hub_tabwidgets", None) or {}).get(ix)
        if sub is not None and hasattr(sub, "count"):
            for i in range(sub.count()):
                t = (sub.tabText(i) or "").lower()
                if "kreditanstalt" in t or "loan" in t or "kredit" in t:
                    sub.setTabText(
                        i,
                        "💳 Bank & Loans" if en else "💳 Bank & Kredite",
                    )
                elif "kerosin" in t or "fuel" in t:
                    sub.setTabText(
                        i,
                        "⛽ Fuel trading" if en else "⛽ Kerosin-Trading",
                    )

    @staticmethod
    def _gsx_send_simconnect_event(sm: Any, event_name: str, data: int = 1) -> bool:
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

    @staticmethod
    def _gsx_open_menu_native(sm: Any, aq: Any) -> None:
        for ev in GSX_MENU_OPEN_SIM_EVENTS:
            if _PlatinInjector._gsx_send_simconnect_event(sm, ev, 1):
                break
        if aq is not None:
            try:
                aq.set("L:FSDT_GSX_MENU_OPEN", 1.0)
            except Exception:
                pass
        try:
            import ctypes

            user32 = ctypes.windll.user32
            VK_CONTROL, VK_SHIFT, VK_F12 = 0x11, 0x10, 0x7B
            KEYEVENTF_KEYUP = 0x0002

            def _tap(vk: int) -> None:
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(VK_SHIFT, 0, 0, 0)
            _tap(VK_F12)
            user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        except Exception:
            pass

    def _relocate_kerosin_to_hangar(self) -> None:
        if getattr(self.win, "_platin_kerosin_moved", False):
            return
        fuel_tab = getattr(self.win, "_bank_fuel_tab", None)
        hangar_inner = getattr(self.win, "hangar_inner_tabs", None)
        bank_ix = getattr(self.win, "_hub_ix_bank", None)
        if fuel_tab is None or not isinstance(hangar_inner, QTabWidget):
            return
        hub_tw = getattr(self.win, "_hub_tabwidgets", {}).get(bank_ix)
        if isinstance(hub_tw, QTabWidget):
            for i in range(hub_tw.count() - 1, -1, -1):
                if hub_tw.widget(i) is fuel_tab:
                    hub_tw.removeTab(i)
                    break
        title = self._tr("hub.bank.fuel", "⛽ Kerosin-Trading")
        if hangar_inner.indexOf(fuel_tab) < 0:
            hangar_inner.addTab(fuel_tab, title)
        self.win._platin_kerosin_moved = True

    @staticmethod
    def _hub_tab_unwrap(shell: QWidget | None) -> QWidget | None:
        if shell is None:
            return None
        sa = shell.findChild(QScrollArea)
        if sa is not None:
            inner = sa.widget()
            if inner is not None:
                return inner
        return shell

    @staticmethod
    def _widget_tree_contains(root: QWidget | None, needle: QWidget | None) -> bool:
        if root is None or needle is None:
            return False
        node: QWidget | None = needle
        while node is not None:
            if node is root:
                return True
            node = node.parentWidget()
        return False

    def _hangar_inner_widget_role(self, page: QWidget | None) -> str:
        if page is None:
            return "unknown"
        win = self.win
        markers: tuple[tuple[str, QWidget | None], ...] = (
            ("p2p", getattr(win, "_platin_p2p_market_page", None)),
            ("scrap", getattr(win, "tab_used_scrapyard", None)),
            ("newparts", getattr(win, "tab_new_parts_market", None)),
            ("fuel", getattr(win, "_bank_fuel_tab", None)),
            ("prof", getattr(win, "scroll_hangar_maint", None)),
            ("parts", getattr(win, "table_spare_parts_market", None)),
            ("maint", getattr(win, "btn_hangar_paint_web", None)),
            ("market", getattr(win, "market_inner_tabs", None)),
        )
        for role, needle in markers:
            if needle is not None and self._widget_tree_contains(page, needle):
                return role
        return "unknown"

    @staticmethod
    def _remove_widget_from_layout(lay: Any, widget: QWidget) -> bool:
        if lay is None:
            return False
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is not None and item.widget() is widget:
                lay.removeWidget(widget)
                return True
        return False

    def _expand_widget_layouts(self, root: QWidget | None, _depth: int = 0) -> None:
        if root is None or _depth > 10:
            return
        root.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay = root.layout()
        if isinstance(lay, (QVBoxLayout, QHBoxLayout)):
            for i in range(lay.count()):
                item = lay.itemAt(i)
                if item is None:
                    continue
                w = item.widget()
                if w is None:
                    continue
                if isinstance(
                    w,
                    (
                        QTableWidget,
                        QTabWidget,
                        QListWidget,
                        QStackedWidget,
                        QScrollArea,
                    ),
                ):
                    lay.setStretch(i, 1)
                    w.setSizePolicy(
                        QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Expanding,
                    )
                    if isinstance(w, QTableWidget):
                        w.horizontalHeader().setSectionResizeMode(
                            QHeaderView.ResizeMode.Stretch
                        )
                self._expand_widget_layouts(w, _depth + 1)
        if isinstance(root, QTabWidget):
            for i in range(root.count()):
                page = root.widget(i)
                if page is not None:
                    page.setSizePolicy(
                        QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Expanding,
                    )
                    sa = page.findChild(QScrollArea)
                    if sa is not None:
                        sa.setWidgetResizable(True)
                        inner = sa.widget()
                        if inner is not None:
                            self._expand_widget_layouts(inner, _depth + 1)
                    self._expand_widget_layouts(page, _depth + 1)

    def _fix_hangar_hub_layout_expansion(self) -> None:
        if getattr(self.win, "_platin_hangar_layout_fix", False):
            return
        for attr in (
            "_platin_p2p_market_page",
            "_platin_market_widget",
            "hangar_inner_tabs",
            "market_inner_tabs",
            "table_market",
            "table_p2p",
        ):
            w = getattr(self.win, attr, None)
            if w is not None:
                self._expand_widget_layouts(w)
        hangar_ix = getattr(self.win, "_hub_ix_hangar", None)
        hub_tw = getattr(self.win, "_hub_tabwidgets", {}).get(hangar_ix)
        if isinstance(hub_tw, QTabWidget):
            for i in range(hub_tw.count()):
                shell = hub_tw.widget(i)
                if shell is not None:
                    self._expand_widget_layouts(shell)
        mit = getattr(self.win, "market_inner_tabs", None)
        if mit is not None:
            parent = mit.parentWidget()
            if parent is not None:
                pl = parent.layout()
                if isinstance(pl, (QVBoxLayout, QHBoxLayout)):
                    for i in range(pl.count()):
                        if pl.itemAt(i) is not None and pl.itemAt(i).widget() is mit:
                            pl.setStretch(i, 1)
                            break
        self.win._platin_hangar_layout_fix = True

    def _restructure_career_profit_tab(self) -> None:
        if getattr(self.win, "_platin_profit_in_profile", False):
            self.win._platin_career_profit_done = True
            return
        if getattr(self.win, "_platin_career_profit_done", False):
            return
        career_ix = getattr(self.win, "_hub_ix_career", None)
        inner = getattr(self.win, "_hub_tabwidgets", {}).get(career_ix)
        if not isinstance(inner, QTabWidget):
            return
        en = self._ui_lang_en()
        lic = getattr(self.win, "label_prof_license", None)
        if lic is not None:
            lic.hide()
            prof_lay = getattr(self.win, "_profile_tab_layout", None)
            if isinstance(prof_lay, QVBoxLayout):
                self._remove_widget_from_layout(prof_lay, lic)

        profit = QWidget()
        profit_l = QVBoxLayout(profit)
        profit_l.setContentsMargins(8, 8, 8, 8)
        hdr = QLabel(
            "💰 Profit · Top routes & landing logbook"
            if en
            else "💰 Profit · Top-Flüge & Landungs-Logbuch"
        )
        hdr.setStyleSheet("color:#e8e8ec;font-weight:900;font-size:14px;")
        profit_l.addWidget(hdr)

        prof_lay = getattr(self.win, "_profile_tab_layout", None)
        if isinstance(prof_lay, QVBoxLayout):
            for i in range(prof_lay.count()):
                item = prof_lay.itemAt(i)
                w = item.widget() if item else None
                if isinstance(w, QLabel) and "top-fl" in (w.text() or "").lower():
                    self._remove_widget_from_layout(prof_lay, w)
                    profit_l.addWidget(w)
                    break
            else:
                profit_l.addWidget(
                    QLabel(
                        "Your top flights (profit):"
                        if en
                        else "Deine Top-Flüge (Profit):"
                    )
                )
            log_lbl = QLabel(
                "✈️ Flown routes · hardest landing logbook"
                if en
                else "✈️ Geflogene Strecken · härteste Landung (Logbuch)"
            )
            log_lbl.setStyleSheet("color:#90caf9;font-weight:700;margin-top:8px;")
            profit_l.addWidget(log_lbl)
            move_attrs = (
                "label_prof_stats",
                "label_prof_flights",
                "table_highscores",
                "btn_export_csv",
            )
            for attr in move_attrs:
                widget = getattr(self.win, attr, None)
                if widget is not None and self._remove_widget_from_layout(
                    prof_lay, widget
                ):
                    if attr == "table_highscores":
                        profit_l.addWidget(widget, 1)
                    else:
                        profit_l.addWidget(widget)

        for i in range(inner.count() - 1, -1, -1):
            title = (inner.tabText(i) or "").lower()
            if "prestige" in title or "reset" in title:
                inner.removeTab(i)

        profit_title = "💰 Profit" if en else "💰 Profit"
        insert_at = min(1, inner.count())
        inner.insertTab(insert_at, _platin_scroll_wrap(profit), profit_title)
        self.win._platin_career_profit_done = True
        try:
            fn = getattr(self.win, "_refresh_profile_tab", None)
            if callable(fn):
                fn()
        except Exception:
            pass

    def _move_wallstreet_tabs_to_alliance(self) -> None:
        if getattr(self.win, "_alliance_wallstreet_wrapped", False):
            self.win._platin_wallstreet_moved = True
            return
        if getattr(self.win, "_platin_wallstreet_moved", False):
            return
        mit = getattr(self.win, "market_inner_tabs", None)
        alliance_host = getattr(self.win, "tab_alliances", None)
        if mit is None or alliance_host is None:
            return
        en = self._ui_lang_en()
        move_keys = (
            "wallstreet /",
            "wallstreet/",
            "mitternacht",
            "midnight market",
            "allianz-börse",
            "alliance stock",
        )
        extracted: list[tuple[str, QWidget]] = []
        for i in range(mit.count() - 1, -1, -1):
            title = (mit.tabText(i) or "").lower()
            if any(k in title for k in move_keys):
                w = mit.widget(i)
                label = mit.tabText(i)
                mit.removeTab(i)
                if w is not None:
                    extracted.append((label, w))
        if not extracted:
            self.win._platin_wallstreet_moved = True
            return

        alliance_tabs = getattr(self.win, "_platin_alliance_tabs", None)
        if alliance_tabs is None:
            old_lay = alliance_host.layout()
            if not isinstance(old_lay, QVBoxLayout):
                return
            core = QWidget()
            core_l = QVBoxLayout(core)
            core_l.setContentsMargins(0, 0, 0, 0)
            while old_lay.count():
                stretch = old_lay.stretch(0)
                item = old_lay.takeAt(0)
                if item is None:
                    continue
                w = item.widget()
                if w is not None:
                    core_l.addWidget(w, stretch)
                elif item.layout() is not None:
                    core_l.addLayout(item.layout(), stretch)
            alliance_tabs = QTabWidget()
            old_lay.addWidget(alliance_tabs, 1)
            alliance_tabs.addTab(
                core,
                "🤝 Alliance HQ" if en else "🤝 Allianz-HQ",
            )
            self.win._platin_alliance_tabs = alliance_tabs
            stack = getattr(self.win, "alliance_stack", None)
            if stack is not None:
                stack.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
                )

        for label, widget in reversed(extracted):
            widget.setParent(None)
            alliance_tabs.addTab(widget, label)
            self._expand_widget_layouts(widget)

        self.win._platin_wallstreet_moved = True

    def _restructure_hangar_p2p_hub(self) -> None:
        if getattr(self.win, "_platin_hangar_restructured", False):
            return
        hangar_ix = getattr(self.win, "_hub_ix_hangar", None)
        hub_tw = getattr(self.win, "_hub_tabwidgets", {}).get(hangar_ix)
        inner_hang = getattr(self.win, "hangar_inner_tabs", None)
        hangar_leaf = getattr(self.win, "_hub_leaf_hangar", None)
        if not isinstance(hub_tw, QTabWidget) or not isinstance(inner_hang, QTabWidget):
            return
        en = self._ui_lang_en()
        extracted: dict[str, QWidget] = {}
        remove_ix: list[int] = []
        for i in range(inner_hang.count()):
            page = inner_hang.widget(i)
            role = self._hangar_inner_widget_role(page)
            if role in ("p2p", "unknown", "market"):
                continue
            if page is not None:
                extracted[role] = page
                remove_ix.append(i)
        for i in reversed(remove_ix):
            inner_hang.removeTab(i)

        fleet_ix = -1
        market_ix = -1
        market_widget: QWidget | None = None
        for i in range(hub_tw.count()):
            content = self._hub_tab_unwrap(hub_tw.widget(i))
            if content is hangar_leaf:
                fleet_ix = i
            elif content is not None and self._hangar_inner_widget_role(content) == "market":
                market_ix = i
                market_widget = content
            elif content is not None and getattr(self.win, "market_inner_tabs", None):
                mit = self.win.market_inner_tabs
                if self._widget_tree_contains(content, mit):
                    market_ix = i
                    market_widget = content
        if market_ix >= 0 and market_widget is not None:
            hub_tw.removeTab(market_ix)
            self.win._platin_market_widget = market_widget

        if fleet_ix >= 0:
            hub_tw.setTabText(
                fleet_ix,
                "✈️ Fleet list" if en else "✈️ Flottenliste",
            )

        tech_page = QWidget()
        tech_l = QVBoxLayout(tech_page)
        tech_tw = QTabWidget()
        tech_l.addWidget(tech_tw, 1)
        tech_specs: tuple[tuple[str, str, str], ...] = (
            (
                "prof",
                "🛠️ 12-Checks maintenance",
                "🛠️ 12-Checks-Wartung",
            ),
            (
                "parts",
                "📁 Local spare parts warehouse",
                "📁 Lokales Ersatzteil-Lager",
            ),
            (
                "scrap",
                "🛸 Cloud scrapyard",
                "🛸 Cloud-Schrottplatz",
            ),
            (
                "fuel",
                "⛽ Jet fuel trading & tank limit",
                "⛽ Kerosin-Trading & Tank-Limit",
            ),
            (
                "maint",
                "🔧 Hangar maintenance & paint",
                "🔧 Hangar-Wartung & Lack",
            ),
            (
                "newparts",
                "💎 Hangar new parts (100%)",
                "💎 Hangar-Neuteile (100 %)",
            ),
        )
        for role, en_t, de_t in tech_specs:
            w = extracted.get(role)
            if w is not None:
                tech_tw.addTab(w, en_t if en else de_t)
        mkt = getattr(self.win, "_platin_market_widget", None)
        if mkt is not None:
            tech_tw.addTab(
                mkt,
                "🛒 Global used market" if en else "🛒 Gebraucht-Marktplatz (Global)",
            )
            self.win._platin_market_widget = None
        p2p_page = extracted.get("p2p") or getattr(
            self.win, "_platin_p2p_market_page", None
        )
        if p2p_page is not None:
            tech_tw.addTab(
                p2p_page,
                "🌐 P2P listings" if en else "🌐 P2P-Inserate",
            )
        while inner_hang.count() > 0:
            page = inner_hang.widget(0)
            title = inner_hang.tabText(0)
            inner_hang.removeTab(0)
            if page is not None and self._hangar_inner_widget_role(page) not in (
                "unknown",
            ):
                if tech_tw.indexOf(page) < 0:
                    tech_tw.addTab(page, title)
        if tech_tw.count() > 0:
            tech_title = (
                "✈️ Aircraft yard"
                if en
                else "✈️ Flugzeug-Werft"
            )
            shell = QWidget()
            shell_l = QVBoxLayout(shell)
            shell_l.setContentsMargins(0, 0, 0, 0)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(tech_page)
            shell_l.addWidget(scroll, 1)
            hub_tw.addTab(shell, tech_title)
        self._apply_hangar_hub_tab_labels()
        self._fix_hangar_hub_layout_expansion()
        self.win._platin_hangar_restructured = True

    def _apply_hangar_hub_tab_labels(self) -> None:
        """Hangar-Hub: Flottenliste + Flugzeug-Werft (nicht Marktplatz / P2P auf Flotte)."""
        hangar_ix = getattr(self.win, "_hub_ix_hangar", None)
        hub_tw = getattr(self.win, "_hub_tabwidgets", {}).get(hangar_ix)
        if not isinstance(hub_tw, QTabWidget):
            return
        en = self._ui_lang_en()
        fleet_l = "✈️ Fleet list" if en else "✈️ Flottenliste"
        werft_l = "✈️ Aircraft yard" if en else "✈️ Flugzeug-Werft"
        for i in range(hub_tw.count()):
            t = (hub_tw.tabText(i) or "").lower()
            if "flotten" in t or "fleet list" in t:
                hub_tw.setTabText(i, fleet_l)
            elif "p2p" in t and "flotten" not in t:
                continue
            elif any(
                k in t
                for k in (
                    "marktplatz",
                    "marketplace",
                    "werft",
                    "yard",
                    "tech-zentrum",
                    "tech center",
                )
            ):
                hub_tw.setTabText(i, werft_l)
        sub_i18n = getattr(self.win, "_hub_sub_i18n", None)
        if isinstance(sub_i18n, list):
            for j, (tw, ti, sk, _sd) in enumerate(sub_i18n):
                if sk == "hub.hangar.market":
                    sub_i18n[j] = (tw, ti, sk, werft_l)
                    if isinstance(tw, QTabWidget) and ti < tw.count():
                        tw.setTabText(ti, werft_l)

    def _open_desktop_portal_page(self, path: str) -> None:
        base = self._api_base() or "https://skytycoon.info"
        hid = self.m.p2p_hardware_id(self.db_path)
        url = f"{base.rstrip('/')}{path}"
        try:
            r = requests.post(
                f"{base.rstrip('/')}/api/v1/desktop/portal_url",
                json={"hardware_id": hid, "path": path},
                headers=self._headers(),
                timeout=12,
            )
            j = r.json()
            if r.status_code == 200 and j.get("ok") and j.get("url"):
                url = str(j["url"])
        except requests.RequestException:
            pass
        QDesktopServices.openUrl(QUrl(url))

    def _patch_dispatch_eventradar_buttons(self) -> None:
        """Krisen-Eventradar ist eigener Haupt-Reiter in main.py — nicht im Dispatcher."""
        self.win._platin_portal_btns = True
        crisis_ix = getattr(self.win, "_hub_ix_crisis", None)
        tw = getattr(self.win, "tab_widget", None)
        if not isinstance(crisis_ix, int) or tw is None or crisis_ix < 0:
            return
        page = tw.widget(crisis_ix)
        if page is None:
            return
        events_page = self._hub_tab_unwrap(page) or page
        for btn in events_page.findChildren(QPushButton):
            txt = (btn.text() or "").lower()
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            if "event" in txt and "radar" in txt:
                btn.clicked.connect(self._open_eventradar_weather_portal)
            elif ("live" in txt and "radar" in txt) or "live-radar" in txt:
                btn.clicked.connect(self._open_live_market_radar_portal)

    def _focus_dispatch_subtab(self, keyword: str) -> None:
        dix = getattr(self.win, "_hub_ix_dispatch", -1)
        tw = getattr(self.win, "tab_widget", None)
        if isinstance(dix, int) and dix >= 0 and tw is not None:
            try:
                tw.setCurrentIndex(dix)
            except RuntimeError:
                pass
        inner = getattr(self.win, "_hub_tabwidgets", {}).get(dix)
        if not isinstance(inner, QTabWidget):
            return
        key = keyword.lower()
        for i in range(inner.count()):
            if key in (inner.tabText(i) or "").lower():
                inner.setCurrentIndex(i)
                break

    def _open_eventradar_weather_portal(self) -> None:
        base = (self._api_base() or "https://skytycoon.info").rstrip("/")
        QDesktopServices.openUrl(QUrl(f"{base}/market/weather"))
        self._focus_dispatch_subtab("event")

    def _open_live_market_radar_portal(self) -> None:
        base = (self._api_base() or "https://skytycoon.info").rstrip("/")
        QDesktopServices.openUrl(QUrl(f"{base}/market/radar"))
        self._focus_dispatch_subtab("event")

    def _patch_charter_buttons_async(self) -> None:
        if getattr(self.win, "_platin_charter_async", False):
            return
        calc = getattr(self.win, "btn_charter_calc", None)
        disp = getattr(self.win, "btn_charter_dispatch", None)
        if calc is None and disp is None:
            return
        self.win._platin_charter_async = True
        if calc is not None:
            try:
                calc.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            calc.clicked.connect(
                lambda _c=False: self._charter_button_async(
                    "/api/v1/dispatch/calculate_custom_route"
                )
            )
        if disp is not None:
            try:
                disp.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            disp.clicked.connect(self._open_charter_flight_settings_dialog)

    def _open_charter_flight_settings_dialog(self) -> None:
        dep_w = getattr(self.win, "edit_charter_dep", None)
        arr_w = getattr(self.win, "edit_charter_arr", None)
        dep = (dep_w.text() if dep_w else "").strip().upper()[:4]
        arr = (arr_w.text() if arr_w else "").strip().upper()[:4]
        if not dep or not arr:
            QMessageBox.warning(
                self.win,
                self._tr("charter.title", "Charter"),
                self._tr("charter.icao_required", "Bitte DEP und ARR eingeben."),
            )
            return
        dlg = _CharterFlightSettingsDialog(self.win, en=self._ui_lang_en())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dlg.settings_dict()
        combo = getattr(self.win, "combo_charter_fleet", None)
        model = ""
        if combo is not None:
            model = str(combo.currentData() or combo.currentText() or "")
        payload: dict[str, Any] = {
            "dep_icao": dep,
            "arr_icao": arr,
            "aircraft_model": model,
            "passengers": 78,
            **settings,
        }
        self._pool().start(
            _CharterApiRunnable(
                self,
                "/api/v1/dispatch/activate_flight",
                payload,
            )
        )

    def _charter_button_async(self, api_path: str) -> None:
        dep_w = getattr(self.win, "edit_charter_dep", None)
        arr_w = getattr(self.win, "edit_charter_arr", None)
        dep = (dep_w.text() if dep_w else "").strip().upper()[:4]
        arr = (arr_w.text() if arr_w else "").strip().upper()[:4]
        if not dep or not arr:
            QMessageBox.warning(
                self.win,
                self._tr("charter.title", "Charter"),
                self._tr("charter.icao_required", "Bitte DEP und ARR eingeben."),
            )
            return
        combo = getattr(self.win, "combo_charter_fleet", None)
        model = ""
        if combo is not None:
            model = str(combo.currentData() or combo.currentText() or "")
        lbl = getattr(self.win, "label_charter_rewards", None)
        if lbl is not None and api_path.endswith("calculate_custom_route"):
            lbl.setText(self._tr("charter.calc_busy", "Berechne Charter-Route…"))
        self._pool().start(
            _CharterApiRunnable(
                self,
                api_path,
                {
                    "dep_icao": dep,
                    "arr_icao": arr,
                    "aircraft_model": model,
                    "passengers": 78,
                },
            )
        )

    def _on_charter_api_fail(self, err: str) -> None:
        QMessageBox.warning(
            self.win,
            self._tr("charter.title", "Charter"),
            self._tr("charter.net_err", "Server nicht erreichbar: {err}").format(
                err=err
            ),
        )

    def _on_charter_api_done(self, packet: object) -> None:
        if not isinstance(packet, dict):
            return
        api_path = str(packet.get("path") or "")
        data = packet.get("data")
        if not isinstance(data, dict):
            data = {}
        if not data.get("ok"):
            detail = data.get("detail") or data.get("error") or "error"
            QMessageBox.warning(
                self.win, self._tr("charter.title", "Charter"), str(detail)
            )
            return
        if api_path.endswith("calculate_custom_route"):
            lbl = getattr(self.win, "label_charter_rewards", None)
            if lbl is not None:
                lbl.setText(
                    self._tr(
                        "charter.reward_fmt",
                        "Strecke: {dist} NM | Credits: {cr} | XP: {xp} | Mit +15%: {crb} CR / {xpb} XP",
                    ).format(
                        dist=data.get("distance_nm", 0),
                        cr=data.get("credits", data.get("credits_base", 0)),
                        xp=data.get("xp", data.get("xp_miles", data.get("xp_miles_base", 0))),
                        crb=data.get("credits_with_bonus", 0),
                        xpb=data.get(
                            "xp_with_bonus",
                            data.get("xp_miles_with_bonus", 0),
                        ),
                    )
                )
            append = getattr(self.win, "_append_log", None)
            if callable(append):
                dep = data.get("dep_icao", "?")
                arr = data.get("arr_icao", "?")
                append(
                    f"Charter: {dep}→{arr} — {data.get('distance_nm', 0)} NM, "
                    f"{data.get('credits', 0)} CR (+15% Dispatch)."
                )
            return
        if api_path.endswith("dispatch_custom_route") or api_path.endswith(
            "activate_flight"
        ):
            dep = data.get("dep_icao", "?")
            arr = data.get("arr_icao", "?")
            settings = data.get("flight_settings") or {}
            if data.get("pax_mode") or settings.get("pax_mode"):
                mode_txt = (
                    "Passenger live (+25% CR/XP)"
                    if self._ui_lang_en()
                    else "Passagier-Live (+25% CR/XP)"
                )
            else:
                mode_txt = (
                    "Ferry flight"
                    if self._ui_lang_en()
                    else "Überführungsflug"
                )
            append = getattr(self.win, "_append_log", None)
            if callable(append):
                append(
                    self._tr(
                        "charter.dispatched_log",
                        "Charter scharfgeschaltet: {dep}→{arr} (+15% nach Landung).",
                    ).format(dep=dep, arr=arr)
                    + f" · {mode_txt}"
                )
            if data.get("gsx_auto_requested") or settings.get("pax_mode") or settings.get(
                "vip_flight"
            ):
                self._gsx_pax_auto_handshake_async()
            QMessageBox.information(
                self.win,
                self._tr("charter.title", "Charter"),
                self._tr(
                    "charter.dispatched_ok",
                    "Charter-Flug aktiv. Nach Landung: exakte Credits/XP inkl. +15% Sky-Dispatch.",
                ),
            )
            refresh = getattr(self.win, "_refresh_charter_popular_routes", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass

    def _cabin_announcement_filenames(self) -> list[str]:
        names: list[str] = []
        anns = getattr(self.m, "CABIN_MANUAL_ANNOUNCEMENTS", ()) or ()
        for key, _, _ in anns:
            for lo in ("de", "en"):
                for g in ("female", "male"):
                    names.append(f"{key}_{lo}_{g}.wav")
        return names

    def _cabin_sound_roots(self) -> list[Path]:
        seen: set[str] = set()
        roots: list[Path] = []
        for base in (
            Path(os.getcwd()),
            Path(getattr(self.m, "BASE_DIR", Path.cwd())),
            Path(__file__).resolve().parent,
        ):
            p = base / "assets" / "sounds"
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            roots.append(p)
        if hasattr(self.m, "assets_sounds_dir"):
            p = Path(self.m.assets_sounds_dir())
            key = str(p)
            if key not in seen:
                seen.add(key)
                roots.append(p)
        return roots

    def _cabin_sounds_dir(self) -> Path:
        root = Path(os.getcwd()) / "assets" / "sounds"
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            root = Path(getattr(self.m, "BASE_DIR", Path.cwd())) / "assets" / "sounds"
            root.mkdir(parents=True, exist_ok=True)
        return root

    def _platin_forward_sound_path(self, filename: str) -> str:
        """QSoundEffect: bereinigter Forward-Slash-Pfad (assets/sounds/…)."""
        return str(Path(os.getcwd()) / "assets" / "sounds" / filename).replace(
            "\\", "/"
        )

    def _cabin_sound_path_str(self, filename: str) -> str:
        for root in self._cabin_sound_roots():
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            p = root / filename
            if _cabin_audio_is_real(p):
                return str(p.resolve()).replace("\\", "/")
            if p.is_file() and p.suffix.lower() == ".mp3":
                try:
                    if p.stat().st_size > PLATIN_MIN_REAL_AUDIO_BYTES:
                        return str(p.resolve()).replace("\\", "/")
                except OSError:
                    pass
        primary = Path(os.getcwd()) / "assets" / "sounds" / filename
        try:
            primary.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            primary = (
                Path(getattr(self.m, "BASE_DIR", Path.cwd()))
                / "assets"
                / "sounds"
                / filename
            )
            primary.parent.mkdir(parents=True, exist_ok=True)
        return str(primary.resolve()).replace("\\", "/")

    def _mirror_cabin_wav_to_cwd(self, filename: str, src: Path | None = None) -> None:
        dest = Path(os.getcwd()) / "assets" / "sounds" / filename
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        if dest.is_file() and dest.stat().st_size > 128:
            return
        if src is None:
            for root in self._cabin_sound_roots():
                p = root / filename
                if p.is_file() and p.stat().st_size > 128:
                    src = p
                    break
        if src is None or not src.is_file():
            return
        try:
            dest.write_bytes(src.read_bytes())
        except OSError:
            pass

    def _ensure_cabin_qsound(self) -> QSoundEffect:
        fx = getattr(self.win, "_platin_cabin_qsound", None)
        if fx is None:
            fx = QSoundEffect(self.win)
            fx.setLoopCount(1)
            fx.setVolume(PLATIN_CABIN_DEFAULT_VOL / 100.0)
            self.win._platin_cabin_qsound = fx
        vol = max(0.0, min(1.0, self._platin_cabin_volume_pct() / 100.0))
        if vol <= 0.0:
            vol = PLATIN_CABIN_DEFAULT_VOL / 100.0
        fx.setVolume(vol)
        return fx

    def _play_cabin_wav_qsound(self, filename: str) -> bool:
        self._mirror_cabin_wav_to_cwd(filename)
        path_str = self._cabin_sound_path_str(filename)
        p = Path(path_str.replace("/", os.sep))
        if not _cabin_audio_is_real(p):
            path_str = self._platin_forward_sound_path(filename)
            p = Path(path_str.replace("/", os.sep))
        if not _cabin_audio_is_real(p) and not (
            p.is_file() and p.suffix.lower() == ".mp3" and p.stat().st_size > 8000
        ):
            return False
        path_abs = str(p.resolve()).replace("\\", "/")
        vol = max(
            PLATIN_CABIN_DEFAULT_VOL / 100.0,
            self._platin_cabin_volume_pct() / 100.0,
        )

        def _fire_play() -> None:
            try:
                fx = self._ensure_cabin_qsound()
                fx.stop()
                url = QUrl.fromLocalFile(path_abs)
                if url.isEmpty():
                    return
                fx.setSource(url)
                if fx.source().isEmpty():
                    return
                fx.setVolume(vol)

                def _start_play(*_args: Any, **_kwargs: Any) -> None:
                    try:
                        if fx.isLoaded():
                            fx.play()
                            try:
                                fx.statusChanged.disconnect(_start_play)
                            except (RuntimeError, TypeError):
                                pass
                    except RuntimeError:
                        pass

                try:
                    fx.statusChanged.disconnect()
                except (RuntimeError, TypeError):
                    pass
                fx.statusChanged.connect(_start_play)
                if fx.isLoaded():
                    _start_play()
            except RuntimeError:
                pass

        QTimer.singleShot(0, _fire_play)
        return True

    def _cabin_sounds_need_download(self) -> bool:
        root = self._cabin_sounds_dir()
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        wavs = [p for p in root.glob("*.wav") if p.is_file() and p.stat().st_size > 64]
        if len(wavs) < 8:
            return True
        if hasattr(self.m, "cabin_sounds_all_present"):
            try:
                return not bool(self.m.cabin_sounds_all_present())
            except Exception:
                return True
        return len(wavs) < 40

    def _cabin_audio_download_async(self) -> None:
        if getattr(self.win, "_platin_cabin_dl_running", False):
            return
        self.win._platin_cabin_dl_running = True
        self._pool().start(_FnRunnable(self._cabin_audio_download_work))

    def _cabin_audio_download_work(self) -> None:
        try:
            if hasattr(self.m, "ensure_builtin_sound_wavs"):
                self.m.ensure_builtin_sound_wavs()
            for root in self._cabin_sound_roots():
                try:
                    root.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
            root = self._cabin_sounds_dir()
            root.mkdir(parents=True, exist_ok=True)
            session = requests.Session()
            session.headers.update(
                {"User-Agent": f"SkyTycoonPro/{getattr(self.m, 'APP_VERSION', '1.0')}"}
            )
            for fname in self._cabin_announcement_filenames():
                dest = root / fname
                if dest.is_file() and dest.stat().st_size > 128:
                    continue
                for base in CABIN_CDN_BASES:
                    url = f"{base.rstrip('/')}/{fname}"
                    try:
                        r = session.get(url, timeout=25)
                        if r.status_code == 200 and len(r.content) > 128:
                            dest.write_bytes(r.content)
                            break
                    except (requests.RequestException, OSError, ValueError):
                        continue
            try:
                import download_cabin_sounds as dcs

                for r in self._cabin_sound_roots():
                    dcs.download_all(r)
            except Exception:
                pass
            try:
                self.m.ensure_cabin_announcements_download(background=False)
            except Exception:
                pass
            roots = list(self._cabin_sound_roots())
            _ensure_platin_cabin_voice_files(self.m, roots)
        finally:
            self.win._platin_cabin_dl_running = False
            ready = False
            try:
                ready = bool(self.m.cabin_sounds_all_present())
            except Exception:
                ready = False
            QTimer.singleShot(
                0,
                lambda: setattr(self.win, "_platin_cabin_dl_ready", ready),
            )

    def _synth_missing_cabin_announcements(self, root: Path) -> None:
        """Keine Pieps-Töne — echte Stimmen nur per CDN/TTS."""
        return

    def _ensure_cabin_volume_defaults(self) -> None:
        for k in ("platin_cabin_volume_pct", "cabin_sb_volume_pct"):
            raw = (self.m.app_meta_get(self.db_path, k, "") or "").strip()
            if not raw:
                self.m.app_meta_set(self.db_path, k, str(PLATIN_CABIN_DEFAULT_VOL))

    def _platin_cabin_volume_pct(self) -> int:
        self._ensure_cabin_volume_defaults()
        try:
            v = int(
                float(
                    self.m.app_meta_get(self.db_path, "platin_cabin_volume_pct", "")
                    or self.m.app_meta_get(self.db_path, "cabin_sb_volume_pct", "")
                    or PLATIN_CABIN_DEFAULT_VOL
                )
            )
        except (TypeError, ValueError):
            v = PLATIN_CABIN_DEFAULT_VOL
        return max(0, min(100, v))

    def _platin_cabin_lang_gender(self) -> tuple[str, str]:
        lang = self.m.app_meta_get(self.db_path, "cabin_sb_lang", "de") or "de"
        gender = self.m.app_meta_get(self.db_path, "cabin_sb_gender", "female") or "female"
        combo_l = getattr(self.win, "combo_platin_cabin_lang", None)
        combo_g = getattr(self.win, "combo_platin_cabin_gender", None)
        if combo_l is not None:
            lang = str(combo_l.currentData() or lang)
        if combo_g is not None:
            gender = str(combo_g.currentData() or gender)
        return str(lang), str(gender)

    def _play_board_gong(self) -> None:
        for name in ("cabin_chime.wav", "dingdong.wav", "boarding_chime.wav"):
            if self._play_cabin_wav_qsound(name):
                return

    def _download_cabin_wav_now(self, key: str, lang: str, gender: str) -> Path | None:
        lo = "en" if str(lang).lower().startswith("en") else "de"
        g = "male" if str(gender).lower() in ("male", "m", "männlich", "man") else "female"
        fname = f"{key}_{lo}_{g}.wav"
        root = self._cabin_sounds_dir()
        root.mkdir(parents=True, exist_ok=True)
        dest = root / fname
        for alt_root in self._cabin_sound_roots():
            if alt_root == root:
                continue
            try:
                alt_root.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            alt_dest = alt_root / fname
        if dest.is_file() and dest.stat().st_size > 128:
            return dest
        session = requests.Session()
        session.headers.update(
            {"User-Agent": f"SkyTycoonPro/{getattr(self.m, 'APP_VERSION', '1.0')}"}
        )
        for base in CABIN_CDN_BASES:
            url = f"{base.rstrip('/')}/{fname}"
            try:
                r = session.get(url, timeout=18)
                if r.status_code == 200 and len(r.content) > 128:
                    dest.write_bytes(r.content)
                    for alt_root in self._cabin_sound_roots():
                        if alt_root == root:
                            continue
                        try:
                            (alt_root / fname).write_bytes(r.content)
                        except OSError:
                            pass
                    return dest
            except (requests.RequestException, OSError, ValueError):
                continue
        phrase = (
            PLATIN_CABIN_TTS_SCRIPTS.get(key, {})
            .get(lo, {})
            .get(g, "")
        )
        if phrase and _tts_windows_generate_wav(phrase, dest, gender=g):
            return dest
        if _cabin_audio_is_real(dest):
            return dest
        return None

    def _sync_platin_cabin_soundboard(self) -> None:
        """Kein pygame-Volume — nur QSoundEffect (kein System-Ping)."""
        lang_raw = (
            self.m.app_meta_get(self.db_path, "ui_lang", "")
            or self.m.app_meta_get(self.db_path, "selected_language", "")
            or self.m.app_meta_get(self.db_path, "cabin_sb_lang", "de")
            or "de"
        )
        self.m.app_meta_set(
            self.db_path,
            "cabin_sb_lang",
            "en" if str(lang_raw).lower().startswith("en") else "de",
        )
        g_raw = self.m.app_meta_get(self.db_path, "cabin_sb_gender", "female") or "female"
        self.m.app_meta_set(self.db_path, "cabin_sb_gender", str(g_raw)[:16])

    def _platin_play_cabin_announcement(self, key: str) -> None:
        self._ensure_cabin_volume_defaults()
        lang, gender = self._platin_cabin_lang_gender()
        sb = getattr(self.win, "_cabin_soundboard", None)
        if sb is not None:
            try:
                sb.set_lang(lang)
                sb.set_gender(gender)
                sb.set_volume_pct(self._platin_cabin_volume_pct())
                if sb.play_key(key):
                    return
            except Exception:
                pass
        lo = "en" if str(lang).lower().startswith("en") else "de"
        g = "male" if str(gender).lower() in ("male", "m", "männlich", "man") else "female"
        fname = f"{key}_{lo}_{g}.wav"
        roots = self._cabin_sound_roots()
        phrase = (
            PLATIN_CABIN_TTS_SCRIPTS.get(key, {})
            .get(lo, {})
            .get(g, "")
        )
        if phrase:
            for root in roots:
                dest = root / fname
                if not _cabin_audio_is_real(dest):
                    if _tts_windows_generate_wav(phrase, dest, gender=g):
                        self._mirror_cabin_wav_to_cwd(fname, dest)
                        break
        if self._play_cabin_wav_qsound(fname):
            return
        path = self._download_cabin_wav_now(key, lang, gender)
        if path is not None:
            self._mirror_cabin_wav_to_cwd(fname, path)
        if sb is not None and sb.play_key(key):
            return
        if self._play_cabin_wav_qsound(fname):
            return
        if not getattr(self.win, "_platin_cabin_dl_running", False):
            self._cabin_audio_download_async()

    def _bootstrap_cabin_sounds(self) -> None:
        if getattr(self.win, "_platin_cabin_boot", False):
            return
        self.win._platin_cabin_boot = True
        self.win._play_cabin_soundboard_announcement = self._platin_play_cabin_announcement
        QTimer.singleShot(0, self._cabin_audio_download_async)
        QTimer.singleShot(8000, self._cabin_assets_hint_once)

    def _cabin_assets_hint_once(self) -> None:
        if getattr(self.win, "_platin_cabin_hint_shown", False):
            return
        ready = getattr(self.win, "_platin_cabin_dl_ready", False)
        try:
            ready = ready or bool(self.m.cabin_sounds_all_present())
        except Exception:
            pass
        dl_lbl = getattr(self.win, "_platin_cabin_dl_status", None)
        if dl_lbl is not None:
            en = self._ui_lang_en()
            if ready:
                dl_lbl.setText(
                    "✅ Cabin audio ready — tap any announcement."
                    if en
                    else "✅ Kabinen-Audio bereit — Ansage antippen."
                )
            else:
                dl_lbl.setText(
                    "⏬ Still loading cabin audio…"
                    if en
                    else "⏬ Kabinen-Audio lädt noch…"
                )
        if ready:
            return
        if self._cabin_sounds_need_download():
            self._cabin_audio_download_async()
        self.win._platin_cabin_hint_shown = True

    def _gsx_pax_auto_handshake_async(self) -> None:
        """Passagier/VIP-Flug: GSX MENU_OPEN → 200ms → Catering → Boarding."""

        def _work() -> None:
            if not getattr(self.win, "simconnect_connected", False):
                return
            sm = getattr(self.win, "_sm", None)
            aq = getattr(self.win, "_aq", None)
            if sm is None and aq is None:
                return
            self.m.app_meta_set(self.db_path, "ground_ops_mode", "gsx")
            if sm is not None:
                for ev in GSX_MENU_OPEN_SIM_EVENTS:
                    if self._gsx_send_simconnect_event(sm, ev, 1):
                        break
                time.sleep(0.2)
                for ev in GSX_NATIVE_SIM_EVENTS.get("catering", ()):
                    self._gsx_send_simconnect_event(sm, ev, 1)
                for ev in GSX_NATIVE_SIM_EVENTS.get("boarding", ()):
                    self._gsx_send_simconnect_event(sm, ev, 1)
            if aq is not None:
                for key in ("catering", "boarding"):
                    lvar = GSX_TRIGGER_LVARS.get(key)
                    if lvar:
                        try:
                            aq.set(lvar, 1.0)
                        except Exception:
                            pass

        self._pool().start(_FnRunnable(_work))

    def _gsx_start_full_handling_async(self) -> None:
        """GSX-Bodenabfertigung: Menü öffnen → Betankung → Catering → Boarding in MSFS."""

        def _work() -> None:
            if not getattr(self.win, "simconnect_connected", False):
                return
            sm = getattr(self.win, "_sm", None)
            aq = getattr(self.win, "_aq", None)
            if sm is None and aq is None:
                return
            self.m.app_meta_set(self.db_path, "ground_ops_mode", "gsx")
            radio = getattr(self.win, "radio_ground_gsx", None)
            if radio is not None:
                try:
                    radio.setChecked(True)
                except RuntimeError:
                    pass
            if sm is not None:
                for ev in GSX_START_HANDLING_SIM_EVENTS:
                    if self._gsx_send_simconnect_event(sm, ev, 1):
                        break
                self._gsx_open_menu_native(sm, aq)
                time.sleep(0.35)
                for action in ("refuel", "catering", "boarding"):
                    time.sleep(0.28)
                    for ev in GSX_NATIVE_SIM_EVENTS.get(action, ()):
                        if self._gsx_send_simconnect_event(sm, ev, 1):
                            break
                    lvar = GSX_TRIGGER_LVARS.get(action)
                    if aq is not None and lvar:
                        try:
                            aq.set(lvar, 1.0)
                        except Exception:
                            pass
            elif aq is not None:
                for action in ("refuel", "catering", "boarding"):
                    lvar = GSX_TRIGGER_LVARS.get(action)
                    if lvar:
                        try:
                            aq.set(lvar, 1.0)
                        except Exception:
                            pass

            def _post_cloud() -> None:
                try:
                    if hasattr(self.win, "_gsx_post_update_status"):
                        self.win._gsx_post_update_status(start_command=True)
                except Exception:
                    pass

            QTimer.singleShot(0, self.win, _post_cloud)

        self._pool().start(_FnRunnable(_work))

    def _trigger_gsx_async(self, action: str) -> None:
        if action not in GSX_NATIVE_SIM_EVENTS:
            return
        if not getattr(self.win, "simconnect_connected", False):
            QMessageBox.warning(
                self.win,
                self._tr("platin.gsx.title", "GSX Pro Remote Control"),
                self._tr(
                    "platin.gsx.no_sim",
                    "MSFS/SimConnect nicht verbunden — zuerst Simulator starten und verbinden.",
                ),
            )
            return
        self.m.app_meta_set(self.db_path, "ground_ops_mode", "gsx")
        radio = getattr(self.win, "radio_ground_gsx", None)
        if radio is not None:
            try:
                radio.setChecked(True)
            except RuntimeError:
                pass

        def _work() -> None:
            if not getattr(self.win, "simconnect_connected", False):
                return
            sm = getattr(self.win, "_sm", None)
            aq = getattr(self.win, "_aq", None)
            if sm is None and aq is None:
                return
            if sm is not None:
                self._gsx_open_menu_native(sm, aq)
                time.sleep(0.22)
                for ev in GSX_NATIVE_SIM_EVENTS[action]:
                    if self._gsx_send_simconnect_event(sm, ev, 1):
                        break
            lvar = GSX_TRIGGER_LVARS.get(action)
            if aq is not None and lvar:
                try:
                    aq.set(lvar, 1.0)
                except Exception:
                    pass
            if action == "refuel" and self._online():
                try:
                    storage, cap = self._fetch_fuel_status_sync()
                    self._safe_bus_emit(self._bus.fuel_status,storage, cap)
                except Exception:
                    pass

        self._pool().start(_FnRunnable(_work))

    def _gsx_poll_async(self) -> None:
        if not getattr(self.win, "simconnect_connected", False):
            return

        def _work() -> None:
            aq = getattr(self.win, "_aq", None)
            if aq is None:
                return
            state = 0
            boarded = 0.0
            progress = 0.0
            try:
                state = int(float(aq.get(GSX_POLL_LVARS[0]) or 0))
                boarded = float(aq.get(GSX_POLL_LVARS[1]) or 0)
                progress = float(aq.get(GSX_POLL_LVARS[2]) or 0)
            except (TypeError, ValueError, Exception):
                pass
            total_pax = 180.0
            job = getattr(self.win, "_job_board_selected_job", None)
            if isinstance(job, dict):
                try:
                    total_pax = max(
                        1.0,
                        float(
                            job.get("passengers")
                            or job.get("pax")
                            or job.get("payload_pax")
                            or 180
                        ),
                    )
                except (TypeError, ValueError):
                    pass
            if state == 6:
                pct = 100
            elif progress > 0:
                pct = int(min(100, max(0, progress * 100 if progress <= 1 else progress)))
            elif boarded > 0:
                pct = int(min(100, round(100.0 * boarded / total_pax)))
            else:
                pct = 0
            self._safe_bus_emit(self._bus.gsx_boarding_pct,state, pct, boarded)
            self._gsx_post_boarding_status(state, pct, boarded)

        self._pool().start(_FnRunnable(_work))

    def _on_gsx_boarding_pct(self, state: int, pct: int, boarded: float) -> None:
        if hasattr(self.win, "prog_platin_gsx_boarding") and _qt_widget_alive(
            self.win.prog_platin_gsx_boarding
        ):
            self.win.prog_platin_gsx_boarding.setValue(pct)
        if hasattr(self.win, "label_platin_gsx_boarding") and _qt_widget_alive(
            self.win.label_platin_gsx_boarding
        ):
            self.win.label_platin_gsx_boarding.setText(
                self._tr(
                    "platin.gsx.status_fmt",
                    "GSX Boarding: {pct}% · State {st} · Pax {pax}",
                ).format(pct=pct, st=state, pax=int(boarded))
            )
        pax_board = getattr(self.win, "_platin_pax_boarding_lbl", None)
        if _qt_widget_alive(pax_board):
            pax_board.setText(
                (
                    "🧳 GSX boarding live: {pct}% · {pax} passengers on board"
                    if self._ui_lang_en()
                    else "🧳 GSX-Boarding live: {pct}% · {pax} Passagiere an Bord"
                ).format(pct=pct, pax=int(boarded))
            )

    def _gsx_post_boarding_status(self, state: int, pct: int, boarded: float) -> None:
        if not self._online():
            return
        base = self._api_base()
        if not base:
            return
        pilot = (
            self.m.app_meta_get(self.db_path, "pilot_display_name", "")
            or self.m.app_meta_get(self.db_path, "pilot_name", "")
            or ""
        ).strip()[:80]
        body = {
            "hardware_id": self.m.p2p_hardware_id(self.db_path),
            "username": pilot,
            "pilot_name": pilot,
            "boarding_status": str(state),
            "boarding_pct": pct,
            "total_progress": pct,
            "catering_pct": 0,
            "baggage_pct": 0,
            "gsx_ready": pct >= 100 or state == 6,
            "status": "DEPARTURE_READY" if (pct >= 100 or state == 6) else "BOARDING_ACTIVE",
            "boarded_pax": boarded,
        }
        try:
            requests.post(
                f"{base}/api/v1/gsx/update_status",
                json=body,
                headers=self._headers(),
                timeout=8,
            )
        except requests.RequestException:
            pass

    def _coldstart_auth_gate(self) -> None:
        """Jeder Kaltstart: nur StartupAuthDialog — Rest erst nach Login."""
        if getattr(self.win, "_platin_auth_gate_done", False) or _PLATIN_PREMAIN_AUTH_OK:
            self.win._platin_auth_gate_done = True
            if _PLATIN_PREMAIN_AUTH_OK:
                self.win._platin_license_trusted = True
                self.win._platin_license_prompt_block_until = time.time() + 86400.0
            self._after_platin_login_success()
            self._post_auth_bootstrap()
            return
        if not _run_modal_startup_auth(self.win, self.m, self.db_path, self):
            try:
                self.win.close()
            except RuntimeError:
                pass
            return

    def _post_startup_license_enforce(self) -> None:
        """Nach Login: keine zweite Lizenz-Maske wenn Portal-Login bereits OK."""
        if not getattr(self.win, "_platin_auth_gate_done", False):
            return
        if getattr(self.win, "_platin_license_trusted", False):
            _unlock_six_main_hub_tabs(self.win)
            self.win._platin_fresh_cloud_sync = True
            self._cloud_sync_pull_async()
            return
        if self.m.app_meta_get(self.db_path, "license_activated", "0") == "1":
            _unlock_six_main_hub_tabs(self.win)
            self.win._platin_fresh_cloud_sync = True
            self._cloud_sync_pull_async()
            return
        if getattr(self.win, "_platin_license_pending", False):
            self.win._platin_license_pending = False
            QTimer.singleShot(0, self._show_license_dialog)
            return
        self.win._platin_fresh_cloud_sync = True
        self._enforce_license_or_lock()

    def _enforce_license_or_lock(self) -> None:
        def _work() -> None:
            licensed = False
            base = self._api_base()
            pilot = (
                self.m.app_meta_get(self.db_path, "pilot_display_name", "")
                or self.m.app_meta_get(self.db_path, "pilot_name", "")
                or ""
            ).strip()
            em = (
                self.m.app_meta_get(self.db_path, "portal_email", "")
                or pilot
                or ""
            ).strip().lower()
            pw = (self.m.cloud_password_get(self.db_path) or "").strip()
            if base and pilot and pw:
                try:
                    body = _sterile_login_json(
                        self.m,
                        self.db_path,
                        pilot,
                        pw,
                        license_key=(
                            self.m.app_meta_get(self.db_path, "license_key_installed", "")
                            or ""
                        ),
                        portal_email=em,
                    )
                    endpoint = f"{base}/api/v1/profile/cloud_sync"
                    r = requests.post(
                        endpoint,
                        json=body,
                        headers=self._headers(),
                        timeout=12,
                    )
                    j = r.json() if r.content else {}
                    st_lc = str(j.get("status", "")).lower()
                    if (
                        st_lc in ("ok", "activated", "success")
                        or int(j.get("has_license") or 0)
                        or bool(j.get("auto_license_activated"))
                    ):
                        licensed = True
                        self.m.app_meta_set(self.db_path, "license_activated", "1")
                        lk = str(j.get("license_key") or "").strip()
                        if lk:
                            self.m.app_meta_set(
                                self.db_path, "license_key_installed", lk[:256]
                            )
                except (requests.RequestException, json.JSONDecodeError, ValueError):
                    pass
            if not licensed and self.m.app_meta_get(self.db_path, "license_activated", "0") == "1":
                ok, _ = self.m.ionos_drm_gate_run(self.db_path)
                licensed = ok
            if not licensed:
                key = (
                    self.m.app_meta_get(self.db_path, "license_key_installed", "") or ""
                ).strip()
                if key and re.match(
                    r"^ST-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$", key.upper()
                ):
                    ok, _ = self.m.ionos_drm_gate_run(self.db_path)
                    licensed = ok
            if licensed:
                self.m.app_meta_set(self.db_path, "license_activated", "1")
                self.win._platin_license_trusted = True
                win = self.win
                QTimer.singleShot(0, win, lambda w=win: _unlock_six_main_hub_tabs(w))
                self._cloud_sync_pull_async()
                return
            if getattr(self.win, "_platin_license_trusted", False):
                return
            if self.m.app_meta_get(self.db_path, "license_activated", "0") == "1":
                return
            block_until = float(
                getattr(self.win, "_platin_license_prompt_block_until", 0) or 0
            )
            if block_until > time.time():
                return
            win = self.win
            QTimer.singleShot(0, win, lambda w=win: _lock_six_main_hub_tabs(w))
            self._safe_bus_emit(self._bus.license_need_dialog)

        self._pool().start(_FnRunnable(_work))

    def _license_gate_async(self) -> None:
        if not getattr(self.win, "_platin_auth_gate_done", False):
            return
        self._enforce_license_or_lock()

    def _wire_cloud_sync_engine(self) -> None:
        if getattr(self.win, "_platin_cloud_hook", False):
            return
        self.win._platin_cloud_hook = True
        filt = _PlatinCloseEventFilter(self)
        self.win._platin_close_filter = filt
        self.win.installEventFilter(filt)

    def _cloud_license_payload(self) -> dict[str, Any]:
        pilot = (
            self.m.app_meta_get(self.db_path, "pilot_display_name", "")
            or self.m.app_meta_get(self.db_path, "pilot_name", "")
            or ""
        ).strip()
        em = (
            self.m.app_meta_get(self.db_path, "portal_email", "")
            or pilot
            or ""
        ).strip().lower()
        pw = (self.m.cloud_password_get(self.db_path) or "").strip()
        lk = ""
        if self.m.app_meta_get(self.db_path, "license_activated", "0") == "1":
            lk = (
                self.m.app_meta_get(self.db_path, "license_key_installed", "") or ""
            ).strip()
        return dict(
            _sterile_login_json(
                self.m,
                self.db_path,
                pilot,
                pw,
                license_key=lk,
                portal_email=em,
            )
        )

    def _collect_cloud_save_body(self) -> dict[str, Any]:
        body = self._cloud_license_payload()
        try:
            conn = self.m._conn(self.db_path)
            row = conn.execute(
                "SELECT credits, xp FROM pilot_stats WHERE id = 1;"
            ).fetchone()
            conn.close()
            if row:
                body["credits"] = float(row[0] or 0)
                body["xp"] = float(row[1] or 0)
        except Exception:
            body.setdefault("credits", 0.0)
            body.setdefault("xp", 0.0)
        body["reputation"] = float(
            self.m.app_meta_get(self.db_path, "company_reputation", "72") or 72
        )
        body["fuel_storage"] = int(
            getattr(self.win, "_platin_cached_fuel", {}).get("storage") or 0
        )
        body["fuel_max_capacity"] = int(
            getattr(self.win, "_platin_cached_fuel", {}).get("cap") or 50_000
        )
        body["flight_minutes"] = float(
            self.m.app_meta_get(self.db_path, "last_flight_minutes", "0") or 0
        )
        fleet = getattr(self.win, "fleet_data", None)
        if isinstance(fleet, list):
            body["fleet_data"] = fleet
        return body

    def _cloud_sync_pull_async(self) -> None:
        if not self._online():
            return
        base = self._api_base()
        if not base:
            return

        def _work() -> None:
            err = ""
            ok = False
            try:
                payload = self._cloud_license_payload()
                r = requests.post(
                    f"{base}/api/v1/profile/cloud_sync",
                    json=payload,
                    headers=self._headers(),
                    timeout=25,
                )
                j = r.json()
                ok = bool(j.get("ok"))
                _store_login_access_token(self.m, self.db_path, j)
                if str(j.get("role", "")).upper() == "SUPERADMIN" or j.get("is_superadmin"):
                    self.m.app_meta_set(self.db_path, "platin_superadmin", "1")
                    self.m.app_meta_set(self.db_path, "online_network_enabled", "1")
                    em_sa = str(
                        j.get("email")
                        or payload.get("portal_email")
                        or payload.get("email")
                        or GLOBAL_SUPERADMIN_EMAIL
                    ).strip().lower()
                    if em_sa and "@" in em_sa:
                        self.m.app_meta_set(self.db_path, "portal_email", em_sa[:200])
                if j.get("auto_license_activated") or int(j.get("has_license") or 0):
                    lk_auto = str(j.get("license_key") or "").strip()
                    if lk_auto:
                        self.m.app_meta_set(
                            self.db_path, "license_key_installed", lk_auto[:256]
                        )
                    self.m.app_meta_set(self.db_path, "license_activated", "1")
                    win = self.win
                    QTimer.singleShot(0, win, lambda w=win: _unlock_six_main_hub_tabs(w))
                profile = j.get("profile") if isinstance(j.get("profile"), dict) else j
                blob = str(j.get("profile_blob") or "").strip()
                if blob:
                    try:
                        from skytycoon_profile_cloud import unpack_profile_blob

                        unpacked = unpack_profile_blob(blob)
                        if unpacked:
                            profile = unpacked
                    except Exception:
                        pass
                lang_srv = str(
                    j.get("selected_language")
                    or j.get("ui_lang")
                    or ""
                ).strip().lower()[:8]
                if ok and isinstance(profile, dict):
                    if getattr(self.win, "_platin_fresh_cloud_sync", False):
                        self.m.reset_local_career_to_starter_profile(
                            self.db_path, profile
                        )
                    cred_srv = float(profile.get("credits", 0) or 0)
                    if cred_srv >= 49999.0:
                        self.m.app_meta_set(self.db_path, "license_activated", "1")
                        self.m.app_meta_set(self.db_path, "online_network_enabled", "1")
                    if not lang_srv:
                        lang_srv = str(
                            profile.get("selected_language")
                            or profile.get("ui_lang")
                            or ""
                        ).strip().lower()[:8]
                    self.m.apply_server_profile_authority(self.db_path, profile)
                    QTimer.singleShot(0, lambda p=profile: self._apply_gui_from_profile(p))
                    win_ok = self.win
                    QTimer.singleShot(
                        0,
                        win_ok,
                        lambda w=win_ok: (_show_main_cockpit(w), _unlock_six_main_hub_tabs(w)),
                    )
                if lang_srv in ("de", "en"):
                    win_lang = self.win
                    QTimer.singleShot(
                        0,
                        win_lang,
                        lambda w=win_lang, lg=lang_srv: _apply_desktop_language(
                            w, self.db_path, self.m, lg
                        ),
                    )
            except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
                err = str(exc)
            self._safe_bus_emit(self._bus.cloud_sync_done,ok, err)

        self._pool().start(_FnRunnable(_work))

    def _on_cloud_sync_done(self, ok: bool, _msg: str) -> None:
        if getattr(self.win, "_platin_fresh_cloud_sync", False):
            self.win._platin_fresh_cloud_sync = False
        if ok:
            if self.m.app_meta_get(self.db_path, "license_activated", "0") == "1":
                _show_main_cockpit(self.win)
                win = self.win
                QTimer.singleShot(0, win, lambda w=win: _unlock_six_main_hub_tabs(w))
            if hasattr(self.win, "_refresh_credits_label"):
                self.win._refresh_credits_label()

    def _apply_gui_from_profile(self, profile: dict[str, Any]) -> None:
        cred = float(profile.get("credits", 0) or 0)
        xp_v = float(profile.get("xp", 0) or 0)
        for attr, val in (("credits", cred), ("xp", xp_v)):
            if hasattr(self.win, attr):
                setattr(self.win, attr, val)
        fleet = profile.get("fleet_data") or profile.get("fleet")
        if isinstance(fleet, list) and hasattr(self.win, "fleet_data"):
            self.win.fleet_data = fleet
        fuel_s = int(profile.get("fuel_storage", 0) or 0)
        fuel_c = max(50_000, int(profile.get("fuel_max_capacity", 50_000) or 50_000))
        if fuel_s or fuel_c:
            self._on_fuel_status(fuel_s, fuel_c)
        if hasattr(self.win, "_refresh_credits_label"):
            self.win._refresh_credits_label()
        bridge = getattr(self.win, "_profile_cloud_bridge", None)
        if bridge is not None:
            try:
                bridge.profile_updated.emit(profile)
            except RuntimeError:
                pass

    def _cloud_save_async(self) -> None:
        if not self._online() or self._cloud_save_armed:
            return
        base = self._api_base()
        if not base:
            return
        if self.m.app_meta_get(self.db_path, "license_activated", "0") != "1":
            return
        if getattr(self.win, "_platin_fresh_cloud_sync", False):
            return
        if getattr(self.m, "PLATIN_CLOUD_ONLY", False):
            em = (
                self.m.app_meta_get(self.db_path, "career_bound_portal_email", "")
                or self.m.app_meta_get(self.db_path, "portal_email", "")
            ).strip()
            if not em or "@" not in em:
                return
        self._cloud_save_armed = True

        def _work() -> None:
            try:
                body = self._collect_cloud_save_body()
                requests.post(
                    f"{base}/api/v1/profile/cloud_save",
                    json=body,
                    headers=self._headers(),
                    timeout=30,
                )
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                pass
            finally:
                self._cloud_save_armed = False

        self._pool().start(_FnRunnable(_work))

    def _check_sim_shutdown_cloud_save(self) -> None:
        graceful = bool(
            getattr(self.win, "_simconnect_graceful_close", False)
            or getattr(self.win, "_graceful_sim_shutdown", False)
        )
        if graceful and not self._last_graceful_save:
            self._last_graceful_save = True
            self._cloud_save_async()
        elif not graceful:
            self._last_graceful_save = False

    def _show_license_dialog(self) -> None:
        if _PLATIN_BLOCK_STARTUP_POPUPS or not getattr(
            self.win, "_platin_auth_gate_done", False
        ):
            self.win._platin_license_pending = True
            return
        if getattr(self.win, "_platin_license_trusted", False):
            _unlock_six_main_hub_tabs(self.win)
            return
        block_until = float(
            getattr(self.win, "_platin_license_prompt_block_until", 0) or 0
        )
        if block_until > time.time():
            return
        if self.m.app_meta_get(self.db_path, "license_activated", "0") == "1":
            _show_main_cockpit(self.win)
            _unlock_six_main_hub_tabs(self.win)
            return
        _lock_six_main_hub_tabs(self.win)
        dlg = _PlatinLicenseDialog(self.win, self.db_path, self.m)
        dlg._lbl.setText(_license_required_bilingual_text())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            _unlock_six_main_hub_tabs(self.win)
            self._cloud_sync_pull_async()
            return
        QMessageBox.warning(
            self.win,
            self._tr("platin.license.title", "Lizenz"),
            self._tr(
                "platin.license.continue_offline",
                "Keine Aktivierung — Hub-Reiter bleiben gesperrt.",
            ),
        )

    def _apply_branches_payload(self, data: dict) -> None:
        raw = data.get("branches")
        if raw is None:
            raw = data.get("branches_json")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                return
        if not isinstance(raw, list) or not raw:
            return
        try:
            n = self.m._apply_cloud_branches_to_local(self.db_path, raw)
        except Exception:
            return
        if n and hasattr(self.win, "_refresh_realty_broker_table_rows"):
            QTimer.singleShot(0, self.win._refresh_realty_broker_table_rows)

    def _pull_branches_from_ionos_async(self) -> None:
        if self._sync_busy or not self._online():
            return

        def _work() -> None:
            try:
                ok, msg = self.m.career_cloud_pull_branches_to_local(self.db_path)
                self._safe_bus_emit(self._bus.branches_pull_done,ok, str(msg))
            except Exception as exc:
                self._safe_bus_emit(self._bus.branches_pull_done,False, str(exc))

        self._pool().start(_FnRunnable(_work))

    def _on_branches_pull_done(self, ok: bool, _msg: str) -> None:
        if ok and hasattr(self.win, "_refresh_realty_broker_table_rows"):
            self.win._refresh_realty_broker_table_rows()

    def _wire_profile_branches_sync(self) -> None:
        bridge = getattr(self.win, "_profile_cloud_bridge", None)
        if bridge is None or getattr(self.win, "_platin_branches_hook", False):
            return

        def _on_profile(data: dict) -> None:
            if not isinstance(data, dict):
                return
            if data.get("branches") or data.get("branches_json"):
                self._apply_branches_payload(data)

        bridge.profile_updated.connect(_on_profile)
        self.win._platin_branches_hook = True

    def _gold_frame(self, title_key: str, title_default: str) -> tuple[QFrame, QVBoxLayout]:
        fr = QFrame()
        fr.setObjectName("platinTile")
        fr.setStyleSheet(GOLD_TILE_STYLE)
        lay = QVBoxLayout(fr)
        hdr = QLabel(self._tr(title_key, title_default))
        hdr.setObjectName("platinHdr")
        lay.addWidget(hdr)
        return fr, lay

    def _inject_bank_fuel_platin(self) -> None:
        if getattr(self.win, "_platin_fuel_host", None) is not None:
            return
        parent_w = getattr(self.win, "_bank_fuel_tab", None)
        if parent_w is None:
            anchor = getattr(self.win, "label_bank_fuel_tank", None)
            parent_w = anchor.parentWidget() if anchor else None
        if parent_w is None:
            return
        lay = parent_w.layout()
        if lay is None:
            return

        fr, fl = self._gold_frame(
            "platin.fuel.title",
            "⛽ Kerosin-Tank & Ausbaustufen",
        )
        self.win.label_platin_fuel_bar = QLabel("—")
        self.win.label_platin_fuel_bar.setWordWrap(True)
        fl.addWidget(self.win.label_platin_fuel_bar)
        self.win.prog_platin_fuel_tank = QProgressBar()
        self.win.prog_platin_fuel_tank.setRange(0, 100)
        self.win.prog_platin_fuel_tank.setFormat(
            self._tr("platin.fuel.bar_fmt", "%p % · Postgres-Lager")
        )
        self.win.prog_platin_fuel_tank.setStyleSheet(
            "QProgressBar { border:1px solid #3a3a42; height:24px; }"
            "QProgressBar::chunk { background:#3a3a42; }"
        )
        fl.addWidget(self.win.prog_platin_fuel_tank)
        tier_row = QHBoxLayout()
        self.win._platin_fuel_btns: list[QPushButton] = []
        for i, liters in enumerate(FUEL_TIER_LITERS):
            cost = FUEL_TIER_COSTS[i]
            btn = QPushButton(
                self._tr(
                    "platin.fuel.tier_btn",
                    "Stufe {n}: {lit} L ({cost} CR)",
                ).format(
                    n=i + 1,
                    lit=f"{liters // 1000}k",
                    cost=f"{int(cost // 1000)}k",
                )
            )
            btn.setObjectName("platinBtn")
            btn.setStyleSheet(GOLD_TILE_STYLE)
            btn.clicked.connect(lambda _c=False, ix=i: self._on_fuel_tier_async(ix))
            tier_row.addWidget(btn)
            self.win._platin_fuel_btns.append(btn)
        fl.addLayout(tier_row)
        self.win._platin_fuel_host = fr
        lay.addWidget(fr)

    def _fetch_fuel_status_sync(self) -> tuple[int, int]:
        storage, cap = 0, 50_000
        base = self._api_base()
        if base and self._online():
            try:
                r = requests.get(
                    f"{base}/api/v1/fuel/tank/status",
                    headers=self._headers(),
                    timeout=8,
                )
                j = r.json()
                if j.get("ok"):
                    storage = int(j.get("fuel_storage") or 0)
                    cap = max(50_000, int(j.get("fuel_max_capacity") or 50_000))
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                pass
        return storage, cap

    def _background_sync_ram_cache(self) -> None:
        if self._sync_busy:
            return
        self._sync_busy = True

        def _work() -> None:
            try:
                storage, cap = self._fetch_fuel_status_sync()
                self._safe_bus_emit(self._bus.fuel_status,storage, cap)
                if not getattr(self.win, "_platin_branches_applied_once", False):
                    if self._online():
                        ok, _ = self.m.career_cloud_pull_branches_to_local(self.db_path)
                        self._safe_bus_emit(self._bus.branches_pull_done,ok, "")
                        self.win._platin_branches_applied_once = True
            finally:
                self._sync_busy = False

        self._pool().start(_FnRunnable(_work))

    def _on_fuel_status(self, storage: int, cap: int) -> None:
        pct = int(min(100, max(0, round(100.0 * storage / cap)))) if cap else 0
        txt = self._tr(
            "platin.fuel.stored_fmt",
            "Gelagert: {cur} / {max} Liter",
        ).format(
            cur=f"{storage:,}".replace(",", "."),
            max=f"{cap:,}".replace(",", "."),
        )
        self.win._platin_cached_fuel = {
            "storage": storage,
            "cap": cap,
            "pct": pct,
            "txt": txt,
            "ready": True,
            "ts": time.time(),
        }
        self._paint_fuel_from_ram_cache()

    def _paint_fuel_from_ram_cache(self) -> None:
        if not hasattr(self.win, "prog_platin_fuel_tank"):
            return
        c = getattr(self.win, "_platin_cached_fuel", None) or {}
        storage = int(c.get("storage") or 0)
        cap = max(50_000, int(c.get("cap") or 50_000))
        pct = int(c.get("pct") or 0)
        txt = str(c.get("txt") or "—")
        self.win.prog_platin_fuel_tank.setRange(0, max(cap, 1))
        self.win.prog_platin_fuel_tank.setValue(storage)
        self.win.label_platin_fuel_bar.setText(txt)
        if hasattr(self.win, "prog_fuel_tank"):
            self.win.prog_fuel_tank.setValue(pct)
        if hasattr(self.win, "label_bank_fuel_tank"):
            self.win.label_bank_fuel_tank.setText(txt)

    def _on_fuel_tier_async(self, tier_ix: int) -> None:
        base = self._api_base()
        if not base:
            return
        for btn in getattr(self.win, "_platin_fuel_btns", []):
            btn.setEnabled(False)

        def _work() -> None:
            err = ""
            ok = False
            try:
                r = requests.post(
                    f"{base}/api/v1/fuel/tank/upgrade",
                    json={
                        "tier_index": tier_ix,
                        "hardware_id": self.m.p2p_hardware_id(self.db_path),
                    },
                    headers=self._headers(),
                    timeout=20,
                )
                data = r.json()
                ok = bool(data.get("ok"))
                if not ok:
                    err = str(data.get("message") or data.get("error") or "?")
            except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
                err = str(exc)
            self._safe_bus_emit(self._bus.fuel_upgrade_done,ok, err)

        self._pool().start(_FnRunnable(_work))

    def _on_fuel_upgrade_done(self, ok: bool, err: str) -> None:
        for btn in getattr(self.win, "_platin_fuel_btns", []):
            btn.setEnabled(True)
        if not ok:
            QMessageBox.warning(
                self.win,
                self._tr("platin.fuel.title", "Tank"),
                err or "?",
            )
            return
        self._background_sync_ram_cache()
        if hasattr(self.win, "_refresh_credits_label"):
            self.win._refresh_credits_label()
        QMessageBox.information(
            self.win,
            self._tr("platin.fuel.title", "Tank"),
            self._tr("platin.fuel.upgrade_ok", "Tank-Ausbau erfolgreich."),
        )

    def _ui_lang_en(self) -> bool:
        lg = (
            self.m.app_meta_get(self.db_path, "ui_lang", "")
            or self.m.app_meta_get(self.db_path, "selected_language", "")
            or "de"
        )
        return str(lg).strip().lower().startswith("en")

    def _detach_platin_widget(self, attr: str) -> None:
        w = getattr(self.win, attr, None)
        if w is None:
            return
        try:
            w.setParent(None)
            w.deleteLater()
        except RuntimeError:
            pass
        setattr(self.win, attr, None)

    def _inject_pax_main_tab(self) -> None:
        if getattr(self.win, "_platin_pax_fused_v2", False):
            return
        tw = getattr(self.win, "tab_widget", None)
        if tw is None:
            return
        for i in range(tw.count()):
            title = (tw.tabText(i) or "").lower()
            if "passagier" in title and "pax" in title:
                self.win._platin_pax_tab_ix = i
                self.win._platin_pax_fused_v2 = True
                return
        self._detach_platin_widget("_platin_pax_panel")
        self._detach_platin_widget("_platin_pax_profile_ticker")
        tw = getattr(self.win, "tab_widget", None)
        if tw is None:
            return
        old_ix = getattr(self.win, "_platin_pax_tab_ix", None)
        if old_ix is not None and 0 <= int(old_ix) < tw.count():
            try:
                old_w = tw.widget(int(old_ix))
                tw.removeTab(int(old_ix))
                if old_w is not None:
                    old_w.deleteLater()
            except (RuntimeError, TypeError, ValueError):
                pass
        self._ensure_cabin_volume_defaults()
        en = self._ui_lang_en()
        tab_title = (
            "👥 Passenger Feedback & Pax Radar"
            if en
            else "👥 Passagier-Feedback / Pax Radar"
        )
        page = QWidget()
        page.setStyleSheet(_PLATIN_GLOBAL_DARK_STYLE)
        root = QVBoxLayout(page)
        hdr = QLabel(tab_title)
        hdr.setStyleSheet("color:#e8e8ec;font-weight:900;font-size:15px;")
        root.addWidget(hdr)
        split = QHBoxLayout()
        left = QFrame()
        left.setStyleSheet(
            "QFrame{background:#0b0b10;border:2px solid #3a3a42;border-radius:10px;}"
        )
        left_l = QVBoxLayout(left)
        left_hdr = QLabel(
            "🎙️ Cabin PA · 48 voices (DE/EN)"
            if en
            else "🎙️ Kabinen-Funk · 48 Stimmen (DE/EN)"
        )
        left_hdr.setStyleSheet("color:#e8e8ec;font-weight:900;font-size:12px;")
        left_l.addWidget(left_hdr)
        vol_row = QHBoxLayout()
        vol_row.addWidget(
            QLabel("🔊 Volume / Lautstärke" if en else "🔊 Lautstärke / Volume")
        )
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(self._platin_cabin_volume_pct())
        slider.valueChanged.connect(self._on_platin_volume_changed)
        vol_row.addWidget(slider, 1)
        self.win._platin_volume_slider = slider
        left_l.addLayout(vol_row)
        self._apply_platin_cabin_volume()
        self.win._platin_cabin_dl_status = QLabel(
            "⏬ Loading cabin audio…" if en else "⏬ Kabinen-Audio lädt…"
        )
        self.win._platin_cabin_dl_status.setStyleSheet("color:#90a4ae;font-size:11px;")
        left_l.addWidget(self.win._platin_cabin_dl_status)
        lg_row = QHBoxLayout()
        lg_row.addWidget(QLabel("Lang" if en else "Spr."))
        self.win.combo_platin_cabin_lang = QComboBox()
        self.win.combo_platin_cabin_lang.addItem("DE", "de")
        self.win.combo_platin_cabin_lang.addItem("EN", "en")
        self.win.combo_platin_cabin_lang.setCurrentIndex(1 if en else 0)
        lg_row.addWidget(self.win.combo_platin_cabin_lang)
        lg_row.addWidget(QLabel("Voice" if en else "Stimme"))
        self.win.combo_platin_cabin_gender = QComboBox()
        self.win.combo_platin_cabin_gender.addItem("♀", "female")
        self.win.combo_platin_cabin_gender.addItem("♂", "male")
        lg_row.addWidget(self.win.combo_platin_cabin_gender)
        left_l.addLayout(lg_row)

        def _on_lang_gender_changed(_v: int = 0) -> None:
            lang = str(self.win.combo_platin_cabin_lang.currentData() or "de")
            gender = str(self.win.combo_platin_cabin_gender.currentData() or "female")
            self.m.app_meta_set(self.db_path, "cabin_sb_lang", lang[:8])
            self.m.app_meta_set(self.db_path, "cabin_sb_gender", gender[:16])
            self._sync_platin_cabin_soundboard()

        self.win.combo_platin_cabin_lang.currentIndexChanged.connect(
            _on_lang_gender_changed
        )
        self.win.combo_platin_cabin_gender.currentIndexChanged.connect(
            _on_lang_gender_changed
        )
        sat_fr = getattr(self.win, "frame_passenger_satisfaction", None)
        if sat_fr is not None:
            try:
                sat_fr.setParent(None)
            except RuntimeError:
                pass
            left_l.addWidget(sat_fr)
        cabin_scroll = QScrollArea()
        cabin_scroll.setWidgetResizable(True)
        cabin_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cabin_scroll.setMinimumHeight(320)
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setSpacing(6)
        anns = getattr(self.m, "CABIN_MANUAL_ANNOUNCEMENTS", ()) or ()
        existing: dict[str, QPushButton] = {}
        for idx, (key, i18n_key, default_lbl) in enumerate(anns):
            btn = (getattr(self.win, "_cabin_sb_buttons", None) or {}).get(key)
            if btn is None:
                btn = QPushButton(self._tr(i18n_key, default_lbl))
            try:
                btn.setParent(None)
            except RuntimeError:
                pass
            btn.setMinimumHeight(48)
            btn.setStyleSheet(
                "QPushButton{background:#161618;color:#3a3a42;border:2px solid #3a3a42;"
                "border-radius:8px;font-weight:800;padding:6px;}"
                "QPushButton:hover{background:#2a1f0a;}"
            )
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            btn.clicked.connect(
                lambda _c=False, k=key: self._platin_play_cabin_announcement(k)
            )
            grid.addWidget(btn, idx // 2, idx % 2)
            existing[key] = btn
        self.win._cabin_sb_buttons = existing
        cabin_scroll.setWidget(grid_host)
        left_l.addWidget(cabin_scroll, 1)
        split.addWidget(left, 1)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_w = QWidget()
        right_l = QVBoxLayout(right_w)
        radar_hdr = QLabel(
            "📡 Pax Radar · Live PostgreSQL"
            if en
            else "📡 Pax-Radar · Live PostgreSQL"
        )
        radar_hdr.setStyleSheet("color:#e8e8ec;font-weight:900;font-size:12px;")
        right_l.addWidget(radar_hdr)
        stats = QHBoxLayout()
        self.win._platin_pax_avg_lbl = QLabel(
            "⭐ Avg satisfaction: —" if en else "⭐ Ø Pax-Zufriedenheit: —"
        )
        self.win._platin_pax_avg_lbl.setStyleSheet(
            "color:#e8e8ec;font-weight:800;font-size:13px;"
        )
        self.win._platin_pax_mult_lbl = QLabel(
            "💰 Credit multiplier: ×1.00"
            if en
            else "💰 Credit-Multiplikator: ×1,00"
        )
        self.win._platin_pax_mult_lbl.setStyleSheet(
            "color:#00ff66;font-weight:800;font-size:13px;"
        )
        stats.addWidget(self.win._platin_pax_avg_lbl)
        stats.addWidget(self.win._platin_pax_mult_lbl)
        stats.addStretch(1)
        right_l.addLayout(stats)
        appr_row = QHBoxLayout()
        self.win._platin_pax_approval_lbl = QLabel(
            "Pax approval" if en else "Pax-Zustimmung"
        )
        self.win._platin_pax_approval_bar = QProgressBar()
        self.win._platin_pax_approval_bar.setRange(0, 100)
        self.win._platin_pax_approval_bar.setFormat("%p%")
        appr_row.addWidget(self.win._platin_pax_approval_lbl)
        appr_row.addWidget(self.win._platin_pax_approval_bar, 1)
        right_l.addLayout(appr_row)
        self.win._platin_pax_carousel = QLabel(
            "✈️ Waiting for passenger voices…"
            if en
            else "✈️ Warte auf Passagierstimmen…"
        )
        self.win._platin_pax_carousel.setWordWrap(True)
        self.win._platin_pax_carousel.setMinimumHeight(100)
        self.win._platin_pax_carousel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.win._platin_pax_carousel.setStyleSheet(
            "color:#eceff1;font-size:14px;font-weight:700;padding:14px;"
            "background:#12161f;border:2px solid #3a3a42;border-radius:10px;"
        )
        right_l.addWidget(self.win._platin_pax_carousel, 1)
        self.win._platin_pax_sqi_lbl = QLabel("SQI: —")
        self.win._platin_pax_sqi_lbl.setStyleSheet(
            "color:#00e676;font-weight:800;font-size:12px;"
        )
        right_l.addWidget(self.win._platin_pax_sqi_lbl)
        self.win._platin_pax_boarding_lbl = QLabel("🧳 GSX: —")
        self.win._platin_pax_boarding_lbl.setStyleSheet(
            "color:#42a5f5;font-weight:700;font-size:12px;"
        )
        right_l.addWidget(self.win._platin_pax_boarding_lbl)
        self.win._platin_pax_log = QTextEdit()
        self.win._platin_pax_log.setReadOnly(True)
        self.win._platin_pax_log.setMaximumHeight(160)
        right_l.addWidget(self.win._platin_pax_log)
        right_scroll.setWidget(right_w)
        split.addWidget(right_scroll, 1)
        root.addLayout(split, 1)
        insert_at = getattr(self.win, "_platin_pax_tab_insert_after", None)
        if isinstance(insert_at, int) and 0 <= insert_at <= tw.count():
            ix = tw.insertTab(insert_at, page, tab_title)
        else:
            dispatch_ix = getattr(self.win, "_hub_ix_dispatch", None)
            if isinstance(dispatch_ix, int) and dispatch_ix >= 0:
                ix = tw.insertTab(min(dispatch_ix + 1, tw.count()), page, tab_title)
            else:
                ix = tw.addTab(page, tab_title)
        self.win._platin_pax_tab_ix = ix
        self.win._platin_pax_main_tab = page
        self.win._platin_pax_carousel_lines = []
        self.win._platin_pax_carousel_ix = 0
        self.win._platin_cabin_merged = True
        self.win._platin_pax_fused_v2 = True
        finalize = getattr(self.win, "_finalize_main_tab_bar", None)
        if callable(finalize):
            finalize()
        _apply_platin_global_dark_theme(self.win)
        self._sync_platin_cabin_soundboard()
        self._apply_platin_cabin_volume()
        if not getattr(self.win, "_platin_pax_timer", None):
            self.win._platin_pax_timer = QTimer(self.win)
            self.win._platin_pax_timer.setInterval(5000)
            self.win._platin_pax_timer.timeout.connect(self._pax_feedback_pull_async)
            self.win._platin_pax_timer.start()
        if not getattr(self.win, "_platin_pax_carousel_timer", None):
            self.win._platin_pax_carousel_timer = QTimer(self.win)
            self.win._platin_pax_carousel_timer.setInterval(4200)
            self.win._platin_pax_carousel_timer.timeout.connect(
                self._pax_carousel_rotate_ui
            )
            self.win._platin_pax_carousel_timer.start()
        QTimer.singleShot(5500, self._pax_feedback_pull_async)

    def _hide_cabin_live_hub_tab(self) -> None:
        if getattr(self.win, "_platin_cabin_hub_hidden", False):
            return
        tw = getattr(self.win, "tab_widget", None)
        if tw is None:
            return
        cabin_markers = (
            "cabin live",
            "kabinen-funk",
            "kabinen funk",
            "cabin pa",
            "live cabin",
        )

        def _is_cabin_tab_title(title: str) -> bool:
            t = (title or "").lower()
            return any(m in t for m in cabin_markers)

        removed = False
        try:
            for i in range(tw.count() - 1, -1, -1):
                title = tw.tabText(i)
                ix_hint = getattr(self.win, "_hub_ix_cabin", None)
                if _is_cabin_tab_title(title) or (
                    ix_hint is not None and int(i) == int(ix_hint)
                ):
                    w = tw.widget(i)
                    tw.removeTab(i)
                    if w is not None:
                        w.deleteLater()
                    removed = True
            if removed:
                setattr(self.win, "_hub_ix_cabin", None)
                hosts = getattr(self.win, "_hub_host_widgets", None)
                if isinstance(hosts, dict):
                    hosts.pop("cabin", None)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        self.win._platin_cabin_hub_hidden = True

    def _pax_carousel_rotate_ui(self) -> None:
        car = getattr(self.win, "_platin_pax_carousel", None)
        lines = getattr(self.win, "_platin_pax_carousel_lines", None) or []
        if not _qt_widget_alive(car) or not lines:
            return
        ix = int(getattr(self.win, "_platin_pax_carousel_ix", 0) or 0) % len(lines)
        self.win._platin_pax_carousel_ix = ix + 1
        car.setText(lines[ix])

    def _pax_feedback_pull_async(self) -> None:
        if not self._online():
            return
        base = self._api_base()
        if not base:
            return
        en = self._ui_lang_en()

        def _work() -> None:
            lines: list[str] = []
            carousel: list[str] = []
            avg_stars = 0.0
            bonus = 1.0
            approval_pct = 0.0
            sqi = 0.0
            werft_idx = 100.0
            catering_score = 88.0
            try:
                hid = _normalize_client_hwid(self.m, self.db_path)
                r = requests.get(
                    f"{base}/api/v1/pax/feedback",
                    params={"hardware_id": hid, "limit": 24, "lang": "en" if en else "de"},
                    headers=self._headers(),
                    timeout=12,
                )
                j = r.json()
                avg_stars = float(j.get("avg_stars") or 0)
                bonus = float(j.get("credit_bonus_multiplier") or 1.0)
                approval_pct = float(j.get("approval_pct") or (avg_stars / 5.0) * 100.0)
                sqi = float(j.get("service_quality_index") or 0)
                werft_idx = float(j.get("werft_condition_pct") or 100.0)
                catering_score = float(j.get("catering_score") or 88.0)
                for row in j.get("comments") or []:
                    stars = int(row.get("stars") or 5)
                    mult = float(row.get("multiplier") or 1.0)
                    txt = str(row.get("comment") or "").strip()
                    lines.append(f"{'★' * stars}  ×{mult:.2f}  —  {txt}")
                    carousel.append(
                        f"{'★' * stars}\n\n“{txt}”\n\n×{mult:.2f} CR bonus"
                    )
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                lines = []
                carousel = []
            txt_out = (
                "\n\n".join(lines)
                if lines
                else (
                    "No passenger comments yet."
                    if en
                    else "Noch keine Passagierkommentare."
                )
            )
            avg_txt = (
                f"⭐ Avg satisfaction: {avg_stars:.2f} / 5"
                if en
                else f"⭐ Ø Pax-Zufriedenheit: {avg_stars:.2f} / 5"
            )
            mult_txt = (
                f"💰 Credit multiplier bonus: ×{bonus:.2f}"
                if en
                else f"💰 Credit-Multiplikator-Bonus: ×{bonus:.2f}"
            )
            appr_lbl_txt = (
                f"Pax approval · linked to ×{bonus:.2f} CR multiplier"
                if en
                else f"Pax-Zustimmung · gekoppelt an ×{bonus:.2f} CR-Multiplikator"
            )
            sqi_txt = (
                f"Service Quality Index (SQI): {sqi:.1f}% · "
                f"Hangar {werft_idx:.0f}% · Catering {catering_score:.0f}%"
                if en
                else f"Service-Quality-Index (SQI): {sqi:.1f}% · "
                f"Werft {werft_idx:.0f}% · Catering {catering_score:.0f}%"
            )
            if not carousel:
                carousel = [
                    (
                        "✈️ No passenger voices yet — fly your next leg!"
                        if en
                        else "✈️ Noch keine Pax-Stimmen — starte den nächsten Flug!"
                    )
                ]
            self._safe_bus_emit(self._bus.pax_feedback_ready,
                {
                    "carousel": carousel,
                    "log_text": txt_out,
                    "avg_txt": avg_txt,
                    "mult_txt": mult_txt,
                    "appr_lbl_txt": appr_lbl_txt,
                    "approval_pct": approval_pct,
                    "sqi_txt": sqi_txt,
                }
            )

        self._pool().start(_FnRunnable(_work))

    def _on_pax_feedback_ready(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        if not _qt_widget_alive(getattr(self.win, "_platin_pax_main_tab", None)):
            return
        self.win._platin_pax_carousel_lines = list(payload.get("carousel") or [])
        log = getattr(self.win, "_platin_pax_log", None)
        if _qt_widget_alive(log):
            log.setPlainText(str(payload.get("log_text") or ""))
        for attr, key in (
            ("_platin_pax_avg_lbl", "avg_txt"),
            ("_platin_pax_mult_lbl", "mult_txt"),
            ("_platin_pax_approval_lbl", "appr_lbl_txt"),
            ("_platin_pax_sqi_lbl", "sqi_txt"),
        ):
            w = getattr(self.win, attr, None)
            if _qt_widget_alive(w):
                w.setText(str(payload.get(key) or ""))
        bar = getattr(self.win, "_platin_pax_approval_bar", None)
        if _qt_widget_alive(bar):
            bar.setValue(
                max(0, min(100, int(round(float(payload.get("approval_pct") or 0)))))
            )
        self._pax_carousel_rotate_ui()

    def _on_warehouse_item_double_clicked(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        item_id = int(item.data(Qt.ItemDataRole.UserRole) or 0)
        if item_id <= 0:
            return
        meta = item.data(Qt.ItemDataRole.UserRole + 1) or {}
        if not isinstance(meta, dict):
            meta = {}
        dlg = _P2PPartsListDialog(
            self.win,
            item_id=item_id,
            item_label=str(item.text() or ""),
            item_type=str(meta.get("item_type") or ""),
            condition=str(meta.get("condition") or ""),
            en=self._ui_lang_en(),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._p2p_parts_list_async(
            item_id=item_id,
            price=dlg.price_value(),
            listing_type=dlg.listing_type_value(),
            auction_days=dlg.auction_days_value(),
        )

    def _inject_p2p_lease_hangar(self) -> None:
        if getattr(self.win, "_platin_p2p_market_page", None) is not None:
            return
        parent_w = getattr(self.win, "hangar_inner_tabs", None)
        if parent_w is None:
            parent_w = getattr(self.win, "_hub_leaf_hangar", None)
        if parent_w is None:
            return
        en = self._ui_lang_en()
        page = QWidget()
        page.setStyleSheet(_PLATIN_GLOBAL_DARK_STYLE)
        root = QVBoxLayout(page)
        self.win._platin_p2p_ticker = QLabel(
            "📈 LIVE MARKET TICKER — loading…"
            if en
            else "📈 LIVE-BÖRSENTICKER — lädt…"
        )
        self.win._platin_p2p_ticker.setStyleSheet(
            "color:#e8e8ec;font-weight:800;font-size:12px;padding:8px 12px;"
            "background:#161618;border:2px solid #3a3a42;border-radius:8px;"
        )
        self.win._platin_p2p_ticker.setMinimumHeight(36)
        root.addWidget(self.win._platin_p2p_ticker)
        sub = QTabWidget()
        tab_ac = (
            "✈️ Worldwide aircraft marketplace"
            if en
            else "✈️ Weltweiter Flugzeug-Marktplatz"
        )
        tab_wh = (
            "📁 My spare parts warehouse"
            if en
            else "📁 Mein Ersatzteil-Lager"
        )
        tab_gl = (
            "🌍 Global live marketplace"
            if en
            else "🌍 Globaler Live-Marktplatz"
        )
        wh_page = QWidget()
        wh_l = QVBoxLayout(wh_page)
        wh_hint = QLabel(
            "Double-click a part to open the listing mixer (price, auction, publish)."
            if en
            else "Doppelklick auf ein Teil öffnet den Inserats-Mischpult (Preis, Auktion, veröffentlichen)."
        )
        wh_hint.setWordWrap(True)
        wh_hint.setStyleSheet("color:#90a4ae;font-size:11px;padding:4px 0;")
        wh_l.addWidget(wh_hint)
        self.win._platin_parts_list = QListWidget()
        self.win._platin_parts_list.setAlternatingRowColors(True)
        self.win._platin_parts_list.setStyleSheet(
            "QListWidget{background:#08080c;border:2px solid #3a3a42;border-radius:8px;"
            "color:#eceff1;font-size:12px;}"
            "QListWidget::item{padding:10px 12px;border-bottom:1px solid #2a3545;}"
            "QListWidget::item:selected{background:#161618;color:#e8e8ec;}"
        )
        self.win._platin_parts_list.itemDoubleClicked.connect(
            self._on_warehouse_item_double_clicked
        )
        wh_l.addWidget(self.win._platin_parts_list, 1)
        gl_page = QWidget()
        gl_l = QVBoxLayout(gl_page)
        self.win._platin_market_table = QTableWidget(0, 7)
        self.win._platin_market_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Kind",
                "Price",
                "Type",
                "Seller",
                "Bid",
                "Item",
            ]
            if en
            else ["ID", "Art", "Preis", "Typ", "Verkäufer", "Gebot", "Objekt"]
        )
        self.win._platin_market_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.win._platin_market_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        gl_l.addWidget(self.win._platin_market_table, 1)
        act = QHBoxLayout()
        self.win._platin_p2p_price = QLineEdit()
        self.win._platin_p2p_price.setPlaceholderText(
            "Price / bid (CR)" if en else "Preis / Gebot (CR)"
        )
        btn_buy = QPushButton("🚀 Buy now" if en else "🚀 Sofortkauf")
        btn_bid = QPushButton("🔨 Place bid" if en else "🔨 Bieten")
        btn_lease = QPushButton("📊 48h lease" if en else "📊 48h Leasing")
        act.addWidget(self.win._platin_p2p_price, 2)
        act.addWidget(btn_buy)
        act.addWidget(btn_bid)
        act.addWidget(btn_lease)
        gl_l.addLayout(act)
        market_w = getattr(self.win, "_platin_market_widget", None)
        if market_w is not None:
            sub.addTab(market_w, tab_ac)
            self._expand_widget_layouts(market_w)
        sub.addTab(wh_page, tab_wh)
        sub.addTab(gl_page, tab_gl)
        root.addWidget(sub, 1)
        if isinstance(parent_w, QTabWidget):
            while parent_w.count() > 0:
                parent_w.removeTab(0)
            parent_w.addTab(page, "💸 P2P" if en else "💸 P2P")
        self.win._platin_p2p_market_page = page
        self.win._platin_p2p_ticker_lines: list[str] = []
        self.win._platin_p2p_ticker_ix = 0
        btn_buy.clicked.connect(lambda: self._p2p_trade_selected_async("buy"))
        btn_bid.clicked.connect(lambda: self._p2p_trade_selected_async("bid"))
        btn_lease.clicked.connect(lambda: self._p2p_trade_selected_async("lease"))
        if not getattr(self.win, "_platin_p2p_feed_timer", None):
            self.win._platin_p2p_feed_timer = QTimer(self.win)
            self.win._platin_p2p_feed_timer.setInterval(5000)
            self.win._platin_p2p_feed_timer.timeout.connect(
                self._p2p_marketboard_refresh_async
            )
            self.win._platin_p2p_feed_timer.start()
        QTimer.singleShot(600, self._p2p_marketboard_refresh_async)

    def _p2p_lease_listing_async(self) -> None:
        base = self._api_base()
        if not base or not self._online():
            return

        def _work() -> None:
            try:
                body = {
                    "hardware_id": _normalize_client_hwid(self.m, self.db_path),
                    "listing_type": "lease_48h",
                    "price": float(
                        self.m.app_meta_get(self.db_path, "p2p_lease_price", "50000")
                        or 50000
                    ),
                }
                requests.post(
                    f"{base}/api/v1/p2p/list",
                    json=body,
                    headers=self._headers(),
                    timeout=20,
                )
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                pass

        self._pool().start(_FnRunnable(_work))

    def _p2p_marketboard_refresh_async(self) -> None:
        base = self._api_base()
        if not base:
            return

        def _work() -> None:
            listings: list[dict[str, Any]] = []
            ticker_lines: list[str] = []
            try:
                r = requests.get(
                    f"{base}/api/v1/p2p/marketboard",
                    headers=self._headers(),
                    timeout=14,
                )
                j = r.json()
                listings = list(j.get("listings") or [])
                ticker_lines = list(j.get("ticker") or [])
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                pass
            wh_items: list[dict[str, Any]] = []
            try:
                hid = _normalize_client_hwid(self.m, self.db_path)
                wr = requests.get(
                    f"{base}/api/v1/p2p/warehouse",
                    params={"hardware_id": hid},
                    headers=self._headers(),
                    timeout=12,
                )
                wh_items = list(wr.json().get("items") or [])
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                wh_items = []
            self._safe_bus_emit(self._bus.p2p_board_ready,
                {
                    "listings": listings,
                    "ticker_lines": ticker_lines,
                    "warehouse_items": wh_items,
                }
            )

        self._pool().start(_FnRunnable(_work))

    def _on_p2p_board_ready(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        if not _qt_widget_alive(getattr(self.win, "_platin_p2p_market_page", None)):
            return
        self.win._platin_p2p_ticker_lines = list(payload.get("ticker_lines") or [])
        tbl = getattr(self.win, "_platin_market_table", None)
        if _qt_widget_alive(tbl):
            listings = list(payload.get("listings") or [])
            tbl.setRowCount(len(listings))
            for ri, row in enumerate(listings):
                kind = str(row.get("market_kind") or "aircraft")
                obj = (
                    str(row.get("item_type") or row.get("item_id") or "—")
                    if kind == "parts"
                    else str(row.get("fleet_id") or row.get("aircraft_id") or "—")
                )
                vals = [
                    str(row.get("id") or ""),
                    kind,
                    f"{float(row.get('current_bid') or row.get('price') or 0):.0f}",
                    str(row.get("listing_type") or ""),
                    str(row.get("seller_id") or "")[:20],
                    str(row.get("highest_bidder_id") or "—")[:16],
                    obj,
                ]
                for ci, val in enumerate(vals):
                    tbl.setItem(ri, ci, QTableWidgetItem(val))
        wh_list = getattr(self.win, "_platin_parts_list", None)
        if _qt_widget_alive(wh_list):
            en_ui = self._ui_lang_en()
            wh_list.clear()
            items = list(payload.get("warehouse_items") or [])
            for it in items:
                iid = int(it.get("id") or 0)
                itype = str(it.get("item_type") or "PART")
                cond = str(it.get("condition") or "—")
                status = str(it.get("status") or "warehouse")
                icon = "🔩" if "engine" in itype.lower() else "⚙️"
                label = f"{icon}  #{iid}  ·  {itype}  ·  {cond}%  ·  {status}"
                li = QListWidgetItem(label)
                li.setData(Qt.ItemDataRole.UserRole, iid)
                li.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    {"item_type": itype, "condition": cond, "status": status},
                )
                wh_list.addItem(li)
            if not items:
                empty = (
                    "No parts in warehouse."
                    if en_ui
                    else "Keine Teile im Lager."
                )
                wh_list.addItem(QListWidgetItem(empty))
        self._p2p_ticker_rotate_ui()

    def _p2p_ticker_rotate_ui(self) -> None:
        tick = getattr(self.win, "_platin_p2p_ticker", None)
        lines = getattr(self.win, "_platin_p2p_ticker_lines", None) or []
        if not _qt_widget_alive(tick):
            return
        if not lines:
            en = self._ui_lang_en()
            tick.setText(
                "📈 LIVE MARKET TICKER — no listings"
                if en
                else "📈 LIVE-BÖRSENTICKER — keine Inserate"
            )
            return
        ix = int(getattr(self.win, "_platin_p2p_ticker_ix", 0) or 0) % len(lines)
        self.win._platin_p2p_ticker_ix = ix + 1
        prefix = "📈 LIVE · " if self._ui_lang_en() else "📈 LIVE · "
        tick.setText(prefix + lines[ix])

    def _p2p_selected_market_row(self) -> tuple[int, str]:
        tbl = getattr(self.win, "_platin_market_table", None)
        if tbl is None:
            return 0, "aircraft"
        row = tbl.currentRow()
        if row < 0:
            return 0, "aircraft"
        kind_item = tbl.item(row, 1)
        kind = str(kind_item.text() if kind_item else "aircraft")
        id_item = tbl.item(row, 0)
        lid = int(id_item.text()) if id_item and id_item.text().isdigit() else 0
        return lid, kind

    def _p2p_parts_list_async(
        self,
        *,
        item_id: int = 0,
        price: float = 0.0,
        listing_type: str = "BUY_NOW",
        auction_days: int = 1,
    ) -> None:
        base = self._api_base()
        if not base or not self._online():
            return
        if item_id <= 0:
            wh_list = getattr(self.win, "_platin_parts_list", None)
            if wh_list is not None:
                cur = wh_list.currentItem()
                if cur is not None:
                    item_id = int(cur.data(Qt.ItemDataRole.UserRole) or 0)

        def _work() -> None:
            try:
                body: dict[str, Any] = {
                    "hardware_id": _normalize_client_hwid(self.m, self.db_path),
                    "item_id": item_id or 1,
                    "price": price,
                    "listing_type": listing_type,
                    "auction_days": auction_days,
                }
                requests.post(
                    f"{base}/api/v1/p2p/parts/list",
                    json=body,
                    headers=self._headers(),
                    timeout=20,
                )
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                pass
            QTimer.singleShot(500, self._p2p_marketboard_refresh_async)

        self._pool().start(_FnRunnable(_work))

    def _p2p_trade_selected_async(self, mode: str) -> None:
        base = self._api_base()
        if not base or not self._online():
            return
        lid, kind = self._p2p_selected_market_row()
        if lid <= 0:
            en = self._ui_lang_en()
            QMessageBox.information(
                self.win,
                "P2P",
                "Select a listing in the global market table."
                if en
                else "Bitte ein Inserat in der globalen Markt-Tabelle auswählen.",
            )
            return
        pe = getattr(self.win, "_platin_p2p_price", None)
        try:
            price = float(pe.text().strip()) if pe else 0.0
        except (TypeError, ValueError, AttributeError):
            price = 0.0

        def _work() -> None:
            try:
                hid = _normalize_client_hwid(self.m, self.db_path)
                if mode == "lease":
                    fleet_id = None
                    tbl = getattr(self.win, "_platin_market_table", None)
                    if tbl is not None:
                        r = tbl.currentRow()
                        if r >= 0:
                            obj_it = tbl.item(r, 6)
                            if obj_it and str(obj_it.text()).isdigit():
                                fleet_id = int(obj_it.text())
                    requests.post(
                        f"{base}/api/v1/p2p/list",
                        json={
                            "hardware_id": hid,
                            "listing_type": "lease_48h",
                            "fleet_id": fleet_id,
                            "price": price or 50000,
                        },
                        headers=self._headers(),
                        timeout=25,
                    )
                elif mode == "bid":
                    requests.post(
                        f"{base}/api/v1/p2p/bid",
                        json={
                            "hardware_id": hid,
                            "listing_id": lid,
                            "bid": price,
                            "market": kind,
                        },
                        headers=self._headers(),
                        timeout=25,
                    )
                elif kind == "parts":
                    requests.post(
                        f"{base}/api/v1/p2p/parts/buy",
                        json={"hardware_id": hid, "listing_id": lid},
                        headers=self._headers(),
                        timeout=25,
                    )
                else:
                    requests.post(
                        f"{base}/api/v1/p2p/buy",
                        json={"hardware_id": hid, "listing_id": lid},
                        headers=self._headers(),
                        timeout=25,
                    )
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                pass
            QTimer.singleShot(600, self._p2p_marketboard_refresh_async)

        self._pool().start(_FnRunnable(_work))

    def _nuke_cabin_preview_widgets(self) -> None:
        if getattr(self.win, "_platin_cabin_preview_nuked", False):
            return
        for attr in (
            "_label_job_cabin_hdr",
            "label_cabin_caption",
            "seat_grid_host",
            "cargo_cap_bar",
            "cargo_cap_bar_lower",
            "label_cargo_deck",
        ):
            w = getattr(self.win, attr, None)
            if w is not None:
                w.hide()
                w.setParent(None)
        self.win._platin_cabin_preview_nuked = True

    def _sanitize_job_board_tabs(self) -> None:
        tabs = getattr(self.win, "job_board_tabs", None)
        if tabs is None or getattr(self.win, "_platin_local_tab_removed", False):
            return
        for i in range(tabs.count() - 1, -1, -1):
            title = (tabs.tabText(i) or "").lower()
            if "lokal" in title or "local" in title:
                tabs.removeTab(i)
                self.win._platin_local_tab_removed = True
                break

    def _inject_short_haul_main_tab(self) -> None:
        """Kurzstrecken nur als Dispatcher-Unter-Reiter in main.py — kein Extra-Haupttab."""
        return
        if getattr(self.win, "_platin_short_haul_tab_ix", None) is not None:
            return
        tw = getattr(self.win, "tab_widget", None)
        if tw is None:
            return
        en = self._ui_lang_en()
        page = QWidget()
        page.setStyleSheet(_PLATIN_GLOBAL_DARK_STYLE)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(15)
        title = QLabel(
            "✈️ Short-Haul Market · routes under 1,500 NM (UTC reset 00:00)"
            if en
            else "✈️ Kurzstrecken-Flugbörse · Strecken unter 1.500 NM (UTC-Reset 00:00)"
        )
        title.setWordWrap(True)
        title.setStyleSheet("color:#e8e8ec;font-weight:900;font-size:14px;")
        lay.addWidget(title)
        hint = QLabel(
            "Cloud jobs below 1,500 NM only. Long-haul passenger routes: Dispatch → Passenger Service."
            if en
            else "Nur Cloud-Jobs unter 1.500 NM. Langstrecken-Passagier: Flugbörse → Passagier-Service."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#90a4ae;font-size:12px;")
        lay.addWidget(hint)
        open_btn = QPushButton(
            "🛫 Load short-haul jobs (< 1,500 NM)"
            if en
            else "🛫 Kurzstrecken-Jobs laden (< 1.500 NM)"
        )
        open_btn.setStyleSheet(
            "QPushButton{background:#161618;color:#e8e8ec;border:2px solid #3a3a42;"
            "font-weight:900;padding:14px;border-radius:10px;}"
            "QPushButton:hover{background:#2c2c32;}"
        )
        open_btn.clicked.connect(self._open_short_haul_dispatch_board)
        lay.addWidget(open_btn)
        lay.addStretch()
        tab_title = (
            "✈️ Short-Haul Market"
            if en
            else "✈️ Kurzstrecken-Flugbörse"
        )
        ix = tw.insertTab(
            min(2, tw.count()),
            _platin_scroll_wrap(page),
            tab_title,
        )
        self.win._platin_short_haul_tab_ix = ix
        if not getattr(self.win, "_platin_short_haul_tab_hook", False):
            tw.currentChanged.connect(self._on_main_tab_short_haul_focus)
            self.win._platin_short_haul_tab_hook = True

    def _on_main_tab_short_haul_focus(self, index: int) -> None:
        sh_ix = getattr(self.win, "_platin_short_haul_tab_ix", None)
        active = index == sh_ix
        self.win._platin_short_haul_main_active = active
        if active:
            self._open_short_haul_dispatch_board()

    def _open_short_haul_dispatch_board(self) -> None:
        self.win._platin_short_haul_main_active = True
        dix = getattr(self.win, "_hub_ix_dispatch", -1)
        tw = getattr(self.win, "tab_widget", None)
        if isinstance(dix, int) and dix >= 0 and tw is not None:
            tw.setCurrentIndex(dix)
        inner = getattr(self.win, "_hub_tabwidgets", {}).get(dix)
        if isinstance(inner, QTabWidget):
            for i in range(inner.count()):
                t = (inner.tabText(i) or "").lower()
                if "job" in t or "vorgefertigt" in t or "prefab" in t:
                    inner.setCurrentIndex(i)
                    break
        self._request_cloud_jobs_for_short_haul()
        if hasattr(self.win, "_refresh_job_table"):
            try:
                self.win._refresh_job_table()
            except Exception:
                pass

    def _focus_dispatch_job_board(self) -> None:
        self.win._platin_short_haul_main_active = False
        dix = getattr(self.win, "_hub_ix_dispatch", -1)
        tw = getattr(self.win, "tab_widget", None)
        if isinstance(dix, int) and dix >= 0 and tw is not None:
            tw.setCurrentIndex(dix)

    def _request_cloud_jobs_for_short_haul(self) -> None:
        if hasattr(self.win, "_request_cloud_jobs_global_fallback"):
            try:
                self.win._request_cloud_jobs_global_fallback()
            except Exception:
                pass

    def _apply_global_scroll_armor(self) -> None:
        """Leichtgewichtig: kein rekursives Stretch auf alle Tabellen (verursacht UI-Freezes)."""
        if getattr(self.win, "_platin_scroll_armor_done", False):
            return
        self.win._platin_scroll_armor_done = True
        tw = getattr(self.win, "tab_widget", None)
        if tw is not None:
            tw.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
        return
        targets: list[QWidget | None] = []
        for attr in (
            "_platin_p2p_market_page",
            "_platin_market_widget",
            "_platin_gsx_host",
            "tab_alliances",
            "_platin_alliance_13_center",
            "_hub_leaf_profile",
        ):
            w = getattr(self.win, attr, None)
            if w is not None:
                targets.append(w)
        career_ix = getattr(self.win, "_hub_ix_career", None)
        inner = getattr(self.win, "_hub_tabwidgets", {}).get(career_ix)
        if isinstance(inner, QTabWidget):
            for i in range(inner.count()):
                targets.append(inner.widget(i))
        hangar_ix = getattr(self.win, "_hub_ix_hangar", None)
        hub_tw = getattr(self.win, "_hub_tabwidgets", {}).get(hangar_ix)
        if isinstance(hub_tw, QTabWidget):
            for i in range(hub_tw.count()):
                targets.append(hub_tw.widget(i))
        dispatch_ix = getattr(self.win, "_hub_ix_dispatch", None)
        d_inner = getattr(self.win, "_hub_tabwidgets", {}).get(dispatch_ix)
        if isinstance(d_inner, QTabWidget):
            for i in range(d_inner.count()):
                targets.append(d_inner.widget(i))
        crew_ix = getattr(self.win, "_hub_ix_crew", None)
        c_inner = getattr(self.win, "_hub_tabwidgets", {}).get(crew_ix)
        if isinstance(c_inner, QTabWidget):
            for i in range(c_inner.count()):
                targets.append(c_inner.widget(i))
        pax_ix = getattr(self.win, "_platin_pax_main_tab_ix", None)
        if isinstance(pax_ix, int) and hasattr(self.win, "tab_widget"):
            tw = self.win.tab_widget
            if 0 <= pax_ix < tw.count():
                targets.append(tw.widget(pax_ix))
        seen: set[int] = set()
        for w in targets:
            if w is None or id(w) in seen:
                continue
            seen.add(id(w))
            inner = self._hub_tab_unwrap(w)
            if inner is not None:
                self._expand_widget_layouts(inner)
        self.win._platin_scroll_armor_done = True

    def _patch_safe_crew_ui_refresh(self) -> None:
        """Instanz-Patch entfällt — Klassen-Patch in _patch_crew_refresh_safe."""
        _patch_crew_refresh_safe(self.m)

    def _arm_swiss_code_backup_timer(self) -> None:
        """2h-Takt: Projekt-ZIP auf dem Laufwerk des aktiven Entwickler-PCs."""
        if getattr(self.win, "_platin_swiss_backup_timer", None) is not None:
            return
        from admin_vault_core import SWISS_SYNC_INTERVAL_MS

        bak = platin_swiss_backup_root()
        t = QTimer(self.win)
        t.setInterval(SWISS_SYNC_INTERVAL_MS)
        t.timeout.connect(_platin_run_swiss_backup_zip)
        t.start()
        self.win._platin_swiss_backup_timer = t
        QTimer.singleShot(30_000, _platin_run_swiss_backup_zip)
        print(
            f"[SkyTycoon] Swiss 2h-Code-Backup → {bak} armiert.",
            flush=True,
        )

    def _install_zero_delay_lazy_tabs(self) -> None:
        """Dispatch, Charter, Karriere-Charts, FIDS — erst beim ersten Klick."""
        if getattr(self.win, "_platin_zero_lazy_installed", False):
            return
        self.win._platin_zero_lazy_installed = True
        self.win._platin_lazy_vault: dict[str, QWidget] = {}
        self.win._platin_lazy_slots: dict[str, Any] = {}
        self.win._platin_lazy_materialized: set[str] = set()
        hub_al = getattr(self.win, "_hub_ix_alliance", -1)
        if hub_al >= 0:
            self.win._tab_ix_alliance = hub_al

        for tname in ("timer_fids_rotation", "timer_fids_heartbeat"):
            t = getattr(self.win, tname, None)
            if t is not None:
                try:
                    t.stop()
                except RuntimeError:
                    pass
        pulse = getattr(self.win, "career_dash_pulse_timer", None)
        if pulse is not None:
            try:
                pulse.stop()
            except RuntimeError:
                pass
            self.win._platin_career_pulse_deferred = True

        self._lazy_stow_fids()
        self._lazy_stow_dispatch_jobs()
        self._lazy_stow_career_charts()
        print(
            "[SkyTycoon] Zero-Delay Lazy-Tabs: Dispatch, Charter, Karriere, FIDS.",
            flush=True,
        )

    def _lazy_stow_fids(self) -> None:
        if "fids" in getattr(self.win, "_platin_lazy_vault", {}):
            return
        ix = int(getattr(self.win, "_tab_ix_fids", -1))
        tw = getattr(self.win, "tab_widget", None)
        if ix < 0 or tw is None or ix >= tw.count():
            return
        shell = tw.widget(ix)
        if not isinstance(shell, QScrollArea):
            return
        real = _platin_lazy_take_from_scroll(shell)
        if real is None:
            return
        self.win._platin_lazy_vault["fids"] = real
        ph = _platin_lazy_placeholder(self, "fids")
        shell.setWidget(ph)
        self.win._platin_lazy_slots["fids"] = shell

    def _lazy_stow_dispatch_jobs(self) -> None:
        if "dispatch" in getattr(self.win, "_platin_lazy_vault", {}):
            return
        dix = int(getattr(self.win, "_hub_ix_dispatch", -1))
        inner = getattr(self.win, "_hub_tabwidgets", {}).get(dix)
        if not isinstance(inner, QTabWidget):
            return
        sub_ix = int(getattr(self.win, "_dispatch_jobs_subtab_ix", 1))
        wrapped = inner.widget(sub_ix)
        real: QWidget | None = None
        if isinstance(wrapped, QScrollArea):
            real = _platin_lazy_take_from_scroll(wrapped)
            slot = wrapped
        else:
            real = wrapped
            slot = None
        if real is None:
            return
        self.win._platin_lazy_vault["dispatch"] = real
        ph = _platin_lazy_placeholder(self, "dispatch")
        if isinstance(slot, QScrollArea):
            slot.setWidget(ph)
            self.win._platin_lazy_slots["dispatch"] = slot
        else:
            inner.removeTab(sub_ix)
            inner.insertTab(sub_ix, ph, inner.tabText(sub_ix))

    def _lazy_stow_career_charts(self) -> None:
        if "career_charts" in getattr(self.win, "_platin_lazy_vault", {}):
            return
        dash = getattr(self.win, "frame_career_dash", None)
        if dash is None:
            return
        parent = dash.parentWidget()
        lay = parent.layout() if parent is not None else None
        if lay is None:
            dash.hide()
            self.win._platin_lazy_vault["career_charts"] = dash
            return
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is None or item.widget() is not dash:
                continue
            lay.removeWidget(dash)
            ph = QWidget()
            ph.setObjectName("platinLazyCareerChartsPh")
            ph.setFixedHeight(1)
            lay.insertWidget(i, ph)
            dash.setParent(None)
            self.win._platin_lazy_vault["career_charts"] = dash
            self.win._platin_lazy_slots["career_charts"] = (parent, lay, i, ph)
            return

    def _lazy_mark_done(self, key: str) -> None:
        done = getattr(self.win, "_platin_lazy_materialized", None)
        if isinstance(done, set):
            done.add(key)

    def _ensure_lazy_vault(self) -> bool:
        if hasattr(self.win, "_platin_lazy_vault"):
            return True
        if not getattr(self.win, "_platin_zero_lazy_installed", False):
            self._install_zero_delay_lazy_tabs()
        return hasattr(self.win, "_platin_lazy_vault")

    def _lazy_materialize_fids(self) -> None:
        if "fids" in getattr(self.win, "_platin_lazy_materialized", set()):
            return
        if not self._ensure_lazy_vault():
            return
        real = self.win._platin_lazy_vault.pop("fids", None)
        slot = self.win._platin_lazy_slots.get("fids")
        if real is None or not isinstance(slot, QScrollArea):
            return
        slot.setWidget(real)
        self._lazy_mark_done("fids")
        if not getattr(self.win, "_platin_fids_timer_armed", False):
            self._arm_fids_live_refresh()
        QTimer.singleShot(0, self._fids_fetch_live_async)

    def _lazy_materialize_dispatch(self) -> None:
        if "dispatch" in getattr(self.win, "_platin_lazy_materialized", set()):
            return
        if not self._ensure_lazy_vault():
            return
        real = self.win._platin_lazy_vault.pop("dispatch", None)
        slot = self.win._platin_lazy_slots.get("dispatch")
        if real is None:
            return
        if isinstance(slot, QScrollArea):
            slot.setWidget(real)
        elif isinstance(slot, QTabWidget):
            sub_ix = int(getattr(self.win, "_dispatch_jobs_subtab_ix", 1))
            slot.removeTab(sub_ix)
            slot.insertTab(sub_ix, real, slot.tabText(sub_ix))
        self._lazy_mark_done("dispatch")
        self._patch_dispatch_eventradar_buttons()
        self._patch_charter_buttons_async()
        reparent = getattr(self.win, "_reparent_dispatch_job_board", None)
        if callable(reparent):
            try:
                reparent(kurzstrecke=False)
            except Exception:
                pass

    def _lazy_materialize_charter(self) -> None:
        self._lazy_materialize_dispatch()
        if "charter" in getattr(self.win, "_platin_lazy_materialized", set()):
            return
        self._lazy_mark_done("charter")
        self._patch_charter_buttons_async()
        rf = getattr(self.win, "_refresh_charter_fleet_combo", None)
        rp = getattr(self.win, "_refresh_charter_popular_routes", None)
        if callable(rf):
            QTimer.singleShot(0, rf)
        if callable(rp):
            QTimer.singleShot(0, rp)

    def _lazy_materialize_career_charts(self) -> None:
        if "career_charts" in getattr(self.win, "_platin_lazy_materialized", set()):
            return
        if not self._ensure_lazy_vault():
            return
        real = self.win._platin_lazy_vault.pop("career_charts", None)
        slot = self.win._platin_lazy_slots.get("career_charts")
        if real is None:
            return
        if isinstance(slot, tuple) and len(slot) == 4:
            parent, lay, idx, ph = slot
            if ph is not None and lay is not None:
                lay.removeWidget(ph)
                ph.deleteLater()
                lay.insertWidget(idx, real)
        else:
            real.show()
        self._lazy_mark_done("career_charts")
        try:
            from platin_career_layout import patch_career_original_layout

            patch_career_original_layout(self.m)
        except Exception:
            pass
        if not getattr(self.win, "_platin_career_profit_done", False):
            self._restructure_career_profit_tab()
        self._restore_career_original_layout()
        if getattr(self.win, "_platin_career_pulse_deferred", False):
            pulse = getattr(self.win, "career_dash_pulse_timer", None)
            if pulse is not None:
                try:
                    pulse.start()
                except RuntimeError:
                    pass

    def _lazy_on_main_tab(self, index: int) -> None:
        if index == int(getattr(self.win, "_hub_ix_dispatch", -999)):
            self._lazy_materialize_dispatch()
        elif index == int(getattr(self.win, "_tab_ix_fids", -999)):
            self._lazy_materialize_fids()
        elif index == int(getattr(self.win, "_hub_ix_career", -999)):
            self._lazy_materialize_career_charts()

    def _install_lazy_hub_hooks(self) -> None:
        """Schwere Hub-Patches erst beim ersten Besuch des Reiters."""
        if getattr(self.win, "_platin_lazy_hub_hooks", False):
            return
        self.win._platin_lazy_hub_hooks = True
        orig = self.win._on_main_tab_changed_impl

        def _wrapped(index: int) -> None:
            self._lazy_on_main_tab(index)
            self._lazy_prepare_hub(index)
            orig(index)

        self.win._on_main_tab_changed_impl = _wrapped

    def _lazy_prepare_hub(self, index: int) -> None:
        hangar_ix = getattr(self.win, "_hub_ix_hangar", -999)
        alliance_ix = int(
            getattr(
                self.win,
                "_hub_ix_alliance",
                getattr(self.win, "_tab_ix_alliance", -999),
            )
        )
        career_ix = getattr(self.win, "_hub_ix_career", -999)
        if index == hangar_ix:
            self._ensure_hangar_werft_hub()
        elif index == alliance_ix:
            self._ensure_alliance_13_hub()
        elif index == career_ix:
            self._lazy_materialize_career_charts()

    def _ensure_hangar_werft_hub(self) -> None:
        if getattr(self.win, "_platin_hangar_restructured", False):
            self._apply_hangar_hub_tab_labels()
            return
        self.win.setUpdatesEnabled(False)
        try:
            self._restructure_hangar_p2p_hub()
        finally:
            self.win.setUpdatesEnabled(True)

    def _ensure_alliance_13_hub(self) -> None:
        if not getattr(self.win, "_platin_wallstreet_moved", False):
            try:
                self._move_wallstreet_tabs_to_alliance()
            except Exception:
                pass
        wrap = getattr(self.win, "_wrap_alliance_wallstreet_subtabs", None)
        if callable(wrap) and not getattr(
            self.win, "_alliance_wallstreet_wrapped", False
        ):
            try:
                wrap()
            except Exception:
                pass
        if getattr(self.win, "_platin_alliance_13_installed", False):
            center = getattr(self.win, "_platin_alliance_13_center", None)
            if center is not None and hasattr(center, "refresh_current_pillar"):
                try:
                    center.refresh_current_pillar(fetch_state=False)
                except Exception:
                    pass
            return
        try:
            self._install_alliance_13_pillar_center()
            if not getattr(self.win, "_platin_scroll_armor_done", False):
                self._apply_global_scroll_armor()
        except Exception as exc:
            print(f"[SkyTycoon] Allianz-Hub: {exc!s}", flush=True)

    def _on_platin_language_changed(self) -> None:
        self._apply_hangar_hub_tab_labels()
        if hasattr(self.win, "_refresh_ceo_report_panel"):
            self.win._refresh_ceo_report_panel()
        if hasattr(self.win, "_retranslate_i18n_widgets"):
            self.win._retranslate_i18n_widgets()

    def _restore_career_original_layout(self) -> None:
        try:
            from platin_career_layout import restore_career_original_layout

            restore_career_original_layout(self.win, self)
        except Exception as exc:
            print(f"[SkyTycoon] Karriere-Layout: {exc!s}", flush=True)

    def _install_alliance_13_pillar_center(self) -> None:
        try:
            from platin_alliance_center import install_platin_alliance_13_center

            ok = install_platin_alliance_13_center(self.win, self)
            if not ok:
                print(
                    "[SkyTycoon] Allianz-13-Säulen: Installation fehlgeschlagen "
                    "(siehe alliance_inner_tabs / _alliance_inner_tabs).",
                    flush=True,
                )
        except Exception as exc:
            print(f"[SkyTycoon] Allianz-13-Säulen: {exc!s}", flush=True)

    def _fix_crew_hub_overlap(self) -> None:
        try:
            from platin_alliance_center import fix_crew_hub_overlap

            fix_crew_hub_overlap(self.win, self)
        except Exception as exc:
            print(f"[SkyTycoon] Crew-Layout: {exc!s}", flush=True)

    def _inject_crew_platin_hint(self) -> None:
        if getattr(self.win, "_platin_crew_hint_set", False):
            return
        intro = getattr(self.win, "label_crew_intro", None)
        if intro is None:
            return
        extra = self._tr(
            "platin.crew.hint",
            "Gehalt 1.500 CR · Express-Erholung 5.000 CR · Rekrutierung über Markt.",
        )
        cur = (intro.text() or "").strip()
        if extra not in cur:
            intro.setText(f"{cur}\n{extra}" if cur else extra)
        self.win._platin_crew_hint_set = True


    def _apply_platin_cabin_volume(self) -> None:
        v = self._platin_cabin_volume_pct()
        lin = max(0.0, min(1.0, v / 100.0))
        fx = getattr(self.win, "_platin_cabin_qsound", None)
        if fx is None:
            fx = self._ensure_cabin_qsound()
        try:
            fx.setVolume(lin)
        except RuntimeError:
            pass

    def _on_platin_volume_changed(self, value: int) -> None:
        v = max(0, min(100, int(value)))
        self.m.app_meta_set(self.db_path, "platin_cabin_volume_pct", str(v))
        self.m.app_meta_set(self.db_path, "cabin_sb_volume_pct", str(v))
        fx = getattr(self.win, "_platin_cabin_qsound", None)
        if fx is None:
            fx = self._ensure_cabin_qsound()
        fx.setVolume(v / 100.0)


class _CharterFlightSettingsDialog(QDialog):
    """Gold-Pop-out: Passagier-Live vs. Überführung + 5 strategische Hebel."""

    def __init__(self, parent: QWidget, *, en: bool) -> None:
        super().__init__(parent)
        self._en = en
        self.setModal(True)
        self.setStyleSheet(_PLATIN_GOLD_STYLE)
        self.setWindowTitle(
            "🎛️ Flight settings" if en else "🎛️ Flug-Einstellungen"
        )
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        hdr = QLabel(
            "Choose your flight mode and strategic options"
            if en
            else "Wähle Flugmodus und strategische Optionen"
        )
        hdr.setStyleSheet("color:#e8e8ec;font-weight:900;font-size:14px;")
        hdr.setWordWrap(True)
        lay.addWidget(hdr)
        self._grp = QButtonGroup(self)
        self._rb_pax = QRadioButton(
            "👥 Passenger live flight" if en else "👥 Passagier-Live-Flug"
        )
        self._rb_pax.setChecked(True)
        self._rb_ferry = QRadioButton(
            "📦 Ferry / positioning flight" if en else "📦 Reiner Überführungsflug"
        )
        self._grp.addButton(self._rb_pax, 1)
        self._grp.addButton(self._rb_ferry, 2)
        lay.addWidget(self._rb_pax)
        lay.addWidget(
            QLabel(
                "Enables Pax Feedback Radar and +25% credit & XP bonus."
                if en
                else "Schaltet das Pax-Feedback-Radar frei und gewährt +25% Credit- und XP-Bonus!"
            )
        )
        lay.addWidget(self._rb_ferry)
        lay.addWidget(
            QLabel(
                "Standard base income, no Pax feedback — ideal for maintenance ferries."
                if en
                else "Normales Basis-Einkommen, kein Pax-Feedback — ideal für Wartungsflüge."
            )
        )
        lay.addWidget(QLabel("—" * 20))
        self._cb_clean = QCheckBox(
            "🧼 Express cabin cleaning (-850 CR)"
            if en
            else "🧼 Express-Kabinenreinigung durchführen (-850 CR)"
        )
        self._cb_cargo = QCheckBox(
            "📦 Load valuable belly cargo (+15% cargo credits)"
            if en
            else "📦 Wertfracht zuladen (+15% Cargo-Credits)"
        )
        self._cb_hazard = QCheckBox(
            "⛈️ Accept extreme weather (+30% risk bonus)"
            if en
            else "⛈️ Extreme Wetterbedingungen akzeptieren (+30% Risiko-Bonus)"
        )
        self._cb_vip = QCheckBox(
            "👑 VIP charter (3× credits, luxury catering required)"
            if en
            else "👑 VIP-Charter-Flug freischalten (3× Credits, Luxus-Catering)"
        )
        self._cb_eco = QCheckBox(
            "🍃 Eco-flight wear protection (50% less hangar wear)"
            if en
            else "🍃 Eco-Flight Verschleißschutz aktivieren (50% weniger Werft-Verschleiß)"
        )
        for cb in (
            self._cb_clean,
            self._cb_cargo,
            self._cb_hazard,
            self._cb_vip,
            self._cb_eco,
        ):
            lay.addWidget(cb)
        btn_go = QPushButton(
            "🛫 Ignite engines & depart!" if en else "🛫 Triebwerke zünden & Abflug!"
        )
        btn_go.clicked.connect(self.accept)
        lay.addWidget(btn_go)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def settings_dict(self) -> dict[str, Any]:
        pax = self._rb_pax.isChecked()
        return {
            "pax_mode": pax,
            "ferry_mode": not pax,
            "flight_mode": "passenger_live" if pax else "ferry",
            "clean_cabin": self._cb_clean.isChecked(),
            "belly_cargo": self._cb_cargo.isChecked(),
            "hazard_weather": self._cb_hazard.isChecked(),
            "vip_flight": self._cb_vip.isChecked(),
            "eco_wear": self._cb_eco.isChecked(),
        }


class _P2PPartsListDialog(QDialog):
    """Gold/schwarz Pop-Out: Ersatzteil weltweit inserieren."""

    def __init__(
        self,
        parent: QWidget,
        *,
        item_id: int,
        item_label: str,
        item_type: str,
        condition: str,
        en: bool,
    ) -> None:
        super().__init__(parent)
        self._item_id = item_id
        self.setModal(True)
        self.setStyleSheet(_PLATIN_GOLD_STYLE)
        self.setWindowTitle(
            "📦 Worldwide parts listing"
            if en
            else "📦 Weltweites Ersatzteil-Inserat"
        )
        self.resize(480, 320)
        lay = QVBoxLayout(self)
        hdr = QLabel(item_label)
        hdr.setWordWrap(True)
        hdr.setStyleSheet("color:#e8e8ec;font-weight:900;font-size:13px;")
        lay.addWidget(hdr)
        sub = QLabel(
            f"Type: {item_type}  ·  Condition: {condition}"
            if en
            else f"Typ: {item_type}  ·  Zustand: {condition}"
        )
        sub.setStyleSheet("color:#90a4ae;font-size:11px;")
        lay.addWidget(sub)
        lay.addWidget(
            QLabel("💰 Price (Credits)" if en else "💰 Preis (Credits)")
        )
        self._price = QLineEdit()
        self._price.setPlaceholderText("0" if en else "0")
        lay.addWidget(self._price)
        lay.addWidget(QLabel("Type" if en else "Typ"))
        self._mode = QComboBox()
        self._mode.addItem(
            "Buy now" if en else "Sofortkauf",
            "BUY_NOW",
        )
        self._mode.addItem("Auction" if en else "Auktion", "AUCTION")
        lay.addWidget(self._mode)
        lay.addWidget(QLabel("Duration" if en else "Laufzeit"))
        self._days = QComboBox()
        self._days.addItems(
            [
                "1 day" if en else "1 Tag",
                "2 days" if en else "2 Tage",
                "3 days" if en else "3 Tage",
            ]
        )
        lay.addWidget(self._days)
        btn_pub = QPushButton(
            "📦 Publish listing worldwide"
            if en
            else "📦 Inserat weltweit veröffentlichen"
        )
        btn_pub.clicked.connect(self.accept)
        lay.addWidget(btn_pub)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def price_value(self) -> float:
        try:
            return float(self._price.text().strip())
        except (TypeError, ValueError):
            return 0.0

    def listing_type_value(self) -> str:
        return str(self._mode.currentData() or "BUY_NOW").upper()

    def auction_days_value(self) -> int:
        return {0: 1, 1: 2, 2: 3}.get(self._days.currentIndex(), 1)


class _PlatinLicenseDialog(QDialog):
    def __init__(self, parent: Any, db_path: Any, main_mod: Any) -> None:
        super().__init__(parent)
        self._path = db_path
        self.m = main_mod
        self.setModal(True)
        self.setWindowTitle(
            main_mod.i18n_db(db_path, "platin.license.title", "SkyTycoon Lizenz")
        )
        self.resize(520, 240)
        lay = QVBoxLayout(self)
        self._lbl = QLabel(_license_required_bilingual_text())
        self._lbl.setWordWrap(True)
        self._lbl.setStyleSheet("color:#e8e8ec;font-weight:800;font-size:14px;")
        lay.addWidget(self._lbl)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("ST-XXXX-XXXX-XXXX")
        lay.addWidget(self.edit)
        row = QHBoxLayout()
        ok_btn = QPushButton(main_mod.i18n_db(db_path, "platin.license.activate", "Aktivieren"))
        ok_btn.clicked.connect(self._activate)
        cancel_btn = QPushButton(main_mod.i18n_db(db_path, "platin.license.quit", "Beenden"))
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        lay.addLayout(row)

    def _activate(self) -> None:
        key = (self.edit.text() or "").strip().upper()
        if not re.match(r"^ST-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$", key):
            QMessageBox.warning(
                self,
                self.m.i18n_db(self._path, "platin.license.title", "Lizenz"),
                self.m.i18n_db(
                    self._path,
                    "platin.license.format",
                    "Format: ST-XXXX-XXXX-XXXX",
                ),
            )
            return
        hid = self.m.p2p_hardware_id(self._path)
        em = (
            self.m.app_meta_get(self._path, "portal_email", "")
            or self.m.app_meta_get(self._path, "pilot_display_name", "")
            or ""
        ).strip().lower()
        pilot = (
            self.m.app_meta_get(self._path, "pilot_display_name", "")
            or self.m.pilot_handle(self._path)
            or "Pilot"
        )
        base = self.m.ionos_api_base_url() or _CLOUD_API_FALLBACK
        try:
            r = requests.post(
                f"{base.rstrip('/')}/api/v1/auth/activate",
                json={
                    "hardware_id": hid,
                    "license_key": key,
                    "email": em if "@" in em else "",
                    "portal_email": em if "@" in em else "",
                    "pilot_name": pilot[:120],
                    "app_version": getattr(self.m, "APP_VERSION", "1.0"),
                },
                headers={
                    "User-Agent": f"{self.m.SKYTYCOON_APP_NAME}/{getattr(self.m, 'APP_VERSION', '1.0')}",
                    "Content-Type": "application/json",
                },
                timeout=20,
                verify=self.m.auth_requests_verify_tls(),
            )
            j = r.json() if r.content else {}
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.m.i18n_db(self._path, "platin.license.title", "Lizenz"),
                str(exc),
            )
            return
        st = str(j.get("status", "")).lower()
        if st not in ("activated", "ok", "success"):
            QMessageBox.critical(
                self,
                self.m.i18n_db(self._path, "platin.license.title", "Lizenz"),
                str(j.get("message") or j.get("status") or "activation_failed"),
            )
            return
        self.m.app_meta_set(self._path, "license_key_installed", key[:256])
        self.m.app_meta_set(self._path, "license_activated", "1")
        _bind_server_hardware_id(self.m, self._path, j, hid)
        parent = self.parent()
        win = parent if parent is not None else None
        if win is not None:
            _unlock_six_main_hub_tabs(win)
        inj = getattr(win, "_platin_injector", None) if win is not None else None
        if inj is not None:
            QTimer.singleShot(400, inj._cloud_sync_pull_async)
        self.accept()
