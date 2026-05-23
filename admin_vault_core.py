# -*- coding: utf-8 -*-
"""Platin-Sicherheits-Tresor: lokale SSD, SFTP-Empfang (Port 2222), Retention, Projekt-Zips."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import stat
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[misc, assignment]

try:
    import paramiko
except ImportError:  # pragma: no cover
    paramiko = None  # type: ignore[assignment]

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

APP_ROOT = Path(__file__).resolve().parent
VAULT_CONFIG_PATH = APP_ROOT / "admin_vault_config.json"
HOST_KEY_PATH = APP_ROOT / "admin_vault_host_key"
VAULT_SUBDIRS = ("datenbank_dumps", "rechnungen_invoices", "git_repositories")
PROJECT_ROOT_DEFAULT = Path(
    os.environ.get("SKYTYCOON_PROJECT_ROOT") or r"A:\SkyTycoon"
).resolve()
SWISS_BACKUP_ROOT = Path(
    os.environ.get("SKYTYCOON_SWISS_BACKUP_ROOT") or r"A:\SkyTycoon_Backups"
).resolve()
SFTP_PORT = int(os.environ.get("SKYTYCOON_PC_VAULT_PORT") or "2222")
SFTP_USER = (os.environ.get("SKYTYCOON_PC_VAULT_USER") or "skytycoon").strip()
SFTP_PASSWORD = (
    os.environ.get("SKYTYCOON_PC_VAULT_PASSWORD")
    or os.environ.get("SKYTYCOON_ADMIN_MASTER_PASSWORD")
    or "e85OieJLPMV6Nuv"
).strip()
CAP_MB_DEFAULT = float(os.environ.get("SKYTYCOON_PC_VAULT_CAP_MB") or "500")

VAULT_I18N: dict[str, dict[str, str]] = {
    "tab.title": {"de": "🗄️ Platin-Sicherheits-Tresor", "en": "🗄️ Platinum Security Vault"},
    "lang": {"de": "Sprache", "en": "Language"},
    "drive.label": {
        "de": "💾 Ziel-Festplatte auswählen:",
        "en": "💾 Select target hard drive:",
    },
    "drive.line1": {
        "de": "💾 Laufwerk {drive} | Gesamt: {total}",
        "en": "💾 Drive {drive} | Total: {total}",
    },
    "drive.line2": {
        "de": "🟢 Frei: {free} verfügbar",
        "en": "🟢 Free: {free} available",
    },
    "vault.path": {"de": "Tresor-Pfad:", "en": "Vault path:"},
    "sftp.status": {"de": "SFTP-Server (Port {port}):", "en": "SFTP server (port {port}):"},
    "sftp.on": {"de": "🟢 Aktiv — IONOS kann andocken", "en": "🟢 Active — IONOS can connect"},
    "sftp.off": {"de": "🔴 Gestoppt", "en": "🔴 Stopped"},
    "btn.sftp_start": {"de": "SFTP starten", "en": "Start SFTP"},
    "btn.sftp_stop": {"de": "SFTP stoppen", "en": "Stop SFTP"},
    "btn.prune": {"de": "Speicherbremse jetzt", "en": "Run retention now"},
    "btn.project": {"de": "Projekt-Backup jetzt", "en": "Project backup now"},
    "retention.hint": {
        "de": "Stündliche Dumps/Zips: 7 Tage + Wochen-Archiv, max. {cap} MB auf Dumps/Zips. PDF-Rechnungen werden NIEMALS gelöscht.",
        "en": "Hourly dumps/zips: 7 days + weekly archive, max. {cap} MB on dumps/zips. Invoice PDFs are NEVER deleted.",
    },
    "log.title": {"de": "Aktivitätsprotokoll", "en": "Activity log"},
    "swiss.label": {
        "de": "🇨🇭 Swiss 2h-Sync → Festplatte „SkyTycoon Backup (A)“",
        "en": "🇨🇭 Swiss 2h sync → drive “SkyTycoon Backup (A)”",
    },
    "swiss.next": {"de": "Nächster Lauf (Zürich): {ts}", "en": "Next run (Zurich): {ts}"},
    "swiss.ok": {"de": "Swiss-Sync OK: {path}", "en": "Swiss sync OK: {path}"},
    "swiss.fail": {"de": "Swiss-Sync fehlgeschlagen: {e}", "en": "Swiss sync failed: {e}"},
    "swiss.no_drive": {
        "de": "Festplatte mit Label „SkyTycoon Backup (A)“ nicht gefunden.",
        "en": 'Drive labeled "SkyTycoon Backup (A)" not found.',
    },
    "swiss.log_ok": {
        "de": "🟢 [{ts}] Backup erfolgreich auf 'SkyTycoon Backup (A)' gesichert.",
        "en": "🟢 [{ts}] Backup successfully secured to 'SkyTycoon Backup (A)'.",
    },
}

ZIP_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".cursor",
        "__pycache__",
        "node_modules",
        "venv",
        "dist",
        "build",
        "backups",
    }
)

SWISS_VOLUME_LABEL = (
    os.environ.get("SKYTYCOON_SWISS_VOLUME_LABEL") or "SkyTycoon Backup (A)"
).strip()
SWISS_SYNC_INTERVAL_MS = int(
    os.environ.get("SKYTYCOON_SWISS_SYNC_INTERVAL_MS") or str(2 * 3600 * 1000)
)


def t(key: str, lang: str, **fmt: Any) -> str:
    lang = "en" if str(lang).lower().startswith("en") else "de"
    raw = VAULT_I18N.get(key, {}).get(lang) or key
    if fmt:
        try:
            return raw.format(**fmt)
        except (KeyError, ValueError):
            return raw
    return raw


def fmt_gb(n: int) -> str:
    return f"{n / (1024 ** 3):.1f} GB"


def _windows_volume_label(mount: str) -> str:
    if sys.platform != "win32":
        return ""
    letter = (mount or "").strip()
    if len(letter) >= 2 and letter[1] == ":":
        root = letter[0].upper() + ":\\"
    elif letter.endswith("\\"):
        root = letter
    else:
        return ""
    try:
        import ctypes

        vol = ctypes.create_unicode_buffer(256)
        ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            root,
            vol,
            256,
            None,
            None,
            None,
            None,
            0,
        )
        return (vol.value or "").strip()
    except Exception:
        return ""


def list_drives_with_labels() -> list[tuple[str, str]]:
    if psutil is None:
        return [("C:\\", "")]
    out: list[tuple[str, str]] = []
    for part in psutil.disk_partitions(all=False):
        opts = (part.opts or "").lower()
        if "cdrom" in opts:
            continue
        mp = (part.mountpoint or "").strip()
        if len(mp) < 2 or mp[1] != ":":
            continue
        letter = mp[0].upper() + ":\\"
        if any(d == letter for d, _ in out):
            continue
        out.append((letter, _windows_volume_label(letter)))
    return out or [("C:\\", "")]


def find_drive_by_volume_label(label: str | None = None) -> str | None:
    target = (label or SWISS_VOLUME_LABEL).strip().lower()
    if not target:
        return None
    for letter, vol in list_drives_with_labels():
        if vol.strip().lower() == target:
            return letter
    return None


def zurich_now() -> datetime:
    """Schweizer Zeit — ohne tzdata-Paket (Windows: lokale Uhr)."""
    try:
        if ZoneInfo is not None:
            return datetime.now(ZoneInfo("Europe/Zurich"))
    except Exception:
        pass
    return datetime.now()


def list_windows_drives() -> list[str]:
    if psutil is None:
        return ["C:\\"]
    out: list[str] = []
    for part in psutil.disk_partitions(all=False):
        opts = (part.opts or "").lower()
        if "cdrom" in opts:
            continue
        mp = (part.mountpoint or "").strip()
        if len(mp) >= 2 and mp[1] == ":":
            letter = mp[0].upper() + ":\\"
            if letter not in out:
                out.append(letter)
    return sorted(out) or ["C:\\"]


def vault_root_for_drive(drive: str) -> Path:
    d = (drive or "A:\\").strip()
    if len(d) == 2 and d[1] == ":":
        d = d[0].upper() + ":\\"
    elif not d.endswith("\\"):
        d = d.rstrip("/") + "\\"
    if d.upper().startswith("A:"):
        return SWISS_BACKUP_ROOT
    return Path(d) / "SkyTycoon_Sovereign_Vault"


def resolve_swiss_backup_root() -> Path:
    """Festes Backup-Ziel A:\\SkyTycoon_Backups (Schweizer 2h-ZIP)."""
    root = SWISS_BACKUP_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_swiss_sync_to_backup_root(
    project_root: Path | None = None,
) -> tuple[bool, str]:
    root = resolve_swiss_backup_root()
    dest = create_swiss_sync_zip(root, project_root, prefix="SWISS_SYNC_2H")
    if dest is None:
        return False, "zip_failed"
    prune_local_vault(root, cap_mb=CAP_MB_DEFAULT)
    return True, str(dest)


def ensure_vault_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for sub in VAULT_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)


def load_vault_config() -> dict[str, Any]:
    if not VAULT_CONFIG_PATH.is_file():
        return {"drive": "C:\\", "lang": "de"}
    try:
        data = json.loads(VAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"drive": "C:\\", "lang": "de"}
    except (json.JSONDecodeError, OSError):
        return {"drive": "C:\\", "lang": "de"}


def save_vault_config(cfg: dict[str, Any]) -> None:
    VAULT_CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def disk_usage_for_drive(drive: str) -> tuple[int, int, int, float]:
    if psutil is None:
        return (0, 0, 0, 0.0)
    path = drive if drive.endswith("\\") else drive.rstrip("/") + "\\"
    u = psutil.disk_usage(path)
    return int(u.total), int(u.used), int(u.free), float(u.percent)


def _parse_ts_from_name(name: str) -> float | None:
    m = re.search(r"_(\d{8})_(\d{6})", name)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
        return dt.timestamp()
    except ValueError:
        return None


def _folder_size_mb(folder: Path) -> float:
    total = 0
    if not folder.is_dir():
        return 0.0
    for p in folder.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def prune_local_vault(
    vault_root: Path,
    *,
    cap_mb: float = CAP_MB_DEFAULT,
    hourly_keep_days: int = 7,
    monthly_drop_days: int = 30,
) -> dict[str, int]:
    """Retention auf PC-SSD: Dumps + Projekt-Zips; PDFs in rechnungen_invoices bleiben."""
    stats = {"deleted": 0, "kept": 0, "skipped_pdf": 0}
    vault_root = Path(vault_root).resolve()
    if not vault_root.is_dir():
        return stats
    now = time.time()
    cutoff_7d = now - hourly_keep_days * 86400
    cutoff_30d = now - monthly_drop_days * 86400
    targets = [
        vault_root / "datenbank_dumps",
        vault_root / "git_repositories",
    ]
    for folder in targets:
        if not folder.is_dir():
            continue
        by_week: dict[str, list[tuple[Path, float]]] = {}
        for fp in folder.iterdir():
            if not fp.is_file():
                continue
            low = fp.name.lower()
            if low.endswith(".pdf"):
                stats["skipped_pdf"] += 1
                continue
            mtime = fp.stat().st_mtime
            ts = _parse_ts_from_name(fp.name) or mtime
            if ts >= cutoff_7d:
                stats["kept"] += 1
                continue
            if ts < cutoff_30d:
                try:
                    fp.unlink()
                    stats["deleted"] += 1
                except OSError:
                    pass
                continue
            wk = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%G-W%V")
            by_week.setdefault(wk, []).append((fp, ts))
        for _wk, items in by_week.items():
            items.sort(key=lambda x: x[1], reverse=True)
            for fp, _ts in items[1:]:
                try:
                    fp.unlink()
                    stats["deleted"] += 1
                except OSError:
                    pass
            if items:
                stats["kept"] += 1
    dumps_mb = _folder_size_mb(vault_root / "datenbank_dumps")
    git_mb = _folder_size_mb(vault_root / "git_repositories")
    total_mb = dumps_mb + git_mb
    if total_mb > cap_mb:
        candidates: list[tuple[float, Path]] = []
        for folder in targets:
            if not folder.is_dir():
                continue
            for fp in folder.iterdir():
                if fp.is_file() and not fp.name.lower().endswith(".pdf"):
                    candidates.append((fp.stat().st_mtime, fp))
        candidates.sort()
        for _mtime, fp in candidates:
            if dumps_mb + git_mb <= cap_mb:
                break
            try:
                sz = fp.stat().st_size / (1024 * 1024)
                fp.unlink()
                stats["deleted"] += 1
                if fp.parent.name == "datenbank_dumps":
                    dumps_mb = max(0.0, dumps_mb - sz)
                else:
                    git_mb = max(0.0, git_mb - sz)
            except OSError:
                pass
    return stats


def create_swiss_sync_zip(
    vault_root: Path,
    project_root: Path | None = None,
    *,
    stamp: str | None = None,
    prefix: str = "SWISS_SYNC_2H",
) -> Path | None:
    """Projekt-Zip nach git_repositories (Standard: SWISS_SYNC_2H_*.zip)."""
    src = Path(project_root or PROJECT_ROOT_DEFAULT).resolve()
    if not src.is_dir():
        return None
    ensure_vault_tree(vault_root)
    out_dir = vault_root / "git_repositories"
    ts = stamp or zurich_now().strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"{prefix}_{ts}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in ZIP_SKIP_DIRS]
            for fn in files:
                if fn.endswith((".pyc", ".pyo")):
                    continue
                full = Path(root) / fn
                try:
                    arc = str(full.relative_to(src))
                except ValueError:
                    continue
                zf.write(full, arc)
    return dest


def create_project_backup_zip(
    vault_root: Path,
    project_root: Path | None = None,
) -> Path | None:
    return create_swiss_sync_zip(
        vault_root,
        project_root,
        prefix="PROJECT_BACKUP",
    )


def run_swiss_sync_to_label_drive(
    project_root: Path | None = None,
    volume_label: str | None = None,
) -> tuple[bool, str]:
    """Swiss 2h: primär A:\\SkyTycoon_Backups, Fallback Volume-Label."""
    if SWISS_BACKUP_ROOT.drive and Path(SWISS_BACKUP_ROOT.drive).exists():
        return run_swiss_sync_to_backup_root(project_root)
    letter = find_drive_by_volume_label(volume_label)
    if not letter:
        return False, "no_drive"
    root = vault_root_for_drive(letter)
    dest = create_swiss_sync_zip(root, project_root, prefix="SWISS_SYNC_2H")
    if dest is None:
        return False, "zip_failed"
    prune_local_vault(root, cap_mb=CAP_MB_DEFAULT)
    return True, str(dest)


def _ensure_host_key() -> "paramiko.PKey | None":
    if paramiko is None:
        return None
    if HOST_KEY_PATH.is_file():
        try:
            return paramiko.RSAKey.from_private_key_file(str(HOST_KEY_PATH))
        except Exception:
            pass
    key = paramiko.RSAKey.generate(2048)
    key.write_private_key_file(str(HOST_KEY_PATH))
    return key


if paramiko is not None:

    class _VaultSFTPServerInterface(paramiko.SFTPServerInterface):  # type: ignore[misc]
        def __init__(self, server: Any, root: str) -> None:
            super().__init__(server)
            self.root = os.path.abspath(root)

        def _rp(self, path: str) -> str:
            p = os.path.join(self.root, (path or "").lstrip("/"))
            rp = os.path.realpath(p)
            if not rp.startswith(self.root):
                raise OSError("access denied")
            return rp

        def list_folder(self, path: str) -> list[Any]:
            rp = self._rp(path)
            out: list[Any] = []
            for name in os.listdir(rp):
                fp = os.path.join(rp, name)
                st = os.stat(fp)
                attr = paramiko.SFTPAttributes.from_stat(st)
                attr.filename = name
                out.append(attr)
            return out

        def stat(self, path: str) -> Any:
            st = os.stat(self._rp(path))
            attr = paramiko.SFTPAttributes.from_stat(st)
            attr.filename = os.path.basename(path) or "/"
            return attr

        def lstat(self, path: str) -> Any:
            return self.stat(path)

        def open(self, path: str, flags: int, attr: Any) -> Any:
            rp = self._rp(path)
            if flags & os.O_WRONLY:
                if flags & os.O_APPEND:
                    fd = open(rp, "ab")
                else:
                    fd = open(rp, "wb")
            elif flags & os.O_RDWR:
                fd = open(rp, "r+b")
            else:
                fd = open(rp, "rb")
            fd2 = fd.fileno()
            return paramiko.SFTPHandle(fd2)

        def remove(self, path: str) -> None:
            os.remove(self._rp(path))

        def rename(self, oldpath: str, newpath: str) -> None:
            os.rename(self._rp(oldpath), self._rp(newpath))

        def mkdir(self, path: str, attr: Any) -> None:
            os.mkdir(self._rp(path), mode=0o755)

        def rmdir(self, path: str) -> None:
            os.rmdir(self._rp(path))

        def chattr(self, path: str, attr: Any) -> None:
            pass

        def canonicalize(self, path: str) -> str:
            return self._rp(path)

    class _VaultSSHServer(paramiko.ServerInterface):  # type: ignore[misc]
        def __init__(self, password: str) -> None:
            super().__init__()
            self._password = password

        def check_auth_password(self, username: str, password: str) -> int:
            if username == SFTP_USER and password == self._password:
                return paramiko.AUTH_SUCCESSFUL
            return paramiko.AUTH_FAILED

        def check_channel_request(self, kind: str, chanid: int) -> int:
            if kind == "session":
                return paramiko.OPEN_SUCCEEDED
            return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def get_allowed_auths(self, username: str) -> str:
            return "password"

        def check_channel_subsystem_request(self, channel: Any, name: str) -> int:
            if name == "sftp":
                return paramiko.OPEN_SUCCEEDED
            return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED


class VaultSFTPServer:
    """Leichtgewichtiger SFTP-Empfänger (Thread), Root = gewähltes Vault-Verzeichnis."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._root = ""
        self._password = SFTP_PASSWORD
        self._sock: socket.socket | None = None
        self.last_error = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_root(self, root: Path) -> None:
        self._root = str(Path(root).resolve())
        ensure_vault_tree(Path(self._root))

    def set_password(self, password: str) -> None:
        self._password = (password or SFTP_PASSWORD).strip()

    def start(self) -> bool:
        if paramiko is None:
            self.last_error = "paramiko fehlt"
            return False
        if self.running:
            return True
        if not self._root:
            self.last_error = "Kein Vault-Pfad"
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None

    def _handle_client(self, client: socket.socket) -> None:
        if paramiko is None:
            return
        try:
            transport = paramiko.Transport(client)
            host_key = _ensure_host_key()
            if host_key is None:
                return
            transport.add_server_key(host_key)
            transport.start_server(server=_VaultSSHServer(self._password))
            channel = transport.accept(30)
            if channel is None:
                return
            server = paramiko.SFTPServer(
                channel, _VaultSFTPServerInterface(channel, self._root)
            )
            server.serve_forever()
            transport.close()
        except Exception as exc:
            self.last_error = str(exc)

    def _serve_loop(self) -> None:
        if paramiko is None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", SFTP_PORT))
            sock.listen(32)
            sock.settimeout(1.0)
            self._sock = sock
            while not self._stop.is_set():
                try:
                    client, _addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(
                    target=self._handle_client,
                    args=(client,),
                    daemon=True,
                ).start()
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self._sock = None
