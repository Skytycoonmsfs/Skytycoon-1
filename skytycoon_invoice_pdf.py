# -*- coding: utf-8 -*-
"""SkyTycoon PayPal-Rechnung PDF — DE/EN bilingual, Schwarz/Gold/Cyber-Blau."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from fpdf import FPDF


def _lang_is_en(lang: str) -> bool:
    return str(lang or "de").strip().lower().startswith("en")


def _ascii(s: str) -> str:
    return (
        (s or "")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("€", "EUR")
        .encode("ascii", "replace")
        .decode("ascii")
    )


def build_license_invoice_pdf(
    *,
    lang: str,
    pilot_name: str,
    customer_email: str,
    license_key: str,
    amount_eur: float,
    invoice_id: str,
    paypal_capture_id: str = "",
    paypal_order_id: str = "",
    bilingual: bool = True,
) -> bytes:
    """Rechnung als PDF — Standard: DE+EN auf einem Dokument."""
    pilot = (pilot_name or "Captain").strip()[:120] or "Captain"
    email = (customer_email or "").strip()[:200]
    lk = (license_key or "").strip()
    inv = (invoice_id or "ST-INV").strip()[:48]
    cap = (paypal_capture_id or "").strip()[:64]
    oid = (paypal_order_id or "").strip()[:64]
    amt = f"{float(amount_eur):.2f}"
    utc_ts = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.set_fill_color(11, 15, 25)
    pdf.rect(0, 0, 210, 297, style="F")
    pdf.set_draw_color(0, 162, 255)
    pdf.set_line_width(0.6)
    pdf.rect(10, 10, 190, 277, style="D")
    pdf.set_draw_color(212, 175, 55)
    pdf.set_line_width(0.4)
    pdf.rect(12, 12, 186, 273, style="D")

    pdf.set_text_color(0, 162, 255)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_xy(18, 18)
    if bilingual:
        pdf.cell(0, 10, _ascii("SkyTycoon Rechnung / SkyTycoon Invoice"), ln=1)
    elif _lang_is_en(lang):
        pdf.cell(0, 10, _ascii("SkyTycoon Invoice"), ln=1)
    else:
        pdf.cell(0, 10, _ascii("SkyTycoon Rechnung"), ln=1)

    pdf.set_text_color(138, 199, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(18)
    pdf.cell(0, 7, _ascii("SkyTycoon Pro Lifetime License · PayPal Live"), ln=1)

    pdf.set_text_color(212, 175, 55)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_x(18)
    if bilingual:
        pdf.cell(0, 8, _ascii("STATUS: BEZAHLT / PAID (PayPal)"), ln=1)
    elif _lang_is_en(lang):
        pdf.cell(0, 8, _ascii("STATUS: PAID (PayPal)"), ln=1)
    else:
        pdf.cell(0, 8, _ascii("STATUS: BEZAHLT (PayPal)"), ln=1)

    def _block(title: str, rows: list[tuple[str, str]], y_start: float) -> float:
        pdf.set_text_color(0, 162, 255)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_xy(18, y_start)
        pdf.cell(0, 7, _ascii(title), ln=1)
        y = pdf.get_y() + 2
        for label, value in rows:
            pdf.set_xy(18, y)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(120, 140, 160)
            pdf.cell(52, 6, _ascii(f"{label}:"), ln=0)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(236, 236, 240)
            pdf.multi_cell(118, 6, _ascii(str(value)[:500]))
            y = pdf.get_y() + 2
        return y

    base_rows = [
        ("Rechnungs-Nr. / Invoice No.", inv),
        ("Datum (UTC)", utc_ts),
        ("Kunde / Customer", pilot),
        ("E-Mail", email),
        ("Betrag / Amount", f"EUR {amt}"),
    ]
    if oid:
        base_rows.append(("PayPal Order", oid))
    if cap:
        base_rows.append(("PayPal Capture", cap))

    y = _block("Rechnungsdaten / Invoice Data", base_rows, 52)

    pdf.set_fill_color(20, 28, 42)
    pdf.set_draw_color(0, 162, 255)
    pdf.rect(16, y + 4, 178, 28, style="FD")
    pdf.set_text_color(138, 199, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(20, y + 8)
    pdf.cell(0, 6, _ascii("Lizenzschlüssel / License Key"), ln=1)
    pdf.set_text_color(0, 255, 120)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_x(20)
    pdf.multi_cell(170, 8, _ascii(lk or "-"))
    y = pdf.get_y() + 10

    pdf.set_text_color(255, 220, 100)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_xy(18, y)
    if bilingual:
        pdf.cell(0, 12, _ascii("VIELEN DANK! / THANK YOU SO MUCH!"), ln=1)
    elif _lang_is_en(lang):
        pdf.cell(0, 12, _ascii("THANK YOU SO MUCH!"), ln=1)
    else:
        pdf.cell(0, 12, _ascii("VIELEN DANK!"), ln=1)

    pdf.set_text_color(200, 210, 220)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(18)
    if bilingual:
        pdf.multi_cell(
            174,
            5,
            _ascii(
                "DE: Willkommen bei SkyTycoon Pro! Starten Sie die Desktop-App, melden Sie sich "
                "mit Ihrer E-Mail an und tragen Sie den Lizenzschlüssel beim Erststart ein.\n"
                "EN: Welcome aboard SkyTycoon Pro! Launch the desktop app, sign in with your "
                "e-mail and enter the license key on first start."
            ),
        )
    elif _lang_is_en(lang):
        pdf.multi_cell(
            174,
            5,
            _ascii(
                "Welcome aboard SkyTycoon Pro! Launch the desktop app, sign in with your e-mail "
                "and enter the license key on first start."
            ),
        )
    else:
        pdf.multi_cell(
            174,
            5,
            _ascii(
                "Willkommen bei SkyTycoon Pro! Starten Sie die Desktop-App, melden Sie sich mit "
                "Ihrer E-Mail an und tragen Sie den Lizenzschlüssel beim Erststart ein."
            ),
        )

    pdf.set_text_color(120, 130, 140)
    pdf.set_xy(18, 268)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(
        0,
        5,
        _ascii("skytycoon.info · info@skytycoon.info · noreply@skytycoon.info"),
        ln=0,
    )

    out = BytesIO()
    try:
        pdf.output(out)
        return out.getvalue()
    finally:
        out.close()


def write_invoice_preview(path: str | Any, **kwargs: Any) -> Path:
    """Schreibt eine Vorschau-PDF auf die Platte (Admin/Entwicklung)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = build_license_invoice_pdf(**kwargs)
    dest.write_bytes(data)
    return dest
