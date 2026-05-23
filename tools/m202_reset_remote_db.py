#!/usr/bin/env python3
"""Meilenstein 202: Alte Server-DBs auf IONOS löschen und Dienst neu starten."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deploy_system import (  # noqa: E402
    _load_deploy_env_from_known_locations,
    _paramiko_ssh_connect,
    execute_ssh_commands,
)


def main() -> int:
    _, loaded = _load_deploy_env_from_known_locations()
    host = os.environ.get("SKYTYCOON_DEPLOY_HOST", "").strip()
    user = os.environ.get("SKYTYCOON_DEPLOY_USER", "").strip()
    port = int(os.environ.get("SKYTYCOON_DEPLOY_PORT", "22"))
    password = os.environ.get("SKYTYCOON_DEPLOY_PASSWORD", "").strip()
    key_path = os.environ.get("SKYTYCOON_DEPLOY_KEY_PATH", "").strip()
    key_pass = os.environ.get("SKYTYCOON_DEPLOY_KEY_PASSPHRASE", "").strip() or password
    remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon").rstrip("/")

    if not host or not user or (not password and not key_path):
        print("[FEHLER] Deploy-Zugangsdaten fehlen (.env.deploy).", file=sys.stderr)
        return 2

    try:
        import paramiko
    except ImportError:
        print("[FEHLER] pip install paramiko", file=sys.stderr)
        return 3

    if loaded:
        print(f"[INFO] Env: {', '.join(str(p) for p in loaded)}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    _paramiko_ssh_connect(
        ssh,
        host=host,
        port=port,
        user=user,
        password=password,
        key_path=key_path,
        key_passphrase=key_pass,
    )
    ok = execute_ssh_commands(
        ssh,
        [
            f"cd {remote}",
            f"sudo rm -f {remote}/database/skytycoon_server.db",
            f"sudo rm -f {remote}/database/ionos_users.sqlite",
            "sudo systemctl restart skytycoon.service",
            "sleep 2",
            "sudo systemctl is-active skytycoon.service",
            f"tail -n 8 {remote}/server.log 2>/dev/null || true",
        ],
    )
    ssh.close()
    print("[M202] Remote-DB-Reset", "OK" if ok else "FEHLGESCHLAGEN")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
