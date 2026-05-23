#!/usr/bin/env python3
"""Kopiert skytycoon-efb-cockpit + FBW-A32NX-Override in den MSFS Community-Ordner."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    ("skytycoon-efb-cockpit", ROOT / "skytycoon-efb-cockpit"),
    ("zzz-skytycoon-fbw-a32nx-efb", ROOT / "zzz-skytycoon-fbw-a32nx-efb"),
)


def _default_community() -> Path | None:
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None
    store = (
        Path(local)
        / "Packages"
        / "Microsoft.Limitless_8wekyb3d8bbwe"
        / "LocalCache"
        / "Packages"
        / "Community"
    )
    if store.is_dir():
        return store
    steam = Path(os.environ.get("APPDATA", "")) / "Microsoft Flight Simulator" / "Packages" / "Community"
    if steam.is_dir():
        return steam
    return None


def _copy_pkg(community: Path, folder_name: str, src: Path) -> Path:
    target = community / folder_name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(src, target)
    return target


def main() -> int:
    dest_root = os.environ.get("MSFS_COMMUNITY", "").strip()
    community = Path(dest_root) if dest_root else _default_community()
    if community is None or not community.is_dir():
        print("MSFS Community-Ordner nicht gefunden. Setze MSFS_COMMUNITY=Pfad", file=sys.stderr)
        return 1
    for name, src in PACKAGES:
        if not src.is_dir():
            print(f"Fehler: Quelle fehlt: {src}", file=sys.stderr)
            return 1
        tgt = _copy_pkg(community, name, src)
        print(f"Installiert: {tgt}")
    print()
    print("=== Wichtig ===")
    print("Die Zeile htmlgauge00=... ist KEIN PowerShell-Befehl.")
    print("Sie steht bereits in zzz-skytycoon-fbw-a32nx-efb (panel.cfg Override).")
    print()
    print("Voraussetzungen:")
    print("  1) FlyByWire A32NX (flybywire-aircraft-a320-neo) im Community-Ordner")
    print("  2) SkyTycoon Desktop-App läuft (WebSocket Port 8383)")
    print("  3) MSFS neu starten")
    print()
    print("Alternative (nur eine Zeile im FBW-Original ändern):")
    print("  python tools/patch_fbw_a32nx_panel.py")
    patch = ROOT / "tools" / "patch_fbw_a32nx_panel.py"
    if patch.is_file():
        subprocess.run([sys.executable, str(patch)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
