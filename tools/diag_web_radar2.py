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

remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")
script = f"""cd {remote} && /home/skytycoon/venv/bin/python << 'PYEOF'
import time, traceback
import psycopg2
cutoff = time.time() - 15
c = psycopg2.connect(host='localhost', dbname='skytycoon_prod', user='sky_admin', password='e85OieJLPMV6Nuv', port=5432)
cur = c.cursor()
cur.execute("SELECT pilot_name, last_heartbeat, ts, status FROM radar_positions ORDER BY last_heartbeat DESC NULLS LAST LIMIT 5")
print('pg_rows', cur.fetchall())
cur.execute("SELECT COUNT(*) FROM radar_positions WHERE COALESCE(NULLIF(last_heartbeat,0),ts) >= %s", (cutoff,))
print('pg_online', cur.fetchone()[0])
c.close()
try:
    import server_backend as s
    r = s._web_radar_positions_impl()
    print('impl', r.body.decode()[:900])
except Exception:
    traceback.print_exc()
PYEOF
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
