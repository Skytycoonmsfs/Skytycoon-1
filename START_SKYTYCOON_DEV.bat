@echo off
REM Startet die AKTUELLE main.py (nicht dist\SkyTycoon_Pro.exe).
cd /d "%~dp0"
echo SkyTycoon — Entwickler-Start aus diesem Ordner:
echo %CD%
".\.venv\Scripts\python.exe" main.py
if errorlevel 1 (
  echo.
  echo Fehler — falls keine venv:  python -m venv .venv
  echo   .\.venv\Scripts\pip install -r requirements.txt
  pause
)
