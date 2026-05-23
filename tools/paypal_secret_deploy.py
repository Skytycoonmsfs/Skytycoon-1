# -*- coding: utf-8 -*-
"""
PayPal-Secret auf den Server schreiben (paypal.env), ohne andere Server-Dateien zu löschen.
Nutzung (einmalig):
  set PAYPAL_CLIENT_SECRET=dein_live_secret
  python tools/paypal_secret_deploy.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

secret = (
    (os.environ.get("PAYPAL_CLIENT_SECRET") or "").strip()
    or (os.environ.get("PAYPAL_SECRET") or "").strip()
)
client_id = (os.environ.get("PAYPAL_CLIENT_ID") or "").strip()
if not secret:
    print(
        "FEHLER: PAYPAL_CLIENT_SECRET oder PAYPAL_SECRET in .env.deploy setzen "
        "(oder als Umgebungsvariable).",
        file=sys.stderr,
    )
    sys.exit(1)

import paramiko  # noqa: E402

remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")
lines = [
    f"PAYPAL_CLIENT_ID={client_id or 'AchnHu1yPwiFxcQ_9573Zmo-mcOGw4L_HS-deTQXT7zOpqn4qmeARNovOubH_CXj8zMN2M_jrIkiO333'}",
    f"PAYPAL_CLIENT_SECRET={secret}",
    "PAYPAL_MODE=live",
]
content = "\n".join(lines) + "\n"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ["SKYTYCOON_DEPLOY_HOST"],
    username=os.environ["SKYTYCOON_DEPLOY_USER"],
    password=os.environ["SKYTYCOON_DEPLOY_PASSWORD"],
    timeout=30,
)
tmp = f"/tmp/paypal.env.{os.getpid()}"
sftp = ssh.open_sftp()
with sftp.file(tmp, "w") as fh:
    fh.write(content)
dest = f"{remote}/paypal.env"
try:
    sftp.remove(dest)
except OSError:
    pass
sftp.rename(tmp, dest)
sftp.close()
ssh.exec_command(f"chmod 600 {dest}", timeout=15)
ssh.exec_command("sudo systemctl restart skytycoon.service", timeout=60)
print(f"[OK] paypal.env geschrieben ({len(lines)} Zeilen), Dienst neu gestartet.")
ssh.close()
