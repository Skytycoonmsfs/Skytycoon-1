#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyTycoon Pro – Admin Commander (eigenständig, PySide6).
Steuerzentrale: Update-version.json, P2P-Listings, Bann-Liste, globale Wirtschaft, lokaler Gott-Modus (DB).

Umgebung:
  SKYTYCOON_IONOS_API_BASE / SKYTYCOON_IONOS_SERVER_URL  Produktions-API (Standard: https://skytycoon.info)
  SKYTYCOON_DB_PATH              optional, Standard: career.db neben dieser Datei
  EXE-Deploy (optional): SKYTYCOON_DEPLOY_HOST, SKYTYCOON_DEPLOY_USER, SKYTYCOON_DEPLOY_PASSWORD,
    SKYTYCOON_SSH_REMOTE_EXE (Zielpfad auf dem Server)
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from PySide6.QtCore import QObject, QDateTime, QEvent, QRect, QRunnable, QSettings, QThread, QThreadPool, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QFont, QGuiApplication, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from admin_vault_core import (  # noqa: E402
    CAP_MB_DEFAULT,
    PROJECT_ROOT_DEFAULT,
    SWISS_SYNC_INTERVAL_MS,
    VaultSFTPServer,
    create_project_backup_zip,
    disk_usage_for_drive,
    ensure_vault_tree,
    find_drive_by_volume_label,
    fmt_gb,
    list_drives_with_labels,
    list_windows_drives,
    load_vault_config,
    prune_local_vault,
    run_swiss_sync_to_label_drive,
    save_vault_config,
    t as vault_t,
    vault_root_for_drive,
    zurich_now,
)

APP_TITLE = "SkyTycoon Pro · Admin Commander"
BASE_DIR = Path(__file__).resolve().parent
# Produktions-Domain (Update-Manifest POST, CRM-Basis in ENV)
IONOS_SERVER_URL_DEFAULT = (
    (os.environ.get("SKYTYCOON_IONOS_SERVER_URL") or "https://skytycoon.info")
    .strip()
    .rstrip("/")
)
IONOS_SERVER_URL = IONOS_SERVER_URL_DEFAULT
# Muss mit Server-ADMIN_API_PASSWORD (SKYTYCOON_ADMIN_PASSWORD) übereinstimmen.
ADMIN_MASTER_PASSWORD = (
    os.environ.get("SKYTYCOON_ADMIN_MASTER_PASSWORD")
    or os.environ.get("SKYTYCOON_ADMIN_PASSWORD")
    or "e85OieJLPMV6Nuv"
).strip()
def _superadmin_emails_admin() -> frozenset[str]:
    raw = (os.environ.get("SKYTYCOON_SUPERADMIN_EMAILS") or "").strip()
    return frozenset(
        x.strip().lower()
        for x in raw.replace(";", ",").split(",")
        if x.strip() and "@" in x
    )


GLOBAL_SUPERADMIN_EMAILS: frozenset[str] = _superadmin_emails_admin()
GLOBAL_SUPERADMIN_EMAIL = (
    os.environ.get("SKYTYCOON_PRIMARY_SUPERADMIN_EMAIL", "").strip().lower()
    or next(iter(GLOBAL_SUPERADMIN_EMAILS), "")
)
GLOBAL_SUPERADMIN_BOOT_PASSWORD = (
    os.environ.get("SKYTYCOON_SUPERADMIN_BOOT_PASSWORD")
    or os.environ.get("SKYTYCOON_SUPERADMIN_PASSWORD")
    or ""
).strip()
DEFAULT_DB = Path(os.environ.get("SKYTYCOON_DB_PATH") or (BASE_DIR / "career.db")).resolve()
ADMIN_LOG = BASE_DIR / "admin_actions.log"
PLATIN_CYBER_STYLE = """
QMainWindow, QWidget { background-color: #0b0f19; color: #ffffff; font-family: 'Segoe UI'; }
QGroupBox {
  border: 1px solid #00a2ff; margin-top: 14px; padding-top: 10px;
  color: #8ac7ff; font-weight: bold;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QComboBox, QListWidget, QTableWidget {
  background-color: #111625; color: #ffffff;
  border: 1px solid #00a2ff; border-radius: 4px; padding: 4px;
}
QPushButton {
  background-color: #00a2ff; border: 1px solid #00d2ff;
  color: #ffffff; border-radius: 4px; padding: 8px 14px; font-weight: bold;
}
QPushButton:hover { background-color: #00d2ff; }
QPushButton#secondary { background-color: #1a2438; border: 1px solid #8ac7ff; }
QTabWidget::pane { border: 1px solid #111625; background: #0b0f19; }
QTabBar::tab {
  background: #111625; color: #8ac7ff; padding: 8px 14px;
  border: 1px solid #00a2ff; border-bottom: none;
}
QTabBar::tab:selected { background: #00a2ff; color: #0b0f19; font-weight: bold; }
QScrollArea { border: none; background: #0b0f19; }
QLabel#head { color: #00a2ff; font-size: 18px; font-weight: 700; }
"""


def apply_platin_cyber_blue_chrome(win: Any | None = None) -> None:
    """Universelle Scroll-Dampfwalze + Cyber-Blue für alle Admin-Tabs."""
    target = win if win is not None else QApplication.instance()
    if target is None:
        return
    if isinstance(target, QApplication):
        for w in target.topLevelWidgets():
            if isinstance(w, AdminCommanderWindow):
                target = w
                break
    if not isinstance(target, AdminCommanderWindow):
        return
    target.setStyleSheet(PLATIN_CYBER_STYLE)
    tabs = getattr(target, "tabs", None)
    if not isinstance(tabs, QTabWidget):
        return
    for i in range(tabs.count()):
        page = tabs.widget(i)
        if page is None or getattr(page, "_platin_scroll_wrapped", False):
            continue
        inner = page
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lay = tabs.tabBar().tabText(i)
        tabs.removeTab(i)
        scroll.setWidget(inner)
        tabs.insertTab(i, scroll, lay)
        inner._platin_scroll_wrapped = True  # type: ignore[attr-defined]


def _load_deploy_env_into_os() -> None:
    """Admin Commander Standalone: .env.deploy für SFTP/Release ohne Shell-Setup laden."""
    env_path = BASE_DIR / ".env.deploy"
    if not env_path.is_file():
        return
    try:
        raw = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_deploy_env_into_os()


def _admin_token_headers(pw: str) -> dict[str, str]:
    """HTTP-Header für Admin-API (serverseitig ``X-Admin-Token``)."""
    if not (pw or "").strip():
        return {}
    return {"X-Admin-Token": pw.strip()}


def _admin_merge_json(base: dict, pw: str) -> dict:
    """JSON-Body: ``admin_password`` und ``admin_master_password`` (Server akzeptiert beides)."""
    out = dict(base)
    p = (pw or "").strip()
    out["admin_password"] = p
    out["admin_master_password"] = p
    return out


class _FnVaultBackupRunnable(QRunnable):
    """Hintergrund-Job für Vault-Zips (QThreadPool)."""

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        self._fn()


class _SwissSyncThread(QThread):
    """2h Swiss-Sync — blockiert weder Admin noch main.py."""

    result = Signal(bool, str)

    def run(self) -> None:
        try:
            ok, msg = run_swiss_sync_to_label_drive(BASE_DIR)
            self.result.emit(ok, msg)
        except Exception as exc:
            self.result.emit(False, str(exc))


class BuildWorker(QThread):
    """PyInstaller-Build + optionaler SFTP-Upload (Paramiko), Ausgabe per Signal."""

    line_out = Signal(str)
    finished_ok = Signal(str)
    finished_err = Signal(str)

    def __init__(self, project_root: Path, app_version: str) -> None:
        super().__init__()
        self.project_root = project_root.resolve()
        self.app_version = (app_version or "1.0.0").strip()

    @staticmethod
    def _bump_patch_version(version: str) -> str:
        raw = (version or "1.0.0").strip()
        parts = raw.split(".")
        if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
            return raw or "1.0.1"
        parts[2] = str(int(parts[2]) + 1)
        return ".".join(parts[:3])

    @staticmethod
    def _sftp_mkdirs(sftp, remote_dir: str) -> None:
        current = ""
        for part in remote_dir.replace("\\", "/").split("/"):
            if not part:
                current = "/"
                continue
            current = (current.rstrip("/") + "/" + part) if current else part
            try:
                sftp.mkdir(current)
            except OSError:
                pass

    def run(self) -> None:
        root = self.project_root
        locales = root / "locales"
        assets = root / "assets"
        main_py = root / "main.py"
        if not main_py.is_file():
            self.finished_err.emit(f"main.py nicht gefunden unter {root}")
            return
        sep = ";" if sys.platform == "win32" else ":"
        icon_path = root / "app_icon.ico"
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile",
            "--noconsole",
            "--name",
            "SkyTycoon_Pro",
            "--add-data",
            f"locales{sep}locales",
            "--add-data",
            f"assets{sep}assets",
        ]
        if icon_path.is_file():
            cmd.extend(["--icon", str(icon_path)])
        cmd.append(str(main_py.name))
        if not locales.is_dir():
            self.line_out.emit("[Warnung] Ordner locales/ fehlt — Build läuft trotzdem.")
        if not assets.is_dir():
            self.line_out.emit("[Warnung] Ordner assets/ fehlt — Build läuft trotzdem.")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            self.finished_err.emit(str(exc))
            return
        if proc.stdout:
            for line in proc.stdout:
                self.line_out.emit(line.rstrip("\r\n"))
        code = proc.wait()
        if code != 0:
            self.finished_err.emit(f"PyInstaller beendet mit Code {code}")
            return
        dist_exe = root / "dist" / "SkyTycoon_Pro.exe"
        if not dist_exe.is_file():
            legacy = root / "dist" / "main.exe"
            if legacy.is_file():
                dist_exe = legacy
        if not dist_exe.is_file():
            self.finished_err.emit(
                "dist/SkyTycoon_Pro.exe nicht gefunden nach erfolgreichem Exit-Code."
            )
            return
        host = (os.environ.get("SKYTYCOON_DEPLOY_HOST") or "217.154.16.248").strip()
        user = (os.environ.get("SKYTYCOON_DEPLOY_USER") or "root").strip()
        pw = (os.environ.get("SKYTYCOON_DEPLOY_PASSWORD") or "").strip()
        remote = (
            os.environ.get("SKYTYCOON_SSH_REMOTE_EXE") or ""
        ).strip() or "/home/skytycoon/static/downloads/SkyTycoon_Pro.exe"
        if not host or not pw:
            self.line_out.emit(
                "[Hinweis] Kein SFTP: SKYTYCOON_DEPLOY_HOST / SKYTYCOON_DEPLOY_PASSWORD setzen. "
                f"Lokales Artefakt: {dist_exe}"
            )
            self.finished_ok.emit(str(dist_exe))
            return
        try:
            import paramiko  # type: ignore[import-untyped]
        except ImportError:
            self.finished_err.emit(
                "Build OK, aber paramiko fehlt (pip install paramiko) — SFTP nicht möglich."
            )
            return
        try:
            t = paramiko.Transport((host, 22))
            t.connect(username=user, password=pw)
            sftp = paramiko.SFTPClient.from_transport(t)
            try:
                self._sftp_mkdirs(sftp, str(Path(remote).parent).replace("\\", "/"))
                sftp.put(str(dist_exe), remote)
            finally:
                sftp.close()
                t.close()
        except Exception as exc:
            self.finished_err.emit(f"SFTP: {exc}")
            return
        self.line_out.emit(f"[OK] Hochgeladen nach {host}:{remote}")
        ver_path = root / "version.json"
        try:
            import json as _json

            ver_doc: dict = {}
            if ver_path.is_file():
                try:
                    ver_doc = _json.loads(ver_path.read_text(encoding="utf-8"))
                    if not isinstance(ver_doc, dict):
                        ver_doc = {}
                except Exception:
                    ver_doc = {}
            base_version = str(ver_doc.get("version") or self.app_version or "1.0.0")
            new_version = self._bump_patch_version(base_version)
            public_exe = "https://skytycoon.info/static/downloads/SkyTycoon_Pro.exe"
            ver_doc.update(
                {
                    "version": new_version,
                    "url": public_exe,
                    "exe_url": public_exe,
                    "download_url": public_exe,
                    "protected_download_url": "https://skytycoon.info/api/v1/web/download/app",
                    "filename": "SkyTycoon_Pro.exe",
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            ver_path.write_text(
                _json.dumps(ver_doc, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            remote_ver = (
                os.environ.get("SKYTYCOON_SSH_REMOTE_VERSION_JSON") or ""
            ).strip() or "/home/skytycoon/version.json"
            t2 = paramiko.Transport((host, 22))
            t2.connect(username=user, password=pw)
            sftp2 = paramiko.SFTPClient.from_transport(t2)
            try:
                self._sftp_mkdirs(sftp2, str(Path(remote_ver).parent).replace("\\", "/"))
                sftp2.put(str(ver_path), remote_ver)
            finally:
                sftp2.close()
                t2.close()
            self.line_out.emit(f"[OK] version.json v{new_version} → {remote_ver}")
        except Exception as ver_exc:
            self.line_out.emit(f"[Warnung] version.json Upload: {ver_exc}")
        self.finished_ok.emit(remote)


def _label_selectable(lbl: QLabel) -> None:
    lbl.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )


META_STAND_ICAO = "persist_stand_icao"
META_STAND_LAT = "persist_stand_lat"
META_STAND_LON = "persist_stand_lon"
META_STAND_TS = "persist_stand_ts_unix"

AIRPORT_COORDS: dict[str, tuple[float, float]] = {
    "EDDF": (50.0379, 8.5622),
    "EDDM": (48.3538, 11.7861),
    "EDDH": (53.6304, 9.9882),
    "LSZH": (47.4647, 8.5492),
    "EGLL": (51.4700, -0.4543),
    "LFPG": (49.0097, 2.5479),
    "KJFK": (40.6413, -73.7781),
    "OMDB": (25.2532, 55.3657),
}


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        ADMIN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ADMIN_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def app_meta_get(path: Path, key: str, default: str = "") -> str:
    if not path.is_file():
        return default
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key = ? LIMIT 1;", (key,)
        ).fetchone()
        return str(row[0]) if row and row[0] is not None else default
    finally:
        conn.close()


def app_meta_set(path: Path, key: str, value: str) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?);",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


class _AdminHttpSignals(QObject):
    json_ok = Signal(dict)
    json_err = Signal(str)


class _AdminListFetchRunnable(QRunnable):
    def __init__(self, url: str, sig: _AdminHttpSignals) -> None:
        super().__init__()
        self._url = url
        self._sig = sig

    def run(self) -> None:
        try:
            r = requests.get(self._url, timeout=25)
            r.raise_for_status()
            self._sig.json_ok.emit(r.json())
        except Exception as exc:
            self._sig.json_err.emit(str(exc))


class _AdminPayoutRunnable(QRunnable):
    """POST /api/v1/admin/payout/execute — PayPal Payouts asynchron."""

    def __init__(
        self,
        base_url: str,
        password: str,
        recipient_email: str,
        amount: float,
        sig: _AdminHttpSignals,
    ) -> None:
        super().__init__()
        self._base = base_url.rstrip("/")
        self._password = password
        self._email = recipient_email.strip()
        self._amount = float(amount)
        self._sig = sig

    def run(self) -> None:
        try:
            hdr = _admin_token_headers(self._password)
            r = requests.post(
                f"{self._base}/api/v1/admin/payout/execute",
                json=_admin_merge_json(
                    {
                        "recipient_email": self._email,
                        "amount": self._amount,
                        "currency": "EUR",
                        "note": "SkyTycoon Co-Founder Profit Split",
                    },
                    self._password,
                ),
                headers=hdr,
                timeout=90,
            )
            data = r.json() if r.content else {}
            if r.status_code >= 400:
                msg = (
                    data.get("message")
                    or data.get("detail")
                    or r.text[:300]
                    or f"HTTP {r.status_code}"
                )
                self._sig.json_err.emit(str(msg))
                return
            self._sig.json_ok.emit(data if isinstance(data, dict) else {"ok": True})
        except Exception as exc:
            self._sig.json_err.emit(str(exc))


class _AdminUserDeleteRunnable(QRunnable):
    """DELETE /api/v1/admin/user/delete/{user_id} — asynchron."""

    def __init__(
        self,
        base_url: str,
        user_id: str,
        password: str,
        sig: _AdminHttpSignals,
    ) -> None:
        super().__init__()
        self._base = base_url.rstrip("/")
        self._user_id = str(user_id or "").strip()
        self._password = password
        self._sig = sig

    def run(self) -> None:
        try:
            hdr = _admin_token_headers(self._password)
            url = f"{self._base}/api/v1/admin/user/delete/{self._user_id}"
            r = requests.post(
                url,
                json=_admin_merge_json({}, self._password),
                headers=hdr,
                timeout=45,
            )
            if r.status_code == 405:
                r = requests.delete(
                    url,
                    params={
                        "admin_master_password": self._password,
                        "admin_password": self._password,
                    },
                    headers=hdr,
                    timeout=45,
                )
            r.raise_for_status()
            self._sig.json_ok.emit(r.json() if r.content else {"ok": True})
        except Exception as exc:
            self._sig.json_err.emit(str(exc))


class _AdminUsersListPostRunnable(QRunnable):
    """POST /api/v1/admin/users/list mit Master-Passwort (Meilenstein 162)."""

    def __init__(self, url: str, password: str, sig: _AdminHttpSignals) -> None:
        super().__init__()
        self._url = url
        self._password = password
        self._sig = sig

    def run(self) -> None:
        try:
            hdr = _admin_token_headers(self._password)
            r = requests.post(
                self._url,
                json=_admin_merge_json({}, self._password),
                headers=hdr,
                timeout=25,
            )
            if r.status_code == 404:
                r = requests.get(
                    self._url,
                    params={
                        "admin_master_password": self._password,
                        "admin_password": self._password,
                    },
                    headers=hdr,
                    timeout=25,
                )
            r.raise_for_status()
            self._sig.json_ok.emit(r.json())
        except Exception as exc:
            self._sig.json_err.emit(str(exc))


class _AsynchronousSftpWorker(QThread):
    """Vault-SFTP (Port 2222) — vollständig getrennt von GUI- und IONOS-HTTP-Pfad."""

    started_ok = Signal()
    failed = Signal(str)
    stopped = Signal()

    def __init__(
        self,
        server: VaultSFTPServer,
        *,
        action: str,
        password: str = "",
    ) -> None:
        super().__init__()
        self._server = server
        self._action = action
        self._password = (password or "").strip()

    def run(self) -> None:
        try:
            if self._action == "start":
                if self._password:
                    self._server.set_password(self._password)
                if self._server.start():
                    self.started_ok.emit()
                else:
                    self.failed.emit(self._server.last_error or "SFTP start failed")
            elif self._action == "stop":
                self._server.stop()
                self.stopped.emit()
        except Exception as exc:
            if self._action == "stop":
                self.stopped.emit()
            else:
                self.failed.emit(str(exc))


class _MarketingApiSignals(QObject):
    ok = Signal(dict)
    err = Signal(str)


class _MarketingApiPostRunnable(QRunnable):
    """Marketing/Kill/Export — QThreadPool, blockiert GUI nicht."""

    def __init__(
        self,
        base_url: str,
        path: str,
        payload: dict,
        password: str,
        sig: _MarketingApiSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._base = (base_url or "").rstrip("/")
        self._path = path if path.startswith("/") else f"/{path}"
        self._payload = dict(payload)
        self._password = (password or "").strip()
        self._sig = sig

    def run(self) -> None:
        try:
            r = requests.post(
                f"{self._base}{self._path}",
                json=_admin_merge_json(self._payload, self._password),
                headers=_admin_token_headers(self._password),
                timeout=90,
            )
            data = r.json() if r.content else {}
            if not isinstance(data, dict):
                data = {"raw": str(data)[:500]}
            if r.ok:
                self._sig.ok.emit(data)
            else:
                msg = (
                    data.get("message")
                    or data.get("detail")
                    or r.text[:300]
                    or "request_failed"
                )
                self._sig.err.emit(f"HTTP {r.status_code}: {msg}")
        except Exception as exc:
            self._sig.err.emit(str(exc))


class AdminCommanderWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(980, 720)
        self._settings = QSettings("SkyTycoonPro", "AdminCommander")
        self._last_support_open_count = -1
        self._db_path = Path(
            self._settings.value("db_path", str(DEFAULT_DB), str) or str(DEFAULT_DB)
        ).resolve()
        self._crm_list_sig = _AdminHttpSignals()
        self._crm_list_sig.json_ok.connect(self._crm_on_users_list_json)
        self._crm_list_sig.json_err.connect(self._crm_on_users_list_err)
        self._crm_delete_sig = _AdminHttpSignals()
        self._crm_delete_sig.json_ok.connect(self._crm_on_user_delete_ok)
        self._crm_delete_sig.json_err.connect(self._crm_on_user_delete_err)
        self._payout_sig = _AdminHttpSignals()
        self._payout_sig.json_ok.connect(self._on_payout_ok)
        self._payout_sig.json_err.connect(self._on_payout_err)
        self._mkt_sig = _MarketingApiSignals()
        self._mkt_sig.ok.connect(self._mkt_on_api_ok)
        self._mkt_sig.err.connect(self._mkt_on_api_err)
        self._mkt_pending_export = False
        self._support_pending_reload = False
        self._sftp_worker: _AsynchronousSftpWorker | None = None
        self._superadmin_executive = False

        root = QWidget()
        self.setCentralWidget(root)
        vl = QVBoxLayout(root)

        self.setStyleSheet(PLATIN_CYBER_STYLE)

        hl = QLabel("ADMIN COMMANDER – Platin Cyber-Blue")
        hl.setObjectName("head")
        vl.addWidget(hl)

        db_row = QHBoxLayout()
        db_row.addWidget(QLabel("career.db:"))
        self.ed_db = QLineEdit(str(self._db_path))
        db_row.addWidget(self.ed_db, stretch=1)
        bdb = QPushButton("Pfad übernehmen")
        bdb.setObjectName("secondary")
        bdb.clicked.connect(self._apply_db_path)
        db_row.addWidget(bdb)
        vl.addLayout(db_row)

        self.tabs = QTabWidget()
        vl.addWidget(self.tabs, stretch=1)

        self._build_tab_update()
        self._build_tab_p2p()
        self._build_tab_bans()
        self._build_tab_global()
        self._build_tab_cloud_sync()
        self._build_tab_user_crm()
        self._build_tab_license_keys()
        self._build_tab_promo_codes()
        self._build_tab_email_marketing()
        self._build_tab_god()
        self._build_tab_exe_release()
        self._build_tab_support()
        self._build_tab_platin_vault()
        self._build_tab_payout()
        self._build_tab_log()
        apply_platin_cyber_blue_chrome(self)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_log_tail)
        self._timer.start(2000)

        if hasattr(self, "ed_admin_master"):
            if not (self.ed_admin_master.text() or "").strip():
                self.ed_admin_master.setText(ADMIN_MASTER_PASSWORD)
        if hasattr(self, "ed_ionos_api") and not self.ed_ionos_api.text().strip():
            self.ed_ionos_api.setText(IONOS_SERVER_URL)
        QTimer.singleShot(80, self._ensure_admin_password_valid)
        QTimer.singleShot(200, self.load_active_users)
        self._wire_crm_copy_and_tables()
        QTimer.singleShot(50, self._executive_superadmin_handshake)

    def _ensure_admin_password_valid(self) -> None:
        """Altes gespeichertes Passwort (z. B. Wilkommen007) → Standard-Admin-PW."""
        base = self._ionos_base_url()
        if not base or not hasattr(self, "ed_admin_master"):
            return
        pw = (self.ed_admin_master.text() or "").strip()
        test_pw = pw or ADMIN_MASTER_PASSWORD

        def _probe(candidate: str) -> bool:
            try:
                r = requests.post(
                    f"{base.rstrip('/')}/api/v1/admin/users/list",
                    json=_admin_merge_json({}, candidate),
                    headers=_admin_token_headers(candidate),
                    timeout=18,
                )
                return r.status_code == 200
            except requests.RequestException:
                return False

        if _probe(test_pw):
            return
        if pw != ADMIN_MASTER_PASSWORD and _probe(ADMIN_MASTER_PASSWORD):
            self.ed_admin_master.setText(ADMIN_MASTER_PASSWORD)
            self._settings.setValue("admin_master_pw", ADMIN_MASTER_PASSWORD)
            _log(
                "Admin-Passwort auf gültigen IONOS-Standard zurückgesetzt "
                f"(HTTP 403 mit altem Eintrag: {pw[:3]}…)."
            )

    def _executive_superadmin_handshake(self) -> None:
        """SuperAdmin-Whitelist (ENV) → Volllizenz + Admin-Rechte."""
        email = GLOBAL_SUPERADMIN_EMAIL
        if email not in GLOBAL_SUPERADMIN_EMAILS:
            email = next(iter(GLOBAL_SUPERADMIN_EMAILS), email)
        password = GLOBAL_SUPERADMIN_BOOT_PASSWORD
        if not email or not password:
            return
        self._superadmin_executive = True
        if hasattr(self, "ed_admin_master") and password:
            self.ed_admin_master.setText(password)
            self._settings.setValue("admin_master_pw", password)
        base = (self.ed_ionos_api.text().strip() if hasattr(self, "ed_ionos_api") else "") or IONOS_SERVER_URL
        hid = f"sa-{email.split('@', 1)[0][:12]}"
        try:
            r = requests.post(
                f"{base.rstrip('/')}/api/v1/auth/login",
                json={
                    "pilot_name": email,
                    "email": email,
                    "portal_email": email,
                    "password": password,
                    "hardware_id": hid,
                    "pc_hardware_id": hid,
                },
                timeout=20,
                headers={"User-Agent": "SkyTycoonPro-AdminCommander/1"},
            )
            j = r.json() if r.content else {}
            if str(j.get("status", "")) == "login_success":
                lk = str(j.get("license_key") or "").strip()
                if lk and hasattr(self, "ed_license_key"):
                    self.ed_license_key.setText(lk)
        except requests.RequestException:
            pass
        for ix in range(self.tabs.count()):
            self.tabs.setTabEnabled(ix, True)
        _log(
            f"SUPERADMIN Executive-Handshake aktiv ({email}) — CRM, Marketing, Support freigeschaltet."
        )
        if hasattr(self, "tbl_license_keys"):
            QTimer.singleShot(400, self._crm_keys_refresh)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.matches(QKeySequence.StandardKey.Copy):
                if obj is self.tbl_p2p or obj is self.tbl_bans:
                    if not obj.selectedIndexes():
                        return False
                    self._crm_copy_table_cells(obj)
                    return True
                if obj is self.list_active_users:
                    if (
                        not self.list_active_users.selectedItems()
                        and self.list_active_users.currentItem() is None
                    ):
                        return False
                    self._crm_copy_user_list_selection()
                    return True
                if getattr(self, "list_tickets", None) is obj:
                    if (
                        not self.list_tickets.selectedItems()
                        and self.list_tickets.currentItem() is None
                    ):
                        return False
                    self._crm_copy_support_ticket_selection()
                    return True
        return super().eventFilter(obj, event)

    def _crm_copy_table_cells(self, tbl: QTableWidget) -> None:
        sel = tbl.selectedIndexes()
        if not sel:
            return
        rows = sorted({i.row() for i in sel})
        cols = sorted({i.column() for i in sel})
        lines: list[str] = []
        for r in rows:
            parts: list[str] = []
            for c in cols:
                it = tbl.item(r, c)
                parts.append(it.text() if it else "")
            lines.append("\t".join(parts))
        QGuiApplication.clipboard().setText("\n".join(lines))

    def _crm_copy_user_list_selection(self) -> None:
        items = self.list_active_users.selectedItems()
        if not items:
            cur = self.list_active_users.currentItem()
            if cur is not None:
                items = [cur]
        if not items:
            return
        lines = []
        for it in items:
            hid = str(it.data(Qt.ItemDataRole.UserRole) or "")
            txt = (it.text() or "").strip()
            lines.append(f"{txt}\t{hid}" if hid else txt)
        QGuiApplication.clipboard().setText("\n".join(lines))

    def _crm_copy_support_ticket_selection(self) -> None:
        items = self.list_tickets.selectedItems()
        if not items:
            cur = self.list_tickets.currentItem()
            if cur is not None:
                items = [cur]
        if not items:
            return
        lines: list[str] = []
        for it in items:
            hid = str(it.data(Qt.ItemDataRole.UserRole) or "")
            txt = (it.text() or "").strip()
            lines.append(f"{txt}\t{hid}" if hid else txt)
        QGuiApplication.clipboard().setText("\n".join(lines))

    def _crm_clipboard_feedback(self, anchor: QWidget, msg: str = "Kopiert!") -> None:
        QToolTip.showText(QCursor.pos(), msg, anchor, QRect(), 1800)

    def _crm_copy_license_clicked(self) -> None:
        txt = (self.lbl_crm_license.text() or "").strip()
        if txt.startswith("—"):
            self._crm_clipboard_feedback(self.btn_crm_copy_license, "Leer")
            return
        QGuiApplication.clipboard().setText(txt)
        self._crm_clipboard_feedback(self.btn_crm_copy_license)

    def _crm_copy_hw_clicked(self) -> None:
        txt = (self.lbl_crm_hwid.text() or "").strip()
        if not txt or txt == "—":
            self._crm_clipboard_feedback(self.btn_crm_copy_hw, "Leer")
            return
        QGuiApplication.clipboard().setText(txt)
        self._crm_clipboard_feedback(self.btn_crm_copy_hw)

    def _god_copy_hw_clicked(self) -> None:
        txt = (self.lbl_hw.text() or "").strip()
        if not txt or txt in ("—", "(leer)"):
            self._crm_clipboard_feedback(self.btn_god_copy_hw, "Leer")
            return
        QGuiApplication.clipboard().setText(txt)
        self._crm_clipboard_feedback(self.btn_god_copy_hw)

    def _bans_copy_keygen_clicked(self) -> None:
        txt = (self.ed_keygen.text() or "").strip()
        if not txt:
            self._crm_clipboard_feedback(self.btn_bans_copy_key, "Leer")
            return
        QGuiApplication.clipboard().setText(txt)
        self._crm_clipboard_feedback(self.btn_bans_copy_key)

    def _wire_crm_copy_and_tables(self) -> None:
        for tbl in (self.tbl_p2p, self.tbl_bans):
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
            tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            tbl.installEventFilter(self)
        self.list_active_users.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_active_users.installEventFilter(self)
        self.list_tickets.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_tickets.installEventFilter(self)
        if hasattr(self, "lbl_promo_list"):
            _label_selectable(self.lbl_promo_list)

    def _apply_db_path(self) -> None:
        p = Path(self.ed_db.text().strip()).expanduser()
        self._db_path = p
        self._settings.setValue("db_path", str(p))
        _log(f"DB-Pfad gesetzt: {p}")
        QMessageBox.information(self, "DB", f"Pfad aktiv:\n{p}")

    def _build_tab_update(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Update-Zentrale (version.json)")
        fl = QFormLayout(g)
        self.ed_ver = QLineEdit(self._settings.value("rel_version", "1.0.1", str))
        self.ed_ver_url = QLineEdit(
            self._settings.value(
                "rel_url",
                f"{IONOS_SERVER_URL_DEFAULT}/download",
                str,
            )
        )
        self.ed_changelog = QTextEdit()
        self.ed_changelog.setPlainText(
            self._settings.value("rel_changelog", "Wartungsrelease.", str)
        )
        self.ed_changelog.setMaximumHeight(120)
        fl.addRow("Neue Version:", self.ed_ver)
        fl.addRow("Download-URL:", self.ed_ver_url)
        fl.addRow("Changelog:", self.ed_changelog)
        hint = QLabel(
            f"Ziel: IONOS {IONOS_SERVER_URL_DEFAULT}/api/v1/admin/version-manifest (POST, Admin-Passwort).\n"
            "Optional: eigene Ziel-URL (nur POST auf IONOS-Manifest oder direktes HTTP-PUT auf version.json)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#90a4ae;")
        lay.addWidget(hint)
        lay.addWidget(g)
        self.cb_mandatory_update = QCheckBox(
            "Update zwingend erforderlich (Alte Version blockieren)"
        )
        lay.addWidget(self.cb_mandatory_update)
        self.combo_release_channel = QComboBox()
        self.combo_release_channel.addItems(
            ["Kanal: Alle Nutzer", "Kanal: Nur Beta-Tester"]
        )
        lay.addWidget(self.combo_release_channel)
        self.ed_version_put_url = QLineEdit(
            self._settings.value(
                "version_json_url",
                f"{IONOS_SERVER_URL_DEFAULT}/api/v1/admin/version-manifest",
                str,
            )
        )
        lay.addWidget(QLabel("Ziel-URL version.json / IONOS-Manifest (optional, sonst automatisch):"))
        lay.addWidget(self.ed_version_put_url)
        b = QPushButton("Update weltweit freigeben (PUT / POST)")
        b.clicked.connect(self._on_publish_version)
        lay.addWidget(b)
        self.btn_maint_toggle = QPushButton(
            "[🛠️ WARTUNGSMODUS UMSCHALTEN] (IONOS /api/v1/status + admin/config/update)"
        )
        self.btn_maint_toggle.setStyleSheet(
            "background-color:#7f0000;color:#fff;font-weight:800;padding:12px;"
        )
        self.btn_maint_toggle.clicked.connect(self._toggle_maintenance_mode)
        lay.addWidget(self.btn_maint_toggle)
        g_ann = QGroupBox("Globale In-App-Nachricht (Live-News)")
        ann_l = QVBoxLayout(g_ann)
        self.input_global_announcement = QTextEdit()
        self.input_global_announcement.setPlaceholderText(
            "Nachricht für alle Desktop-Apps (Karriere-Dashboard-Banner) …"
        )
        self.input_global_announcement.setMaximumHeight(100)
        ann_l.addWidget(self.input_global_announcement)
        btn_ann = QPushButton("📢 Globale Nachricht senden")
        btn_ann.clicked.connect(self._on_send_global_announcement)
        ann_l.addWidget(btn_ann)
        lay.addWidget(g_ann)
        lay.addStretch()
        self.tabs.addTab(w, "Update & System")

    def _on_send_global_announcement(self) -> None:
        base = self._ionos_base_url()
        pw = self._admin_master_pw()
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Ankündigung",
                "IONOS-Basis-URL und Admin-Passwort erforderlich.",
            )
            return
        msg = self.input_global_announcement.toPlainText().strip()
        if not msg:
            QMessageBox.warning(self, "Ankündigung", "Bitte einen Text eingeben.")
            return
        url = f"{base.rstrip('/')}/api/v1/admin/announcement"
        try:
            r = requests.post(
                url,
                json={"admin_password": pw, "message": msg},
                timeout=25,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ankündigung", str(exc))
            return
        if r.status_code != 200:
            QMessageBox.warning(
                self,
                "Ankündigung",
                f"HTTP {r.status_code}\n{r.text[:400]}",
            )
            return
        QMessageBox.information(
            self,
            "Ankündigung",
            "Globale Nachricht wurde an den Server übermittelt.",
        )
        _log(f"Globale Ankündigung gesendet ({len(msg)} Zeichen).")

    def _version_put_target(self) -> str:
        manual = self.ed_version_put_url.text().strip()
        if manual:
            return manual
        return f"{IONOS_SERVER_URL_DEFAULT}/api/v1/admin/version-manifest"

    def _admin_master_pw(self) -> str:
        if hasattr(self, "ed_admin_master"):
            return (self.ed_admin_master.text() or "").strip()
        return (
            os.environ.get("SKYTYCOON_ADMIN_MASTER_PASSWORD")
            or os.environ.get("SKYTYCOON_ADMIN_PASSWORD")
            or ""
        ).strip()

    def _toggle_maintenance_mode(self) -> None:
        base = self._ionos_base_url()
        pw = self._admin_master_pw()
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Wartung",
                "IONOS-Basis-URL und Admin-Passwort (CRM-Tab) erforderlich.",
            )
            return
        cur = False
        try:
            r = requests.get(f"{base}/api/v1/status", timeout=18)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict):
                    cur = bool(j.get("maintenance_active"))
        except Exception:
            cur = False
        newv = not cur
        try:
            body = _admin_merge_json({"maintenance_active": newv}, pw)
            put = requests.post(
                f"{base}/api/v1/admin/config/update",
                json=body,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "SkyTycoonPro-AdminCommander/1",
                    **_admin_token_headers(pw),
                },
                timeout=28,
            )
        except requests.RequestException as exc:
            QMessageBox.critical(self, "Wartung", str(exc))
            return
        _log(f"maintenance_active={newv} POST {base}/api/v1/admin/config/update status={put.status_code}")
        QMessageBox.information(
            self,
            "Wartung",
            f"maintenance_active = {newv}\nHTTP {put.status_code}",
        )

    def _on_publish_version(self) -> None:
        url = self._version_put_target()
        if not url:
            QMessageBox.warning(
                self,
                "Update",
                "Keine gültige Ziel-URL.",
            )
            return
        ch = "all" if self.combo_release_channel.currentIndex() == 0 else "beta"
        pw = self.ed_admin_master.text().strip()
        body = {
            "version": self.ed_ver.text().strip(),
            "url": self.ed_ver_url.text().strip(),
            "changelog": self.ed_changelog.toPlainText().strip(),
            "mandatory": bool(self.cb_mandatory_update.isChecked()),
            "release_channel": ch,
        }
        try:
            if "/api/v1/admin/version-manifest" in url:
                body = _admin_merge_json(body, pw)
                hdr = {
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "SkyTycoonPro-AdminCommander/1",
                    **_admin_token_headers(pw),
                }
                r = requests.post(
                    url,
                    json=body,
                    headers=hdr,
                    timeout=35,
                )
            else:
                r = requests.put(
                    url,
                    data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "User-Agent": "SkyTycoonPro-AdminCommander/1",
                    },
                    timeout=25,
                )
        except requests.RequestException as exc:
            QMessageBox.critical(self, "Update", str(exc))
            return
        self._settings.setValue("rel_version", self.ed_ver.text().strip())
        self._settings.setValue("rel_url", self.ed_ver_url.text().strip())
        self._settings.setValue("rel_changelog", self.ed_changelog.toPlainText().strip())
        self._settings.setValue("version_json_url", self.ed_version_put_url.text().strip())
        _log(f"version manifest {url} status={r.status_code}")
        QMessageBox.information(self, "Update", f"HTTP {r.status_code}\n{r.text[:600]}")

    def _build_tab_p2p(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            QLabel(
                "P2P-Listings (IONOS): POST /api/v1/admin/market/list und /delete "
                "(Admin-Passwort im CRM-Tab + Header X-Admin-Token)."
            )
        )
        self.tbl_p2p = QTableWidget(0, 5)
        self.tbl_p2p.setHorizontalHeaderLabels(
            ["id", "model", "price", "seller", "hardware_id"]
        )
        hh = self.tbl_p2p.horizontalHeader()
        for i in range(5):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tbl_p2p)
        row = QHBoxLayout()
        b1 = QPushButton("Listings laden")
        b1.clicked.connect(self._p2p_refresh)
        row.addWidget(b1)
        b2 = QPushButton("Markierte auf dem Server löschen")
        b2.clicked.connect(self._p2p_delete_selected)
        row.addWidget(b2)
        row.addStretch()
        lay.addLayout(row)
        self.tabs.addTab(w, "P2P Markt")

    def _p2p_refresh(self) -> None:
        base = self._ionos_base_url()
        pw = self._admin_master_pw()
        if not base or not pw:
            QMessageBox.warning(self, "P2P", "IONOS-URL und Admin-Passwort (CRM-Tab) erforderlich.")
            return
        try:
            r = requests.post(
                f"{base}/api/v1/admin/market/list",
                json=_admin_merge_json({}, pw),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "SkyTycoonPro-AdminCommander/1",
                    **_admin_token_headers(pw),
                },
                timeout=25,
            )
            r.raise_for_status()
            data = r.json() if r.text.strip() else {}
        except Exception as exc:
            QMessageBox.critical(self, "P2P", str(exc))
            return
        lst = data.get("listings") if isinstance(data, dict) else data
        if not isinstance(lst, list):
            lst = []
        self.tbl_p2p.setRowCount(0)
        for row in lst:
            if not isinstance(row, dict):
                continue
            r = self.tbl_p2p.rowCount()
            self.tbl_p2p.insertRow(r)
            self.tbl_p2p.setItem(r, 0, QTableWidgetItem(str(row.get("id", ""))))
            self.tbl_p2p.setItem(r, 1, QTableWidgetItem(str(row.get("model", ""))))
            self.tbl_p2p.setItem(r, 2, QTableWidgetItem(str(row.get("price", ""))))
            self.tbl_p2p.setItem(r, 3, QTableWidgetItem(str(row.get("seller_name", ""))))
            self.tbl_p2p.setItem(r, 4, QTableWidgetItem(str(row.get("hardware_id", ""))))
        _log(f"P2P refresh {len(lst)} rows")

    def _p2p_delete_selected(self) -> None:
        base = self._ionos_base_url()
        pw = self._admin_master_pw()
        if not base or not pw:
            QMessageBox.warning(self, "P2P", "IONOS-URL und Admin-Passwort (CRM-Tab) erforderlich.")
            return
        rows = sorted({i.row() for i in self.tbl_p2p.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "P2P", "Bitte Zeilen markieren.")
            return
        ids = [self.tbl_p2p.item(r, 0).text() for r in rows if self.tbl_p2p.item(r, 0)]
        if not ids:
            return
        try:
            put = requests.post(
                f"{base}/api/v1/admin/market/delete",
                json=_admin_merge_json({"listing_ids": ids}, pw),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "SkyTycoonPro-AdminCommander/1",
                    **_admin_token_headers(pw),
                },
                timeout=25,
            )
        except requests.RequestException as exc:
            QMessageBox.critical(self, "P2P", str(exc))
            return
        _log(f"P2P delete ids={ids} status={put.status_code}")
        QMessageBox.information(self, "P2P", f"Server-Löschung. HTTP {put.status_code}")
        self._p2p_refresh()

    def _build_tab_bans(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Hardware-Sperren (bans.json)")
        lay.addWidget(g)
        gl = QVBoxLayout(g)
        self.ed_bans_url = QLineEdit(
            self._settings.value(
                "bans_url",
                "",
                str,
            )
        )
        gl.addWidget(QLabel("URL bans.json:"))
        gl.addWidget(self.ed_bans_url)
        self.tbl_bans = QTableWidget(0, 1)
        self.tbl_bans.setHorizontalHeaderLabels(["hardware_id / UUID"])
        self.tbl_bans.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        gl.addWidget(self.tbl_bans)
        row = QHBoxLayout()
        b1 = QPushButton("Bans laden")
        b1.clicked.connect(self._bans_refresh)
        row.addWidget(b1)
        self.ed_new_ban = QLineEdit()
        self.ed_new_ban.setPlaceholderText("neue Hardware-ID …")
        row.addWidget(self.ed_new_ban, stretch=1)
        b2 = QPushButton("User bannen & speichern")
        b2.clicked.connect(self._bans_add)
        row.addWidget(b2)
        gl.addLayout(row)
        gl.addWidget(QLabel("Generierter Lizenzschlüssel (Key-Generator):"))
        row_kg = QHBoxLayout()
        self.ed_keygen = QLineEdit()
        self.ed_keygen.setPlaceholderText("Nach Server-Aktion hier den Schlüssel einfügen …")
        row_kg.addWidget(self.ed_keygen, stretch=1)
        self.btn_bans_copy_key = QPushButton("📋")
        self.btn_bans_copy_key.setObjectName("secondary")
        self.btn_bans_copy_key.setFixedWidth(44)
        self.btn_bans_copy_key.setToolTip("In Zwischenablage kopieren")
        self.btn_bans_copy_key.clicked.connect(self._bans_copy_keygen_clicked)
        row_kg.addWidget(self.btn_bans_copy_key)
        gl.addLayout(row_kg)
        self.tabs.addTab(w, "User / Bann")

    def _bans_url(self) -> str:
        return self.ed_bans_url.text().strip()

    def _bans_refresh(self) -> None:
        url = self._bans_url()
        if not url:
            QMessageBox.warning(self, "Bann", "Keine bans.json-URL.")
            return
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            j = r.json() if r.text.strip() else {}
        except Exception as exc:
            QMessageBox.critical(self, "Bann", str(exc))
            return
        blocked = j.get("blocked") or j.get("banned_hwids") or []
        if not isinstance(blocked, list):
            blocked = []
        self.tbl_bans.setRowCount(0)
        for bid in blocked:
            rr = self.tbl_bans.rowCount()
            self.tbl_bans.insertRow(rr)
            self.tbl_bans.setItem(rr, 0, QTableWidgetItem(str(bid)))
        self._settings.setValue("bans_url", url)
        _log(f"bans refresh count={len(blocked)}")

    def _bans_add(self) -> None:
        url = self._bans_url()
        if not url:
            return
        new_id = self.ed_new_ban.text().strip()
        if not new_id:
            QMessageBox.information(self, "Bann", "ID eingeben.")
            return
        try:
            r = requests.get(url, timeout=15)
            j = r.json() if r.status_code == 200 and r.text.strip() else {}
        except Exception:
            j = {}
        blocked = j.get("blocked") if isinstance(j, dict) else None
        if not isinstance(blocked, list):
            blocked = j.get("banned_hwids") if isinstance(j, dict) else []
        if not isinstance(blocked, list):
            blocked = []
        if new_id not in blocked:
            blocked.append(new_id)
        out = {"blocked": blocked, "updated_unix": time.time()}
        try:
            put = requests.put(
                url,
                data=json.dumps(out, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "SkyTycoonPro-AdminCommander/1",
                },
                timeout=25,
            )
        except requests.RequestException as exc:
            QMessageBox.critical(self, "Bann", str(exc))
            return
        _log(f"ban add {new_id} status={put.status_code}")
        QMessageBox.information(self, "Bann", f"Gespeichert. HTTP {put.status_code}")
        self.ed_new_ban.clear()
        self._bans_refresh()

    def _build_tab_global(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Globale Wirtschaft (global_econ.json)")
        fl = QFormLayout(g)
        self.ed_global_url = QLineEdit(
            self._settings.value(
                "global_url",
                "",
                str,
            )
        )
        fl.addRow("URL:", self.ed_global_url)
        self.sp_fuel = QDoubleSpinBox()
        self.sp_fuel.setRange(0.2, 5.0)
        self.sp_fuel.setSingleStep(0.05)
        self.sp_fuel.setValue(1.0)
        fl.addRow("Sprit-Multiplikator (fuel_mult):", self.sp_fuel)
        self.sp_emerg = QDoubleSpinBox()
        self.sp_emerg.setRange(0.0, 1.0)
        self.sp_emerg.setDecimals(3)
        self.sp_emerg.setSingleStep(0.01)
        self.sp_emerg.setValue(0.02)
        fl.addRow("Notfall-Wahrscheinlichkeit (0–1):", self.sp_emerg)
        lay.addWidget(g)
        b = QPushButton("Global speichern (PUT)")
        b.clicked.connect(self._global_save)
        lay.addWidget(b)
        st_g = QGroupBox("CPU-Governor · Live-FIDS-Stresstest")
        st_l = QVBoxLayout(st_g)
        st_l.addWidget(
            QLabel(
                "Simuliert bis zu 500 KI-Piloten auf der Live-Flugtafel. "
                "Backend bremst bei 85 % CPU — 15 % Reserve für Updates & Synology-Backups."
            )
        )
        self.btn_stresstest = QPushButton("[ 🌋 Server-Stresstest aktivieren ]")
        self.btn_stresstest.setStyleSheet(
            "QPushButton { background:#1a1208; color:#ffd700; border:2px solid #d4af37; "
            "font-weight:900; padding:14px; border-radius:10px; }"
        )
        self.btn_stresstest.clicked.connect(self._toggle_stresstest)
        st_l.addWidget(self.btn_stresstest)
        self.lbl_stresstest = QLabel("Status: —")
        self.lbl_stresstest.setWordWrap(True)
        st_l.addWidget(self.lbl_stresstest)
        lay.addWidget(st_g)
        perf_g = QGroupBox("🖥 IONOS Performance-Matrix (Live)")
        perf_g.setStyleSheet(
            "QGroupBox { color: #8ac7ff; font-weight: 800; border: 2px solid #00a2ff; "
            "border-radius: 10px; margin-top: 12px; padding-top: 14px; }"
        )
        perf_l = QVBoxLayout(perf_g)
        self.lbl_server_perf = QLabel("CPU: — · RAM: — · Disk frei: —")
        self.lbl_server_perf.setWordWrap(True)
        self.lbl_server_perf.setStyleSheet("color: #cfd8dc; font-size: 13px;")
        perf_l.addWidget(self.lbl_server_perf)
        self.pb_server_perf = QProgressBar()
        self.pb_server_perf.setRange(0, 100)
        self.pb_server_perf.setFormat("CPU %p%")
        self.pb_server_perf.setStyleSheet(
            "QProgressBar { border: 1px solid #00a2ff; background: #0b0f19; height: 22px; }"
            "QProgressBar::chunk { background: #00a2ff; }"
        )
        perf_l.addWidget(self.pb_server_perf)
        self.pb_server_ram = QProgressBar()
        self.pb_server_ram.setRange(0, 100)
        self.pb_server_ram.setFormat("RAM %p%")
        self.pb_server_ram.setStyleSheet(
            "QProgressBar { border: 1px solid #8ac7ff; background: #0b0f19; height: 22px; }"
            "QProgressBar::chunk { background: #8ac7ff; }"
        )
        perf_l.addWidget(self.pb_server_ram)
        lay.addWidget(perf_g)
        dep_g = QGroupBox("⚡ IONOS Hotfix-Deployment")
        dep_g.setStyleSheet(
            "QGroupBox { color: #ffd54f; font-weight: 900; border: 2px solid #d4af37; "
            "border-radius: 10px; margin-top: 12px; padding-top: 14px; }"
        )
        dep_l = QVBoxLayout(dep_g)
        self.btn_hotfix_deploy = QPushButton(
            "[ ⚡ ZÜNDE HOTFIX-DEPLOYMENT LIVE AUF IONOS ]"
        )
        self.btn_hotfix_deploy.setStyleSheet(
            "QPushButton { background:#1a1208; color:#ffd700; border:2px solid #d4af37; "
            "font-weight:900; padding:14px; border-radius:10px; }"
            "QPushButton:hover { background:#2a1a08; }"
        )
        self.btn_hotfix_deploy.clicked.connect(self._trigger_hotfix_deploy)
        dep_l.addWidget(self.btn_hotfix_deploy)
        self.lbl_hotfix_deploy = QLabel("Deploy: bereit")
        self.lbl_hotfix_deploy.setWordWrap(True)
        dep_l.addWidget(self.lbl_hotfix_deploy)
        lay.addWidget(dep_g)
        self._perf_timer = QTimer(self)
        self._perf_timer.timeout.connect(self._refresh_server_performance)
        self._perf_timer.start(1000)
        QTimer.singleShot(300, self._refresh_server_performance)
        lay.addStretch()
        self.tabs.addTab(w, "Wirtschaft global")

    def _trigger_hotfix_deploy(self) -> None:
        base = self._ionos_base_url()
        pw = (self.ed_admin_master.text() or "").strip() if hasattr(self, "ed_admin_master") else ""
        if not base or not pw:
            QMessageBox.warning(self, "Deploy", "IONOS-URL und Admin-Passwort erforderlich.")
            return
        self.lbl_hotfix_deploy.setText("Deploy: läuft…")
        self.btn_hotfix_deploy.setEnabled(False)
        try:
            r = requests.post(
                f"{base}/api/v1/admin/deploy/execute",
                json={"admin_master_password": pw, "admin_password": pw},
                timeout=25,
                headers={"User-Agent": "SkyTycoon-AdminCommander/1.0"},
            )
            j = r.json() if r.content else {}
            msg = (
                j.get("message_de")
                or j.get("message_en")
                or j.get("status")
                or f"HTTP {r.status_code}"
            )
            self.lbl_hotfix_deploy.setText(f"Deploy: {msg}")
            if r.status_code < 400:
                QMessageBox.information(self, "Deploy", str(msg))
            else:
                QMessageBox.warning(self, "Deploy", str(msg))
        except requests.RequestException as exc:
            self.lbl_hotfix_deploy.setText(f"Deploy: Fehler — {exc}")
            QMessageBox.critical(self, "Deploy", str(exc))
        finally:
            self.btn_hotfix_deploy.setEnabled(True)

    def _refresh_server_performance(self) -> None:
        base = self._ionos_base_url()
        pw = (self.ed_admin_master.text() or "").strip() if hasattr(self, "ed_admin_master") else ""
        if not base or not pw:
            return
        q = urlencode(
            {
                "admin_master_password": pw,
                "admin_password": pw,
            }
        )
        try:
            r = requests.get(
                f"{base}/api/v1/admin/server/performance?{q}",
                timeout=8,
                headers={"User-Agent": "SkyTycoon-AdminCommander/1.0"},
            )
            j = r.json() if r.content else {}
        except requests.RequestException as exc:
            self.lbl_server_perf.setText(f"Performance: offline ({exc})")
            return
        if not isinstance(j, dict) or not j.get("ok", True):
            self.lbl_server_perf.setText(
                f"Performance: {j.get('error', 'unavailable') if isinstance(j, dict) else 'error'}"
            )
            return
        cpu = float(j.get("cpu_percent", j.get("cpu_usage", 0)) or 0)
        ram = float(j.get("ram_percent", j.get("ram_usage", 0)) or 0)
        disk_free = float(j.get("disk_free_gb", 0) or 0)
        disk_total = float(j.get("disk_total_gb", 0) or 0)
        ram_used = float(j.get("ram_used_gb", 0) or 0)
        ram_total = float(j.get("ram_total_gb", 0) or 0)
        self.pb_server_perf.setValue(int(max(0, min(100, cpu))))
        self.pb_server_ram.setValue(int(max(0, min(100, ram))))
        self.lbl_server_perf.setText(
            f"CPU {cpu:.1f}% · RAM {ram:.1f}% ({ram_used:.1f}/{ram_total:.1f} GB) · "
            f"Disk frei {disk_free:.1f} GB / {disk_total:.1f} GB"
        )

    def _global_save(self) -> None:
        url = self.ed_global_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Global", "URL fehlt.")
            return
        body = {
            "fuel_mult": float(self.sp_fuel.value()),
            "emergency_prob": float(self.sp_emerg.value()),
            "updated_unix": time.time(),
        }
        try:
            r = requests.put(
                url,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "SkyTycoonPro-AdminCommander/1",
                },
                timeout=25,
            )
        except requests.RequestException as exc:
            QMessageBox.critical(self, "Global", str(exc))
            return
        self._settings.setValue("global_url", url)
        _log(f"global_econ PUT {url} status={r.status_code}")
        QMessageBox.information(self, "Global", f"HTTP {r.status_code}")

    def _api_base(self) -> str:
        return (IONOS_SERVER_URL or "").strip().rstrip("/")

    def _toggle_stresstest(self) -> None:
        base = self._api_base()
        if not base:
            QMessageBox.warning(self, "Stresstest", "IONOS-URL fehlt.")
            return
        try:
            st = requests.get(
                f"{base}/api/v1/admin/stresstest/status",
                params=_admin_params(),
                timeout=15,
            )
            cur = st.json() if st.status_code == 200 else {}
            enabled = bool(cur.get("enabled"))
        except requests.RequestException:
            enabled = False
        body = _admin_body({"toggle": True, "enabled": not enabled})
        try:
            r = requests.post(
                f"{base}/api/v1/admin/stresstest/toggle",
                json=body,
                timeout=30,
            )
            data = r.json()
        except requests.RequestException as exc:
            QMessageBox.critical(self, "Stresstest", str(exc))
            return
        if r.status_code != 200 or not data.get("ok"):
            QMessageBox.warning(
                self,
                "Stresstest",
                f"HTTP {r.status_code}\n{data}",
            )
            return
        on = bool(data.get("enabled"))
        label = data.get("brake_label_de") or data.get("brake_label_en") or ""
        pilots = data.get("active_pilots") or data.get("pilots") or "—"
        self.lbl_stresstest.setText(
            f"{'AKTIV' if on else 'AUS'} · Piloten: {pilots}\n{label}"
        )
        self.btn_stresstest.setText(
            "[ 🌋 Server-Stresstest DEAKTIVIEREN ]"
            if on
            else "[ 🌋 Server-Stresstest aktivieren ]"
        )
        QMessageBox.information(
            self,
            "Stresstest",
            "Stresstest eingeschaltet." if on else "Stresstest ausgeschaltet.",
        )

    def _global_config_default_json(self) -> str:
        return json.dumps(
            {
                "update": {
                    "latest_version": "1.0.1",
                    "changelog": "Wartungsrelease.",
                    "download_url": "https://example.com/SkyTycoonPro.exe",
                    "allow_skip": True,
                    "min_version": "",
                    "version_compare": "unequal",
                },
                "active_event": {"type": "spritkrise", "multiplier": 1.3},
                "events": {
                    "fuel_crisis": {"active": False, "fuel_mult": 1.3},
                },
                "banned_users": {},
            },
            ensure_ascii=False,
            indent=2,
        )

    def _build_tab_cloud_sync(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            QLabel(
                "Portal-Konfiguration (JSON, Gegenstück zur main.py): update, events, "
                "active_event, optional banned_users. Standard: IONOS "
                "POST /api/v1/admin/portal-config (op get/set, Admin-Passwort)."
            )
        )
        self.ed_global_config_url = QLineEdit(
            self._settings.value("global_config_url", "", str)
        )
        self.ed_global_config_url.setPlaceholderText(
            "Optional: eigene JSON-URL für direktes HTTP GET/PUT (Experten; sonst leer)"
        )
        lay.addWidget(QLabel("Optional: Direkt-URL (GET/PUT):"))
        lay.addWidget(self.ed_global_config_url)
        self.txt_global_config = QTextEdit()
        self.txt_global_config.setFont(QFont("Consolas", 9))
        self.txt_global_config.setPlainText(
            self._settings.value("global_config_body", self._global_config_default_json(), str)
        )
        lay.addWidget(self.txt_global_config)
        row = QHBoxLayout()
        b_load = QPushButton("Von Server laden")
        b_load.setObjectName("secondary")
        b_load.clicked.connect(self._cloud_cfg_load)
        row.addWidget(b_load)
        b_put = QPushButton("Auf Server speichern (IONOS portal-config / PUT)")
        b_put.clicked.connect(self._cloud_cfg_put)
        row.addWidget(b_put)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        self.tabs.addTab(w, "Cloud Sync")

    def _cloud_cfg_load(self) -> None:
        url = self.ed_global_config_url.text().strip()
        if url:
            try:
                r = requests.get(url, timeout=20)
                r.raise_for_status()
                txt = r.text.strip() or self._global_config_default_json()
                self.txt_global_config.setPlainText(txt)
                self._settings.setValue("global_config_url", url)
                _log(f"global_config GET {url}")
            except Exception as exc:
                QMessageBox.critical(self, "Cloud Sync", str(exc))
            return
        base = self._ionos_base_url()
        pw = self._admin_master_pw()
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Cloud Sync",
                "IONOS-URL und Admin-Passwort (CRM-Tab) erforderlich, oder Direkt-URL eintragen.",
            )
            return
        try:
            r = requests.post(
                f"{base}/api/v1/admin/portal-config",
                json=_admin_merge_json({"op": "get"}, pw),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "SkyTycoonPro-AdminCommander/1",
                    **_admin_token_headers(pw),
                },
                timeout=25,
            )
            r.raise_for_status()
            data = r.json() if r.text.strip() else {}
            cfg = data.get("config") if isinstance(data, dict) else {}
            if not isinstance(cfg, dict):
                cfg = {}
            self.txt_global_config.setPlainText(
                json.dumps(cfg, ensure_ascii=False, indent=2)
                if cfg
                else self._global_config_default_json()
            )
            _log(f"portal-config GET {base}")
        except Exception as exc:
            QMessageBox.critical(self, "Cloud Sync", str(exc))

    def _cloud_cfg_put(self) -> None:
        url = self.ed_global_config_url.text().strip()
        raw = self.txt_global_config.toPlainText().strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "Cloud Sync", f"JSON ungültig: {exc}")
            return
        if not isinstance(parsed, dict):
            QMessageBox.warning(self, "Cloud Sync", "Root-JSON muss ein Objekt sein.")
            return
        if url:
            try:
                r = requests.put(
                    url,
                    data=raw.encode("utf-8"),
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "User-Agent": "SkyTycoonPro-AdminCommander/1",
                    },
                    timeout=25,
                )
            except requests.RequestException as exc:
                QMessageBox.critical(self, "Cloud Sync", str(exc))
                return
            self._settings.setValue("global_config_url", url)
            self._settings.setValue("global_config_body", raw)
            _log(f"global_config PUT {url} status={r.status_code}")
            QMessageBox.information(self, "Cloud Sync", f"HTTP {r.status_code}")
            return
        base = self._ionos_base_url()
        pw = self._admin_master_pw()
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Cloud Sync",
                "IONOS-URL und Admin-Passwort (CRM-Tab) erforderlich, oder Direkt-URL eintragen.",
            )
            return
        try:
            r = requests.post(
                f"{base}/api/v1/admin/portal-config",
                json=_admin_merge_json({"op": "set", "config": parsed}, pw),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "SkyTycoonPro-AdminCommander/1",
                    **_admin_token_headers(pw),
                },
                timeout=25,
            )
        except requests.RequestException as exc:
            QMessageBox.critical(self, "Cloud Sync", str(exc))
            return
        self._settings.setValue("global_config_body", raw)
        _log(f"portal-config SET {base} status={r.status_code}")
        QMessageBox.information(self, "Cloud Sync", f"HTTP {r.status_code}")

    def _ionos_base_url(self) -> str:
        raw = ""
        if hasattr(self, "ed_ionos_api"):
            raw = self.ed_ionos_api.text().strip()
        raw = raw.rstrip("/")
        if raw:
            return raw
        return (
            os.environ.get("SKYTYCOON_IONOS_API_BASE") or "https://skytycoon.info"
        ).strip().rstrip("/")

    def _build_tab_user_crm(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("IONOS API Basis-URL:"))
        self.ed_ionos_api = QLineEdit(
            self._settings.value(
                "ionos_api_base",
                IONOS_SERVER_URL,
                str,
            )
        )
        top.addWidget(self.ed_ionos_api, stretch=1)
        bsave = QPushButton("URL speichern")
        bsave.setObjectName("secondary")

        def _save_url() -> None:
            self._settings.setValue("ionos_api_base", self.ed_ionos_api.text().strip())

        bsave.clicked.connect(_save_url)
        top.addWidget(bsave)
        lay.addLayout(top)
        pw_row = QHBoxLayout()
        pw_row.addWidget(QLabel("Admin-Master-Passwort:"))
        self.ed_admin_master = QLineEdit()
        self.ed_admin_master.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_admin_master.setText(self._settings.value("admin_master_pw", "", str))
        pw_row.addWidget(self.ed_admin_master, stretch=1)
        bpw = QPushButton("PW speichern")
        bpw.setObjectName("secondary")

        def _save_pw() -> None:
            self._settings.setValue("admin_master_pw", self.ed_admin_master.text())

        bpw.clicked.connect(_save_pw)
        pw_row.addWidget(bpw)
        lay.addLayout(pw_row)

        sp = QSplitter(Qt.Orientation.Horizontal)
        self.list_active_users = QListWidget()
        self.list_active_users.currentItemChanged.connect(self._crm_user_selected)
        self.list_active_users.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.list_active_users.customContextMenuRequested.connect(
            self._crm_users_context_menu
        )
        sp.addWidget(self.list_active_users)
        right = QWidget()
        rf = QFormLayout(right)
        self.lbl_crm_credits = QLabel("—")
        self.lbl_crm_xp = QLabel("—")
        self.lbl_crm_rep = QLabel("—")
        self.lbl_crm_loan = QLabel("—")
        self.lbl_crm_strikes = QLabel("—")
        self.lbl_crm_planes = QLabel("—")
        self.lbl_crm_backup = QLabel("—")
        self.lbl_crm_license = QLabel("—")
        self.lbl_crm_license.setWordWrap(True)
        self.lbl_crm_hwid = QLabel("—")
        self.lbl_crm_hwid.setWordWrap(True)
        rf.addRow("Credits:", self.lbl_crm_credits)
        rf.addRow("Prestige-XP / Rang:", self.lbl_crm_xp)
        rf.addRow("Reputation:", self.lbl_crm_rep)
        rf.addRow("Kredit-Restschuld:", self.lbl_crm_loan)
        rf.addRow("Anti-Cheat Strikes:", self.lbl_crm_strikes)
        rf.addRow("Flugzeuge / Ratings:", self.lbl_crm_planes)
        rf.addRow("Letztes Cloud-Backup:", self.lbl_crm_backup)
        row_lic = QHBoxLayout()
        row_lic.addWidget(self.lbl_crm_license, stretch=1)
        self.btn_crm_copy_license = QPushButton("📋")
        self.btn_crm_copy_license.setObjectName("secondary")
        self.btn_crm_copy_license.setFixedWidth(44)
        self.btn_crm_copy_license.setToolTip("In Zwischenablage kopieren")
        self.btn_crm_copy_license.clicked.connect(self._crm_copy_license_clicked)
        row_lic.addWidget(self.btn_crm_copy_license)
        wrap_lic = QWidget()
        wrap_lic.setLayout(row_lic)
        rf.addRow("Hinterlegter Lizenzschlüssel:", wrap_lic)
        row_hw = QHBoxLayout()
        row_hw.addWidget(self.lbl_crm_hwid, stretch=1)
        self.btn_crm_copy_hw = QPushButton("📋")
        self.btn_crm_copy_hw.setObjectName("secondary")
        self.btn_crm_copy_hw.setFixedWidth(44)
        self.btn_crm_copy_hw.setToolTip("In Zwischenablage kopieren")
        self.btn_crm_copy_hw.clicked.connect(self._crm_copy_hw_clicked)
        row_hw.addWidget(self.btn_crm_copy_hw)
        wrap_hw = QWidget()
        wrap_hw.setLayout(row_hw)
        rf.addRow("Hardware-ID:", wrap_hw)
        for _lbl in (
            self.lbl_crm_credits,
            self.lbl_crm_xp,
            self.lbl_crm_rep,
            self.lbl_crm_loan,
            self.lbl_crm_strikes,
            self.lbl_crm_planes,
            self.lbl_crm_backup,
            self.lbl_crm_license,
            self.lbl_crm_hwid,
        ):
            _label_selectable(_lbl)
        self.ed_crm_credits_delta = QLineEdit()
        self.ed_crm_credits_delta.setPlaceholderText("+50000 oder -10000")
        rf.addRow("Credits Δ:", self.ed_crm_credits_delta)
        b_cr = QPushButton("💰 Credits anpassen · Übernehmen")
        b_cr.clicked.connect(self._crm_apply_credits)
        rf.addRow(b_cr)
        self.ed_crm_xp_delta = QLineEdit()
        self.ed_crm_xp_delta.setPlaceholderText("XP-Delta")
        rf.addRow("XP Δ:", self.ed_crm_xp_delta)
        b_xp = QPushButton("⭐ XP anpassen · Übernehmen")
        b_xp.clicked.connect(self._crm_apply_xp)
        rf.addRow(b_xp)
        self.ed_crm_loan = QLineEdit()
        rf.addRow("Kreditschuld (absolut):", self.ed_crm_loan)
        b_lo = QPushButton("🏛️ Kreditschuld setzen · Übernehmen")
        b_lo.clicked.connect(self._crm_apply_loan)
        rf.addRow(b_lo)
        b_st = QPushButton("🛡️ Strikes auf 0 setzen")
        b_st.clicked.connect(self._crm_reset_strikes)
        rf.addRow(b_st)
        b_ban = QPushButton("❌ Account bannen")
        b_ban.clicked.connect(self._crm_ban_user)
        rf.addRow(b_ban)
        b_obl = QPushButton("[ 🪓 Konto unwiderruflich löschen / Obliterate Account ]")
        b_obl.setStyleSheet(
            "background:#4a0000;color:#ff8a80;font-weight:900;padding:10px;"
        )
        b_obl.clicked.connect(self._crm_obliterate_account)
        rf.addRow(b_obl)
        b_dl = QPushButton("📥 Cloud-Backup herunterladen")
        b_dl.setObjectName("secondary")
        b_dl.clicked.connect(self._crm_download_backup)
        rf.addRow(b_dl)
        self.ed_crm_reset_pw = QLineEdit()
        self.ed_crm_reset_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_crm_reset_pw.setPlaceholderText("Neues Cloud-Passwort (min. 4 Zeichen)")
        rf.addRow("Passwort zurücksetzen:", self.ed_crm_reset_pw)
        b_pw_reset = QPushButton("🔑 Cloud-Passwort hashen & setzen")
        b_pw_reset.clicked.connect(self._crm_reset_user_password)
        rf.addRow(b_pw_reset)
        sp.addWidget(right)
        lay.addWidget(sp)
        br_top = QHBoxLayout()
        b_list = QPushButton("Liste vom Server laden")
        b_list.clicked.connect(self._crm_refresh_users)
        br_top.addWidget(b_list)
        self.btn_mass_mail_resend = QPushButton(
            "📧 Allen registrierten Usern ihre Keys & Daten senden"
        )
        self.btn_mass_mail_resend.setStyleSheet(
            "background-color: #002244; color: #d4af37; font-weight: bold; padding: 6px;"
        )
        self.btn_mass_mail_resend.clicked.connect(self.trigger_global_credentials_resend)
        br_top.addWidget(self.btn_mass_mail_resend)
        self.btn_admin_server_log = QPushButton("📜 IONOS Server-Log laden")
        self.btn_admin_server_log.clicked.connect(self._admin_fetch_server_log)
        br_top.addWidget(self.btn_admin_server_log)
        self.btn_admin_crash_tail = QPushButton("💥 Crash-Reports (Server)")
        self.btn_admin_crash_tail.clicked.connect(self._admin_fetch_crash_reports)
        br_top.addWidget(self.btn_admin_crash_tail)
        br_top.addStretch()
        lay.addLayout(br_top)
        self._crm_sel_hw: str | None = None
        self.tabs.addTab(w, "User-Verwaltung (CRM)")

    def _build_tab_license_keys(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            QLabel(
                "Manuelle Lizenzschlüssel live auf skytycoon.info erzeugen und sofort "
                "einem User / Pilot-ID zuweisen. Admin-Passwort und URL kommen aus dem CRM-Tab."
            )
        )

        box = QGroupBox("🔑 Key-Verwaltung & Lizenzen")
        form = QFormLayout(box)
        self.list_key_users = QListWidget()
        self.list_key_users.currentItemChanged.connect(self._key_user_selected)
        form.addRow("Live-User:", self.list_key_users)

        b_refresh_users = QPushButton("🔄 User-Liste vom Server laden")
        b_refresh_users.setObjectName("secondary")
        b_refresh_users.clicked.connect(self._key_refresh_users)
        form.addRow(b_refresh_users)

        self.ed_key_target_user = QLineEdit()
        self.ed_key_target_user.setPlaceholderText("Ziel-Username, E-Mail, Pilot-ID oder Hardware-ID")
        form.addRow("Ziel-User:", self.ed_key_target_user)

        self.combo_key_license_type = QComboBox()
        license_options = [
            ("Radar", "radar"),
            ("SimBrief / Dispatch", "simbrief"),
            ("Hangar", "hangar"),
            ("Banking", "banking"),
            ("Werft / Auktionen", "werft"),
            ("Jobs", "jobs"),
            ("Allianz", "alliance"),
            ("Boarding / Dispatcher", "dispatcher"),
            ("HQ & Immobilien", "properties"),
            ("Academy", "academy"),
            ("Premium Wetter", "weather"),
            ("MSFS / SimConnect", "msfs_link"),
        ]
        for label, value in license_options:
            self.combo_key_license_type.addItem(label, value)
        form.addRow("Lizenz-Typ:", self.combo_key_license_type)

        btn_row = QHBoxLayout()
        b_prefill = QPushButton("Aus CRM-Auswahl übernehmen")
        b_prefill.setObjectName("secondary")
        b_prefill.clicked.connect(self._key_prefill_selected_user)
        btn_row.addWidget(b_prefill)
        b_generate = QPushButton("[ 🛠️ Lizenzschlüssel generieren & zuweisen ]")
        b_generate.clicked.connect(self._key_generate_and_assign)
        btn_row.addWidget(b_generate, stretch=1)
        form.addRow(btn_row)
        self.ed_key_unused_note = QLineEdit()
        self.ed_key_unused_note.setPlaceholderText(
            "Optional: Notiz / E-Mail für Shop (nur Anzeige)"
        )
        form.addRow("Shop-Notiz:", self.ed_key_unused_note)
        b_unused = QPushButton("[ 🎫 Lizenzschlüssel generieren ]")
        b_unused.setStyleSheet(
            "background:#3d2e00;color:#ffd54f;font-weight:900;padding:10px;border:2px solid #d4af37;"
        )
        b_unused.clicked.connect(self._key_generate_unused_st)
        form.addRow(b_unused)

        manual_row = QHBoxLayout()
        self.ed_key_manual_license = QLineEdit()
        self.ed_key_manual_license.setPlaceholderText("CRM-Key übernehmen / vorhandenen Lizenzschlüssel eintragen")
        manual_row.addWidget(self.ed_key_manual_license, stretch=1)
        b_assign_direct = QPushButton("[ 🔗 CRM-Key direkt binden ]")
        b_assign_direct.clicked.connect(self._key_assign_direct)
        manual_row.addWidget(b_assign_direct)
        form.addRow("CRM-Key:", manual_row)

        self.txt_key_result = QTextEdit()
        self.txt_key_result.setReadOnly(True)
        self.txt_key_result.setPlaceholderText("Hier erscheint der generierte ST-Key.")
        form.addRow("Ergebnis:", self.txt_key_result)

        b_copy = QPushButton("📋 Key / Ergebnis kopieren")
        b_copy.setObjectName("secondary")
        b_copy.clicked.connect(self._key_copy_result)
        form.addRow(b_copy)

        lay.addWidget(box)

        g_crm = QGroupBox("🔑 CRM license_keys (Live-Tabelle)")
        cl = QVBoxLayout(g_crm)
        brow = QHBoxLayout()
        b_keys_refresh = QPushButton("🔄 Keys vom Server laden")
        b_keys_refresh.clicked.connect(self._crm_keys_refresh)
        brow.addWidget(b_keys_refresh)
        brow.addStretch()
        cl.addLayout(brow)
        self.tbl_license_keys = QTableWidget(0, 6)
        self.tbl_license_keys.setHorizontalHeaderLabels(
            ["Key", "Status", "HWID", "Pilot", "E-Mail", "Erstellt"]
        )
        self.tbl_license_keys.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl_license_keys.customContextMenuRequested.connect(
            self._crm_keys_context_menu
        )
        hh2 = self.tbl_license_keys.horizontalHeader()
        hh2.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        cl.addWidget(self.tbl_license_keys)
        lay.addWidget(g_crm, 1)
        self.tabs.addTab(w, "🔑 Key-Verwaltung & Lizenzen")

    def _key_users_from_payload(self, users: list) -> None:
        if not hasattr(self, "list_key_users"):
            return
        self.list_key_users.clear()
        for u in users or []:
            if not isinstance(u, dict):
                continue
            hid = str(u.get("hardware_id") or "").strip()
            if not hid:
                continue
            username = str(u.get("username") or u.get("pilot_name") or u.get("email") or "Pilot").strip()
            email = str(u.get("email") or "").strip()
            status = str(u.get("license_status") or "").strip()
            if not status:
                status = "Aktiv" if int(u.get("has_license") or 0) == 1 else "Keine Lizenz"
            marker = "✅" if "aktiv" in status.lower() or int(u.get("has_license") or 0) == 1 else "⛔"
            label = f"{marker} {username}"
            if email and email.lower() not in username.lower():
                label += f" · {email}"
            label += f" · {status} · {hid[:12]}…"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, hid)
            it.setData(int(Qt.ItemDataRole.UserRole) + 1, username)
            it.setData(int(Qt.ItemDataRole.UserRole) + 2, str(u.get("license_key") or ""))
            self.list_key_users.addItem(it)

    def _key_refresh_users(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Key-Verwaltung",
                "IONOS-URL und Admin-Master-Passwort im CRM-Tab sind erforderlich.",
            )
            return
        try:
            r = requests.get(
                f"{base}/api/v1/admin/users/list",
                params={"admin_password": pw, "admin_master_password": pw},
                headers=_admin_token_headers(pw),
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            QMessageBox.critical(self, "Key-Verwaltung", str(exc))
            return
        self._key_users_from_payload(data.get("users") or [])

    def _key_user_selected(self, cur: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if cur is None:
            return
        hid = str(cur.data(Qt.ItemDataRole.UserRole) or "")
        username = str(cur.data(int(Qt.ItemDataRole.UserRole) + 1) or hid)
        existing_key = str(cur.data(int(Qt.ItemDataRole.UserRole) + 2) or "")
        self.ed_key_target_user.setText(username or hid)
        if existing_key and not self.ed_key_manual_license.text().strip():
            self.ed_key_manual_license.setText(existing_key)

    def _key_prefill_selected_user(self) -> None:
        hid = (getattr(self, "_crm_sel_hw", "") or "").strip()
        if not hid:
            QMessageBox.warning(
                self,
                "Key-Verwaltung",
                "Bitte zuerst im CRM-Tab einen User auswählen oder den Ziel-User manuell eintragen.",
            )
            return
        self.ed_key_target_user.setText(hid)

    def _key_copy_result(self) -> None:
        text = self.txt_key_result.toPlainText().strip()
        if text:
            QGuiApplication.clipboard().setText(text)

    def _crm_keys_refresh(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        if not base or not pw:
            QMessageBox.warning(self, "Keys", "IONOS-URL + Admin-Passwort fehlen.")
            return

        def _work() -> None:
            try:
                r = requests.post(
                    f"{base}/api/v1/admin/keys/list",
                    json=_admin_merge_json({}, pw),
                    headers=_admin_token_headers(pw),
                    timeout=45,
                )
                data = r.json() if r.content else {}
                keys = data.get("keys") or []
            except Exception as exc:
                keys = []
                err = str(exc)
            else:
                err = ""
            def _ui() -> None:
                if err:
                    QMessageBox.warning(self, "Keys", err)
                    return
                self.tbl_license_keys.setRowCount(0)
                for row in keys:
                    if not isinstance(row, dict):
                        continue
                    r = self.tbl_license_keys.rowCount()
                    self.tbl_license_keys.insertRow(r)
                    lk = str(row.get("license_key") or "")
                    self.tbl_license_keys.setItem(r, 0, QTableWidgetItem(lk))
                    self.tbl_license_keys.setItem(
                        r, 1, QTableWidgetItem(str(row.get("status") or ""))
                    )
                    self.tbl_license_keys.setItem(
                        r, 2, QTableWidgetItem(str(row.get("hardware_id") or ""))
                    )
                    self.tbl_license_keys.setItem(
                        r, 3, QTableWidgetItem(str(row.get("pilot_name") or ""))
                    )
                    self.tbl_license_keys.setItem(
                        r, 4, QTableWidgetItem(str(row.get("customer_email") or ""))
                    )
                    ts = float(row.get("created_ts") or 0)
                    self.tbl_license_keys.setItem(
                        r,
                        5,
                        QTableWidgetItem(
                            time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
                            if ts
                            else ""
                        ),
                    )

            QTimer.singleShot(0, _ui)

        QThreadPool.globalInstance().start(_FnVaultBackupRunnable(_work))

    def _crm_keys_license_at_row(self, row: int) -> str:
        it = self.tbl_license_keys.item(row, 0)
        return (it.text() if it else "").strip()

    def _crm_keys_context_menu(self, pos) -> None:
        row = self.tbl_license_keys.rowAt(pos.y())
        if row < 0:
            return
        lk = self._crm_keys_license_at_row(row)
        if not lk:
            return
        menu = QMenu(self)
        a_reset = menu.addAction("🔄 HWID zurücksetzen")
        a_lock = menu.addAction("🔒 Key permanent sperren")
        a_vip = menu.addAction("👑 VIP-Key generieren")
        act = menu.exec(self.tbl_license_keys.mapToGlobal(pos))
        if act == a_reset:
            self._crm_keys_action("/api/v1/admin/keys/hwid_reset", {"license_key": lk})
        elif act == a_lock:
            self._crm_keys_action("/api/v1/admin/keys/lock", {"license_key": lk})
        elif act == a_vip:
            self._crm_keys_action("/api/v1/admin/keys/vip_generate", {})

    def _crm_keys_action(self, path: str, payload: dict) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        if not base or not pw:
            return

        def _work() -> None:
            try:
                r = requests.post(
                    f"{base}{path}",
                    json=_admin_merge_json(payload, pw),
                    headers=_admin_token_headers(pw),
                    timeout=35,
                )
                data = r.json() if r.content else {}
                msg = json.dumps(data, ensure_ascii=False, indent=2)
            except Exception as exc:
                msg = str(exc)

            def _ui() -> None:
                self.txt_key_result.setPlainText(msg)
                self._crm_keys_refresh()

            QTimer.singleShot(0, _ui)

        QThreadPool.globalInstance().start(_FnVaultBackupRunnable(_work))

    def _key_generate_and_assign(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        target = self.ed_key_target_user.text().strip()
        license_type = str(self.combo_key_license_type.currentData() or "").strip()
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Key-Verwaltung",
                "IONOS-URL und Admin-Master-Passwort im CRM-Tab sind erforderlich.",
            )
            return
        if not target:
            QMessageBox.warning(self, "Key-Verwaltung", "Bitte Ziel-User / Pilot-ID eintragen.")
            return
        payload = _admin_merge_json(
            {
                "username": target,
                "pilot_id": target,
                "license_type": license_type,
            },
            pw,
        )
        try:
            r = requests.post(
                f"{base}/api/v1/admin/keys/generate",
                json=payload,
                headers=_admin_token_headers(pw),
                timeout=35,
            )
            if not r.ok:
                try:
                    detail = r.json().get("detail", r.text[:500])
                except Exception:
                    detail = r.text[:500] or f"HTTP {r.status_code}"
                QMessageBox.critical(
                    self,
                    "Key-Verwaltung",
                    f"Server hat abgelehnt: HTTP {r.status_code}\n{detail}",
                )
                return
            data = r.json()
        except Exception as exc:
            QMessageBox.critical(self, "Key-Verwaltung", str(exc))
            return
        key = str(data.get("generated_key") or data.get("license_key") or "")
        result = (
            f"Lizenzschlüssel: {key}\n"
            f"Status: {data.get('status', 'activated')}\n"
            f"Ziel: {data.get('target_user', target)}\n"
            f"Hardware-ID: {data.get('hardware_id', '')}\n"
            f"Lizenz-Typ: {data.get('license_type', license_type)}\n"
            f"Modul-Schalter: {data.get('module_key', '')}"
        )
        self.txt_key_result.setPlainText(result)
        QGuiApplication.clipboard().setText(key or result)
        QMessageBox.information(
            self,
            "Key-Verwaltung",
            "Lizenzschlüssel wurde generiert, zugewiesen und in die Zwischenablage kopiert.",
        )
        _log(f"Admin-Key generiert: {key} für {target} ({license_type})")
        if hasattr(self, "list_active_users") and self.list_active_users.currentItem() is not None:
            self._crm_user_selected(self.list_active_users.currentItem(), None)
        self._key_refresh_users()

    def _key_generate_unused_st(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Key-Verwaltung",
                "IONOS-URL und Admin-Master-Passwort im CRM-Tab sind erforderlich.",
            )
            return
        try:
            r = requests.post(
                f"{base}/api/v1/admin/keys/generate_unused",
                json=_admin_merge_json({}, pw),
                headers=_admin_token_headers(pw),
                timeout=35,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            QMessageBox.critical(self, "Key-Verwaltung", str(exc))
            return
        key = str(data.get("generated_key") or data.get("license_key") or "")
        note = ""
        if hasattr(self, "ed_key_unused_note"):
            note = self.ed_key_unused_note.text().strip()
        result = (
            f"Lizenzschlüssel (UNUSED): {key}\n"
            f"Status: {data.get('status', 'unused')}\n"
            + (f"Notiz: {note}\n" if note else "")
        )
        self.txt_key_result.setPlainText(result)
        QGuiApplication.clipboard().setText(key or result)
        QMessageBox.information(
            self,
            "Key-Verwaltung",
            f"ST-Key erzeugt:\n{key}",
        )
        _log(f"Admin UNUSED-Key: {key}")

    def _crm_obliterate_account(self) -> None:
        hid = self._crm_sel_hw
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        if not hid or not base or not pw:
            QMessageBox.warning(self, "CRM", "User, URL oder Admin-Passwort fehlt.")
            return
        if (
            QMessageBox.question(
                self,
                "CRM",
                "Konto unwiderruflich löschen? Alle Cloud-Daten und der Key werden zurückgesetzt.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        payload = _admin_merge_json(
            {"username": hid, "hardware_id": hid, "pilot_id": hid},
            pw,
        )
        try:
            r = requests.post(
                f"{base}/api/v1/admin/account/obliterate",
                json=payload,
                headers=_admin_token_headers(pw),
                timeout=45,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            QMessageBox.critical(self, "CRM", str(exc))
            return
        QMessageBox.information(
            self,
            "CRM",
            f"Konto gelöscht.\nE-Mail: {data.get('email', '—')}",
        )
        _log(f"CRM obliterate {hid}")
        self._crm_refresh_users()

    def _key_assign_direct(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        target = self.ed_key_target_user.text().strip()
        license_key = self.ed_key_manual_license.text().strip()
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Key-Verwaltung",
                "IONOS-URL und Admin-Master-Passwort im CRM-Tab sind erforderlich.",
            )
            return
        if not target or not license_key:
            QMessageBox.warning(
                self,
                "Key-Verwaltung",
                "Bitte Ziel-User und vorhandenen CRM-Key eintragen.",
            )
            return
        payload = _admin_merge_json(
            {"username": target, "pilot_id": target, "license_key": license_key},
            pw,
        )
        try:
            r = requests.post(
                f"{base}/api/v1/admin/keys/assign_direct",
                json=payload,
                headers=_admin_token_headers(pw),
                timeout=35,
            )
            if not r.ok:
                try:
                    detail = r.json().get("detail", r.text[:500])
                except Exception:
                    detail = r.text[:500] or f"HTTP {r.status_code}"
                QMessageBox.critical(
                    self,
                    "Key-Verwaltung",
                    f"Server hat abgelehnt: HTTP {r.status_code}\n{detail}",
                )
                return
            data = r.json()
        except Exception as exc:
            QMessageBox.critical(self, "Key-Verwaltung", str(exc))
            return
        result = (
            f"CRM-Key gebunden: {data.get('license_key', license_key)}\n"
            f"Status: {data.get('status', 'activated')}\n"
            f"Ziel: {data.get('target_user', target)}\n"
            f"Hardware-ID: {data.get('hardware_id', '')}"
        )
        self.txt_key_result.setPlainText(result)
        QGuiApplication.clipboard().setText(str(data.get("license_key") or license_key))
        QMessageBox.information(
            self,
            "Key-Verwaltung",
            "CRM-Key wurde dem User zugewiesen und der Account live freigeschaltet.",
        )
        _log(f"CRM-Key direkt gebunden: {license_key} für {target}")
        self._key_refresh_users()

    def _build_tab_promo_codes(self) -> None:
        self._crm_promo_last_codes: list[str] = []
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            QLabel(
                "Promo-Codes auf dem IONOS-Server anlegen (HTTPS). "
                "Admin-Master-Passwort wie im CRM-Tab."
            )
        )

        gb_price = QGroupBox("Globale Preiskontrolle (SkyTycoon Pro)")
        gl_price = QHBoxLayout(gb_price)
        self.spin_global_price = QDoubleSpinBox()
        self.spin_global_price.setRange(0.0, 199.99)
        self.spin_global_price.setSingleStep(0.5)
        self.spin_global_price.setDecimals(2)
        self.spin_global_price.setSuffix(" €")
        self.spin_global_price.setValue(19.99)
        gl_price.addWidget(self.spin_global_price)
        b_price = QPushButton("💰 Basispreis im Web-Shop aktualisieren")
        b_price.clicked.connect(self._crm_set_base_product_price)
        gl_price.addWidget(b_price)
        lay.addWidget(gb_price)

        gb_camp = QGroupBox("UTC-Kampagne (Banner auf skytycoon.info)")
        camp_form = QFormLayout(gb_camp)
        self.input_promo_name = QLineEdit()
        self.input_promo_name.setPlaceholderText("SUMMER26")
        self.spin_discount_percent = QSpinBox()
        self.spin_discount_percent.setRange(1, 100)
        self.spin_discount_percent.setValue(25)
        now = QDateTime.currentDateTime()
        self.date_valid_from = QDateTimeEdit(now)
        self.date_valid_from.setCalendarPopup(True)
        self.date_valid_from.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.date_valid_until = QDateTimeEdit(now.addSecs(86400))
        self.date_valid_until.setCalendarPopup(True)
        self.date_valid_until.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.spin_max_uses_global = QSpinBox()
        self.spin_max_uses_global.setRange(1, 10_000_000)
        self.spin_max_uses_global.setValue(100)
        camp_form.addRow("Kampagnen-Code:", self.input_promo_name)
        camp_form.addRow("Rabatt %:", self.spin_discount_percent)
        camp_form.addRow("Gültig ab (→ UTC):", self.date_valid_from)
        camp_form.addRow("Gültig bis (→ UTC):", self.date_valid_until)
        camp_form.addRow("Max. Nutzungen weltweit:", self.spin_max_uses_global)
        b_camp = QPushButton("🚀 UTC-Kampagne weltweit aktivieren")
        b_camp.clicked.connect(self._crm_campaign_activate)
        camp_form.addRow(b_camp)
        b_stop = QPushButton("🛑 Laufende Aktion sofort stoppen")
        b_stop.setStyleSheet(
            "QPushButton { background: #c62828; color: #ffffff; font-weight: 800; "
            "padding: 10px 14px; border: 2px solid #ff5252; border-radius: 4px; }"
            "QPushButton:hover { background: #b71c1c; }"
        )
        b_stop.clicked.connect(self._crm_campaign_stop)
        camp_form.addRow(b_stop)
        lay.addWidget(gb_camp)

        gb_simple = QGroupBox("🎟️ Rabattcodes erstellen")
        form = QFormLayout(gb_simple)
        self.input_promo_code = QLineEdit()
        self.input_promo_code.setPlaceholderText("INCENTIVE20 oder SPECIAL")
        self.spin_discount = QSpinBox()
        self.spin_discount.setRange(0, 100)
        self.spin_discount.setValue(100)
        self.spin_discount_eur = QDoubleSpinBox()
        self.spin_discount_eur.setRange(0.0, 500.0)
        self.spin_discount_eur.setDecimals(2)
        self.spin_discount_eur.setSingleStep(1.0)
        self.spin_discount_eur.setSuffix(" €")
        self.spin_max_uses = QSpinBox()
        self.spin_max_uses.setRange(1, 10_000_000)
        self.spin_max_uses.setValue(1000)
        form.addRow("Code-Name:", self.input_promo_code)
        form.addRow("Rabatt in Prozent:", self.spin_discount)
        form.addRow("Rabatt in Euro (optional):", self.spin_discount_eur)
        form.addRow("Max. Verwendungen (weltweit):", self.spin_max_uses)
        lay.addWidget(gb_simple)

        self.lbl_promo_list = QLabel("(Liste: „Vom Server laden“)")
        self.lbl_promo_list.setWordWrap(True)
        lay.addWidget(self.lbl_promo_list)
        b_create = QPushButton("[ 💾 Rabattcode live aktivieren ]")
        b_create.clicked.connect(self._crm_promo_create)
        lay.addWidget(b_create)
        b_list = QPushButton("Promo-Liste vom Server laden")
        b_list.clicked.connect(self._crm_promo_list)
        lay.addWidget(b_list)
        lay.addStretch()
        self.tabs.addTab(w, "🎟️ Gutschein- & Promo-Codes")
        self._promo_refresh_global_price_from_server()

    def _build_tab_email_marketing(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            QLabel(
                "📢 E-Mail- & Marketing-Zentrale · info@skytycoon.info (587 STARTTLS)\n"
                "E-Mail & Marketing Center · bilingual DE/EN"
            )
        )
        gold = (
            "QGroupBox { border: 2px solid #d4af37; color: #d4af37; margin-top: 14px; "
            "font-weight: 800; background: #0a0a0a; }"
        )
        w.setStyleSheet((w.styleSheet() or "") + gold)

        g_disc = QGroupBox("🎫 Rabattcode-Aktion / Discount campaign")
        fl = QFormLayout(g_disc)
        self.ed_mkt_promo = QLineEdit()
        self.ed_mkt_promo.setPlaceholderText("Gutscheincode")
        fl.addRow("Gutscheincode:", self.ed_mkt_promo)
        self.ed_mkt_discount_target = QLineEdit()
        self.ed_mkt_discount_target.setPlaceholderText("E-Mail oder ALL")
        fl.addRow("Ziel-E-Mail:", self.ed_mkt_discount_target)
        btn_disc = QPushButton("🎫 Rabattcode an Kunden senden")
        btn_disc.setStyleSheet(
            "background:#3d2e00;color:#ffd54f;font-weight:900;padding:12px;border:2px solid #d4af37;"
        )
        btn_disc.clicked.connect(self._mkt_send_discount)
        fl.addRow(btn_disc)
        lay.addWidget(g_disc)

        g_news = QGroupBox("📢 Update-Newsletter")
        fl2 = QFormLayout(g_news)
        self.ed_mkt_changelog_de = QTextEdit()
        self.ed_mkt_changelog_de.setMaximumHeight(90)
        fl2.addRow("Changelog DE:", self.ed_mkt_changelog_de)
        self.ed_mkt_changelog_en = QTextEdit()
        self.ed_mkt_changelog_en.setMaximumHeight(90)
        fl2.addRow("Changelog EN:", self.ed_mkt_changelog_en)
        btn_news = QPushButton("📢 Massen-Update-Newsletter abfeuern")
        btn_news.setStyleSheet(
            "background:#1a237e;color:#90caf9;font-weight:900;padding:12px;border:2px solid #d4af37;"
        )
        btn_news.clicked.connect(self._mkt_send_newsletter)
        fl2.addRow(btn_news)
        lay.addWidget(g_news)

        g_kill = QGroupBox("🛑 Gutschein-Kill / Voucher kill switch")
        fl3 = QFormLayout(g_kill)
        self.ed_mkt_kill_code = QLineEdit()
        self.ed_mkt_kill_code.setPlaceholderText("Code zum Stoppen")
        fl3.addRow("Code:", self.ed_mkt_kill_code)
        btn_kill = QPushButton(
            "🛑 Gutscheincode SOFORT stoppen & vernichten / Kill Voucher Code"
        )
        btn_kill.setStyleSheet(
            "background:#b71c1c;color:#fff;font-weight:900;padding:14px;border:2px solid #ff5252;"
        )
        btn_kill.clicked.connect(self._mkt_kill_voucher)
        fl3.addRow(btn_kill)
        lay.addWidget(g_kill)

        btn_export = QPushButton("📧 Alle User-E-Mails exportieren / Export all emails")
        btn_export.setObjectName("secondary")
        btn_export.clicked.connect(self._mkt_export_all_emails)
        lay.addWidget(btn_export)

        g_live = QGroupBox("📰 Live News / Patch Notes")
        fln = QFormLayout(g_live)
        self.ed_global_news_publish = QTextEdit()
        self.ed_global_news_publish.setMaximumHeight(100)
        self.ed_global_news_publish.setPlaceholderText("Patch Notes / News (DE oder EN — KI übersetzt automatisch)")
        fln.addRow("News:", self.ed_global_news_publish)
        btn_pub = QPushButton("📢 News global veröffentlichen / Publish news globally")
        btn_pub.setStyleSheet(
            "background:#1b5e20;color:#a5d6a7;font-weight:900;padding:12px;border:2px solid #d4af37;"
        )
        btn_pub.clicked.connect(self._mkt_publish_global_news)
        fln.addRow(btn_pub)
        lay.addWidget(g_live)

        self.txt_mkt_result = QTextEdit()
        self.txt_mkt_result.setReadOnly(True)
        self.txt_mkt_result.setMaximumHeight(100)
        lay.addWidget(self.txt_mkt_result)
        lay.addStretch()
        self.tabs.addTab(w, "📢 E-Mail- & Marketing-Zentrale")

    def _mkt_api_post_async(self, path: str, payload: dict, *, export_mode: bool = False) -> bool:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        if not base or not pw:
            QMessageBox.warning(self, "Marketing", "CRM: IONOS-URL + Admin-Passwort fehlen.")
            return False
        self._mkt_pending_export = export_mode
        self.txt_mkt_result.setPlainText(
            "⏳ IONOS-Anfrage läuft asynchron (SFTP blockiert HTTP nicht)…"
        )
        QThreadPool.globalInstance().start(
            _MarketingApiPostRunnable(base, path, payload, pw, self._mkt_sig)
        )
        return True

    def _mkt_on_api_ok(self, data: dict) -> None:
        if getattr(self, "_support_pending_reload", False):
            self._support_pending_reload = False
            self.txt_mkt_result.setPlainText(
                json.dumps(data, ensure_ascii=False, indent=2)
            )
            QMessageBox.information(
                self,
                "Support",
                data.get("message") or "Ticket-Antwort gesendet (RESOLVED + i18n-Mail).",
            )
            return
        if self._mkt_pending_export:
            self._mkt_pending_export = False
            emails = data.get("emails") or []
            path = BASE_DIR / "exported_user_emails.json"
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            plain = BASE_DIR / "exported_user_emails.txt"
            plain.write_text("\n".join(str(e) for e in emails), encoding="utf-8")
            self.txt_mkt_result.setPlainText(
                f"Exportiert: {len(emails)} E-Mails\n"
                f"JSON: {path}\nTXT: {plain}\n\n"
                + "\n".join(str(e) for e in emails[:80])
                + ("\n…" if len(emails) > 80 else "")
            )
            _log(f"E-Mail-Export {len(emails)} → {path}")
            QMessageBox.information(
                self,
                "Export",
                f"{len(emails)} E-Mails nach\n{path}\nund\n{plain}",
            )
            return
        self.txt_mkt_result.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        status = str(data.get("status") or "")
        if status == "queued":
            QMessageBox.information(
                self,
                "Marketing",
                data.get("message") or "Kampagne gestartet (E-Mail-Versand im Hintergrund).",
            )
        elif data.get("pg_status") == "EXPIRED" or data.get("ok"):
            QMessageBox.information(
                self,
                "Kill",
                data.get("message") or "Gutschein gestoppt.",
            )

    def _mkt_on_api_err(self, msg: str) -> None:
        self._mkt_pending_export = False
        self.txt_mkt_result.setPlainText(msg)
        QMessageBox.warning(self, "Marketing", msg)

    def _mkt_send_discount(self) -> None:
        code = self.ed_mkt_promo.text().strip()
        target = self.ed_mkt_discount_target.text().strip() or "ALL"
        if not code:
            QMessageBox.warning(self, "Marketing", "Gutscheincode fehlt.")
            return
        if self._mkt_api_post_async(
            "/api/v1/admin/marketing/discount",
            {"promo_code": code, "target_email": target},
        ):
            _log(f"Rabatt-Mail queued (async) {code} → {target}")

    def _mkt_publish_global_news(self) -> None:
        raw = self.ed_global_news_publish.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, "News", "Patch Notes / News eingeben.")
            return
        if self._mkt_api_post_async(
            "/api/v1/admin/news/publish",
            {"message": raw, "send_email": True},
        ):
            _log("Global news publish queued")

    def _mkt_send_newsletter(self) -> None:
        ch_de = self.ed_mkt_changelog_de.toPlainText().strip()
        ch_en = self.ed_mkt_changelog_en.toPlainText().strip()
        if not ch_de and not ch_en:
            QMessageBox.warning(self, "Marketing", "Changelog DE oder EN ausfüllen.")
            return
        if self._mkt_api_post_async(
            "/api/v1/admin/marketing/newsletter",
            {"changelog_de": ch_de, "changelog_en": ch_en},
        ):
            _log("Newsletter queued (async)")

    def _mkt_kill_voucher(self) -> None:
        code = self.ed_mkt_kill_code.text().strip().upper()
        if not code:
            QMessageBox.warning(self, "Kill", "Bitte Gutscheincode eintragen.")
            return
        if (
            QMessageBox.question(
                self,
                "Kill",
                f"Code {code} wirklich auf EXPIRED setzen und von der Website entfernen?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if self._mkt_api_post_async(
            "/api/v1/admin/marketing/discount/kill",
            {"code": code, "promo_code": code},
        ):
            _log(f"Voucher KILL async {code}")

    def _mkt_export_all_emails(self) -> None:
        self._mkt_api_post_async(
            "/api/v1/admin/users/export_emails",
            {},
            export_mode=True,
        )

    def _promo_refresh_global_price_from_server(self) -> None:
        base = self._ionos_base_url()
        if not base:
            return
        try:
            r = requests.get(f"{base}/api/v1/public/base_price", timeout=15)
            r.raise_for_status()
            p = float(r.json().get("price", 19.99))
            self.spin_global_price.setValue(min(199.99, max(0.0, p)))
        except Exception:
            self.spin_global_price.setValue(19.99)

    def _crm_set_base_product_price(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        if not base or not pw:
            QMessageBox.warning(self, "Preis", "URL und Admin-Passwort erforderlich.")
            return
        try:
            r = requests.post(
                f"{base}/api/v1/admin/config/set_price",
                json=_admin_merge_json({"new_price": float(self.spin_global_price.value())}, pw),
                headers=_admin_token_headers(pw),
                timeout=25,
            )
            r.raise_for_status()
        except Exception as exc:
            QMessageBox.critical(self, "Preis", str(exc))
            return
        QMessageBox.information(
            self,
            "Preis",
            "Basispreis erfolgreich geändert! Der Web-Shop verlangt ab sofort den neuen Betrag.",
        )
        self._promo_refresh_global_price_from_server()

    def _crm_campaign_activate(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        code = self.input_promo_name.text().strip()
        if not base or not pw:
            QMessageBox.warning(self, "Kampagne", "URL und Admin-Passwort erforderlich.")
            return
        if len(code) < 3:
            QMessageBox.warning(self, "Kampagne", "Bitte Kampagnen-Code (mind. 3 Zeichen).")
            return
        vf = self.date_valid_from.dateTime().toUTC().toString(Qt.DateFormat.ISODate)
        vu = self.date_valid_until.dateTime().toUTC().toString(Qt.DateFormat.ISODate)
        body = _admin_merge_json(
            {
                "code": code.upper(),
                "discount_percent": int(self.spin_discount_percent.value()),
                "valid_from": vf,
                "valid_until": vu,
                "max_uses": int(self.spin_max_uses_global.value()),
            },
            pw,
        )
        try:
            r = requests.post(
                f"{base}/api/v1/admin/promo/create",
                json=body,
                headers=_admin_token_headers(pw),
                timeout=25,
            )
            r.raise_for_status()
        except Exception as exc:
            QMessageBox.critical(self, "Kampagne", str(exc))
            return
        QMessageBox.information(
            self,
            "Kampagne",
            "Kampagne erfolgreich gestartet! Der Werbebanner leuchtet ab jetzt live auf der Webseite skytycoon.info.",
        )
        self._crm_promo_list()

    def _crm_campaign_stop(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        code = self._crm_resolve_campaign_stop_code()
        if not base or not pw:
            QMessageBox.warning(self, "Kampagne", "URL und Admin-Passwort erforderlich.")
            return
        if len(code) < 3:
            QMessageBox.warning(
                self,
                "Kampagne",
                "Bitte Kampagnen-Code eingeben oder zuerst „Promo-Liste vom Server laden“.",
            )
            return
        body = _admin_merge_json({"code": code}, pw)
        try:
            r = requests.post(
                f"{base}/api/v1/admin/promo/stop",
                json=body,
                headers=_admin_token_headers(pw),
                timeout=30,
            )
            if not r.ok:
                try:
                    err = r.json()
                    detail = err.get("detail", err)
                    if isinstance(detail, list) and detail:
                        detail = detail[0].get("msg", str(detail))
                    msg = str(detail) if detail else r.text[:400]
                except Exception:
                    msg = r.text[:400] or f"HTTP {r.status_code}"
                QMessageBox.critical(self, "Kampagne", msg)
                return
        except Exception as exc:
            QMessageBox.critical(self, "Kampagne", str(exc))
            return
        QMessageBox.information(
            self,
            "Kampagne",
            "Kampagne vorzeitig beendet! Der Werbebanner wurde von skytycoon.info entfernt "
            "und der Code deaktiviert.",
        )
        self._crm_promo_list()

    def _crm_promo_list(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        if not base:
            QMessageBox.warning(self, "Promo", "Keine API-Basis-URL.")
            return
        try:
            r = requests.get(
                f"{base}/api/v1/admin/promo/list",
                params={
                    "admin_master_password": pw,
                    "admin_password": pw,
                },
                headers=_admin_token_headers(pw),
                timeout=25,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            QMessageBox.critical(self, "Promo", str(exc))
            return
        rows = data.get("promos") or []
        self._crm_promo_last_codes = [
            str(p.get("code") or "").strip()
            for p in rows
            if isinstance(p, dict) and len(str(p.get("code") or "").strip()) >= 2
        ]
        lines = []
        for p in rows:
            v0 = str(p.get("valid_from") or "")[:19]
            v1 = str(p.get("valid_until") or "")[:19]
            extra = f" | {v0} → {v1}" if (v0.strip() or v1.strip()) else ""
            lines.append(
                f"{p.get('code')} — {p.get('discount_percent')}% / "
                f"{float(p.get('discount_eur') or 0):.2f}€ — "
                f"{p.get('uses')}/{p.get('max_uses')}{extra}"
            )
        self.lbl_promo_list.setText("\n".join(lines) if lines else "(keine Einträge)")

    def _crm_resolve_campaign_stop_code(self) -> str:
        """Kampagnen-Code: Eingabefeld, sonst einfacher Gutschein, sonst letzte Server-Liste."""
        raw = (self.input_promo_name.text() or "").strip().upper()
        if len(raw) >= 3:
            return raw
        alt = (self.input_promo_code.text() or "").strip().upper()
        if len(alt) >= 3:
            return alt
        for c in getattr(self, "_crm_promo_last_codes", ()) or ():
            c2 = (c or "").strip().upper()
            if len(c2) >= 3:
                return c2
        return ""

    def _crm_promo_create(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        code = self.input_promo_code.text().strip()
        if not base or not pw:
            QMessageBox.warning(self, "Promo", "URL und Admin-Passwort erforderlich.")
            return
        if not code:
            QMessageBox.warning(self, "Promo", "Bitte einen Gutschein-Code eingeben.")
            return
        body = _admin_merge_json(
            {
                "code": code,
                "discount_percent": int(self.spin_discount.value()),
                "discount_eur": float(self.spin_discount_eur.value()),
                "max_uses": int(self.spin_max_uses.value()),
            },
            pw,
        )
        try:
            r = requests.post(
                f"{base}/api/v1/admin/promo/upsert",
                json=body,
                headers=_admin_token_headers(pw),
                timeout=25,
            )
            r.raise_for_status()
            j = r.json()
        except Exception as exc:
            QMessageBox.critical(self, "Promo", str(exc))
            return
        QMessageBox.information(
            self,
            "Promo",
            f"Gespeichert: {j.get('code')} · {j.get('discount_percent')}% / "
            f"{float(j.get('discount_eur') or 0):.2f}€ · max. {j.get('max_uses')} Nutzungen",
        )
        self._crm_promo_list()

    def _crm_on_users_list_json(self, data: dict) -> None:
        self.list_active_users.clear()
        for u in data.get("users") or []:
            hid = str(u.get("hardware_id", ""))
            if not hid:
                continue
            pilot = str(u.get("pilot_name") or "").strip()
            status = str(u.get("license_status") or "").strip()
            suffix = f" · {status}" if status else ""
            label = f"{pilot} ({hid}){suffix}" if pilot else f"Pilot ({hid}){suffix}"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, hid)
            self.list_active_users.addItem(it)
        self._key_users_from_payload(data.get("users") or [])
        _log(f"CRM user list geladen ({self.list_active_users.count()})")

    def _crm_on_users_list_err(self, msg: str) -> None:
        QMessageBox.critical(self, "CRM", msg)

    def _crm_users_context_menu(self, pos) -> None:
        item = self.list_active_users.itemAt(pos)
        if item is None:
            item = self.list_active_users.currentItem()
        if item is None:
            return
        hid = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not hid:
            return
        menu = QMenu(self)
        act_del = menu.addAction("🪓 User permanent löschen & wegbannen")
        chosen = menu.exec(self.list_active_users.mapToGlobal(pos))
        if chosen is act_del:
            self._crm_delete_user_confirmed(item, hid)

    def _crm_delete_user_confirmed(self, item: QListWidgetItem, hid: str) -> None:
        pilot = (item.text() or "").split("(")[0].strip() or hid[:16]
        msg_de = (
            f"Benutzer „{pilot}“ ({hid}) unwiderruflich löschen?\n\n"
            "PostgreSQL-Kaskade, Lizenz-Freigabe und Discord-Bann werden ausgeführt."
        )
        msg_en = (
            f"Permanently delete user “{pilot}” ({hid})?\n\n"
            "PostgreSQL cascade, license release and Discord ban will run."
        )
        lg = app_meta_get(self._db_path, "ui_lang", "de").strip().lower()[:2]
        msg = msg_en if lg == "en" else msg_de
        title = "Delete user permanently" if lg == "en" else "Benutzer endgültig löschen"
        if (
            QMessageBox.question(
                self,
                title,
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        if not base or not pw:
            QMessageBox.warning(self, "CRM", "IONOS-URL oder Admin-Passwort fehlt.")
            return
        self._crm_pending_delete_item = item
        self._crm_pending_delete_hid = hid
        QThreadPool.globalInstance().start(
            _AdminUserDeleteRunnable(
                base,
                hid,
                pw,
                self._crm_delete_sig,
            )
        )

    def _crm_on_user_delete_ok(self, data: dict) -> None:
        item = getattr(self, "_crm_pending_delete_item", None)
        hid = getattr(self, "_crm_pending_delete_hid", "")
        row = self.list_active_users.row(item) if item is not None else -1
        if item is not None:
            self.list_active_users.takeItem(row)
        _log(f"CRM user deleted: {hid[:24]!r} → {data.get('status', 'ok')}")
        lg = app_meta_get(self._db_path, "ui_lang", "de").strip().lower()[:2]
        ok_msg = (
            "User removed from database. Discord ban queued."
            if lg == "en"
            else "Benutzer aus der Datenbank entfernt. Discord-Bann wurde angestoßen."
        )
        QMessageBox.information(self, "CRM", ok_msg)
        self._crm_pending_delete_item = None
        self._crm_pending_delete_hid = ""

    def _crm_on_user_delete_err(self, msg: str) -> None:
        self._crm_pending_delete_item = None
        self._crm_pending_delete_hid = ""
        QMessageBox.critical(self, "CRM", msg)

    def load_active_users(self) -> None:
        """CRM-Liste direkt nach Start (und manuell nutzbar)."""
        self._crm_refresh_users()

    def _crm_refresh_users(self) -> None:
        base = self._ionos_base_url()
        if not base:
            QMessageBox.warning(self, "CRM", "Keine API-Basis-URL.")
            return
        pw = self.ed_admin_master.text().strip()
        if not pw:
            QMessageBox.warning(self, "CRM", "Admin-Master-Passwort fehlt.")
            return
        url = f"{base}/api/v1/admin/users/list"
        QThreadPool.globalInstance().start(
            _AdminUsersListPostRunnable(url, pw, self._crm_list_sig)
        )

    def trigger_global_credentials_resend(self) -> None:
        """Massen-Mail: Lizenzschlüssel an alle registrierten Nutzer (Server-API)."""
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        if not base or not pw:
            QMessageBox.warning(
                self,
                "Massen-Mail",
                "IONOS-URL und Admin-Master-Passwort (CRM-Tab) erforderlich.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Massen-Mail",
            "Möchten Sie den automatischen E-Mail-Versand an ALLE registrierten "
            "Nutzer jetzt starten?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        url = f"{base}/api/v1/admin/users/resend_all_credentials"
        payload = _admin_merge_json({}, pw)
        headers = _admin_token_headers(pw)
        try:
            r = requests.post(
                url, json=payload, headers=headers, timeout=300
            )
            if r.status_code == 200:
                j = r.json()
                msg = str(
                    j.get("message")
                    or f"{j.get('sent_count', '?')} E-Mails versendet."
                )
                sent = j.get("sent_count")
                total = j.get("total_targets")
                if sent is not None and total is not None:
                    msg = (
                        f"{msg}\n\nErfolgreich: {sent} von {total} "
                        f"(fehlgeschlagen: {j.get('failed_count', 0)})."
                    )
                QMessageBox.information(self, "Erfolg", msg)
                _log(f"Massen-Mail Zugangsdaten: {sent}/{total}")
            else:
                detail = r.text[:400] if r.text else ""
                QMessageBox.critical(
                    self,
                    "Fehler",
                    f"Server-Sperre: HTTP {r.status_code}\n{detail}",
                )
        except Exception as exc:
            QMessageBox.critical(self, "Fehler", str(exc))

    def _admin_fetch_server_log(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        if not base or not pw:
            QMessageBox.warning(
                self, "Server-Log", "IONOS-URL und Admin-Passwort erforderlich."
            )
            return
        try:
            q = urlencode(
                {
                    "admin_password": pw,
                    "admin_master_password": pw,
                    "lines": "250",
                }
            )
            r = requests.get(
                f"{base}/api/v1/admin/server/log?{q}",
                headers=_admin_token_headers(pw),
                timeout=30,
            )
            r.raise_for_status()
            j = r.json()
            lines = j.get("lines") or []
            text = "\n".join(str(x) for x in lines)[-12000:]
            dlg = QMessageBox(self)
            dlg.setWindowTitle("IONOS server.log (Tail)")
            dlg.setText(text or "(leer)")
            dlg.setDetailedText(str(j.get("path", "")))
            dlg.exec()
            _log(f"Server-Log geladen ({len(lines)} Zeilen)")
        except Exception as exc:
            QMessageBox.critical(self, "Server-Log", str(exc))

    def _admin_fetch_crash_reports(self) -> None:
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        if not base or not pw:
            QMessageBox.warning(
                self, "Crash-Reports", "IONOS-URL und Admin-Passwort erforderlich."
            )
            return
        try:
            q = urlencode(
                {
                    "admin_password": pw,
                    "admin_master_password": pw,
                    "lines": "120",
                }
            )
            r = requests.get(
                f"{base}/api/v1/admin/reports/crash/tail?{q}",
                headers=_admin_token_headers(pw),
                timeout=30,
            )
            r.raise_for_status()
            j = r.json()
            lines = j.get("lines") or []
            text = "\n".join(str(x) for x in lines)[-12000:]
            QMessageBox.information(
                self,
                "Crash-Reports (Server)",
                text or "Keine Crash-Einträge auf dem Server.",
            )
            _log(f"Crash-Tail geladen ({len(lines)} Zeilen)")
        except Exception as exc:
            QMessageBox.critical(self, "Crash-Reports", str(exc))

    def _crm_user_selected(self, cur: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if cur is None:
            return
        hid = str(cur.data(Qt.ItemDataRole.UserRole) or "")
        self._crm_sel_hw = hid or None
        self.lbl_crm_hwid.setText(hid if hid else "—")
        if hid and hasattr(self, "ed_key_target_user"):
            self.ed_key_target_user.setText(hid)
        base = self._ionos_base_url()
        if not base or not hid:
            return
        try:
            r = requests.get(f"{base}/api/v1/admin/users/detail/{hid}", timeout=25)
            r.raise_for_status()
            d = r.json()
        except Exception as exc:
            QMessageBox.warning(self, "CRM", str(exc))
            return
        self.lbl_crm_credits.setText(f"{float(d.get('credits', 0)):.0f}")
        self.lbl_crm_xp.setText(f"{float(d.get('xp', 0)):.0f}")
        self.lbl_crm_rep.setText(f"{float(d.get('reputation', 0)):.1f}")
        self.lbl_crm_loan.setText(f"{float(d.get('loan_debt', 0)):.0f}")
        self.lbl_crm_strikes.setText(str(int(d.get("strikes", 0))))
        self.lbl_crm_planes.setText(
            json.dumps(d.get("planes"), ensure_ascii=False)[:200]
        )
        ts = float(d.get("last_cloud_backup_ts") or 0)
        self.lbl_crm_backup.setText(
            time.strftime("%d.%m.%Y %H:%M", time.localtime(ts)) if ts > 0 else "—"
        )
        lic = str(d.get("license_key") or "").strip()
        lact = int(d.get("license_activated") or 0)
        if lic and lact:
            self.lbl_crm_license.setText(lic)
        else:
            self.lbl_crm_license.setText("— (nicht aktiviert)")

    def _crm_post_modify(self, field: str, value: object) -> None:
        hid = self._crm_sel_hw
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        if not hid or not base or not pw:
            QMessageBox.warning(self, "CRM", "User, URL oder Admin-Passwort fehlt.")
            return
        body = _admin_merge_json(
            {"field": field, "value": value},
            pw,
        )
        try:
            r = requests.post(
                f"{base}/api/v1/admin/users/modify/{hid}",
                json=body,
                headers=_admin_token_headers(pw),
                timeout=30,
            )
            r.raise_for_status()
        except Exception as exc:
            QMessageBox.critical(self, "CRM", str(exc))
            return
        _log(f"CRM modify {field} für {hid}")
        QMessageBox.information(self, "CRM", "Server hat übernommen.")
        self._crm_user_selected(self.list_active_users.currentItem(), None)

    def _crm_apply_credits(self) -> None:
        try:
            v = float(self.ed_crm_credits_delta.text().replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "CRM", "Ungültiger Betrag.")
            return
        self._crm_post_modify("credits_mod", v)

    def _crm_apply_xp(self) -> None:
        try:
            v = float(self.ed_crm_xp_delta.text().replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "CRM", "Ungültiger XP-Wert.")
            return
        self._crm_post_modify("xp_mod", v)

    def _crm_apply_loan(self) -> None:
        try:
            v = float(self.ed_crm_loan.text().replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "CRM", "Ungültiger Schuldenwert.")
            return
        self._crm_post_modify("loan_debt_set", v)

    def _crm_reset_strikes(self) -> None:
        self._crm_post_modify("strikes_reset", True)

    def _crm_ban_user(self) -> None:
        if QMessageBox.question(
            self,
            "CRM",
            "Nutzer wirklich global sperren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._crm_post_modify("ban_set", True)

    def _crm_reset_user_password(self) -> None:
        hid = self._crm_sel_hw
        base = self._ionos_base_url()
        pw = self._admin_master_pw()
        new_pw = self.ed_crm_reset_pw.text().strip()
        if not hid or not base or not pw:
            QMessageBox.warning(self, "CRM", "User, URL oder Admin-Passwort fehlt.")
            return
        if len(new_pw) < 4:
            QMessageBox.warning(self, "CRM", "Passwort mindestens 4 Zeichen.")
            return
        if (
            QMessageBox.question(
                self,
                "CRM",
                "Cloud-Passwort wirklich überschreiben?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            r = requests.post(
                f"{base}/api/v1/admin/users/reset_password",
                json=_admin_merge_json(
                    {
                        "hardware_id": hid,
                        "new_clear_password": new_pw,
                    },
                    pw,
                ),
                headers={
                    "Content-Type": "application/json",
                    **_admin_token_headers(pw),
                },
                timeout=20,
            )
            if r.status_code != 200:
                QMessageBox.critical(self, "CRM", r.text[:500])
                return
            j = r.json()
            if not j.get("ok"):
                QMessageBox.critical(self, "CRM", str(j.get("error", j)))
                return
        except Exception as exc:
            QMessageBox.critical(self, "CRM", str(exc))
            return
        self.ed_crm_reset_pw.clear()
        _log(f"CRM Passwort-Reset für {hid}")
        QMessageBox.information(self, "CRM", "Passwort serverseitig gehasht und gesetzt.")

    def _fetch_server_log_live(self) -> None:
        base = self._ionos_base_url()
        pw = self._admin_master_pw()
        if not base or not pw:
            QMessageBox.warning(self, "Log", "IONOS-URL oder Admin-Passwort fehlt.")
            return
        try:
            r = requests.post(
                f"{base}/api/v1/admin/logs/stream",
                json=_admin_merge_json({"lines": 120}, pw),
                headers={
                    "Content-Type": "application/json",
                    **_admin_token_headers(pw),
                },
                timeout=20,
            )
            if r.status_code != 200:
                QMessageBox.critical(self, "Log", f"Server: HTTP {r.status_code}")
                return
            j = r.json()
            logs = str(j.get("logs", "") or "(leer)")
            self.txt_log.setPlainText(f"=== IONOS Server ({base}) ===\n{logs}")
        except Exception as exc:
            QMessageBox.critical(self, "Log", str(exc))

    def _crm_download_backup(self) -> None:
        hid = self._crm_sel_hw
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip()
        if not hid or not base or not pw:
            QMessageBox.warning(self, "CRM", "User, URL oder Admin-Passwort fehlt.")
            return
        try:
            r = requests.get(
                f"{base}/api/v1/admin/users/backup/download/{hid}",
                params={
                    "admin_master_password": pw,
                    "admin_password": pw,
                },
                headers=_admin_token_headers(pw),
                timeout=120,
            )
            r.raise_for_status()
        except Exception as exc:
            QMessageBox.critical(self, "CRM", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Backup speichern", f"{hid}_career_backup.db", "SQLite (*.db)"
        )
        if path:
            Path(path).write_bytes(r.content)
            _log(f"CRM Cloud-Backup gespeichert: {path}")
            QMessageBox.information(self, "CRM", "Datei gespeichert.")

    def _build_tab_god(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lic = QGroupBox("Lizenz-Management (Staging)")
        lf = QFormLayout(lic)
        hw = ""
        if self._db_path.is_file():
            hw = app_meta_get(self._db_path, "econ_device_tag", "") or "(leer)"
        self.lbl_hw = QLabel(hw or "—")
        self.lbl_hw.setWordWrap(True)
        _label_selectable(self.lbl_hw)
        row_hw_god = QHBoxLayout()
        row_hw_god.addWidget(self.lbl_hw, stretch=1)
        self.btn_god_copy_hw = QPushButton("📋")
        self.btn_god_copy_hw.setObjectName("secondary")
        self.btn_god_copy_hw.setFixedWidth(44)
        self.btn_god_copy_hw.setToolTip("In Zwischenablage kopieren")
        self.btn_god_copy_hw.clicked.connect(self._god_copy_hw_clicked)
        row_hw_god.addWidget(self.btn_god_copy_hw)
        wrap_hw_god = QWidget()
        wrap_hw_god.setLayout(row_hw_god)
        lf.addRow("Hardware-ID (app_meta):", wrap_hw_god)
        self.ed_lic_override = QLineEdit()
        self.ed_lic_override.setPlaceholderText("Aktiviert | Testmodus | Gesperrt")
        lf.addRow("Lizenz-Status (Support):", self.ed_lic_override)
        b_lic = QPushButton("Lizenz-Status schreiben")
        b_lic.setObjectName("secondary")
        b_lic.clicked.connect(self._god_license)
        lf.addRow(b_lic)
        lay.addWidget(lic)

        fin = QGroupBox("Finanz / Rating")
        ff = QFormLayout(fin)
        self.sp_credits = QDoubleSpinBox()
        self.sp_credits.setRange(0, 2_000_000_000)
        self.sp_credits.setDecimals(0)
        self.sp_credits.setSingleStep(10_000)
        self.sp_credits.setValue(6_000_000)
        self.sp_xp = QSpinBox()
        self.sp_xp.setRange(0, 50_000_000)
        ff.addRow("Credits setzen:", self.sp_credits)
        ff.addRow("XP setzen:", self.sp_xp)
        bf = QPushButton("Credits & XP anwenden (pilot_stats)")
        bf.clicked.connect(self._god_finance)
        ff.addRow(bf)
        self.slider_rating = QSlider(Qt.Orientation.Horizontal)
        self.slider_rating.setRange(0, 5000)
        self.slider_rating.setValue(3500)
        ff.addRow("Airline-Rating (0–5 Sterne intern 0–5000):", self.slider_rating)
        br = QPushButton("Rating speichern (app_meta airline_rating_stars)")
        br.clicked.connect(self._god_rating)
        ff.addRow(br)
        lay.addWidget(fin)

        hang = QGroupBox("Hangar / Anti-Cheat")
        hf = QVBoxLayout(hang)
        bh = QPushButton("Hangar: alle Bauteile auf 100 %")
        bh.clicked.connect(self._god_hangar_fix)
        hf.addWidget(bh)
        ba = QPushButton("Anti-Cheat: Strikes & Bann-Flags zurücksetzen")
        ba.setObjectName("secondary")
        ba.clicked.connect(self._god_acs_reset)
        hf.addWidget(ba)
        lay.addWidget(hang)

        tp = QGroupBox("Teleport (persistenter Stand)")
        tf = QFormLayout(tp)
        self.cb_icao = QComboBox()
        self.cb_icao.addItems(sorted(AIRPORT_COORDS.keys()))
        tf.addRow("Flughafen:", self.cb_icao)
        bt = QPushButton("Standort in DB schreiben")
        bt.clicked.connect(self._god_teleport)
        tf.addRow(bt)
        lay.addWidget(tp)
        lay.addStretch()
        self.tabs.addTab(w, "Gott-Modus")

    def _god_license(self) -> None:
        if not self._db_path.is_file():
            QMessageBox.warning(self, "Lizenz", "DB fehlt.")
            return
        v = self.ed_lic_override.text().strip()
        app_meta_set(self._db_path, "license_status_override", v)
        _log(f"license override={v}")
        QMessageBox.information(self, "Lizenz", "Gespeichert.")

    def _god_finance(self) -> None:
        if not self._db_path.is_file():
            return
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "UPDATE pilot_stats SET credits = ?, xp = ? WHERE id = 1;",
                (float(self.sp_credits.value()), float(self.sp_xp.value())),
            )
            conn.commit()
        finally:
            conn.close()
        _log(f"finance set credits={self.sp_credits.value()} xp={self.sp_xp.value()}")
        QMessageBox.information(self, "Finanz", "pilot_stats aktualisiert.")

    def _god_rating(self) -> None:
        if not self._db_path.is_file():
            return
        stars = self.slider_rating.value() / 1000.0
        app_meta_set(self._db_path, "airline_rating_stars", f"{stars:.4f}")
        _log(f"rating set {stars}")
        QMessageBox.information(self, "Rating", f"airline_rating_stars = {stars:.2f}")

    def _god_hangar_fix(self) -> None:
        if not self._db_path.is_file():
            return
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "UPDATE aircraft_parts SET condition_pct = 100.0, block_until = 0.0, used_part = 0;"
            )
            conn.commit()
        finally:
            conn.close()
        _log("hangar instant fix all parts 100%")
        QMessageBox.information(self, "Hangar", "aircraft_parts auf 100 %.")

    def _god_acs_reset(self) -> None:
        if not self._db_path.is_file():
            return
        for k, v in (
            ("acs_strike_count", "0"),
            ("cheater_detected", "0"),
            ("pilot_profile_banned", "0"),
            ("pilot_ban_reason", ""),
            ("pilot_ban_at_unix", "0"),
            ("pilot_banned_name_snapshot", ""),
        ):
            app_meta_set(self._db_path, k, v)
        _log("acs reset")
        QMessageBox.information(self, "ACS", "Strikes/Bann-Meta zurückgesetzt.")

    def _god_teleport(self) -> None:
        if not self._db_path.is_file():
            return
        icao = self.cb_icao.currentText().strip().upper()
        lat, lon = AIRPORT_COORDS.get(icao, (50.0379, 8.5622))
        app_meta_set(self._db_path, META_STAND_ICAO, icao)
        app_meta_set(self._db_path, META_STAND_LAT, f"{lat:.8f}")
        app_meta_set(self._db_path, META_STAND_LON, f"{lon:.8f}")
        app_meta_set(self._db_path, META_STAND_TS, str(time.time()))
        _log(f"teleport {icao}")
        QMessageBox.information(self, "Teleport", f"Standort → {icao}")

    def _play_admin_support_chime(self) -> None:
        wav = (BASE_DIR / "assets" / "sounds" / "admin_chime.wav").resolve()
        try:
            from PySide6.QtMultimedia import QSoundEffect

            if not hasattr(self, "_admin_chime_fx"):
                self._admin_chime_fx = QSoundEffect(self)
            self._admin_chime_fx.setSource(QUrl.fromLocalFile(str(wav)))
            if wav.is_file():
                self._admin_chime_fx.play()
                return
        except Exception:
            pass
        try:
            if sys.platform == "win32":
                import winsound

                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    def _build_tab_exe_release(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("Neue App-Versionsnummer:"))
        self.input_app_version_build = QLineEdit(
            self._settings.value("exe_rel_version", "1.0.0", str)
        )
        row.addWidget(self.input_app_version_build, stretch=1)
        lay.addLayout(row)
        self.text_build_output = QTextEdit()
        self.text_build_output.setReadOnly(True)
        self.text_build_output.setFont(QFont("Consolas", 11))
        self.text_build_output.setStyleSheet(
            "QTextEdit { background-color: #000000; color: #00ff41; }"
        )
        lay.addWidget(self.text_build_output, stretch=1)
        self.btn_build_upload = QPushButton(
            "[⚙️ All-In-One EXE kompilieren & hochladen]"
        )
        self.btn_build_upload.setStyleSheet(
            "QPushButton { background-color: #c9a227; color: #1a1a1a; font-weight: 800; "
            "padding: 14px; border-radius: 8px; }"
            "QPushButton:hover { background-color: #e6c34d; }"
            "QPushButton:disabled { background-color: #5c5c5c; color: #9e9e9e; }"
        )
        self.btn_build_upload.clicked.connect(self._on_exe_build_clicked)
        lay.addWidget(self.btn_build_upload)
        self._exe_build_worker: BuildWorker | None = None
        self.tabs.addTab(w, "📦 EXE-Release & Build")

    def _append_build_line(self, s: str) -> None:
        self.text_build_output.append(s)

    def _on_exe_build_clicked(self) -> None:
        if self._exe_build_worker and self._exe_build_worker.isRunning():
            QMessageBox.information(self, "Build", "Ein Build läuft bereits.")
            return
        self.text_build_output.clear()
        ver = self.input_app_version_build.text().strip() or "1.0.0"
        self._settings.setValue("exe_rel_version", ver)
        self.btn_build_upload.setEnabled(False)
        self._exe_build_worker = BuildWorker(BASE_DIR, ver)
        self._exe_build_worker.line_out.connect(self._append_build_line)
        self._exe_build_worker.finished_ok.connect(self._on_exe_build_finished_ok)
        self._exe_build_worker.finished_err.connect(self._on_exe_build_finished_err)
        self._exe_build_worker.start()

    def _on_exe_build_finished_ok(self, msg: str) -> None:
        self.btn_build_upload.setEnabled(True)
        _log(f"build ok {msg}")
        QMessageBox.information(self, "Build / Upload", f"Abgeschlossen.\n{msg}")

    def _on_exe_build_finished_err(self, msg: str) -> None:
        self.btn_build_upload.setEnabled(True)
        _log(f"build err {msg}")
        QMessageBox.warning(self, "Build", msg)

    def _build_tab_support(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            QLabel(
                "Support-Zentrale (IONOS): POST /api/v1/admin/support/tickets, /messages, /reply "
                "(Admin-Passwort und X-Admin-Token wie CRM)."
            )
        )
        split = QSplitter()
        self.list_tickets = QListWidget()
        self.list_tickets.setMinimumWidth(220)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.chat_view = QTextBrowser()
        self.chat_view.setReadOnly(True)
        rl.addWidget(self.chat_view, 1)
        row = QHBoxLayout()
        self.admin_reply = QLineEdit()
        btn_reply = QPushButton("✉️ Antworten")
        btn_hwid_reset = QPushButton(
            "🔓 HWID-Slots steril nullen & Ticket schließen"
        )
        btn_hwid_reset.setStyleSheet(
            "QPushButton { background:#1565c0; color:#fff; font-weight:800; padding:10px; }"
        )
        row.addWidget(self.admin_reply, 1)
        row.addWidget(btn_reply)
        rl.addLayout(row)
        rl.addWidget(btn_hwid_reset)
        split.addWidget(self.list_tickets)
        split.addWidget(right)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self._support_sel_hid: str | None = None
        self._support_sel_ticket_id: int = 0
        self._support_sel_email: str = ""
        self._support_seen_msg: set[str] = set()
        self._support_boot = True

        hdr_json = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "SkyTycoonPro-AdminCommander/1",
        }

        def refresh_tickets() -> None:
            base = self._ionos_base_url()
            pw = self._admin_master_pw()
            if not base or not pw:
                return
            try:
                r = requests.post(
                    f"{base}/api/v1/admin/support/tickets",
                    json=_admin_merge_json({}, pw),
                    headers={**hdr_json, **_admin_token_headers(pw)},
                    timeout=14,
                )
                if r.status_code >= 400:
                    return
                payload = r.json()
            except Exception:
                return
            tickets = payload.get("tickets") if isinstance(payload, dict) else []
            if not isinstance(tickets, list):
                return
            open_c = 0
            for head0 in tickets:
                if not isinstance(head0, dict):
                    continue
                if str(head0.get("status", "")).lower() == "open":
                    open_c += 1
            if self._last_support_open_count >= 0 and open_c > self._last_support_open_count:
                self._play_admin_support_chime()
            self._last_support_open_count = open_c
            cur = self.list_tickets.currentItem()
            cur_txt = cur.text() if cur else ""
            self.list_tickets.blockSignals(True)
            self.list_tickets.clear()
            for head in tickets:
                if not isinstance(head, dict):
                    continue
                st = str(head.get("status", "")).lower()
                if st not in ("open", "pending", "replied"):
                    continue
                hid = str(head.get("hardware_id") or "")
                if not hid:
                    continue
                tid = int(head.get("id") or 0)
                pilot = str(head.get("pilot_name", "?"))[:40]
                uem = str(head.get("user_email") or "")[:80]
                bell = "🔔 " if st == "open" else ""
                lab = f"{bell}#{tid} {pilot} · {st.upper()}"
                it = QListWidgetItem(lab)
                it.setData(
                    Qt.ItemDataRole.UserRole,
                    {"hid": hid, "ticket_id": tid, "email": uem},
                )
                self.list_tickets.addItem(it)
            self.list_tickets.blockSignals(False)
            if cur_txt:
                for i in range(self.list_tickets.count()):
                    if self.list_tickets.item(i).text() == cur_txt:
                        self.list_tickets.setCurrentRow(i)
                        break

        def load_chat() -> None:
            it = self.list_tickets.currentItem()
            if it is None:
                self.chat_view.clear()
                self._support_sel_hid = None
                return
            raw = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(raw, dict):
                self._support_sel_hid = str(raw.get("hid") or "")
                self._support_sel_ticket_id = int(raw.get("ticket_id") or 0)
                self._support_sel_email = str(raw.get("email") or "")
            else:
                self._support_sel_hid = str(raw or "")
                self._support_sel_ticket_id = 0
                self._support_sel_email = ""
            self._support_seen_msg.clear()
            self._support_boot = True
            base = self._ionos_base_url()
            pw = self._admin_master_pw()
            if not base or not pw:
                return
            try:
                r = requests.post(
                    f"{base}/api/v1/admin/support/messages",
                    json=_admin_merge_json({"hardware_id": hid}, pw),
                    headers={**hdr_json, **_admin_token_headers(pw)},
                    timeout=14,
                )
                dct = r.json() if r.status_code < 400 else {}
            except Exception:
                dct = {}
            msgs = dct.get("messages") if isinstance(dct, dict) else []
            lines: list[str] = []
            if isinstance(msgs, list):
                for v in msgs:
                    if not isinstance(v, dict):
                        continue
                    sender = str(v.get("sender", ""))
                    mtxt = str(v.get("message_text", ""))
                    who = "Admin" if sender == "admin" else "User"
                    lines.append(f"<b>{who}</b>: {mtxt}")
            self.chat_view.setHtml("<br/>".join(lines) if lines else "(leer)")

        def poll_chat() -> None:
            hid = self._support_sel_hid
            if not hid:
                return
            base = self._ionos_base_url()
            pw = self._admin_master_pw()
            if not base or not pw:
                return
            try:
                r = requests.post(
                    f"{base}/api/v1/admin/support/messages",
                    json=_admin_merge_json({"hardware_id": hid}, pw),
                    headers={**hdr_json, **_admin_token_headers(pw)},
                    timeout=12,
                )
                data = r.json() if r.status_code < 400 else {}
            except Exception:
                return
            msgs = data.get("messages") if isinstance(data, dict) else []
            if not isinstance(msgs, list):
                return
            if self._support_boot:
                for v in msgs:
                    if isinstance(v, dict):
                        self._support_seen_msg.add(str(v.get("id", "")))
                self._support_boot = False
                return
            for v in msgs:
                if not isinstance(v, dict):
                    continue
                ks = str(v.get("id", ""))
                if not ks or ks in self._support_seen_msg:
                    continue
                self._support_seen_msg.add(ks)
                sender = str(v.get("sender", ""))
                mtxt = str(v.get("message_text", ""))
                who = "Admin" if sender == "admin" else "User"
                self.chat_view.append(f"<b>{who}</b>: {mtxt}")

        def send_hwid_reset() -> None:
            hid = self._support_sel_hid
            if not hid:
                QMessageBox.information(
                    self, "Support", "Bitte zuerst ein Ticket auswählen."
                )
                return
            txt = self.admin_reply.text().strip()
            if not txt:
                txt = (
                    "HWID slots reset. / Ihre HWID-Slots wurden zurückgesetzt."
                )
            base = self._ionos_base_url()
            pw = self._admin_master_pw()
            if not base or not pw:
                return
            ticket_id = int(getattr(self, "_support_sel_ticket_id", 0) or 0)
            email = str(getattr(self, "_support_sel_email", "") or "")

            class _HwidResetRun(QRunnable):
                def __init__(self, outer: Any) -> None:
                    super().__init__()
                    self.outer = outer

                def run(self) -> None:
                    try:
                        requests.post(
                            f"{base}/api/v1/admin/user/reset_hwid",
                            json=_admin_merge_json(
                                {
                                    "ticket_id": ticket_id,
                                    "hardware_id": hid,
                                    "user_email": email,
                                    "admin_response": txt[:8000],
                                },
                                pw,
                            ),
                            headers={
                                **hdr_json,
                                **_admin_token_headers(pw),
                            },
                            timeout=25,
                        )
                    except Exception as exc:
                        print(f"[Admin] HWID reset: {exc!s}", flush=True)

            QThreadPool.globalInstance().start(_HwidResetRun(self))
            QMessageBox.information(
                self,
                "Support",
                "HWID-Reset & Ticket-Abschluss an Server gesendet.",
            )
            refresh_tickets()

        def send_admin() -> None:
            hid = self._support_sel_hid
            txt = self.admin_reply.text().strip()
            if not hid or not txt:
                return
            self.admin_reply.clear()
            self._support_pending_reload = True
            self._mkt_api_post_async(
                "/api/v1/admin/support/ticket/reply",
                {
                    "hardware_id": hid,
                    "message_text": txt[:4000],
                    "resolve": True,
                },
            )

        self.list_tickets.currentItemChanged.connect(lambda _a, _b: load_chat())
        btn_reply.clicked.connect(send_admin)
        btn_hwid_reset.clicked.connect(send_hwid_reset)
        t1 = QTimer(self)
        t1.setInterval(8000)
        t1.timeout.connect(refresh_tickets)
        t1.start()
        t2 = QTimer(self)
        t2.setInterval(5000)
        t2.timeout.connect(poll_chat)
        t2.start()
        refresh_tickets()
        self.tabs.addTab(w, "Support")

    def _vault_lang(self) -> str:
        return str(getattr(self, "_vault_cfg", {}).get("lang", "de"))

    def _vault_log(self, msg: str) -> None:
        if not hasattr(self, "txt_vault_log"):
            return
        ts = time.strftime("%H:%M:%S")
        self.txt_vault_log.append(f"[{ts}] {msg}")

    def _vault_refresh_disk_ui(self) -> None:
        drive = self.combo_vault_drive.currentData() or "C:\\"
        total, _used, free, pct = disk_usage_for_drive(str(drive))
        lang = self._vault_lang()
        self.lbl_vault_disk_line1.setText(
            vault_t(
                "drive.line1",
                lang,
                drive=drive,
                total=fmt_gb(total) if total else "—",
            )
        )
        self.lbl_vault_disk_line2.setText(
            vault_t("drive.line2", lang, free=fmt_gb(free) if free else "—")
        )
        self.prog_vault_disk.setRange(0, 100)
        self.prog_vault_disk.setValue(int(pct))
        root = vault_root_for_drive(str(drive))
        self.lbl_vault_path.setText(str(root))
        ensure_vault_tree(root)
        self._vault_sftp.set_root(root)

    def _vault_on_drive_changed(self, _ix: int) -> None:
        drive = self.combo_vault_drive.currentData() or "C:\\"
        self._vault_cfg["drive"] = str(drive)
        save_vault_config(self._vault_cfg)
        self._vault_refresh_disk_ui()

    def _vault_on_lang_changed(self, _ix: int) -> None:
        self._vault_cfg["lang"] = self.combo_vault_lang.currentData() or "de"
        save_vault_config(self._vault_cfg)
        ix = self.tabs.indexOf(getattr(self, "_vault_tab_widget", None))
        if ix >= 0:
            self.tabs.setTabText(ix, vault_t("tab.title", self._vault_lang()))

    def _vault_start_sftp(self) -> None:
        if self._sftp_worker is not None and self._sftp_worker.isRunning():
            return
        self.lbl_vault_sftp.setText(
            vault_t("sftp.off", self._vault_lang()) + " — startet…"
        )
        self._sftp_worker = _AsynchronousSftpWorker(
            self._vault_sftp,
            action="start",
            password=ADMIN_MASTER_PASSWORD,
        )
        self._sftp_worker.started_ok.connect(self._vault_on_sftp_started)
        self._sftp_worker.failed.connect(self._vault_on_sftp_failed)
        self._sftp_worker.start()

    def _vault_on_sftp_started(self) -> None:
        self.lbl_vault_sftp.setText(vault_t("sftp.on", self._vault_lang(), port=2222))
        self._vault_log("SFTP gestartet auf Port 2222 (isolierter QThread)")

    def _vault_on_sftp_failed(self, err: str) -> None:
        self.lbl_vault_sftp.setText(
            f"{vault_t('sftp.off', self._vault_lang())} — {err}"
        )
        self._vault_log(f"SFTP Fehler: {err}")

    def _vault_stop_sftp(self) -> None:
        if self._sftp_worker is not None and self._sftp_worker.isRunning():
            self._sftp_worker.requestInterruption()
        worker = _AsynchronousSftpWorker(self._vault_sftp, action="stop")
        worker.stopped.connect(self._vault_on_sftp_stopped)
        worker.start()
        self._sftp_stop_worker = worker

    def _vault_on_sftp_stopped(self) -> None:
        self.lbl_vault_sftp.setText(vault_t("sftp.off", self._vault_lang()))
        self._vault_log("SFTP gestoppt")

    def _vault_run_prune(self) -> None:
        drive = self.combo_vault_drive.currentData() or "C:\\"
        root = vault_root_for_drive(str(drive))
        stats = prune_local_vault(root, cap_mb=CAP_MB_DEFAULT)
        self._vault_log(f"Retention: {stats}")
        self._vault_refresh_disk_ui()

    def _vault_run_project_backup(self) -> None:
        drive = self.combo_vault_drive.currentData() or "C:\\"
        root = vault_root_for_drive(str(drive))

        def _work() -> None:
            dest = create_project_backup_zip(root, BASE_DIR)
            self._vault_backup_sig.done.emit(str(dest) if dest else "")

        self._vault_log("Projekt-Backup läuft …")
        QThreadPool.globalInstance().start(_FnVaultBackupRunnable(_work))

    def _vault_run_swiss_sync_async(self) -> None:
        th = getattr(self, "_swiss_thread", None)
        if th is not None and th.isRunning():
            return
        lang = self._vault_lang()
        self._vault_log(vault_t("swiss.label", lang))
        self._swiss_thread = _SwissSyncThread()
        self._swiss_thread.result.connect(self._vault_on_swiss_done)
        self._swiss_thread.start()

    def _vault_on_swiss_done(self, ok: bool, msg: str) -> None:
        lang = self._vault_lang()
        if ok:
            ts = zurich_now().strftime("%H:%M:%S")
            self._vault_log(vault_t("swiss.log_ok", lang, ts=ts))
            self._vault_log(vault_t("swiss.ok", lang, path=msg))
        elif msg == "no_drive":
            self._vault_log(vault_t("swiss.no_drive", lang))
        else:
            self._vault_log(vault_t("swiss.fail", lang, e=msg))
        nxt = zurich_now().strftime("%Y-%m-%d %H:%M")
        if hasattr(self, "lbl_vault_swiss_next"):
            self.lbl_vault_swiss_next.setText(vault_t("swiss.next", lang, ts=nxt))
        self._vault_refresh_disk_ui()

    def _vault_on_backup_done(self, path: str) -> None:
        if path:
            self._vault_log(f"Projekt-Zip: {path}")
        else:
            self._vault_log("Projekt-Backup fehlgeschlagen")
        stats = prune_local_vault(
            vault_root_for_drive(str(self.combo_vault_drive.currentData() or "C:\\")),
            cap_mb=CAP_MB_DEFAULT,
        )
        self._vault_log(f"Retention nach Backup: {stats}")
        self._vault_refresh_disk_ui()

    def _build_tab_platin_vault(self) -> None:
        self._vault_cfg = load_vault_config()
        lang0 = self._vault_cfg.get("lang", "de")
        self._vault_sftp = VaultSFTPServer()
        self._vault_tab_widget = QWidget()
        w = self._vault_tab_widget
        w.setStyleSheet(
            "QWidget { background:#050508; color:#e8d9a0; }"
            "QGroupBox { border:2px solid #d4af37; margin-top:14px; color:#d4af37; font-weight:900; }"
            "QComboBox, QLabel, QTextEdit { color:#f5e6b8; }"
            "QProgressBar { border:1px solid #d4af37; height:22px; text-align:center; color:#fff; }"
            "QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8b6914, stop:1 #ffd54f); }"
            "QPushButton { background:#1a1208; color:#ffd54f; border:2px solid #d4af37; font-weight:800; padding:10px; }"
            "QPushButton:hover { background:#2a2210; }"
        )
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.combo_vault_lang = QComboBox()
        self.combo_vault_lang.addItem("Deutsch", "de")
        self.combo_vault_lang.addItem("English", "en")
        lix = 0 if lang0 != "en" else 1
        self.combo_vault_lang.setCurrentIndex(lix)
        self.combo_vault_lang.currentIndexChanged.connect(self._vault_on_lang_changed)
        top.addWidget(QLabel(vault_t("lang", lang0)))
        top.addWidget(self.combo_vault_lang)
        top.addStretch()
        lay.addLayout(top)

        g_drive = QGroupBox(vault_t("tab.title", lang0))
        fl = QFormLayout(g_drive)
        self.combo_vault_drive = QComboBox()
        drives_labeled = list_drives_with_labels()
        drives = [d for d, _ in drives_labeled] or list_windows_drives()
        saved = str(self._vault_cfg.get("drive", drives[0]))
        for d, lbl in drives_labeled or [(x, "") for x in drives]:
            text = f"{d}  ({lbl})" if lbl else d
            self.combo_vault_drive.addItem(text, d)
        idx = max(0, self.combo_vault_drive.findData(saved))
        self.combo_vault_drive.setCurrentIndex(idx)
        self.combo_vault_drive.currentIndexChanged.connect(self._vault_on_drive_changed)
        fl.addRow(vault_t("drive.label", lang0), self.combo_vault_drive)
        self.lbl_vault_disk_line1 = QLabel("—")
        self.lbl_vault_disk_line2 = QLabel("—")
        self.prog_vault_disk = QProgressBar()
        fl.addRow(self.lbl_vault_disk_line1)
        fl.addRow(self.prog_vault_disk)
        fl.addRow(self.lbl_vault_disk_line2)
        self.lbl_vault_path = QLabel("—")
        self.lbl_vault_path.setWordWrap(True)
        fl.addRow(vault_t("vault.path", lang0), self.lbl_vault_path)
        lay.addWidget(g_drive)

        g_sftp = QGroupBox(vault_t("sftp.status", lang0, port=2222))
        sl = QVBoxLayout(g_sftp)
        self.lbl_vault_sftp = QLabel(vault_t("sftp.off", lang0))
        sl.addWidget(self.lbl_vault_sftp)
        row = QHBoxLayout()
        b_start = QPushButton(vault_t("btn.sftp_start", lang0))
        b_start.clicked.connect(self._vault_start_sftp)
        b_stop = QPushButton(vault_t("btn.sftp_stop", lang0))
        b_stop.clicked.connect(self._vault_stop_sftp)
        row.addWidget(b_start)
        row.addWidget(b_stop)
        sl.addLayout(row)
        lay.addWidget(g_sftp)

        g_swiss = QGroupBox(vault_t("swiss.label", lang0))
        sw_l = QVBoxLayout(g_swiss)
        self.lbl_vault_swiss_next = QLabel(
            vault_t("swiss.next", lang0, ts=zurich_now().strftime("%Y-%m-%d %H:%M"))
        )
        sw_l.addWidget(self.lbl_vault_swiss_next)
        btn_swiss = QPushButton(
            "🇨🇭 "
            + ("Swiss-Sync jetzt" if lang0 == "de" else "Swiss sync now")
        )
        btn_swiss.clicked.connect(self._vault_run_swiss_sync_async)
        sw_l.addWidget(btn_swiss)
        lay.addWidget(g_swiss)

        hint = QLabel(
            vault_t("retention.hint", lang0, cap=int(CAP_MB_DEFAULT))
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)
        row2 = QHBoxLayout()
        b_prune = QPushButton(vault_t("btn.prune", lang0))
        b_prune.clicked.connect(self._vault_run_prune)
        b_proj = QPushButton(vault_t("btn.project", lang0))
        b_proj.clicked.connect(self._vault_run_project_backup)
        row2.addWidget(b_prune)
        row2.addWidget(b_proj)
        lay.addLayout(row2)

        self.txt_vault_log = QTextEdit()
        self.txt_vault_log.setReadOnly(True)
        self.txt_vault_log.setMinimumHeight(160)
        self.txt_vault_log.setMaximumHeight(220)
        self.txt_vault_log.setStyleSheet("background:#0b0b12;color:#90caf9;")
        lay.addWidget(QLabel(vault_t("log.title", lang0)))
        lay.addWidget(self.txt_vault_log)

        class _VaultBackupSig(QObject):
            done = Signal(str)

        self._vault_backup_sig = _VaultBackupSig()
        self._vault_backup_sig.done.connect(self._vault_on_backup_done)

        self.tabs.addTab(w, vault_t("tab.title", lang0))
        self._vault_refresh_disk_ui()
        QTimer.singleShot(1500, self._vault_start_sftp)

        self._vault_hourly = QTimer(self)
        self._vault_hourly.setInterval(3_600_000)
        self._vault_hourly.timeout.connect(self._vault_hourly_tick)
        self._vault_hourly.start()

        self._swiss_timer = QTimer(self)
        self._swiss_timer.setInterval(SWISS_SYNC_INTERVAL_MS)
        self._swiss_timer.timeout.connect(self._vault_run_swiss_sync_async)
        self._swiss_timer.start()
        swiss_drive = find_drive_by_volume_label()
        if swiss_drive:
            ix = self.combo_vault_drive.findData(swiss_drive)
            if ix >= 0:
                self.combo_vault_drive.setCurrentIndex(ix)
        QTimer.singleShot(12_000, self._vault_run_swiss_sync_async)

    def _vault_hourly_tick(self) -> None:
        self._vault_run_project_backup()
        self._vault_run_prune()

    def _build_tab_payout(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            QLabel("🎛️ CO-FOUNDER REVENUE SHARE / INSTANT PAYOUT CONSOLE")
        )
        lay.addWidget(QLabel("📧 Empfänger PayPal E-Mail / Recipient Email:"))
        self.ed_payout_email = QLineEdit()
        self.ed_payout_email.setPlaceholderText(
            "Empfänger-PayPal-Adresse (frei wählbar)…"
        )
        lay.addWidget(self.ed_payout_email)
        lay.addWidget(QLabel("💰 Auszahlungsbetrag (EUR):"))
        self.sp_payout_amount = QDoubleSpinBox()
        self.sp_payout_amount.setRange(0.01, 10000.0)
        self.sp_payout_amount.setDecimals(2)
        self.sp_payout_amount.setValue(50.0)
        lay.addWidget(self.sp_payout_amount)
        self.btn_payout_fire = QPushButton(
            "💸 Gewinn-Split jetzt via PayPal Payouts senden!"
        )
        self.btn_payout_fire.clicked.connect(self._trigger_nuclear_payout)
        lay.addWidget(self.btn_payout_fire)
        self.lbl_payout_status = QLabel("Bereit.")
        self.lbl_payout_status.setWordWrap(True)
        lay.addWidget(self.lbl_payout_status)
        lay.addStretch()
        self.tabs.addTab(w, "💸 PayPal Payout")

    def _trigger_nuclear_payout(self) -> None:
        target_email = self.ed_payout_email.text().strip()
        payout_value = float(self.sp_payout_amount.value())
        if not target_email or "@" not in target_email:
            self.lbl_payout_status.setText("❌ Ungültige E-Mail-Adresse.")
            return
        base = self._ionos_base_url()
        pw = self.ed_admin_master.text().strip() if hasattr(self, "ed_admin_master") else ""
        if not base or not pw:
            QMessageBox.warning(
                self, "Payout", "IONOS-URL + Admin-Master-Passwort erforderlich."
            )
            return
        self.btn_payout_fire.setEnabled(False)
        self.lbl_payout_status.setText("⚡ Blitz-Auszahlung wird abgefeuert…")
        QThreadPool.globalInstance().start(
            _AdminPayoutRunnable(base, pw, target_email, payout_value, self._payout_sig)
        )

    def _on_payout_ok(self, data: dict) -> None:
        self.btn_payout_fire.setEnabled(True)
        batch = str(data.get("paypal_batch_id") or data.get("sender_batch_id") or "")
        self.lbl_payout_status.setText(
            f"✅ Payout OK — Batch: {batch or '—'}"
        )
        QMessageBox.information(
            self,
            "PayPal Payout",
            f"Auszahlung angestoßen.\nBatch-ID: {batch or '—'}",
        )

    def _on_payout_err(self, msg: str) -> None:
        self.btn_payout_fire.setEnabled(True)
        self.lbl_payout_status.setText(f"❌ Payout fehlgeschlagen: {msg[:240]}")
        QMessageBox.warning(self, "PayPal Payout", msg[:1200])

    def _build_tab_log(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("Protokoll (lokal + IONOS-Server)"))
        b_local = QPushButton("Lokal laden")
        b_local.setObjectName("secondary")
        b_local.clicked.connect(self._refresh_log_tail)
        row.addWidget(b_local)
        b_srv = QPushButton("🔄 Live Server-Log (IONOS)")
        b_srv.clicked.connect(self._fetch_server_log_live)
        row.addWidget(b_srv)
        row.addStretch()
        lay.addLayout(row)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 10))
        self.txt_log.setStyleSheet("background-color:#0b0b0b;color:#00ff00;")
        lay.addWidget(self.txt_log)
        self.tabs.addTab(w, "Log")

    def _refresh_log_tail(self) -> None:
        if not ADMIN_LOG.is_file():
            self.txt_log.setPlainText("(noch kein Log)")
            return
        try:
            lines = ADMIN_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        self.txt_log.setPlainText("\n".join(lines[-50:]))


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = AdminCommanderWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
