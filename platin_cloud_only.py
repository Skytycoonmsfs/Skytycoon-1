# -*- coding: utf-8 -*-
"""100 % Cloud-Only: keine persistente career.db auf der Platte (Session-RAM-Cache)."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PLATIN_CLOUD_ONLY = True
_SESSION_DB: Path | None = None
_SCHEMA_READY = False
_INIT_GUARD = False


def _session_db_path() -> Path:
    global _SESSION_DB
    if _SESSION_DB is None:
        root = Path(tempfile.gettempdir()) / "skytycoon_cloud_sessions"
        root.mkdir(parents=True, exist_ok=True)
        _SESSION_DB = root / f"live_{os.getpid()}.db"
    return _SESSION_DB


def _session_schema_ok(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        conn = sqlite3.connect(str(path), timeout=8.0)
        try:
            row = conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'app_meta' LIMIT 1;
                """
            ).fetchone()
            return bool(row)
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _sync_db_path_everywhere(main_mod: Any, sess: Path) -> None:
    main_mod.DB_PATH = sess
    for name in ("__main__", "main"):
        mod = sys.modules.get(name)
        if mod is not None:
            try:
                mod.DB_PATH = sess
            except Exception:
                pass


def _direct_meta_get(
    sess: Path, orig_conn: Any, key: str, default: str = ""
) -> str:
    try:
        conn = orig_conn(sess)
        try:
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?;", (key,)
            ).fetchone()
            return str(row[0]) if row else default
        finally:
            conn.close()
    except sqlite3.Error:
        return default


def _direct_meta_set(sess: Path, orig_conn: Any, key: str, value: str) -> None:
    conn = orig_conn(sess)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?);",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def _bootstrap_schema(main_mod: Any) -> None:
    """Schema einmalig mit orig_conn anlegen — ohne patched _conn (Rekursion)."""
    global _SCHEMA_READY, _INIT_GUARD
    if _SCHEMA_READY or _INIT_GUARD:
        return
    orig_init = getattr(main_mod, "_platin_orig_init_database", None)
    orig_conn = getattr(main_mod, "_platin_orig_conn", None)
    if not callable(orig_init) or not callable(orig_conn):
        return

    sess = _session_db_path()
    _sync_db_path_everywhere(main_mod, sess)
    if _session_schema_ok(sess):
        _SCHEMA_READY = True
        return

    _INIT_GUARD = True
    try:
        try:
            if sess.is_file():
                sess.unlink()
        except OSError:
            pass
        saved_conn = main_mod._conn
        try:
            main_mod._conn = orig_conn
            orig_init(sess)
        finally:
            main_mod._conn = saved_conn
        _SCHEMA_READY = _session_schema_ok(sess)
    finally:
        _INIT_GUARD = False


def platin_meta_get_safe(main_mod: Any, key: str, default: str = "") -> str:
    """Robuster Meta-Lesezugriff — nie SQLite-Exception in die GUI."""
    try:
        ensure_platin_session_db(main_mod)
        orig_conn = getattr(main_mod, "_platin_orig_conn", None)
        if not callable(orig_conn):
            return default
        return _direct_meta_get(_session_db_path(), orig_conn, key, default)
    except Exception:
        return default


def platin_meta_set_safe(main_mod: Any, key: str, value: str) -> None:
    try:
        ensure_platin_session_db(main_mod)
        orig_conn = getattr(main_mod, "_platin_orig_conn", None)
        if not callable(orig_conn):
            return
        _direct_meta_set(_session_db_path(), orig_conn, key, value)
    except Exception:
        pass


