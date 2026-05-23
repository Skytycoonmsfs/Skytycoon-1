# -*- coding: utf-8 -*-
"""Erzeugt echte Kabinen-Ansagen (Windows SAPI) in assets/sounds/."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import skytycoon_extensions as ext  # noqa: E402


def main() -> int:
    import main as main_mod

    roots = [
        Path(main_mod.BASE_DIR) / "assets" / "sounds",
        Path.cwd() / "assets" / "sounds",
    ]
    for r in roots:
        r.mkdir(parents=True, exist_ok=True)
    n = ext._ensure_platin_cabin_voice_files(main_mod, roots)
    print(f"[OK] {n} Kabinen-WAVs mit Sprachsynthese erzeugt/aktualisiert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
