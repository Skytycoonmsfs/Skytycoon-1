# -*- coding: utf-8 -*-
import hashlib
import os
import sqlite3
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if s and not s.startswith("#") and "=" in s:
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")
script = f"""
import hashlib, sqlite3, json, sys
sys.path.insert(0, '{remote}')
# minimal scan
def pid(h):
    return hashlib.sha256(h.encode()).hexdigest()[:16]
uconn = sqlite3.connect('{remote}/database/ionos_users.sqlite')
for (hid,) in uconn.execute('select hardware_id from users'):
    h=str(hid)
    print(h[:20], pid(h))
uconn.close()
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ["SKYTYCOON_DEPLOY_HOST"], username=os.environ["SKYTYCOON_DEPLOY_USER"], password=os.environ["SKYTYCOON_DEPLOY_PASSWORD"], timeout=45)
_i, o, e = ssh.exec_command(f"python3 -c {repr(script)}", timeout=60)
print(o.read().decode())
print(e.read().decode())
ssh.close()
