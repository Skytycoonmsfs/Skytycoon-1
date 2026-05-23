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

import paramiko

remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")
script = f"""cd {remote} && /home/skytycoon/venv/bin/python << 'PYEOF'
import server_backend as s
r = s._web_radar_positions_impl()
print(r.body.decode()[:800])
PYEOF
curl -sS http://127.0.0.1:8000/api/v1/web/radar/positions
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ["SKYTYCOON_DEPLOY_HOST"],
    username=os.environ["SKYTYCOON_DEPLOY_USER"],
    password=os.environ["SKYTYCOON_DEPLOY_PASSWORD"],
    timeout=30,
)
_i, o, e = ssh.exec_command(script, timeout=120)
print(o.read().decode("utf-8", "replace"))
err = e.read().decode("utf-8", "replace")
if err.strip():
    print("ERR:", err)
ssh.close()
