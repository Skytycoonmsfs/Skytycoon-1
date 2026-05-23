# -*- coding: utf-8 -*-
"""Einmaliger SMTP-Test auf IONOS (lokal ausführen)."""
from __future__ import annotations

import os
import ssl
import smtplib
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

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=30)

cmds = [
    "grep '^SKYTYCOON_SMTP' /home/skytycoon/smtp.env | sed 's/PASSWORD=.*/PASSWORD=***/'",
    "tail -n 20 /home/skytycoon/server_logs/server.log 2>/dev/null || true",
    "cd /home/skytycoon && python3 tools/test_smtp_send_remote.py 2>&1 || python3 -c 'print(no_script)'",
]
for c in cmds:
    print(">", c)
    _i, stdout, stderr = ssh.exec_command(c, timeout=90)
    print(stdout.read().decode("utf-8", "replace"))
    err = stderr.read().decode("utf-8", "replace")
    if err.strip():
        print("stderr:", err)
ssh.close()
