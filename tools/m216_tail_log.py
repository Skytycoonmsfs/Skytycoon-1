# -*- coding: utf-8 -*-
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ["SKYTYCOON_DEPLOY_HOST"],
    username=os.environ["SKYTYCOON_DEPLOY_USER"],
    password=os.environ["SKYTYCOON_DEPLOY_PASSWORD"],
    timeout=30,
)
for c in [
    "curl -sS http://127.0.0.1:8000/market/license_shop 2>&1 | head -c 600",
    "tail -n 40 /home/skytycoon/server.log",
]:
    print("===", c, "===")
    _i, o, e = ssh.exec_command(c, timeout=30)
    print(o.read().decode("utf-8", "replace"))
ssh.close()
