#!/usr/bin/env python3
"""Kurzer Live-Check: skytycoon.info APIs + Remote smtp.env (ohne Secrets)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_deploy_env() -> None:
    p = ROOT / ".env.deploy"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _http(method: str, url: str, body: dict | None = None, timeout: float = 18.0) -> tuple[int, str]:
    data = None
    headers = {"User-Agent": "SkyTycoon-HealthCheck/1.0"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")[:500]
    except urllib.error.HTTPError as exc:
        return int(exc.code), (exc.read().decode("utf-8", errors="replace")[:500])


def main() -> int:
    base = (os.environ.get("SKYTYCOON_HEALTH_BASE") or "https://skytycoon.info").rstrip("/")
    print(f"=== API checks ({base}) ===")
    checks = [
        ("GET", f"{base}/api/v1/health", None),
        ("GET", f"{base}/api/v1/public/version.json", None),
        ("GET", f"{base}/api/v1/jobs/available?current_icao=ALL", None),
        ("GET", f"{base}/api/v1/public/job_board_sample", None),
        ("POST", f"{base}/api/v1/auth/login", {}),
        ("POST", f"{base}/api/v1/jobs/accept", {"job_id": 999999, "hardware_id": "test-hwid"}),
    ]
    ok = 0
    for method, url, body in checks:
        code, text = _http(method, url, body)
        tag = "OK" if 200 <= code < 300 else "WARN" if code in (400, 401, 404, 409) else "FAIL"
        if tag == "OK":
            ok += 1
        print(f"[{tag}] {code} {method} {url.split(base)[-1]}")
        if text.strip() and len(text) < 120:
            print(f"      {text.strip()}")
    print(f"API summary: {ok}/{len(checks)} HTTP-2xx")

    _load_deploy_env()
    host = os.environ.get("SKYTYCOON_DEPLOY_HOST", "").strip()
    if not host:
        print("\n=== Remote (skip: no .env.deploy) ===")
        return 0
    try:
        import paramiko
    except ImportError:
        print("\n=== Remote (skip: paramiko missing) ===")
        return 0
    user = os.environ.get("SKYTYCOON_DEPLOY_USER", "").strip()
    pw = os.environ.get("SKYTYCOON_DEPLOY_PASSWORD", "").strip()
    if not user or not pw:
        print("\n=== Remote (skip: deploy credentials) ===")
        return 0
    print(f"\n=== Remote ({host}) ===")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=pw, timeout=30)
    remote_cmds = [
        "test -f /home/skytycoon/smtp.env && echo smtp.env=OK || echo smtp.env=MISSING",
        "grep -c '^SKYTYCOON_SMTP_PASSWORD=.' /home/skytycoon/smtp.env 2>/dev/null || echo 0",
        "test -f /home/skytycoon/paypal.env && echo paypal.env=OK || echo paypal.env=MISSING",
        "systemctl is-active skytycoon.service nginx",
        "tail -n 40 /home/skytycoon/server.log 2>/dev/null | grep -i smtp | tail -n 5",
    ]
    for cmd in remote_cmds:
        _i, stdout, stderr = ssh.exec_command(cmd, timeout=45)
        out = stdout.read().decode("utf-8", "replace").strip()
        if out:
            print(out)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
