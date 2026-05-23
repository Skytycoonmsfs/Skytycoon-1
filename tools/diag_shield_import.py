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
cmds = [
    "grep -c _SkyPgSafeguardMiddleware /home/skytycoon/server_backend.py",
    "grep -c _sky_global_exception_handler /home/skytycoon/server_backend.py",
    (
        "cd /home/skytycoon && set -a && . ./smtp.env && set +a && "
        "/home/skytycoon/venv/bin/python -c 'import server_backend as sb; "
        "print(\"shield_ok\", hasattr(sb.app, \"exception_handlers\"))'"
    ),
    "curl -sS http://127.0.0.1:8000/api/v1/health",
]
for c in cmds:
    print("===", c[:70], "===")
    _i, o, e = ssh.exec_command(c, timeout=60)
    print(o.read().decode("utf-8", "replace"))
ssh.close()