def hydrate_platin_credentials_from_disk(main_mod: Any) -> None:
    """Portal-E-Mail + Cloud-Passwort aus local_session.json in Session-DB übernehmen."""
    if not _SCHEMA_READY:
        _bootstrap_schema(main_mod)
    if not _SCHEMA_READY:
        return
    sess = _session_db_path()
    orig_conn = getattr(main_mod, "_platin_orig_conn", None)
    if not callable(orig_conn):
        return
    try:
        pw_existing = (
            _direct_meta_get(sess, orig_conn, "cloud_backup_password", "")
            or _direct_meta_get(sess, orig_conn, "cloud_sync_password", "")
        ).strip()
        if pw_existing:
            return
    except Exception:
        pass
    try:
        from skytycoon_extensions import _load_local_session
    except ImportError:
        return
    data = _load_local_session(main_mod, sess)
    if not data:
        return
    pw = str(data.get("password") or "").strip()
    em = str(data.get("portal_email") or "").strip().lower()
    tok = str(data.get("access_token") or "").strip()
    if pw:
        try:
            _direct_meta_set(sess, orig_conn, "cloud_backup_password", pw)
            _direct_meta_set(sess, orig_conn, "cloud_sync_password", pw)
        except (OSError, sqlite3.Error):
            pass
    if em and "@" in em:
        try:
            _direct_meta_set(sess, orig_conn, "portal_email", em[:200])
        except (OSError, sqlite3.Error):
            pass
    if tok:
        try:
            _direct_meta_set(sess, orig_conn, "ionos_jwt", tok[:4096])
        except (OSError, sqlite3.Error):
            pass


def ensure_platin_session_db(main_mod: Any) -> Path:
    """Session-DB mit app_meta-Schema — vor jedem Meta-Zugriff."""
    sess = _session_db_path()
    _sync_db_path_everywhere(main_mod, sess)
    if not _SCHEMA_READY:
        _bootstrap_schema(main_mod)
    hydrate_platin_credentials_from_disk(main_mod)
    return sess


def _archive_legacy_career_db(legacy: Path) -> None:
    if not legacy.is_file():
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = legacy.with_name(f"career.db.frozen_{stamp}")
    try:
        if dest.is_file():
            legacy.unlink()
        else:
            legacy.rename(dest)
    except OSError:
        try:
            legacy.unlink()
        except OSError:
            pass


def install_platin_cloud_only(main_mod: Any) -> None:
    """Erzwingt Cloud-Authority: SQLite nur als flüchtiger UI-Cache."""
    if getattr(main_mod, "_platin_cloud_only_installed", False):
        ensure_platin_session_db(main_mod)
        return
    main_mod.PLATIN_CLOUD_ONLY = True
    main_mod._platin_cloud_only_installed = True

    base = Path(getattr(main_mod, "BASE_DIR", Path.cwd()))
    legacy = base / "career.db"
    main_mod._platin_legacy_career_db = legacy
    _archive_legacy_career_db(legacy)

    sess = _session_db_path()
    _sync_db_path_everywhere(main_mod, sess)

    orig_init = main_mod.init_database
    orig_conn = main_mod._conn
    main_mod._platin_orig_init_database = orig_init
    main_mod._platin_orig_conn = orig_conn

    def init_database(path: Path | None = None) -> None:
        _bootstrap_schema(main_mod)
        if _SCHEMA_READY:
            try:
                _direct_meta_set(sess, orig_conn, "platin_cloud_only_v1", "1")
            except (OSError, sqlite3.Error):
                pass

    def _conn(path: Path) -> sqlite3.Connection:
        if not _SCHEMA_READY:
            _bootstrap_schema(main_mod)
        return orig_conn(sess)

    def app_meta_get(path: Path, key: str, default: str = "") -> str:
        if not _SCHEMA_READY:
            _bootstrap_schema(main_mod)
        if not _SCHEMA_READY:
            return default
        return _direct_meta_get(sess, orig_conn, key, default)

    def app_meta_set(path: Path, key: str, value: str) -> None:
        if not _SCHEMA_READY:
            _bootstrap_schema(main_mod)
        if not _SCHEMA_READY:
            return
        _direct_meta_set(sess, orig_conn, key, value)

    def backup_career_database(*_a: Any, **_k: Any) -> None:
        return

    def _restore_career_from_latest_backup(_path: Path) -> bool:
        return False

    main_mod.init_database = init_database
    main_mod._conn = _conn
    main_mod.app_meta_get = app_meta_get
    main_mod.app_meta_set = app_meta_set
    main_mod.backup_career_database = backup_career_database
    main_mod._restore_career_from_latest_backup = _restore_career_from_latest_backup
    ensure_platin_session_db(main_mod)
    print(
        "[SkyTycoon] Cloud-Only aktiv — career.db eingefroren, Session-Schema bereit.",
        flush=True,
    )


