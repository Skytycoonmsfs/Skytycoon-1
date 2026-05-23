# -*- coding: utf-8 -*-
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

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ["SKYTYCOON_DEPLOY_HOST"],
    username=os.environ["SKYTYCOON_DEPLOY_USER"],
    password=os.environ["SKYTYCOON_DEPLOY_PASSWORD"],
    timeout=30,
)
py = r"""
import psycopg2
conn = psycopg2.connect(host='127.0.0.1', database='skytycoon_prod', user='sky_admin', password='e85OieJLPMV6Nuv', port='5432')
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY 1")
print('users_cols:', [r[0] for r in cur.fetchall()])
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='discord_oauth_links' ORDER BY 1")
print('oauth_cols:', [r[0] for r in cur.fetchall()])
conn.close()
"""
cmd = f"cd /home/skytycoon && /home/skytycoon/venv/bin/python -c {repr(py)}"
_i, o, e = ssh.exec_command(cmd, timeout=60)
print(o.read().decode())
print(e.read().decode())
ssh.close()
