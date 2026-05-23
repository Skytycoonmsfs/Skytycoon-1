# -*- coding: utf-8 -*-
"""Kurz-Diagnose M216 auf dem Produktionsserver."""
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

ssh.exec_command("mkdir -p /home/skytycoon/tools", timeout=30)
sftp = ssh.open_sftp()
try:
    sftp.put(
        str(ROOT / "tools" / "m216_register_test.py"),
        "/home/skytycoon/tools/m216_register_test.py",
    )
finally:
    sftp.close()

cmds = [
    "cd /home/skytycoon && /home/skytycoon/venv/bin/python tools/m216_register_test.py 2>&1",
    "grep -i M216 /home/skytycoon/server.log | tail -5 || echo no_m216_log",
]
for c in cmds:
    print("===", c, "===")
    _stdin, stdout, stderr = ssh.exec_command(c, timeout=120)
    print(stdout.read().decode("utf-8", "replace"))
    err = stderr.read().decode("utf-8", "replace")
    if err.strip():
        print("STDERR:", err)
ssh.close()
