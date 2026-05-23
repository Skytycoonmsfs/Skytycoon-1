# -*- coding: utf-8 -*-
import os, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
import paramiko
time.sleep(10)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ["SKYTYCOON_DEPLOY_HOST"],
    username=os.environ["SKYTYCOON_DEPLOY_USER"],
    password=os.environ["SKYTYCOON_DEPLOY_PASSWORD"],
    timeout=30,
)
_i, o, _ = ssh.exec_command(
    "journalctl -u skytycoon-discord-bot.service --since '8 min ago' --no-pager 2>/dev/null | tail -25",
    timeout=60,
)
print(o.read().decode("utf-8", "replace"))
ssh.close()
