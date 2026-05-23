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

body = '{"dep_icao":"EDDF","arr_icao":"LEPA","aircraft_model":"B738","passengers":78}'
cmds = [
    f"curl -sS -m 12 -X POST http://127.0.0.1:8000/api/v1/dispatch/calculate_custom_route -H 'Content-Type: application/json' -d '{body}'",
    f"curl -sS -m 12 -w '\\nHTTP:%{{http_code}}' -X POST http://127.0.0.1:8000/api/v1/dispatch/calculate_custom_route -H 'Content-Type: application/json' -d '{{}}'",
]
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ["SKYTYCOON_DEPLOY_HOST"],
    username=os.environ["SKYTYCOON_DEPLOY_USER"],
    password=os.environ["SKYTYCOON_DEPLOY_PASSWORD"],
    timeout=30,
)
for c in cmds:
    print(">", c[:90])
    _i, o, e = ssh.exec_command(c, timeout=30)
    print(o.read().decode("utf-8", "replace")[:1500])
ssh.close()
