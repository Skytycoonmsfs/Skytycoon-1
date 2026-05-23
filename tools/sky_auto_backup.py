# -*- coding: utf-8 -*-
"""
SkyTycoon Full-Stack Auto-Backup (stündlich per Cron).

Erzeugt drei verschlüsselte Pakete und pusht sie per SFTP zum PC-Tresor (Admin Commander :2222):
  - skytycoon_postgres_dump.sql.enc  (pg_dump custom → sql label)
  - skytycoon_website_src.zip.enc
  - skytycoon_discord_bot_src.zip.enc

Rechnungs-PDFs: synology_pending + invoices_archive (skytycoon_synology_bridge).

500-GB-HDD-Log-Rotation (IONOS):
  - Live-Logs älter als 7 Tage: löschen (niemals *.pdf)
  - Kalenderwoche: ältere Logs vor dem Löschen nach archive_weekly/ packen
  - PDFs/Rechnungen: absolut geschützt, werden nie gelöscht
  - Bei >85 % Belegung (Cap SKYTYCOON_LOG_HDD_CAP_GB): älteste Wochen-Archive zuerst

Umgebung:
  SKYTYCOON_BACKUP_PASSWORD     Verschlüsselung (Default: Master-Token)
  SKYTYCOON_PC_VAULT_HOST       Windows-PC IP (öffentlich/VPN)
  SKYTYCOON_PC_VAULT_PORT       Standard 2222
  SKYTYCOON_PC_VAULT_USER       Standard skytycoon
  SKYTYCOON_BACKUP_DIR          Lokal (Default: ./backups)
  SKYTYCOON_DEPLOY_REMOTE_DIR   Quell-Webroot auf Server
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skytycoon_synology_bridge import (  # noqa: E402
    BACKUP_PASSWORD,
    REMOTE_DIRS,
    drain_synology_pending_queue,
    invoice_pdf_filename,
    invoice_username_slug,
    prune_synology_vault_retention,
    push_file_or_queue,
    reserve_disk_bytes,
)

_RE_NAMED_PDF = re.compile(
    r"^(?:RECHNUNG|INVOICE)_(\d{4})_([A-Za-z0-9_-]+)\.pdf$",
    re.IGNORECASE,
)

BACKUP_DIR = Path(
    os.environ.get("SKYTYCOON_BACKUP_DIR") or (ROOT / "backups")
).resolve()
REMOTE_ROOT = Path(
    os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR") or "/home/skytycoon"
)
SRC_ROOT = REMOTE_ROOT if REMOTE_ROOT.is_dir() else ROOT

WEBSITE_INCLUDE = [
    "templates",
    "locales",
    "static",
    "server_backend.py",
    "skytycoon_invoice_pdf.py",
    "skytycoon_synology_bridge.py",
    "skytycoon_load_injector.py",
    "sky_dispatch_engine.py",
    "sky_dispatch_pro.py",
    "wirtschaft_m216_extension.py",
    "schema_postgres.sql",
    "mobile_control.py",
    "skytycoon_crash_recovery.py",
    "skytycoon_prestige_pack.py",
]

DISCORD_INCLUDE = [
    "discord_bot.py",
    "download_cabin_sounds.py",
    "skytycoon_settings_dialog.py",
]

LOG_ROOT = Path(
    os.environ.get("SKYTYCOON_LOG_ROOT") or (SRC_ROOT / "server_logs")
).resolve()
LOG_ARCHIVE = Path(
    os.environ.get("SKYTYCOON_LOG_ARCHIVE_DIR")
    or (LOG_ROOT / "archive_weekly")
).resolve()
LOG_RETENTION_DAYS = int(os.environ.get("SKYTYCOON_LOG_RETENTION_DAYS") or "7")
LOG_HDD_CAP_GB = float(os.environ.get("SKYTYCOON_LOG_HDD_CAP_GB") or "120")
LOG_HDD_MAX_USE = float(os.environ.get("SKYTYCOON_LOG_HDD_MAX_USE") or "0.85")
LOG_SCAN_EXTRA = [
    Path(os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR") or "/home/skytycoon")
    / "backups",
    Path(os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR") or "/home/skytycoon")
    / "synology_pending",
]
PDF_PROTECT_KEYWORDS = (
    "rechnung",
    "invoice",
    "rechnungen_invoices",
    "invoices_archive",
)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _encrypt_file(src: Path, out_enc: Path) -> bool:
    if not BACKUP_PASSWORD:
        print("[BACKUP] SKYTYCOON_BACKUP_PASSWORD fehlt.")
        return False
    cmd = [
        "openssl",
        "enc",
        "-aes-256-cbc",
        "-salt",
        "-pbkdf2",
        "-pass",
        f"pass:{BACKUP_PASSWORD}",
        "-in",
        str(src),
        "-out",
        str(out_enc),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=7200)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[BACKUP] openssl enc failed: {exc}")
        return False


def _pg_dump_plain(path: Path) -> bool:
    dsn = (os.environ.get("SKYTYCOON_POSTGRES_DSN") or "").strip()
    if dsn:
        env = dict(os.environ)
        cmd = ["pg_dump", dsn, "-f", str(path)]
    else:
        host = os.environ.get("SKYTYCOON_PG_HOST", "127.0.0.1")
        port = os.environ.get("SKYTYCOON_PG_PORT", "5432")
        db = os.environ.get("SKYTYCOON_PG_DATABASE", "skytycoon_prod")
        user = os.environ.get("SKYTYCOON_PG_USER", "sky_admin")
        pw = os.environ.get("SKYTYCOON_PG_PASSWORD", "")
        env = {**os.environ, "PGPASSWORD": pw}
        cmd = [
            "pg_dump",
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            db,
            "-f",
            str(path),
        ]
    try:
        subprocess.run(cmd, check=True, env=env, timeout=3600)
        return path.is_file() and path.stat().st_size > 0
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[BACKUP] pg_dump failed: {exc}")
        return False


def _zip_tree(names: list[str], out_zip: Path) -> bool:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            sp = SRC_ROOT / name
            if not sp.exists():
                continue
            if sp.is_dir():
                for fp in sp.rglob("*"):
                    if fp.is_file():
                        zf.write(fp, fp.relative_to(SRC_ROOT).as_posix())
            else:
                zf.write(sp, sp.name)
    return out_zip.is_file()


def _package_postgres(stamp: str, work: Path) -> Path | None:
    dump = work / "skytycoon_postgres_dump.sql"
    if not _pg_dump_plain(dump):
        return None
    enc = BACKUP_DIR / f"skytycoon_postgres_dump_{stamp}.sql.enc"
    if not _encrypt_file(dump, enc):
        return None
    return enc


def _package_website(stamp: str, work: Path) -> Path | None:
    z = work / "skytycoon_website_src.zip"
    if not _zip_tree(WEBSITE_INCLUDE, z):
        return None
    enc = BACKUP_DIR / f"skytycoon_website_src_{stamp}.zip.enc"
    if not _encrypt_file(z, enc):
        return None
    return enc


def _package_discord(stamp: str, work: Path) -> Path | None:
    z = work / "skytycoon_discord_bot_src.zip"
    if not _zip_tree(DISCORD_INCLUDE, z):
        return None
    enc = BACKUP_DIR / f"skytycoon_discord_bot_src_{stamp}.zip.enc"
    if not _encrypt_file(z, enc):
        return None
    return enc


def _is_protected_pdf(path: Path) -> bool:
    if path.suffix.lower() == ".pdf":
        return True
    low = path.as_posix().lower()
    return any(k in low for k in PDF_PROTECT_KEYWORDS)


def _log_age_days(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 86400.0


def _iso_week_key(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    y, w, _ = dt.isocalendar()
    return f"{y}_W{w:02d}"


def _hdd_usage_ratio(root: Path) -> float:
    try:
        u = shutil.disk_usage(root)
        cap = max(1, int(LOG_HDD_CAP_GB * (1024**3)))
        used = u.total - u.free
        return min(1.0, used / cap)
    except OSError:
        return 0.0


def _purge_old_weekly_archives() -> int:
    """Drop oldest weekly log tarballs when HDD budget is tight (never PDFs)."""
    if not LOG_ARCHIVE.is_dir():
        return 0
    archives = sorted(
        (
            p
            for p in LOG_ARCHIVE.glob("logs_*.tar.gz")
            if p.is_file() and not _is_protected_pdf(p)
        ),
        key=lambda p: p.stat().st_mtime,
    )
    removed = 0
    while archives and _hdd_usage_ratio(LOG_ROOT.parent) > LOG_HDD_MAX_USE:
        victim = archives.pop(0)
        try:
            victim.unlink()
            removed += 1
            print(f"[LOG ROTATE] HDD cap — removed archive {victim.name}")
        except OSError:
            break
    return removed


def _weekly_archive_file(path: Path) -> Path | None:
    """Pack a single log into the ISO-week archive tarball (idempotent append)."""
    if _is_protected_pdf(path):
        return None
    LOG_ARCHIVE.mkdir(parents=True, exist_ok=True)
    arc = LOG_ARCHIVE / f"logs_{_iso_week_key(path.stat().st_mtime)}.tar.gz"
    mode = "a:gz" if arc.is_file() else "w:gz"
    try:
        with tarfile.open(arc, mode) as tf:
            tf.add(path, arcname=path.name)
        return arc
    except (OSError, tarfile.TarError) as exc:
        print(f"[LOG ROTATE] weekly archive skip {path.name}: {exc}")
        return None


def rotate_server_logs() -> dict[str, int]:
    """
    500-GB-HDD rotation: weekly archive, delete logs >7d, PDFs never touched.
    """
    stats = {"archived": 0, "deleted": 0, "pdf_skipped": 0, "archives_purged": 0}
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ARCHIVE.mkdir(parents=True, exist_ok=True)
    scan_roots = [LOG_ROOT, *LOG_SCAN_EXTRA, BACKUP_DIR]
    seen: set[str] = set()
    cutoff = timedelta(days=LOG_RETENTION_DAYS)
    now = datetime.now(timezone.utc)

    for root in scan_roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            if _is_protected_pdf(path):
                stats["pdf_skipped"] += 1
                continue
            if LOG_ARCHIVE in path.parents:
                continue
            if path.suffix.lower() in {".enc", ".dump", ".sql"} and "backup" in key.lower():
                continue
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            age = now - mtime
            if age >= cutoff:
                if _weekly_archive_file(path):
                    stats["archived"] += 1
                try:
                    path.unlink()
                    stats["deleted"] += 1
                    print(f"[LOG ROTATE] deleted (>={LOG_RETENTION_DAYS}d) {path}")
                except OSError as exc:
                    print(f"[LOG ROTATE] delete fail {path}: {exc}")
            elif age >= timedelta(days=1) and now.weekday() == 6:
                if _weekly_archive_file(path):
                    stats["archived"] += 1

    stats["archives_purged"] = _purge_old_weekly_archives()
    ratio = _hdd_usage_ratio(LOG_ROOT.parent)
    print(
        f"[LOG ROTATE] done archived={stats['archived']} deleted={stats['deleted']} "
        f"pdf_safe={stats['pdf_skipped']} hdd_use={ratio:.1%} cap={LOG_HDD_CAP_GB}GB"
    )
    return stats


def _customer_slug_from_pdf_name(filename: str) -> str:
    """Kundennamen-Slug aus RECHNUNG_2026_feltypaede.pdf / INVOICE_2026_pilot.pdf."""
    m = _RE_NAMED_PDF.match(filename)
    if m:
        return m.group(2).lower()
    stem = Path(filename).stem
    for prefix in ("SkyTycoon_Rechnung_", "SkyTycoon_Invoice_"):
        if stem.startswith(prefix):
            return invoice_username_slug(stem[len(prefix) :])
    return "unsorted"


def _normalize_invoice_filename(pdf: Path) -> Path:
    """Benennt Legacy-PDFs nach RECHNUNG_[JAHR]_[KUNDE].pdf um (lokal, vor SFTP)."""
    if _RE_NAMED_PDF.match(pdf.name):
        return pdf
    slug = _customer_slug_from_pdf_name(pdf.name)
    if slug == "unsorted":
        return pdf
    lang = "en" if "invoice" in pdf.name.lower() else "de"
    new_name = invoice_pdf_filename(lang=lang, pilot_name=slug)
    target = pdf.parent / new_name
    if target.resolve() == pdf.resolve():
        return pdf
    if target.is_file():
        return target
    try:
        pdf.rename(target)
        print(f"[INVOICE] umbenannt → {new_name}")
        return target
    except OSError as exc:
        print(f"[INVOICE] rename skip {pdf.name}: {exc}")
        return pdf


def _sync_invoices() -> dict[str, int]:
    """
    Spiegelt Rechnungs-PDFs zur Synology, sortiert nach Kunde:
    /volume1/skytycoon_vault/rechnungen_invoices/<kunde>/RECHNUNG_2026_<kunde>.pdf
    PDFs werden niemals gelöscht.
    """
    stats = {"pushed": 0, "queued": 0, "skipped": 0}
    seen: set[str] = set()
    inv_roots = [
        SRC_ROOT / "invoices_archive",
        ROOT / "invoices_archive",
        Path(os.environ.get("SKYTYCOON_INVOICE_ARCHIVE_DIR") or ""),
    ]
    for inv_dir in inv_roots:
        if not inv_dir or not Path(inv_dir).is_dir():
            continue
        inv_dir = Path(inv_dir)
        for pdf in sorted(inv_dir.rglob("*.pdf")):
            key = str(pdf.resolve())
            if key in seen:
                continue
            seen.add(key)
            if reserve_disk_bytes(BACKUP_DIR) < pdf.stat().st_size * 2:
                stats["skipped"] += 1
                continue
            pdf = _normalize_invoice_filename(pdf)
            slug = _customer_slug_from_pdf_name(pdf.name)
            remote_dir = f"{REMOTE_DIRS['invoices'].rstrip('/')}/{slug}"
            ok = push_file_or_queue(pdf, remote_dir, pdf.name)
            if ok:
                stats["pushed"] += 1
            else:
                stats["queued"] += 1
            print(f"[INVOICE SYNC] {slug}/{pdf.name} → Synology")
    print(
        f"[INVOICE SYNC] pushed={stats['pushed']} queued={stats['queued']} "
        f"skipped={stats['skipped']}"
    )
    return stats


def _push_enc(enc: Path, remote_dir: str) -> None:
    if reserve_disk_bytes(BACKUP_DIR) < enc.stat().st_size * 2:
        print(f"[BACKUP] Reserve low — queue {enc.name}")
    push_file_or_queue(enc, remote_dir, enc.name)


def run_backup() -> int:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    rotate_server_logs()
    stamp = _ts()
    work = BACKUP_DIR / f"work_{stamp}"
    work.mkdir(parents=True, exist_ok=True)
    ok_any = False
    pg = _package_postgres(stamp, work)
    if pg:
        _push_enc(pg, REMOTE_DIRS["postgres"])
        ok_any = True
    web = _package_website(stamp, work)
    if web:
        _push_enc(web, REMOTE_DIRS["website"])
        ok_any = True
    bot = _package_discord(stamp, work)
    if bot:
        _push_enc(bot, REMOTE_DIRS["discord"])
        ok_any = True
    inv_stats = _sync_invoices()
    drained = drain_synology_pending_queue()
    prune_stats = prune_synology_vault_retention(
        hourly_keep_days=7,
        monthly_drop_days=30,
        ssd_cap_gb=LOG_HDD_CAP_GB,
    )
    print(
        f"[BACKUP] invoice mirror drained={drained} stats={inv_stats} "
        f"syno_prune={prune_stats}"
    )
    shutil.rmtree(work, ignore_errors=True)
    for pattern in ("skytycoon_*_*.sql.enc", "skytycoon_*_*.zip.enc"):
        old = sorted(BACKUP_DIR.glob(pattern))[:-48]
        for f in old:
            try:
                f.unlink()
            except OSError:
                pass
    if not ok_any:
        print("[BACKUP] Kein Paket erzeugt.")
        return 1
    print(f"[BACKUP] OK — {stamp} (3-Säulen + Synology-Queue)")
    return 0


if __name__ == "__main__":
    sys.exit(run_backup())
