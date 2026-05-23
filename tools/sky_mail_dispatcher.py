#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyTycoon — 5 Auto-Wächter (Cron auf IONOS).

Beispiel Crontab (stündlich):
  0 * * * * cd /home/skytycoon && /usr/bin/python3 tools/sky_mail_dispatcher.py >> server_logs/mail_dispatcher.log 2>&1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import server_backend as sb

    try:
        sb._refresh_smtp_env()
        stats = sb.run_mail_dispatcher_guards()
        print("[mail-dispatcher]", stats)
        return 0
    except Exception as exc:
        print("[mail-dispatcher] FATAL:", exc)
        try:
            sb._append_admin_log(f"[mail-dispatcher] FATAL: {exc!r}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
