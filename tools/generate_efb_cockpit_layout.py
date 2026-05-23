#!/usr/bin/env python3
"""Generiert layout.json für skytycoon-efb-cockpit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL_ROOT = ROOT / "skytycoon-efb-cockpit"
EXTS = {".html", ".css", ".js", ".json", ".txt", ".ini"}


def main() -> int:
    if not PANEL_ROOT.is_dir():
        print(f"Fehler: {PANEL_ROOT} fehlt", file=sys.stderr)
        return 1
    entries: list[dict] = []
    for path in sorted(PANEL_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "layout.json" and path.parent == PANEL_ROOT:
            continue
        if path.suffix.lower() not in EXTS and path.suffix.lower() != "":
            continue
        rel = path.relative_to(PANEL_ROOT).as_posix()
        st = path.stat()
        entries.append(
            {"path": rel, "size": int(st.st_size), "date": int(st.st_mtime)}
        )
    out = PANEL_ROOT / "layout.json"
    out.write_text(json.dumps({"content": entries}, indent=2), encoding="utf-8")
    print(f"layout.json ({len(entries)} Dateien) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
