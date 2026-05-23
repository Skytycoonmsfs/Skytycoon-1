#!/usr/bin/env python3
"""IONOS: Rechnungs-Mails batch + Dienst-Health."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import paramiko  # noqa: E402

host = os.environ["SKYTYCOON_DEPLOY_HOST"]
user = os.environ["SKYTYCOON_DEPLOY_USER"]
pw = os.environ["SKYTYCOON_DEPLOY_PASSWORD"]
remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=40)

py = f"{remote}/venv/bin/python"
cmds = [
    f"cd {remote} && {py} tools/resend_license_invoices_batch.py --dry-run --limit 200",
    f"cd {remote} && {py} tools/resend_license_invoices_batch.py --send --limit 200",
    "sudo systemctl restart skytycoon.service",
    "sudo systemctl restart skytycoon_bot.service 2>/dev/null || true",
    "sudo systemctl restart skytycoon-discord-bot.service 2>/dev/null || true",
    "sleep 5",
    "systemctl is-active skytycoon.service",
    "curl -sS -o /dev/null -w 'public_health=%{http_code}\\n' https://skytycoon.info/api/v1/health || true",
    "curl -sS -o /dev/null -w 'login_page=%{http_code}\\n' https://skytycoon.info/login || true",
]
for c in cmds:
    print(">", c)
    _stdin, stdout, stderr = ssh.exec_command(c, timeout=600)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    if out:
        print(out.encode("ascii", "replace").decode("ascii"))
    if err:
        print("ERR:", err.encode("ascii", "replace").decode("ascii"))
ssh.close()
print("[FERTIG] Remote batch + restart.")
