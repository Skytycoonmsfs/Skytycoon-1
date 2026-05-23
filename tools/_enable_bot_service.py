# -*- coding: utf-8 -*-
"""IONOS: skytycoon_bot / discord-bot aktivieren und Diagnose."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if s and not s.startswith("#") and "=" in s:
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

host = os.environ["SKYTYCOON_DEPLOY_HOST"]
user = os.environ["SKYTYCOON_DEPLOY_USER"]
pw = os.environ["SKYTYCOON_DEPLOY_PASSWORD"]
remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")

cmds = [
    "systemctl list-unit-files 'skytycoon*' 'discord*' 2>/dev/null | head -20",
    f"test -f {remote}/discord_bot.py && echo discord_bot.py=OK || echo discord_bot.py=MISSING",
    "sudo systemctl enable skytycoon_bot.service 2>&1",
    "sudo systemctl enable skytycoon-discord-bot.service 2>&1",
    "sudo systemctl restart skytycoon_bot.service 2>&1",
    "sudo systemctl restart skytycoon-discord-bot.service 2>&1",
    "sleep 2",
    "systemctl is-active skytycoon_bot.service 2>&1 || true",
    "systemctl is-active skytycoon-discord-bot.service 2>&1 || true",
    "journalctl -u skytycoon_bot.service -n 8 --no-pager 2>&1 || true",
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=45)
for cmd in cmds:
    print(">", cmd)
    _i, o, e = ssh.exec_command(cmd, timeout=60)
    print(o.read().decode("utf-8", errors="replace"))
    err = e.read().decode("utf-8", errors="replace")
    if err.strip():
        print("ERR:", err)
ssh.close()