def patch_mainwindow_cloud_guard(main_mod: Any) -> None:
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_platin_cloud_guard_patch", False):
        return

    orig_disconnect_backup = getattr(win_cls, "_maybe_backup_on_sim_disconnect", None)
    orig_cloud_ready = getattr(win_cls, "_ionos_cloud_ready", None)
    orig_open_profile = getattr(win_cls, "_open_customer_profile_dialog", None)
    orig_hangar_lazy = getattr(win_cls, "_refresh_hangar_hub_lazy", None)

    def _maybe_backup_on_sim_disconnect_patched(self: Any) -> None:
        if getattr(main_mod, "PLATIN_CLOUD_ONLY", False):
            inj = getattr(self, "_platin_injector", None)
            if inj is not None and hasattr(inj, "_cloud_save_async"):
                inj._cloud_save_async()
            return
        if callable(orig_disconnect_backup):
            orig_disconnect_backup(self)

    def _ionos_cloud_ready_patched(self: Any) -> bool:
        ensure_platin_session_db(main_mod)
        hydrate_platin_credentials_from_disk(main_mod)
        if callable(orig_cloud_ready):
            return bool(orig_cloud_ready(self))
        return False

    def _open_customer_profile_dialog_patched(self: Any) -> None:
        ensure_platin_session_db(main_mod)
        hydrate_platin_credentials_from_disk(main_mod)
        if callable(orig_open_profile):
            orig_open_profile(self)

    def _refresh_hangar_hub_lazy_patched(self: Any) -> None:
        """QApplication hat kein setUpdatesEnabled — nur QWidget."""
        if not getattr(self, "_hub_tab_refresh_fresh", lambda *_a, **_k: True)(
            "_hub_ix_hangar", 50.0
        ):
            return
        updates_off = False
        try:
            self.setUpdatesEnabled(False)
            updates_off = True
            if not getattr(self, "_hangar_scrapyard_injected", False):
                self._inject_hangar_scrapyard_subtab()
                self._hangar_scrapyard_injected = True
            self._refresh_office_level_labels()
            inner = getattr(self, "hangar_inner_tabs", None)
            cur = inner.currentIndex() if inner is not None else -1
            if cur in (1, 2):
                self._refresh_spare_parts_market_ui()
            if cur in (0, 1):
                self._refresh_hangar_maintenance_grid()
            if cur >= 2 and hasattr(self, "tab_used_scrapyard"):
                fn = getattr(self.tab_used_scrapyard, "refresh_market", None)
                if callable(fn):
                    fn()
                elif hasattr(self.tab_used_scrapyard, "refresh_scrapyard_list"):
                    self.tab_used_scrapyard.refresh_scrapyard_list()
        finally:
            if updates_off:
                self.setUpdatesEnabled(True)

    if callable(orig_disconnect_backup):
        win_cls._maybe_backup_on_sim_disconnect = _maybe_backup_on_sim_disconnect_patched
    if callable(orig_cloud_ready):
        win_cls._ionos_cloud_ready = _ionos_cloud_ready_patched
    if callable(orig_open_profile):
        win_cls._open_customer_profile_dialog = _open_customer_profile_dialog_patched
    if callable(orig_hangar_lazy):
        win_cls._refresh_hangar_hub_lazy = _refresh_hangar_hub_lazy_patched
    win_cls._platin_cloud_guard_patch = True
