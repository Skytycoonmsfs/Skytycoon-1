# -*- coding: utf-8 -*-
"""
SkyTycoon Windows Schatten-Wächter (ohne GUI).

- SFTP-Empfang Port 2222 (IONOS → Rechnungen + Backups)
- Alle 2 Stunden: Swiss-Sync-ZIP des Projektordners auf „SkyTycoon Backup (A)“
- Alle 24 Stunden: Speicher-Retention (PDFs bleiben)

Start (Hintergrund):
  pythonw tools/sky_win_background_service.py

Oder sichtbar zum Testen:
  python tools/sky_win_background_service.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from admin_vault_core import (  # noqa: E402
    CAP_MB_DEFAULT,
    PROJECT_ROOT_DEFAULT,
    SWISS_SYNC_INTERVAL_MS,
    SWISS_VOLUME_LABEL,
    VaultSFTPServer,
    find_drive_by_volume_label,
    prune_local_vault,
    run_swiss_sync_to_label_drive,
    vault_root_for_drive,
    zurich_now,
)

LOG_FILE = ROOT / "sky_win_background_service.log"
POLL_SEC = 30
PRUNE_INTERVAL_SEC = 86_400


def _setup_log() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [WIN-VAULT] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("sky_win_vault")


def _resolve_vault() -> tuple[str | None, Path | None]:
    letter = find_drive_by_volume_label(SWISS_VOLUME_LABEL)
    if not letter:
        return None, None
    root = vault_root_for_drive(letter)
    return letter, root


def main() -> int:
    log = _setup_log()
    log.info("Schatten-Wächter gestartet (Projekt: %s)", PROJECT_ROOT_DEFAULT)
    sftp = VaultSFTPServer()
    last_sync = 0.0
    last_prune = 0.0
    sftp_on = False

    while True:
        letter, vault_root = _resolve_vault()
        if letter and vault_root:
            if not sftp_on:
                sftp.set_root(vault_root)
                if sftp.start():
                    log.info("SFTP aktiv auf Port 2222 → %s", vault_root)
                    sftp_on = True
                else:
                    log.warning("SFTP-Start fehlgeschlagen: %s", sftp.last_error)
            now = time.time()
            if now - last_sync >= SWISS_SYNC_INTERVAL_MS / 1000.0:
                ok, msg = run_swiss_sync_to_label_drive(PROJECT_ROOT_DEFAULT)
                if ok:
                    log.info(
                        "Swiss-Sync OK %s → %s",
                        zurich_now().strftime("%Y-%m-%d %H:%M:%S"),
                        msg,
                    )
                elif msg == "no_drive":
                    log.warning("Swiss-Sync: Laufwerk '%s' nicht gefunden", SWISS_VOLUME_LABEL)
                else:
                    log.error("Swiss-Sync fehlgeschlagen: %s", msg)
                last_sync = now
            if now - last_prune >= PRUNE_INTERVAL_SEC:
                stats = prune_local_vault(vault_root, cap_mb=CAP_MB_DEFAULT)
                log.info("Retention: %s", stats)
                last_prune = now
        else:
            if sftp_on:
                sftp.stop()
                sftp_on = False
            log.warning(
                "Warte auf Festplatte mit Label '%s' …",
                SWISS_VOLUME_LABEL,
            )
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("[WIN-VAULT] Beendet.")
        raise SystemExit(0) from None
