#!/usr/bin/env python3
"""
Patcht die installierte FlyByWire-A32NX panel.cfg (VCockpit16 / EFB) für SkyTycoon.
Erstellt vorher eine .bak-Sicherung.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SKYTYCOON_EFB_GAUGE = "htmlgauge00 = InGamePanel, SkyTycoonCockpitEFB, 0,0,1430,1000"
FBW_FOLDER_NAMES = (
    "flybywire-aircraft-a320-neo",
    "flybywire-aircraft-a320-neo-standalone",
    "flybywire-experimental",
)


def _community_root() -> Path | None:
    env = os.environ.get("MSFS_COMMUNITY", "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
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
    return None


def _find_fbw_panel_cfg(community: Path) -> Path | None:
    rel_suffix = Path("SimObjects") / "Airplanes" / "FlyByWire_A320_NEO" / "panel" / "panel.cfg"
    for name in FBW_FOLDER_NAMES:
        cand = community / name / rel_suffix
        if cand.is_file():
            return cand
    for pkg in community.iterdir():
        if not pkg.is_dir():
            continue
        if "flybywire" not in pkg.name.lower() or "a320" not in pkg.name.lower():
            continue
        cand = pkg / rel_suffix
        if cand.is_file():
            return cand
    return None


def _patch_panel_text(text: str) -> tuple[str, bool]:
    if "SkyTycoonCockpitEFB" in text:
        return text, False
    patterns = [
        re.compile(
            r"^htmlgauge00\s*=\s*A32NX/EFB/efb\.html[^\n]*$",
            re.MULTILINE | re.IGNORECASE,
        ),
        re.compile(
            r"^htmlgauge00\s*=\s*A32NX/EFB/efb\.html\?[^\n]*$",
            re.MULTILINE | re.IGNORECASE,
        ),
    ]
    new_text = text
    replaced = False
    for pat in patterns:
        if pat.search(new_text):
            new_text = pat.sub(SKYTYCOON_EFB_GAUGE, new_text, count=1)
            replaced = True
            break
    if not replaced and "[VCockpit16]" in new_text:
        block = re.compile(
            r"(\[VCockpit16\][\s\S]*?)(?=^\[)",
            re.MULTILINE,
        )
        m = block.search(new_text)
        if m:
            sec = m.group(1)
            if "SkyTycoonCockpitEFB" not in sec:
                sec2 = re.sub(
                    r"^htmlgauge00\s*=.*$",
                    SKYTYCOON_EFB_GAUGE,
                    sec,
                    count=1,
                    flags=re.MULTILINE,
                )
                new_text = new_text[: m.start(1)] + sec2 + new_text[m.end(1) :]
                replaced = True
    return new_text, replaced


def main() -> int:
    community = _community_root()
    if community is None:
        print("MSFS Community-Ordner nicht gefunden.", file=sys.stderr)
        return 1
    panel = _find_fbw_panel_cfg(community)
    if panel is None:
        print(
            "FlyByWire A32NX panel.cfg nicht gefunden. "
            "Installiere flybywire-aircraft-a320-neo oder nutze zzz-skytycoon-fbw-a32nx-efb.",
            file=sys.stderr,
        )
        return 1
    raw = panel.read_text(encoding="utf-8", errors="replace")
    patched, changed = _patch_panel_text(raw)
    if not changed:
        print(f"Bereits gepatcht oder unbekanntes Format: {panel}")
        return 0
    bak = panel.with_suffix(".cfg.skytycoon.bak")
    if not bak.is_file():
        bak.write_text(raw, encoding="utf-8")
    panel.write_text(patched, encoding="utf-8")
    print(f"Gepatcht: {panel}")
    print(f"Backup:   {bak}")
    print("Stelle sicher, dass skytycoon-efb-cockpit im Community-Ordner liegt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
