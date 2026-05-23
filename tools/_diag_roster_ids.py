# -*- coding: utf-8 -*-
import hashlib
import sqlite3
from pathlib import Path

ROOT = Path("/home/skytycoon")
u = sqlite3.connect(str(ROOT / "database" / "ionos_users.sqlite"))


def pid(h: str) -> str:
    return hashlib.sha256(h.encode()).hexdigest()[:16]


print("sqlite users:")
for (h,) in u.execute("SELECT hardware_id FROM users"):
    hs = str(h)
    print(pid(hs), hs[:48])
u.close()

# API ids from last check
want = {"84f696a4e4469f2e", "9c9ce5a00244d7c5", "48a269cbbce974ee", "d2b61b7b5fdfd411"}
print("match wanted:", want)
