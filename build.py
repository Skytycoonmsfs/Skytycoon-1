"""
PyInstaller-Build für MSFS Career Tool (Meilenstein 26).

Voraussetzungen: pip install pyinstaller pyinstaller-hooks-contrib

Hinweise:
- SimConnect.dll: aus dem MSFS SDK / SimConnect-Client-Paket manuell neben die .exe legen
  oder mit --add-binary einbinden (Pfad anpassen).
- WASM/MobiFlight: liegt im MSFS Community-Ordner, nicht in dieser .exe.
- Daten assets: optional Ordner data/ anlegen und mit --add-data einbinden (Windows: data;data).

Beispiel (PowerShell, im Projektordner):

  python build.py

Angepasstes Kommando mit Icon + Daten (Pfade prüfen):

  pyinstaller --noconsole --onefile --name MSFS_Career ^
    --icon=app_icon.ico ^
    --add-data "data;data" ^
    main.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    main_py = ROOT / "main.py"
    if not main_py.is_file():
        print("main.py nicht gefunden.", file=sys.stderr)
        return 1
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name",
        "MSFS_Career",
    ]
    icon = ROOT / "app_icon.ico"
    if icon.is_file():
        cmd.extend(["--icon", str(icon)])
    data_dir = ROOT / "data"
    if data_dir.is_dir():
        cmd.extend(["--add-data", f"{data_dir.name};{data_dir.name}"])
    cmd.append(str(main_py))
    print("Starte:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
