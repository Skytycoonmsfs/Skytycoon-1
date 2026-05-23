#!/usr/bin/env python3
"""Ersetzt häufige hardcodierte QMessageBox-Texte in main.py durch self._tr(...)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
TRANS = ROOT / "locales" / "translations.json"

REPLACEMENTS: list[tuple[str, str, str, str]] = [
    (
        r'QMessageBox\.information\(self, self\._tr\("ui\.msg\.sound_download", "Sound-Download"\), "Sound-Paket ist vollständig\."\)',
        'QMessageBox.information(self, self._tr("ui.msg.sound_download", "Sound-Download"), self._tr("ui.msg.sound_complete", "Sound-Paket ist vollständig."))',
        "ui.msg.sound_complete",
        "Sound-Paket ist vollständig.",
    ),
    (
        r'QMessageBox\.warning\(self, self\._tr\("ui\.msg\.preflight", "Pre-Flight"\), "Nicht genug Credits\."\)',
        'QMessageBox.warning(self, self._tr("ui.msg.preflight", "Pre-Flight"), self._tr("ui.msg.not_enough_credits", "Nicht genug Credits."))',
        "ui.msg.not_enough_credits",
        "Nicht genug Credits.",
    ),
    (
        r'QMessageBox\.warning\(self, self\._tr\("ui\.msg\.job_board", "Flug-Börse"\), "Ungültige Zeilendaten\."\)',
        'QMessageBox.warning(self, self._tr("ui.msg.job_board", "Flug-Börse"), self._tr("ui.msg.invalid_row", "Ungültige Zeilendaten."))',
        "ui.msg.invalid_row",
        "Ungültige Zeilendaten.",
    ),
    (
        r'QMessageBox\.information\(self, self\._tr\("ui\.msg\.loading", "Beladung"\), "Kein aktiver Auftrag\."\)',
        'QMessageBox.information(self, self._tr("ui.msg.loading", "Beladung"), self._tr("ui.msg.no_active_job", "Kein aktiver Auftrag."))',
        "ui.msg.no_active_job",
        "Kein aktiver Auftrag.",
    ),
    (
        r'QMessageBox\.warning\(self, self\._tr\("ui\.msg\.insurance", "Versicherung"\), "Nicht genug Credits für Erstprämie\."\)',
        'QMessageBox.warning(self, self._tr("ui.msg.insurance", "Versicherung"), self._tr("ui.msg.insurance_no_credits", "Nicht genug Credits für Erstprämie."))',
        "ui.msg.insurance_no_credits",
        "Nicht genug Credits für Erstprämie.",
    ),
    (
        r'QMessageBox\.information\(self, self\._tr\("ui\.msg\.insurance", "Versicherung"\), "Versicherung gekündigt\."\)',
        'QMessageBox.information(self, self._tr("ui.msg.insurance", "Versicherung"), self._tr("ui.msg.insurance_cancelled", "Versicherung gekündigt."))',
        "ui.msg.insurance_cancelled",
        "Versicherung gekündigt.",
    ),
    (
        r'QMessageBox\.warning\(self, self\._tr\("ui\.msg\.hangar", "Hangar"\), "Kein Flugzeug im Hangar-Match\."\)',
        'QMessageBox.warning(self, self._tr("ui.msg.hangar", "Hangar"), self._tr("ui.msg.hangar_no_match", "Kein Flugzeug im Hangar-Match."))',
        "ui.msg.hangar_no_match",
        "Kein Flugzeug im Hangar-Match.",
    ),
]


def main() -> int:
    text = MAIN.read_text(encoding="utf-8")
    data = json.loads(TRANS.read_text(encoding="utf-8"))
    n = 0
    for pattern, repl, key, de in REPLACEMENTS:
        new_text, count = re.subn(pattern, repl, text)
        if count:
            text = new_text
            n += count
            for lang in ("de", "en"):
                data.setdefault(lang, {})[key] = de if lang == "de" else {
                    "ui.msg.sound_complete": "Sound pack is complete.",
                    "ui.msg.not_enough_credits": "Not enough credits.",
                    "ui.msg.invalid_row": "Invalid row data.",
                    "ui.msg.no_active_job": "No active assignment.",
                    "ui.msg.insurance_no_credits": "Not enough credits for initial premium.",
                    "ui.msg.insurance_cancelled": "Insurance cancelled.",
                    "ui.msg.hangar_no_match": "No aircraft in hangar match.",
                }.get(key, de)
    MAIN.write_text(text, encoding="utf-8")
    TRANS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"main.py: {n} Ersetzungen; translations.json aktualisiert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
