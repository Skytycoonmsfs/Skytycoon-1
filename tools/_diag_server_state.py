# -*- coding: utf-8 -*-
"""Einmal-Diagnose IONOS (Admin 403 / Nutzer / Lizenzen)."""
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
    f"grep SKYTYCOON_ {remote}/smtp.env 2>/dev/null | grep -E 'ADMIN|SUPERADMIN' || echo '(no admin keys in smtp.env)'",
    f"python3 -c \"import sqlite3; p='{remote}/database/ionos_users.sqlite';\n"
    "c=sqlite3.connect(p); print('sqlite users', c.execute('select count(*) from users').fetchone()[0]); c.close()\"",
    f"python3 -c \"import sqlite3; p='{remote}/database/skytycoon_server.db';\n"
    "c=sqlite3.connect(p); print('web_pending', c.execute('select count(*) from web_pending_users').fetchone()[0]);\n"
    "print('lic activated', c.execute(\\\"select count(*) from license_keys where status='activated'\\\").fetchone()[0]); c.close()\"",
    f"curl -sS -o /dev/null -w 'admin_list_no_pw=%{{http_code}}\\n' -X POST {remote.replace('/home/skytycoon','http://127.0.0.1:8000')}/api/v1/admin/users/list -H 'Content-Type: application/json' -d '{{}}'",
    f"curl -sS -o /dev/null -w 'admin_list_pw=%{{http_code}}\\n' -X POST http://127.0.0.1:8000/api/v1/admin/users/list -H 'Content-Type: application/json' -d '{{\"admin_password\":\"e85OieJLPMV6Nuv\"}}'",
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=45)
for cmd in cmds:
    print(">", cmd[:120])
    _stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("ERR:", err)
ssh.close()
