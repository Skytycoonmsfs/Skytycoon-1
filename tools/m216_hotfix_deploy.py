# -*- coding: utf-8 -*-
"""M216 Hotfix: Extension + Backend auf Server, Dienst neu starten."""
from __future__ import annotations

import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import paramiko  # noqa: E402

remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")
host = os.environ["SKYTYCOON_DEPLOY_HOST"]
user = os.environ["SKYTYCOON_DEPLOY_USER"]
pw = os.environ["SKYTYCOON_DEPLOY_PASSWORD"]

files = [
    ("wirtschaft_m216_extension.py", ROOT / "wirtschaft_m216_extension.py"),
    ("server_backend.py", ROOT / "server_backend.py"),
    ("skytycoon_profile_cloud.py", ROOT / "skytycoon_profile_cloud.py"),
    ("skytycoon_extensions.py", ROOT / "skytycoon_extensions.py"),
    ("platin_alliance_center.py", ROOT / "platin_alliance_center.py"),
    ("platin_career_layout.py", ROOT / "platin_career_layout.py"),
    ("platin_cloud_only.py", ROOT / "platin_cloud_only.py"),
    ("skytycoon_invoice_pdf.py", ROOT / "skytycoon_invoice_pdf.py"),
    ("tools/preview_invoice_pdf.py", ROOT / "tools" / "preview_invoice_pdf.py"),
    ("tools/resend_license_invoices_batch.py", ROOT / "tools" / "resend_license_invoices_batch.py"),
    ("admin_vault_core.py", ROOT / "admin_vault_core.py"),
    ("client_source/main.py", ROOT / "main.py"),
    ("skytycoon_synology_bridge.py", ROOT / "skytycoon_synology_bridge.py"),
    ("skytycoon_invoice_pdf.py", ROOT / "skytycoon_invoice_pdf.py"),
    ("skytycoon_settings_dialog.py", ROOT / "skytycoon_settings_dialog.py"),
    ("locales/translations.json", ROOT / "locales" / "translations.json"),
    ("templates/werft/tuning.html", ROOT / "templates" / "werft" / "tuning.html"),
    ("templates/account_hwid_reset.html", ROOT / "templates" / "account_hwid_reset.html"),
    ("templates/delete_account.html", ROOT / "templates" / "delete_account.html"),
    ("templates/dashboard.html", ROOT / "templates" / "dashboard.html"),
    ("templates/checkout.html", ROOT / "templates" / "checkout.html"),
    ("templates/register.html", ROOT / "templates" / "register.html"),
    ("templates/market/weather.html", ROOT / "templates" / "market" / "weather.html"),
    ("templates/market/radar.html", ROOT / "templates" / "market" / "radar.html"),
    ("templates/market/daily_auctions.html", ROOT / "templates" / "market" / "daily_auctions.html"),
    ("wirtschaft_m216_extension.py", ROOT / "wirtschaft_m216_extension.py"),
    ("templates/index.html", ROOT / "templates" / "index.html"),
    ("templates/screenshots.html", ROOT / "templates" / "screenshots.html"),
    ("templates/base.html", ROOT / "templates" / "base.html"),
    ("tools/sky_auto_backup.py", ROOT / "tools" / "sky_auto_backup.py"),
    ("tools/test_smtp_send_remote.py", ROOT / "tools" / "test_smtp_send_remote.py"),
    ("tools/sky_mail_dispatcher.py", ROOT / "tools" / "sky_mail_dispatcher.py"),
    ("tools/sky_i18n_engine.py", ROOT / "tools" / "sky_i18n_engine.py"),
    ("templates/leaderboard.html", ROOT / "templates" / "leaderboard.html"),
    ("Admin_Commander.py", ROOT / "Admin_Commander.py"),
    ("discord_bot.py", ROOT / "discord_bot.py"),
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=30)
ssh.exec_command(f"mkdir -p {remote}/client_source {remote}/locales", timeout=15)
sftp = ssh.open_sftp()
for name, local in files:
    print(f"[SFTP] {name}")
    sftp.put(str(local), f"{remote}/{name}")
sftp.close()

server_env = ROOT / "tools" / "skytycoon_server.env"
if server_env.is_file():
    print("[SFTP] smtp.env (Server-Produktion)")
    sftp2 = ssh.open_sftp()
    sftp2.put(str(server_env), f"{remote}/smtp.env")
    sftp2.close()
    merge_env = (
        f"cd {remote} && "
        "(test -f /etc/systemd/system/skytycoon.service && "
        "grep -q 'EnvironmentFile.*smtp.env' /etc/systemd/system/skytycoon.service || "
        "sudo sed -i '/^\\[Service\\]/a EnvironmentFile=-/home/skytycoon/smtp.env' "
        "/etc/systemd/system/skytycoon.service 2>/dev/null || true) && "
        "(test -f /etc/systemd/system/skytycoon-discord-bot.service && "
        "grep -q 'EnvironmentFile.*smtp.env' /etc/systemd/system/skytycoon-discord-bot.service || "
        "sudo sed -i '/^\\[Service\\]/a EnvironmentFile=-/home/skytycoon/smtp.env' "
        "/etc/systemd/system/skytycoon-discord-bot.service 2>/dev/null || true)"
    )
    print(">", merge_env)
    _stdin, stdout, stderr = ssh.exec_command(merge_env, timeout=30)
    print(stdout.read().decode("utf-8", "replace").strip())

cmds = [
    "grep -q SKYTYCOON_PG_HOST=127.0.0.1 /etc/systemd/system/skytycoon-discord-bot.service 2>/dev/null || "
    "sudo sed -i '/^\\[Service\\]/a Environment=SKYTYCOON_PG_HOST=127.0.0.1' "
    "/etc/systemd/system/skytycoon-discord-bot.service 2>/dev/null || true",
    "sudo systemctl daemon-reload 2>/dev/null || true",
    "sudo systemctl restart skytycoon_bot.service 2>/dev/null || true",
    "sudo systemctl restart skytycoon.service",
    "sudo systemctl restart skytycoon-discord-bot.service 2>/dev/null || true",
    f"(crontab -l 2>/dev/null | grep -v sky_auto_backup; echo '0 * * * * cd {remote} && /usr/bin/python3 tools/sky_auto_backup.py >> server_logs/backup_cron.log 2>&1') | crontab -",
    f"(crontab -l 2>/dev/null | grep -v sky_mail_dispatcher; echo '15 * * * * cd {remote} && /usr/bin/python3 tools/sky_mail_dispatcher.py >> server_logs/mail_dispatcher.log 2>&1') | crontab -",
    "sleep 4",
    "systemctl is-active skytycoon.service",
    "systemctl is-active skytycoon-discord-bot.service",
    "curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/market/license_shop",
    "curl -sS -m 8 http://127.0.0.1:8000/openapi.json | grep -o license_shop | head -1 || echo MISSING",
]
for c in cmds:
    print(">", c)
    _stdin, stdout, stderr = ssh.exec_command(c, timeout=60)
    print(stdout.read().decode("utf-8", "replace").strip())
    err = stderr.read().decode("utf-8", "replace").strip()
    if err:
        print("ERR:", err)
ssh.close()
print("[FERTIG] M216 Hotfix deployed.")
