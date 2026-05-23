# -*- coding: utf-8 -*-
import os
import sys
import traceback

os.chdir("/home/skytycoon")
sys.path.insert(0, "/home/skytycoon")

import server_backend as sb
import wirtschaft_m216_extension as w

print("before_register", "/market/license_shop" in [getattr(r, "path", None) for r in sb.app.routes])
try:
    w.register(sb.app)
    print("register_ok")
except Exception:
    traceback.print_exc()
paths = [getattr(r, "path", None) for r in sb.app.routes]
print("after_register", "/market/license_shop" in paths)
