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

host = os.environ["SKYTYCOON_DEPLOY_HOST"]
user = os.environ["SKYTYCOON_DEPLOY_USER"]
pw = os.environ["SKYTYCOON_DEPLOY_PASSWORD"]
remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")

script = f"""cat > /tmp/sky_pg_diag.py << 'PYEOF'
import time
import psycopg2
cutoff = time.time() - 18
for label, kwargs in [
    ("localhost", dict(host="localhost", dbname="skytycoon_prod", user="sky_admin", password="e85OieJLPMV6Nuv", port=5432)),
    ("217", dict(host="217.154.16.248", dbname="skytycoon_prod", user="sky_admin", password="e85OieJLPMV6Nuv", port=5432)),
]:
    try:
        c = psycopg2.connect(**kwargs)
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM radar_positions WHERE COALESCE(NULLIF(last_heartbeat,0),ts) >= %s", (cutoff,))
        print(label, "online", cur.fetchone()[0])
        cur.execute("SELECT pilot_name, last_heartbeat FROM radar_positions ORDER BY last_heartbeat DESC NULLS LAST LIMIT 5")
        print(label, "rows", cur.fetchall())
        c.close()
    except Exception as e:
        print(label, "ERR", e)
PYEOF
python3 /tmp/sky_pg_diag.py
grep -i 'PostgreSQL persist failed' {remote}/server_logs/*.log 2>/dev/null | tail -5
journalctl -u skytycoon.service -n 40 --no-pager 2>/dev/null | grep -i radar | tail -8
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=30)
_i, o, e = ssh.exec_command(script, timeout=60)
print(o.read().decode("utf-8", "replace"))
err = e.read().decode("utf-8", "replace")
if err.strip():
    print("ERR:", err)
ssh.close()
