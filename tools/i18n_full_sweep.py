#!/usr/bin/env python3
"""
Vollständiger i18n-Sweep für main.py:
- QMessageBox-Titel/Text (Literal-Strings ohne self._tr)
- setWindowTitle / QDialog-Titel in MainWindow-Kontext
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
TRANS = ROOT / "locales" / "translations.json"

RE_MSG_SELF_2 = re.compile(
    r'QMessageBox\.(warning|information|critical|question)\(\s*self,\s*'
    r'"((?:[^"\\]|\\.)*)"\s*,\s*'
    r'"((?:[^"\\]|\\.)*)"\s*(\)|,)',
    re.MULTILINE,
)

RE_MSG_SELF_TITLE_ONLY = re.compile(
    r'QMessageBox\.(warning|information|critical|question)\(\s*self,\s*'
    r'"((?:[^"\\]|\\.)*)"\s*,\s*(?!self\._tr)(?!i18n_db)',
    re.MULTILINE,
)

RE_SET_TITLE = re.compile(
    r'(\w+)\.setWindowTitle\(\s*"((?:[^"\\]|\\.)*)"\s*\)',
    re.MULTILINE,
)

RE_DLG_MSG = re.compile(
    r'QMessageBox\.(warning|information|critical)\(\s*(\w+),\s*'
    r'"((?:[^"\\]|\\.)*)"\s*,\s*'
    r'(?:"((?:[^"\\]|\\.)*)"|f"([^"]*)")',
    re.MULTILINE,
)

SKIP_TITLE_PREFIXES = ("ui.", "broker.", "job.", "market.", "hangar.", "security.", "startup.")


def _key(text: str, prefix: str = "ui.auto") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()[:48]).strip("_") or "msg"
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}.{slug}_{h}"


def _en_guess(de: str) -> str:
    """Einfache DE→EN-Heuristik für häufige UI-Phrasen."""
    m = {
        "Flug-Börse": "Job board",
        "Flug-Historie (AAR)": "Flight history (AAR)",
        "SimBrief": "SimBrief",
        "PDF": "PDF",
        "Karte": "Map",
        "Export": "Export",
        "Beladung": "Loading",
        "Dispatch": "Dispatch",
        "Boarding": "Boarding",
        "Wartung": "Maintenance",
        "Kauf": "Purchase",
        "Hangar": "Hangar",
        "Versicherung": "Insurance",
        "Nicht genug Credits.": "Not enough credits.",
        "Kein aktiver Auftrag.": "No active assignment.",
        "Ungültige Zeilendaten.": "Invalid row data.",
    }
    if de in m:
        return m[de]
    if de.startswith("Gespeichert:"):
        return de.replace("Gespeichert:", "Saved:")
    if "fehlgeschlagen" in de.lower():
        return de.replace("fehlgeschlagen", "failed").replace("Import", "Import")
    return de


def main() -> int:
    text = MAIN.read_text(encoding="utf-8")
    data = json.loads(TRANS.read_text(encoding="utf-8"))
    de_map: dict[str, str] = data.setdefault("de", {})
    en_map: dict[str, str] = data.setdefault("en", {})
    n = 0

    def register(key: str, de: str) -> None:
        nonlocal n
        if key not in de_map:
            de_map[key] = de
            en_map.setdefault(key, _en_guess(de))
            n += 1

    def wrap_tr(s: str, de: str) -> str:
        k = _key(de)
        register(k, de)
        esc = de.replace("\\", "\\\\").replace('"', '\\"')
        return f'self._tr("{k}", "{esc}")'

    def repl_msg2(m: re.Match[str]) -> str:
        method, title, body, tail = m.group(1), m.group(2), m.group(3), m.group(4)
        if title.startswith("self._tr") or body.startswith("self._tr"):
            return m.group(0)
        return (
            f"QMessageBox.{method}(self, {wrap_tr('t', title)}, "
            f"{wrap_tr('b', body)}{tail}"
        )

    text, c1 = RE_MSG_SELF_2.subn(repl_msg2, text)

    def repl_set_title(m: re.Match[str]) -> str:
        obj, title = m.group(1), m.group(2)
        if obj != "dlg" and obj not in ("self", "box", "win", "dialog"):
            return m.group(0)
        if any(title.startswith(p) for p in SKIP_TITLE_PREFIXES):
            return m.group(0)
        k = _key(title, "ui.win")
        register(k, title)
        esc = title.replace("\\", "\\\\").replace('"', '\\"')
        if obj == "self":
            return f'self.setWindowTitle(self._tr("{k}", "{esc}"))'
        return f'{obj}.setWindowTitle(self._tr("{k}", "{esc}"))'

    text, c2 = RE_SET_TITLE.subn(repl_set_title, text)

    # QMessageBox(self, "Title", f"..." ) — nur Titel
    def repl_title_f(m: re.Match[str]) -> str:
        method, title = m.group(1), m.group(2)
        if any(title.startswith(p) for p in SKIP_TITLE_PREFIXES):
            return m.group(0)
        return f'QMessageBox.{method}(self, {wrap_tr("t", title)}, '

    text, c3 = RE_MSG_SELF_TITLE_ONLY.subn(repl_title_f, text)

    def repl_dlg(m: re.Match[str]) -> str:
        method, dlg, title, body, fbody = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        if fbody:
            return m.group(0)
        if not body:
            return m.group(0)
        wt = wrap_tr("t", title)
        wb = wrap_tr("b", body)
        return f"QMessageBox.{method}({dlg}, {wt}, {wb})"

    text, c4 = RE_DLG_MSG.subn(repl_dlg, text)

    # Manuelle Hotfixes für häufige verbleibende Literale
    manual: list[tuple[str, str]] = [
        (
            'QMessageBox.warning(\n                self, "Flug-Börse", f"Du besitzt „{req}“ nicht im Hangar."\n            )',
            'QMessageBox.warning(\n                self,\n                self._tr("job.board_title", "Flug-Börse"),\n                self._tr(\n                    "job.err_no_model_in_hangar",\n                    \'Du besitzt „{req}“ nicht im Hangar.\',\n                ).format(req=req),\n            )',
        ),
        (
            'QMessageBox.warning(\n                self,\n                "Flug-Börse",\n                f"Dein Rang-Level ({lvl}) reicht nicht (benötigt {job.get(\'min_level\')}).",\n            )',
            'QMessageBox.warning(\n                self,\n                self._tr("job.board_title", "Flug-Börse"),\n                self._tr(\n                    "job.err_level_low",\n                    "Dein Rang-Level ({lvl}) reicht nicht (benötigt {need}).",\n                ).format(lvl=lvl, need=job.get("min_level")),\n            )',
        ),
        (
            'QMessageBox.warning(\n                self,\n                "Flug-Börse",\n                f"Im Simulator muss das passende Flugzeug geladen sein (erwartet: „{req}“).",\n            )',
            'QMessageBox.warning(\n                self,\n                self._tr("job.board_title", "Flug-Börse"),\n                self._tr(\n                    "job.err_wrong_aircraft_loaded",\n                    \'Im Simulator muss das passende Flugzeug geladen sein (erwartet: „{req}“).\',\n                ).format(req=req),\n            )',
        ),
        (
            'dlg.setWindowTitle("Flug-Historie (AAR)")',
            'dlg.setWindowTitle(self._tr("flight.history_title", "Flug-Historie (AAR)"))',
        ),
        (
            'QMessageBox.information(\n            self,\n            "SimBrief",\n            "OFP-Daten übernommen. Route und Massen siehe unter „SimBrief OFP“.",\n        )',
            'QMessageBox.information(\n            self,\n            self._tr("ui.msg.simbrief", "SimBrief"),\n            self._tr(\n                "simbrief.import_ok",\n                "OFP-Daten übernommen. Route und Massen siehe unter „SimBrief OFP“.",\n            ),\n        )',
        ),
    ]
    for old, new in manual:
        if old in text:
            text = text.replace(old, new, 1)
            if "job.err_no_model" in new:
                for lang, key, val in (
                    ("de", "job.err_no_model_in_hangar", 'Du besitzt „{req}“ nicht im Hangar.'),
                    ("en", "job.err_no_model_in_hangar", 'You do not own "{req}" in the hangar.'),
                    ("de", "job.err_level_low", "Dein Rang-Level ({lvl}) reicht nicht (benötigt {need})."),
                    ("en", "job.err_level_low", "Your rank level ({lvl}) is too low (requires {need})."),
                    ("de", "job.err_wrong_aircraft_loaded", 'Im Simulator muss das passende Flugzeug geladen sein (erwartet: „{req}“).'),
                    ("en", "job.err_wrong_aircraft_loaded", 'The correct aircraft must be loaded in the simulator (expected: "{req}").'),
                    ("de", "flight.history_title", "Flug-Historie (AAR)"),
                    ("en", "flight.history_title", "Flight history (AAR)"),
                    ("de", "simbrief.import_ok", "OFP-Daten übernommen. Route und Massen siehe unter „SimBrief OFP“."),
                    ("en", "simbrief.import_ok", "OFP data applied. See route and masses under SimBrief OFP."),
                ):
                    data[lang][key] = val

    MAIN.write_text(text, encoding="utf-8")
    TRANS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"i18n sweep: {n} neue Keys, QMessageBox={c1}+{c3}, setWindowTitle={c2}, dlg={c4}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
