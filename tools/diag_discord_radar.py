# -*- coding: utf-8 -*-
"""Remote: Discord-Bot-Status, Radar-PG, Command-Queue."""
from __future__ import annotations

import os
import time
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
remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")

py = r"""
import time, json
import psycopg2
cutoff = time.time() - 18
conn = psycopg2.connect(host='217.154.16.248', dbname='skytycoon_prod', user='sky_admin', password='e85OieJLPMV6Nuv', port=5432)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM radar_positions WHERE COALESCE(NULLIF(last_heartbeat,0),ts) >= %s", (cutoff,))
print('online_radar', cur.fetchone()[0])
cur.execute("SELECT pilot_name, hardware_id, last_heartbeat, ts, status FROM radar_positions ORDER BY COALESCE(NULLIF(last_heartbeat,0),ts) DESC LIMIT 8")
for r in cur.fetchall():
    print('row', r)
cur.execute("SELECT id, command_type, status, created_ts FROM discord_bot_commands ORDER BY id DESC LIMIT 10")
for r in cur.fetchall():
    print('cmd', r)
conn.close()
"""

cmds = [
    "systemctl is-active skytycoon-discord-bot.service; systemctl is-active skytycoon_bot.service",
    "journalctl -u skytycoon-discord-bot.service -n 30 --no-pager 2>/dev/null | tail -22",
    "grep ExecStart /etc/systemd/system/skytycoon-discord-bot.service /etc/systemd/system/skytycoon_bot.service 2>/dev/null",
    f"cd {remote} && python3 -c {repr(py)}",
    f"curl -sS -m 6 -X POST http://127.0.0.1:8000/api/v1/radar/heartbeat -H 'Content-Type: application/json' -d '{{\"hardware_id\":\"diag-test-hwid\",\"username\":\"DiagPilot\",\"pilot_name\":\"DiagPilot\",\"flight_phase\":\"AM GATE / PARKING\",\"aircraft\":\"B738\",\"lat\":50.04,\"lon\":8.56,\"ts\":{time.time()}}}' | head -c 400",
    "curl -sS -m 6 http://127.0.0.1:8000/api/v1/web/radar/positions | head -c 500",
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=30)
for c in cmds:
    print("\n>", c[:100])
    _i, o, e = ssh.exec_command(c, timeout=60)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    if out.strip():
        print(out)
    if err.strip():
        print("ERR:", err[:600])
ssh.close()
