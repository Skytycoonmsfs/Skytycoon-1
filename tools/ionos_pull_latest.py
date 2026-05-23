# -*- coding: utf-8 -*-
"""Lädt die aktuelle Version zentraler Dateien vom IONOS-Server (SFTP GET)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import paramiko  # noqa: E402

REMOTE = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon").rstrip("/")
HOST = os.environ["SKYTYCOON_DEPLOY_HOST"]
USER = os.environ["SKYTYCOON_DEPLOY_USER"]
PW = os.environ["SKYTYCOON_DEPLOY_PASSWORD"]

PULL_LIST = [
    "main.py",
    "server_backend.py",
    "skytycoon_pg.py",
    "skytycoon_synology_bridge.py",
    "skytycoon_invoice_pdf.py",
    "discord_bot.py",
    "tools/sky_auto_backup.py",
    "tools/sky_flash_restore.py",
    "locales/translations.json",
]

stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "pulled_from_ionos" / stamp
OUT.mkdir(parents=True, exist_ok=True)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PW, timeout=45)
sftp = ssh.open_sftp()

ok = 0
for rel in PULL_LIST:
    remote_path = f"{REMOTE}/{rel.replace(chr(92), '/')}"
    local_path = OUT / rel
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sftp.get(remote_path, str(local_path))
        size = local_path.stat().st_size
        print(f"[OK] {rel} ({size:,} bytes)")
        ok += 1
    except OSError as exc:
        print(f"[SKIP] {rel}: {exc}")

sftp.close()
ssh.close()
print(f"\n[FERTIG] {ok}/{len(PULL_LIST)} Dateien -> {OUT}")
