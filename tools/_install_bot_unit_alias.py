# -*- coding: utf-8 -*-
"""Erstellt skytycoon_bot.service als Alias für skytycoon-discord-bot auf IONOS."""
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

unit = """[Unit]
Description=SkyTycoon Bot (Discord — Alias skytycoon_bot)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/skytycoon
EnvironmentFile=-/home/skytycoon/discord_bot.env
EnvironmentFile=-/home/skytycoon/smtp.env
ExecStart=/home/skytycoon/venv/bin/python3 /home/skytycoon/discord_bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=45)
sftp = ssh.open_sftp()
with sftp.file("/etc/systemd/system/skytycoon_bot.service", "w") as f:
    f.write(unit)
sftp.close()
for cmd in (
    "sudo systemctl daemon-reload",
    "sudo systemctl enable skytycoon_bot.service",
    "sudo systemctl restart skytycoon_bot.service",
    "sleep 2",
    "systemctl is-active skytycoon_bot.service",
    "systemctl is-active skytycoon-discord-bot.service",
):
    print(">", cmd)
    _i, o, e = ssh.exec_command(cmd, timeout=60)
    print(o.read().decode())
    err = e.read().decode()
    if err.strip():
        print("ERR:", err.encode("ascii", errors="replace").decode())
ssh.close()
