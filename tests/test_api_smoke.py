"""Smoke tests without pytest (stdlib only)."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_server():
    spec = importlib.util.spec_from_file_location(
        "server_backend", ROOT / "server_backend.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["server_backend"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_password_hash_roundtrip() -> None:
    sb = _load_server()
    plain = "TestPilot_42"
    stored = sb._user_password_hash_store(plain)
    assert stored and len(stored) > 8
    assert sb._password_verify_db("bcrypt", stored, plain)
    assert not sb._password_verify_db("bcrypt", stored, "wrong")


def main() -> int:
    test_password_hash_roundtrip()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
