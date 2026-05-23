#!/usr/bin/env python3
"""Generiert layout.json für das MSFS-Paket skytycoon-ingame-panel."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL_ROOT = ROOT / "skytycoon-ingame-panel"
EXTS = {".html", ".css", ".js", ".json"}


def main() -> int:
    if not PANEL_ROOT.is_dir():
        print(f"Fehler: Ordner fehlt: {PANEL_ROOT}", file=sys.stderr)
        return 1
    entries: list[dict] = []
    for path in sorted(PANEL_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "layout.json" and path.parent == PANEL_ROOT:
            continue
        if path.suffix.lower() not in EXTS:
            continue
        rel = path.relative_to(PANEL_ROOT).as_posix()
        st = path.stat()
        entries.append(
            {
                "path": rel,
                "size": int(st.st_size),
                "date": int(st.st_mtime),
            }
        )
    layout = {"content": entries}
    out = PANEL_ROOT / "layout.json"
    out.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    print(f"layout.json geschrieben ({len(entries)} Dateien) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
