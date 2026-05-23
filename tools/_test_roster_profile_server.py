# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server_backend as sb

pid = "84f696a4e4469f2e"
h = sb._roster_resolve_hardware_id(pid)
print("hid", h)
p = sb._public_roster_profile(pid)
print("prof", bool(p), (p or {}).get("credits_fmt"))
ps = sb._public_roster_profile_sqlite(h)
print("sqlite_prof", bool(ps), (ps or {}).get("credits_fmt"))
