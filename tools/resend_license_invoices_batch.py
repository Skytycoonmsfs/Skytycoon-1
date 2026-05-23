#!/usr/bin/env python3
"""
Nachträglicher Versand von Kauf-Mails inkl. bilingualer PDF-Rechnung.
Lokal: nutzt server_backend + SERVER_DB_PATH (oder per SSH auf IONOS ausführen).

  python tools/resend_license_invoices_batch.py --dry-run
  python tools/resend_license_invoices_batch.py --send --limit 200
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Nur zählen, nicht senden")
    ap.add_argument("--send", action="store_true", help="E-Mails wirklich senden")
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()
    if not args.dry_run and not args.send:
        print("Bitte --dry-run oder --send angeben.")
        return 1

    from server_backend import (
        SERVER_DB_PATH,
        _bg_send_license_purchase_confirmation_email_bilingual,
        _paypal_product_eur_amount,
    )

    if not SERVER_DB_PATH.is_file():
        print(f"SERVER_DB nicht gefunden: {SERVER_DB_PATH}")
        return 1

    conn = sqlite3.connect(str(SERVER_DB_PATH))
    try:
        rows = conn.execute(
            """
            SELECT license_key, customer_email, pilot_name, status
            FROM license_keys
            WHERE trim(customer_email) LIKE '%@%'
              AND trim(license_key) != ''
              AND status IN ('activated', 'unused')
            ORDER BY created_ts DESC
            LIMIT ?;
            """,
            (max(1, int(args.limit)),),
        ).fetchall()
    finally:
        conn.close()

    amt = float(_paypal_product_eur_amount())
    print(f"Gefunden: {len(rows)} Lizenz-E-Mails (Limit {args.limit})")
    sent = 0
    for lk, em, pilot, st in rows:
        em_s = str(em or "").strip().lower()
        lk_s = str(lk or "").strip()
        pilot_s = str(pilot or em_s.split("@", 1)[0]).strip() or "Captain"
        print(f"  {'[DRY]' if args.dry_run else '[SEND]'} {em_s} | {lk_s[:24]}... | {st}")
        if args.send and not args.dry_run:
            _bg_send_license_purchase_confirmation_email_bilingual(
                em_s,
                pilot_s,
                lk_s,
                lang="de",
                amount_eur=amt,
            )
            sent += 1
    if args.send:
        print(f"Versand angestoßen: {sent} (Hintergrund-Retry in server_backend).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
