# -*- coding: utf-8 -*-
"""Zentrale Pfade — Produktion auf Laufwerk A:\\."""
from __future__ import annotations

import os
from pathlib import Path

SKYTYCOON_PROJECT_ROOT = Path(
    os.environ.get("SKYTYCOON_PROJECT_ROOT") or r"A:\SkyTycoon"
).resolve()
SKYTYCOON_BACKUP_ROOT = Path(
    os.environ.get("SKYTYCOON_SWISS_BACKUP_ROOT") or r"A:\SkyTycoon_Backups"
).resolve()
