# -*- coding: utf-8 -*-
"""Prüft, ob main.py die aktuellen UI-Marker enthält (ohne App zu starten)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

MARKERS = (
    "MAIN_UI_BUILD = \"20260523-crew-cyber-v2\"",
    "crew_tab_root",
    "_CREW_TILE_BUTTON_STYLE",
    "crew_pay_mgmt_box.hide()",
    "scroll_hr_portal",
)


def main() -> int:
    if not MAIN.is_file():
        print(f"FEHLER: {MAIN} nicht gefunden")
        return 1
    text = MAIN.read_text(encoding="utf-8", errors="replace")
    print(f"main.py: {MAIN}")
    print(f"Zeilen: {len(text.splitlines())}")
    ok = True
    for m in MARKERS:
        hit = m in text
        print(f"  [{'OK' if hit else 'FEHLT'}] {m}")
        ok = ok and hit
    if ok:
        print("\nOK: Datei enthaelt die Layout-Patches. Start: START_SKYTYCOON_DEV.bat")
    else:
        print("\nFEHLER: main.py ist veraltet oder wurde zurueckgesetzt.")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
