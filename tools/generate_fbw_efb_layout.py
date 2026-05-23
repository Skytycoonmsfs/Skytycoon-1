#!/usr/bin/env python3
"""layout.json für zzz-skytycoon-fbw-a32nx-efb."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "zzz-skytycoon-fbw-a32nx-efb"


def main() -> int:
    if not PKG.is_dir():
        print(f"Fehler: {PKG} fehlt", file=sys.stderr)
        return 1
    entries = []
    for path in sorted(PKG.rglob("*")):
        if not path.is_file() or path.name == "layout.json":
            continue
        rel = path.relative_to(PKG).as_posix()
        st = path.stat()
        entries.append(
            {"path": rel, "size": int(st.st_size), "date": int(st.st_mtime)}
        )
    out = PKG / "layout.json"
    out.write_text(json.dumps({"content": entries}, indent=2), encoding="utf-8")
    print(f"layout.json ({len(entries)} Dateien) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
