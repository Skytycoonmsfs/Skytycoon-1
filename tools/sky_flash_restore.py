# -*- coding: utf-8 -*-
"""
SkyTycoon 1-Klick-Wiederauferstung (leerer Server, < 60 s Ziel).

Lädt die drei verschlüsselten Synology-Pakete (oder ein Legacy-Komplett-.enc),
spielt PostgreSQL ein, entpackt Website + Discord-Bot, startet Dienste neu.

Umgebung:
  SKYTYCOON_BACKUP_PASSWORD
  SKYTYCOON_BACKUP_PACKAGE       Legacy single .enc (optional)
  SKYTYCOON_RESTORE_PG_ENC       Pfad/URL postgres .sql.enc
  SKYTYCOON_RESTORE_WEB_ENC      Pfad/URL website .zip.enc
  SKYTYCOON_RESTORE_BOT_ENC       Pfad/URL discord .zip.enc
  SKYTYCOON_RESTORE_TARGET       Default: /home/skytycoon
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BACKUP_PASSWORD = (
    os.environ.get("SKYTYCOON_BACKUP_PASSWORD") or "e85OieJLPMV6Nuv"
).strip()
PACKAGE = (os.environ.get("SKYTYCOON_BACKUP_PACKAGE") or "").strip()
PG_ENC = (os.environ.get("SKYTYCOON_RESTORE_PG_ENC") or "").strip()
WEB_ENC = (os.environ.get("SKYTYCOON_RESTORE_WEB_ENC") or "").strip()
BOT_ENC = (os.environ.get("SKYTYCOON_RESTORE_BOT_ENC") or "").strip()
TARGET = Path(
    os.environ.get("SKYTYCOON_RESTORE_TARGET") or "/home/skytycoon"
).resolve()


def _fetch(path: Path, spec: str) -> bool:
    if path.is_file():
        return True
    if spec.startswith("http://") or spec.startswith("https://"):
        r = requests.get(spec, timeout=600)
        r.raise_for_status()
        path.write_bytes(r.content)
        return True
    if spec and Path(spec).is_file():
        shutil.copy2(spec, path)
        return True
    return False


def _decrypt(enc: Path, out: Path) -> bool:
    if not BACKUP_PASSWORD:
        print("[RESTORE] SKYTYCOON_BACKUP_PASSWORD fehlt.")
        return False
    cmd = [
        "openssl",
        "enc",
        "-d",
        "-aes-256-cbc",
        "-pbkdf2",
        "-pass",
        f"pass:{BACKUP_PASSWORD}",
        "-in",
        str(enc),
        "-out",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=7200)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[RESTORE] decrypt failed: {exc}")
        return False


def _pg_restore_sql(sql_path: Path) -> bool:
    host = os.environ.get("SKYTYCOON_PG_HOST", "127.0.0.1")
    port = os.environ.get("SKYTYCOON_PG_PORT", "5432")
    db = os.environ.get("SKYTYCOON_PG_DATABASE", "skytycoon_prod")
    user = os.environ.get("SKYTYCOON_PG_USER", "sky_admin")
    env = {**os.environ, "PGPASSWORD": os.environ.get("SKYTYCOON_PG_PASSWORD", "")}
    cmd = ["psql", "-h", host, "-p", str(port), "-U", user, "-d", db, "-f", str(sql_path)]
    try:
        subprocess.run(cmd, check=True, env=env, timeout=3600)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[RESTORE] psql: {exc}")
        return False


def _pg_restore_dump(dump: Path) -> bool:
    host = os.environ.get("SKYTYCOON_PG_HOST", "127.0.0.1")
    port = os.environ.get("SKYTYCOON_PG_PORT", "5432")
    db = os.environ.get("SKYTYCOON_PG_DATABASE", "skytycoon_prod")
    user = os.environ.get("SKYTYCOON_PG_USER", "sky_admin")
    env = {**os.environ, "PGPASSWORD": os.environ.get("SKYTYCOON_PG_PASSWORD", "")}
    cmd = [
        "pg_restore",
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        user,
        "-d",
        db,
        "--clean",
        "--if-exists",
        str(dump),
    ]
    try:
        subprocess.run(cmd, check=True, env=env, timeout=3600)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[RESTORE] pg_restore: {exc}")
        return False


def _unzip_to(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)


def _restart_services() -> None:
    for svc in (
        "skytycoon.service",
        "skytycoon-discord-bot.service",
        "skytycoon_bot.service",
    ):
        subprocess.run(["sudo", "systemctl", "restart", svc], check=False, timeout=120)


def _restore_triple(tmp: Path) -> bool:
    ok = False
    if PG_ENC:
        enc = tmp / "pg.enc"
        if _fetch(enc, PG_ENC):
            plain = tmp / "skytycoon_postgres_dump.sql"
            if _decrypt(enc, plain):
                if plain.suffix == ".sql":
                    ok = _pg_restore_sql(plain) or ok
                else:
                    ok = _pg_restore_dump(plain) or ok
    if WEB_ENC:
        enc = tmp / "web.enc"
        if _fetch(enc, WEB_ENC):
            plain = tmp / "skytycoon_website_src.zip"
            if _decrypt(enc, plain):
                _unzip_to(plain, TARGET)
                ok = True
    if BOT_ENC:
        enc = tmp / "bot.enc"
        if _fetch(enc, BOT_ENC):
            plain = tmp / "skytycoon_discord_bot_src.zip"
            if _decrypt(enc, plain):
                _unzip_to(plain, TARGET)
                ok = True
    return ok


def _restore_legacy(tmp: Path) -> bool:
    if not PACKAGE:
        return False
    enc = tmp / "package.enc"
    if not _fetch(enc, PACKAGE):
        return False
    tar_p = tmp / "package.tar.gz"
    if not _decrypt(enc, tar_p):
        return False
    dest = tmp / "unpacked"
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_p, "r:gz") as tf:
        tf.extractall(dest)
    children = list(dest.iterdir())
    root = children[0] if len(children) == 1 and children[0].is_dir() else dest
    web = root / "webroot"
    if web.is_dir():
        TARGET.mkdir(parents=True, exist_ok=True)
        for item in web.iterdir():
            dst = TARGET / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
    dump = root / "skytycoon_prod.dump"
    if dump.is_file():
        _pg_restore_dump(dump)
    return True


def run_restore() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sky_restore_") as tmp:
        tmp_p = Path(tmp)
        if PG_ENC or WEB_ENC or BOT_ENC:
            if not _restore_triple(tmp_p):
                print("[RESTORE] Triple-Paket fehlgeschlagen.")
                return 2
        elif PACKAGE:
            if not _restore_legacy(tmp_p):
                return 3
        else:
            print(
                "[RESTORE] SKYTYCOON_RESTORE_*_ENC oder SKYTYCOON_BACKUP_PACKAGE setzen."
            )
            return 1
    _restart_services()
    print(f"[RESTORE] Imperium wiederhergestellt → {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(run_restore())
