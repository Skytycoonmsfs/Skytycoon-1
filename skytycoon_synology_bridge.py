# -*- coding: utf-8 -*-
"""PC-SSD SFTP bridge (Admin Commander Port 2222): Rechnungen + stündliche Backups."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import paramiko
except ImportError:  # pragma: no cover
    paramiko = None  # type: ignore[assignment]

APP_ROOT = Path(__file__).resolve().parent
BACKUP_PASSWORD = (os.environ.get("SKYTYCOON_BACKUP_PASSWORD") or "").strip()
SYNO_HOST = (
    os.environ.get("SKYTYCOON_PC_VAULT_HOST")
    or os.environ.get("SKYTYCOON_SYNO_HOST")
    or ""
).strip()
SYNO_PORT = int(
    os.environ.get("SKYTYCOON_PC_VAULT_PORT")
    or os.environ.get("SKYTYCOON_SYNO_PORT")
    or "2222"
)
SYNO_USER = (
    os.environ.get("SKYTYCOON_PC_VAULT_USER")
    or os.environ.get("SKYTYCOON_SYNO_USER")
    or "skytycoon"
).strip()
SYNO_PASSWORD = (
    os.environ.get("SKYTYCOON_PC_VAULT_PASSWORD")
    or os.environ.get("SKYTYCOON_SYNO_PASSWORD")
    or BACKUP_PASSWORD
    or "e85OieJLPMV6Nuv"
).strip()
SYNO_BASE = (
    os.environ.get("SKYTYCOON_PC_VAULT_REMOTE_ROOT")
    or os.environ.get("SKYTYCOON_SYNO_VAULT_ROOT")
    or "SkyTycoon Backup (A)/SkyTycoon_Sovereign_Vault"
).rstrip("/")
PENDING_ROOT = Path(
    os.environ.get("SKYTYCOON_SYNO_PENDING_DIR")
    or (APP_ROOT / "synology_pending")
).resolve()
INVOICE_LOCAL = Path(
    os.environ.get("SKYTYCOON_INVOICE_ARCHIVE_DIR")
    or (APP_ROOT / "invoices_archive")
).resolve()
RESERVE_FRAC = float(os.environ.get("SKYTYCOON_SYNO_RESERVE_FRAC") or "0.15")

REMOTE_DIRS = {
    "postgres": f"{SYNO_BASE}/postgres_dumps",
    "website": f"{SYNO_BASE}/website_src",
    "discord": f"{SYNO_BASE}/discord_bot_src",
    "invoices": f"{SYNO_BASE}/rechnungen_invoices",
}


def invoice_username_slug(name: str) -> str:
    raw = (name or "customer").strip()
    if "@" in raw and not raw.split("@", 1)[0].strip():
        raw = raw.split("@", 1)[0]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", raw)[:48].strip("_").lower()
    return slug or "customer"


def invoice_pdf_filename(*, lang: str, pilot_name: str, year: int | None = None) -> str:
    yr = int(year or datetime.now(timezone.utc).year)
    slug = invoice_username_slug(pilot_name)
    if str(lang or "de").strip().lower().startswith("en"):
        return f"INVOICE_{yr}_{slug}.pdf"
    return f"RECHNUNG_{yr}_{slug}.pdf"


def _ensure_dirs() -> None:
    PENDING_ROOT.mkdir(parents=True, exist_ok=True)
    INVOICE_LOCAL.mkdir(parents=True, exist_ok=True)


def _pending_manifest() -> Path:
    return PENDING_ROOT / "queue.json"


def _load_queue() -> list[dict[str, str]]:
    p = _pending_manifest()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return list(data) if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_queue(items: list[dict[str, str]]) -> None:
    _ensure_dirs()
    _pending_manifest().write_text(
        json.dumps(items, ensure_ascii=False, indent=0),
        encoding="utf-8",
    )


def enqueue_synology_upload(local_path: Path, remote_dir: str, remote_name: str) -> None:
    """Queue file for later SFTP when Synology is offline."""
    _ensure_dirs()
    local_path = Path(local_path).resolve()
    if not local_path.is_file():
        return
    slot = PENDING_ROOT / f"{int(time.time() * 1000)}_{remote_name}"
    shutil.copy2(local_path, slot)
    q = _load_queue()
    q.append(
        {
            "local": str(slot),
            "remote_dir": remote_dir.rstrip("/"),
            "remote_name": remote_name,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_queue(q)
    print(f"[PC VAULT QUEUE] {remote_name} → pending ({len(q)} items)")


def archive_invoice_pdf(pdf_bytes: bytes, filename: str) -> Path:
    _ensure_dirs()
    dest = INVOICE_LOCAL / filename
    dest.write_bytes(pdf_bytes)
    return dest


def synology_reachable() -> bool:
    if not SYNO_HOST or paramiko is None:
        return False
    try:
        t = paramiko.Transport((SYNO_HOST, SYNO_PORT))
        t.connect(username=SYNO_USER, password=SYNO_PASSWORD)
        t.close()
        return True
    except Exception:
        return False


def _sftp_put(local_path: Path, remote_dir: str, remote_name: str) -> bool:
    if not SYNO_HOST or paramiko is None:
        return False
    local_path = Path(local_path)
    if not local_path.is_file():
        return False
    try:
        transport = paramiko.Transport((SYNO_HOST, SYNO_PORT))
        transport.connect(username=SYNO_USER, password=SYNO_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        parts = remote_dir.strip("/").split("/")
        cur = ""
        for part in parts:
            cur = f"{cur}/{part}" if cur else f"/{part}"
            try:
                sftp.stat(cur)
            except OSError:
                try:
                    sftp.mkdir(cur)
                except OSError:
                    pass
        remote_path = f"{remote_dir.rstrip('/')}/{remote_name}"
        sftp.put(str(local_path), remote_path)
        sftp.close()
        transport.close()
        print(f"[PC VAULT SFTP] OK {remote_name} → {remote_dir}")
        return True
    except Exception as exc:
        print(f"[PC VAULT SFTP] FAIL {remote_name}: {exc}")
        return False


def push_file_or_queue(
    local_path: Path, remote_dir: str, remote_name: str | None = None
) -> bool:
    """Upload immediately; on failure enqueue for automatic retry."""
    local_path = Path(local_path)
    name = remote_name or local_path.name
    if synology_reachable() and _sftp_put(local_path, remote_dir, name):
        return True
    enqueue_synology_upload(local_path, remote_dir, name)
    return False


def drain_synology_pending_queue() -> int:
    """Flush queued uploads when NAS is back online."""
    q = _load_queue()
    if not q:
        return 0
    if not synology_reachable():
        return 0
    ok_n = 0
    remain: list[dict[str, str]] = []
    for item in q:
        lp = Path(item.get("local", ""))
        rd = item.get("remote_dir", SYNO_BASE)
        rn = item.get("remote_name", lp.name)
        if lp.is_file() and _sftp_put(lp, rd, rn):
            ok_n += 1
            try:
                lp.unlink()
            except OSError:
                pass
        else:
            remain.append(item)
    _save_queue(remain)
    if ok_n:
        print(f"[SYNO QUEUE] Drained {ok_n} file(s), {len(remain)} left")
    return ok_n


def reserve_disk_bytes(path: Path) -> int:
    """Keep ~15% free on volume for failover buffering."""
    try:
        usage = shutil.disk_usage(path)
        return int(usage.free - usage.total * RESERVE_FRAC)
    except OSError:
        return 0


def store_invoice_and_sync(
    pdf_bytes: bytes,
    *,
    lang: str,
    pilot_name: str,
) -> str:
    """Save invoice locally and push/queue to Synology vault."""
    fname = invoice_pdf_filename(lang=lang, pilot_name=pilot_name)
    dest = archive_invoice_pdf(pdf_bytes, fname)
    slug = invoice_username_slug(pilot_name)
    remote_dir = f"{REMOTE_DIRS['invoices'].rstrip('/')}/{slug}"
    if reserve_disk_bytes(dest.parent) < len(pdf_bytes) * 4:
        print("[SYNO] Low disk reserve — invoice queued only")
        enqueue_synology_upload(dest, remote_dir, fname)
        return fname
    push_file_or_queue(dest, remote_dir, fname)
    drain_synology_pending_queue()
    return fname


def _parse_dump_ts(name: str) -> float | None:
    """Timestamp aus skytycoon_postgres_dump_20260520_153045.sql.enc."""
    import re as _re

    m = _re.search(r"_(\d{8})_(\d{6})\.", name)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
        return dt.timestamp()
    except ValueError:
        return None


def _sftp_list_files(remote_dir: str) -> list[tuple[str, float]]:
    if not SYNO_HOST or paramiko is None:
        return []
    out: list[tuple[str, float]] = []
    try:
        transport = paramiko.Transport((SYNO_HOST, SYNO_PORT))
        transport.connect(username=SYNO_USER, password=SYNO_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        for ent in sftp.listdir_attr(remote_dir):
            if ent.filename.startswith("."):
                continue
            out.append((ent.filename, float(ent.st_mtime or 0)))
        sftp.close()
        transport.close()
    except Exception as exc:
        print(f"[SYNO PRUNE] list {remote_dir}: {exc}")
    return out


def _sftp_remove(remote_dir: str, name: str) -> bool:
    if not SYNO_HOST or paramiko is None:
        return False
    try:
        transport = paramiko.Transport((SYNO_HOST, SYNO_PORT))
        transport.connect(username=SYNO_USER, password=SYNO_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        sftp.remove(f"{remote_dir.rstrip('/')}/{name}")
        sftp.close()
        transport.close()
        return True
    except Exception as exc:
        print(f"[SYNO PRUNE] rm {name}: {exc}")
        return False


def prune_synology_vault_retention(
    *,
    hourly_keep_days: int = 7,
    monthly_drop_days: int = 30,
    ssd_cap_gb: float = 120.0,
) -> dict[str, int]:
    """
    120-GB-SSD-Bremse auf der Synology:
    - Stündliche *.enc der letzten 7 Tage behalten
    - Ältere: pro ISO-Woche nur das neueste Archiv
    - Älter als 30 Tage: löschen (niemals rechnungen_invoices/*.pdf)
    """
    stats = {"deleted": 0, "kept": 0, "skipped_pdf": 0}
    if not synology_reachable():
        print("[SYNO PRUNE] NAS offline — skip")
        return stats
    now = time.time()
    cutoff_7d = now - hourly_keep_days * 86400
    cutoff_30d = now - monthly_drop_days * 86400
    dump_dirs = (
        REMOTE_DIRS["postgres"],
        REMOTE_DIRS["website"],
        REMOTE_DIRS["discord"],
    )
    for remote_dir in dump_dirs:
        files = _sftp_list_files(remote_dir)
        if not files:
            continue
        by_week: dict[str, list[tuple[str, float]]] = {}
        for name, mtime in files:
            low = name.lower()
            if low.endswith(".pdf") or "rechnung" in low or "invoice" in low:
                stats["skipped_pdf"] += 1
                continue
            ts = _parse_dump_ts(name) or mtime
            if ts >= cutoff_7d:
                stats["kept"] += 1
                continue
            if ts < cutoff_30d:
                if _sftp_remove(remote_dir, name):
                    stats["deleted"] += 1
                continue
            wk = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%G-W%V")
            by_week.setdefault(wk, []).append((name, ts))
        for _wk, group in by_week.items():
            group.sort(key=lambda x: x[1], reverse=True)
            for name, _ts in group[1:]:
                if _sftp_remove(remote_dir, name):
                    stats["deleted"] += 1
            if group:
                stats["kept"] += 1
    cap_bytes = max(1, int(ssd_cap_gb * (1024**3)))
    try:
        if paramiko and SYNO_HOST:
            transport = paramiko.Transport((SYNO_HOST, SYNO_PORT))
            transport.connect(username=SYNO_USER, password=SYNO_PASSWORD)
            sftp = paramiko.SFTPClient.from_transport(transport)
            assert sftp is not None
            st = sftp.stat(SYNO_BASE)
            used_est = int(getattr(st, "st_size", 0) or 0)
            sftp.close()
            transport.close()
            if used_est > cap_bytes * 0.9:
                print(f"[SYNO PRUNE] vault near cap ({ssd_cap_gb} GB policy)")
    except Exception:
        pass
    print(f"[SYNO PRUNE] done {stats}")
    return stats
