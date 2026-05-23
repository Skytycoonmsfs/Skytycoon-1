"""
Release-Build: PyInstaller onefile -> Ordner RELEASE/

Voraussetzung: pip install pyinstaller

Optional: app_icon.ico im Projektroot; SimConnect.dll manuell in RELEASE kopieren.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "RELEASE"


def main() -> int:
    main_py = ROOT / "main.py"
    if not main_py.is_file():
        print("main.py nicht gefunden.", file=sys.stderr)
        return 1
    RELEASE.mkdir(parents=True, exist_ok=True)
    (RELEASE / "assets" / "sounds").mkdir(parents=True, exist_ok=True)
    (ROOT / "assets" / "sounds").mkdir(parents=True, exist_ok=True)
    dist_dir = ROOT / "dist"
    if dist_dir.is_dir():
        shutil.rmtree(dist_dir, ignore_errors=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--name",
        "MSFS_Career",
        "--distpath",
        str(RELEASE),
        "--workpath",
        str(ROOT / "build_pyinstaller"),
        "--specpath",
        str(ROOT),
    ]
    icon = ROOT / "app_icon.ico"
    if icon.is_file():
        cmd.extend(["--icon", str(icon)])
    cmd.append(str(main_py))
    print("Starte:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc == 0:
        locales = ROOT / "locales"
        if locales.is_dir():
            shutil.copytree(locales, RELEASE / "locales", dirs_exist_ok=True)
        vex = ROOT / "version.example.json"
        if vex.is_file():
            shutil.copy2(vex, RELEASE / "version.example.json")
        print(f"Fertig. Ausgabe unter: {RELEASE}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
