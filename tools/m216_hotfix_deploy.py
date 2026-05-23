# -*- coding: utf-8 -*-
"""
M216 Hotfix — CH/DE Co-Dev Pipeline.

Primär: git pull auf IONOS (keine CH↔DE SFTP-Kollision).
Fallback: nur kritische Hotfix-Dateien per SFTP, wenn noch kein Git-Repo auf dem Server.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.deploy"
if not ENV_FILE.is_file():
    print("[FEHLER] .env.deploy fehlt — SKYTYCOON_DEPLOY_HOST/USER/PASSWORD setzen.")
    sys.exit(1)

for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

if (os.environ.get("SKYTYCOON_DEPLOY_ALLOW_SFTP") or "").strip().lower() in (
    "1",
    "true",
    "yes",
):
    print(
        "[BLOCKIERT] SKYTYCOON_DEPLOY_ALLOW_SFTP=1 — CH/DE-Pipeline erlaubt kein Voll-SFTP."
    )
    sys.exit(2)

import paramiko  # noqa: E402

remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon").rstrip("/")
host = os.environ["SKYTYCOON_DEPLOY_HOST"]
user = os.environ["SKYTYCOON_DEPLOY_USER"]
pw = os.environ["SKYTYCOON_DEPLOY_PASSWORD"]
branch = (os.environ.get("SKYTYCOON_DEPLOY_GIT_BRANCH") or "main").strip()
git_remote = (os.environ.get("SKYTYCOON_DEPLOY_GIT_REMOTE") or "origin").strip()

HOTFIX_FILES = [
    "server_backend.py",
    "skytycoon_extensions.py",
    "platin_cloud_only.py",
    "Admin_Commander.py",
    "platin_alliance_center.py",
    "platin_career_layout.py",
]

print("[SkyTycoon] CH/DE-Pipeline: git pull bevorzugt, Hotfix-SFTP nur als Fallback.")
print(f"[SkyTycoon] Ziel: {user}@{host}:{remote} ({git_remote}/{branch})")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=45)


def run(cmd: str, timeout: int = 180) -> tuple[int, str, str]:
    print(">", cmd)
    _stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    code = stdout.channel.recv_exit_status()
    if out:
        print(out)
    if err:
        print("ERR:", err)
    return code, out, err


git_ok = True
for c in (
    f"cd {remote} && test -d .git || (echo 'NO_GIT_REPO' && exit 9)",
    f"cd {remote} && git config --global --add safe.directory {remote} 2>/dev/null || true",
    f"cd {remote} && git fetch {git_remote} --prune",
    f"cd {remote} && git checkout {branch}",
    f"cd {remote} && git pull --ff-only {git_remote} {branch}",
):
    code, _o, _e = run(c, timeout=240)
    if code != 0:
        git_ok = False
        break

if not git_ok:
    print("[WARN] git pull fehlgeschlagen — Hotfix-SFTP-Fallback (nur Kern-Dateien).")
    sftp = ssh.open_sftp()
    for name in HOTFIX_FILES:
        local = ROOT / name
        if not local.is_file():
            continue
        print(f"[SFTP-FALLBACK] {name}")
        sftp.put(str(local), f"{remote}/{name}")
    sftp.close()
else:
    print("[OK] git pull erfolgreich — keine direkte Datei-Kollision.")

restart_cmds = [
    "sudo systemctl daemon-reload 2>/dev/null || true",
    "sudo systemctl restart skytycoon.service",
    "sudo systemctl restart skytycoon_bot.service 2>/dev/null || true",
    "sudo systemctl restart skytycoon-discord-bot.service 2>/dev/null || true",
    "sleep 4",
    "systemctl is-active skytycoon.service",
    "systemctl is-active skytycoon_bot.service 2>/dev/null || echo bot-skip",
    "curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/health || echo FAIL",
]

for c in restart_cmds:
    run(c, timeout=90)

ssh.close()
print("[FERTIG] CH/DE deploy — Dienste neu gestartet.")
