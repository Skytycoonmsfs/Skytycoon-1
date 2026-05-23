# Fehlende — nach fehler4-Abarbeitung

**Stand:** 2026-05-20 · **Build:** `20260520-fehler4-v8`

---

## Abschnitt D — erledigt

| Punkt | Status |
|-------|--------|
| `login_widget` | ✅ Ersatz: `_PlatinLoginOverlay` → `win.login_widget` |
| Patrick.S / HWID Slot 2 | ✅ Server `auth/login` + `cloud_sync` Repair-first |
| CDN WAV / Audio | ✅ `download_cabin_sounds.py` + 56 WAV + QSoundEffect 75% |
| PyInstaller EXE | ✅ `dist\main.exe` neu (hiddenimports in `main.spec`) |
| EFB-Tab | 🔒 nur Dialog in main.py — kein Hub-Tab |
| Bank umbenennen | ✅ Hub-Tab „🏦 Bank“ (Extensions, ohne Layout) |

---

## Nur noch vom Pilot testen

1. `python main.py` oder `dist\main.exe`
2. Logout → Vollbild-Login
3. Patrick.S Login
4. Pax-Tab Audio

---

*Details: `fehler4.txt` · Vorher: `fehler3.txt`, `fehler2.txt`*
