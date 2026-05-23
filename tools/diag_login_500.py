# -*- coding: utf-8 -*-
"""Diagnose Login-500 auf IONOS."""
from __future__ import annotations

import os
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

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=30)

cmds = [
    "curl -sS -o /dev/null -w 'GET /login: %{http_code}\n' http://127.0.0.1:8000/login",
    (
        "curl -sS -o /tmp/login_post.out -w 'POST /login: %{http_code}\n' "
        "-X POST -d 'email=test@test.com&password=wrong' http://127.0.0.1:8000/login"
    ),
    "head -5 /tmp/login_post.out 2>/dev/null",
    "tail -80 /home/skytycoon/server.log 2>/dev/null || echo no_server_log",
    "journalctl -u skytycoon.service -n 50 --no-pager 2>/dev/null | tail -30",
    "grep SKYTYCOON_DISCORD /home/skytycoon/smtp.env 2>/dev/null | sed 's/SECRET=.*/SECRET=***/' || echo no_discord_env",
    (
        "cd /home/skytycoon && set -a && . ./smtp.env && set +a && "
        "/home/skytycoon/venv/bin/python -c 'import server_backend as sb; "
        "print(\"import_ok\", sb.DISCORD_CLIENT_ID[:6])'"
    ),
    (
        "journalctl -u skytycoon-discord-bot.service -n 30 --no-pager 2>/dev/null "
        "| grep -E 'guide pinned|NameError|channel_live_radar|Handbuch' | tail -15 "
        "|| echo no_guide_lines"
    ),
    "curl -sS -o /dev/null -w 'GET /login: %{http_code}\n' http://127.0.0.1:8000/login",
]
for c in cmds:
    print("===", c[:90], "===")
    _stdin, stdout, stderr = ssh.exec_command(c, timeout=90)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    print(out)
    if err.strip():
        print("STDERR:", err)
ssh.close()
