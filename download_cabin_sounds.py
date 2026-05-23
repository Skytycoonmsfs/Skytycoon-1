# -*- coding: utf-8 -*-
"""CDN-Download + Windows-SAPI-Stimmen — keine Pieps-Synthese (Forward-Slash für QSoundEffect)."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import requests

CDN_BASES: tuple[str, ...] = (
    "https://skytycoon.info/static/cabin_sounds/",
    "https://skytycoon.info/assets/sounds/",
    "https://skytycoon.info/static/sounds/",
)

CABIN_KEYS: tuple[str, ...] = (
    "welcome_boarding",
    "safety_briefing",
    "seatbelt_on",
    "seatbelt_off",
    "takeoff",
    "cruise",
    "descent",
    "landing",
    "thank_you",
    "turbulence",
    "duty_free",
    "prepare_landing",
)


def announcement_filenames() -> list[str]:
    names: list[str] = []
    for key in CABIN_KEYS:
        for lo in ("de", "en"):
            for gender in ("female", "male"):
                names.append(f"{key}_{lo}_{gender}.wav")
    return names


def forward_sound_path(root: Path | str, filename: str) -> str:
    """Absoluter Pfad nur mit / — für QUrl.fromLocalFile."""
    return str((Path(root) / filename).resolve()).replace("\\", "/")


def download_one(
    session: requests.Session,
    root: Path,
    filename: str,
    *,
    min_bytes: int = 128,
) -> bool:
    dest = root / filename
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        return True
    for base in CDN_BASES:
        url = f"{base.rstrip('/')}/{filename}"
        try:
            r = session.get(url, timeout=28)
            if r.status_code == 200 and len(r.content) >= min_bytes:
                dest.write_bytes(r.content)
                return True
        except (requests.RequestException, OSError, ValueError):
            continue
    return dest.is_file() and dest.stat().st_size >= min_bytes


def download_all(root: Path | str) -> int:
    """Blockierend: fehlende WAVs laden. Rückgabe = Anzahl neu geschriebener Dateien."""
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "SkyTycoonPro/1.0"})
    written = 0
    for fname in announcement_filenames():
        before = (target / fname).is_file()
        if download_one(session, target, fname):
            if not before and (target / fname).is_file():
                written += 1
    cwd_root = Path(os.getcwd()) / "assets" / "sounds"
    if cwd_root.resolve() != target.resolve():
        cwd_root.mkdir(parents=True, exist_ok=True)
        for fname in announcement_filenames():
            src = target / fname
            if src.is_file() and src.stat().st_size >= 128:
                dest = cwd_root / fname
                if not dest.is_file() or dest.stat().st_size < 128:
                    try:
                        dest.write_bytes(src.read_bytes())
                    except OSError:
                        pass
    try:
        import types

        import skytycoon_extensions as ext

        stub = types.SimpleNamespace(
            BASE_DIR=ROOT,
            SKYTYCOON_APP_NAME="SkyTycoon Pro",
        )
        roots = [target, Path(os.getcwd()) / "assets" / "sounds"]
        written += int(
            ext._ensure_platin_cabin_voice_files(stub, roots) or 0  # type: ignore[arg-type]
        )
    except Exception:
        pass
    return written


def download_all_async(
    root: Path | str,
    *,
    on_done: Any | None = None,
) -> threading.Thread:
    """Daemon-Thread — kein Blockieren der Qt-GUI."""

    def _run() -> None:
        try:
            download_all(root)
        finally:
            if callable(on_done):
                try:
                    on_done()
                except Exception:
                    pass

    th = threading.Thread(target=_run, name="cabin-sounds-cdn", daemon=True)
    th.start()
    return th
