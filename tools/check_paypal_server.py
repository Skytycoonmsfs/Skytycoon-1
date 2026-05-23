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
cmds = [
    "wc -c /home/skytycoon/paypal.env 2>/dev/null; wc -c /home/skytycoon/smtp.env 2>/dev/null",
    "grep -E '^PAYPAL_' /home/skytycoon/smtp.env 2>/dev/null | sed 's/=.*$/=***/' || echo no_paypal_in_smtp",
    "grep EnvironmentFile /etc/systemd/system/skytycoon.service",
]
for c in cmds:
    print("===", c, "===")
    _i, o, e = ssh.exec_command(c, timeout=30)
    print(o.read().decode("utf-8", "replace"))
ssh.close()
