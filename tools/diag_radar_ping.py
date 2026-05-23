# -*- coding: utf-8 -*-
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import paramiko

ts = time.time()
body = (
    '{"hardware_id":"diag-test-hwid","username":"feltypaede","pilot_name":"feltypaede",'
    '"flight_phase":"AM GATE / PARKING","aircraft":"B738","lat":50.04,"lon":8.56,"ts":'
    + str(ts)
    + "}"
)
cmds = [
    f"curl -sS -X POST http://127.0.0.1:8000/api/v1/radar/heartbeat -H 'Content-Type: application/json' -d '{body}'",
    "curl -sS http://127.0.0.1:8000/api/v1/web/radar/positions",
    "journalctl -u skytycoon-discord-bot.service -n 8 --no-pager 2>/dev/null | tail -5",
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
    print(">", c[:80])
    _i, o, e = ssh.exec_command(c, timeout=45)
    print(o.read().decode("utf-8", "replace")[:1200])
ssh.close()
