#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TLS-Zertifikat prüfen (Let's Encrypt / manueller PEM-Pfad).

Beispiel:
  python cert_checker.py --host skytycoon.info --port 443
  python cert_checker.py --pem /etc/letsencrypt/live/skytycoon.info/fullchain.pem

Exit-Code 0 = OK, 1 = abgelaufen oder Fehler, 2 = fehlende Abhängigkeit bei --pem.
"""

from __future__ import annotations

import argparse
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path


def _from_socket(host: str, port: int) -> tuple[str, datetime]:
    ctx = ssl.create_default_context()
    with ctx.wrap_socket(ssl.socket(), server_hostname=host) as sock:
        sock.settimeout(12)
        sock.connect((host, port))
        cert = sock.getpeercert()
    nb = cert.get("notAfter")
    if not nb:
        raise RuntimeError("Kein notAfter im Zertifikat")
    exp = datetime.strptime(nb, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    return host, exp


def _from_pem(path: Path) -> tuple[str, datetime]:
    import hashlib  # noqa: PLC0415

    data = path.read_bytes()
    try:
        from cryptography import x509  # noqa: PLC0415
        from cryptography.hazmat.backends import default_backend  # noqa: PLC0415
    except ImportError:
        print(
            "[FEHLER] Paket 'cryptography' fehlt. Installieren: pip install cryptography",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    cert = x509.load_pem_x509_certificate(data, default_backend())
    exp_naive = cert.not_valid_after
    exp = exp_naive.replace(tzinfo=timezone.utc)
    tag = hashlib.sha256(data).hexdigest()[:12]
    return f"{path}#{tag}", exp
    p = argparse.ArgumentParser(description="SSL/TLS-Zertifikat Ablauf prüfen")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--host", help="Domain (SNI)")
    p.add_argument("--port", type=int, default=443)
    g.add_argument("--pem", type=Path, help="Pfad zu fullchain.pem")
    p.add_argument(
        "--warn-days",
        type=int,
        default=21,
        help="Warnung wenn Restlaufzeit < N Tage (Standard 21)",
    )
    args = p.parse_args()

    try:
        if args.host:
            label, exp = _from_socket(args.host, args.port)
        else:
            label, exp = _from_pem(args.pem)
    except Exception as exc:  # noqa: BLE001
        print(f"[FEHLER] {exc}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    left = (exp - now).total_seconds() / 86400.0
    print(f"Ziel: {label}")
    print(f"Ablauf (UTC): {exp.isoformat()}")
    print(f"Verbleibend: ca. {left:.1f} Tage")
    if left < 0:
        print("[KRITISCH] Zertifikat ist abgelaufen.")
        return 1
    if left < args.warn_days:
        print(f"[WARNUNG] Weniger als {args.warn_days} Tage – Renewal einplanen.")
    print("[OK]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
