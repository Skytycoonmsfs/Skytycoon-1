# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import paramiko  # noqa: E402

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ["SKYTYCOON_DEPLOY_HOST"],
    username=os.environ["SKYTYCOON_DEPLOY_USER"],
    password=os.environ["SKYTYCOON_DEPLOY_PASSWORD"],
    timeout=30,
)
time.sleep(18)
cmds = [
    "grep -c 'async def channel_live_radar' /home/skytycoon/discord_bot.py || echo 0",
    "journalctl -u skytycoon-discord-bot.service --since '5 min ago' --no-pager 2>/dev/null | tail -40",
]
for c in cmds:
    print("===", c, "===")
    _i, o, e = ssh.exec_command(c, timeout=60)
    print(o.read().decode("utf-8", "replace"))
ssh.close()
