#!/usr/bin/env python3
"""Erzeugt eine SkyTycoon-Rechnungs-Vorschau (DE/EN bilingual) zum Prüfen."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skytycoon_invoice_pdf import write_invoice_preview


def main() -> int:
    out = ROOT / "assets" / "invoice_preview_SKYTYCOON.pdf"
    dest = write_invoice_preview(
        out,
        lang="de",
        bilingual=True,
        pilot_name="Patrick.S",
        customer_email="patrick.s@example.com",
        license_key="ST-AUTO-DEMO-2026-XXXX",
        amount_eur=49.99,
        invoice_id="ST-INV-PREVIEW-001",
        paypal_order_id="PAYPAL-ORDER-DEMO",
        paypal_capture_id="CAPTURE-DEMO",
    )
    print(f"Vorschau geschrieben: {dest}")
    print("Bitte PDF öffnen und Layout prüfen (SkyTycoon Rechnung / Invoice, Dankeschön, Key).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
