# -*- coding: utf-8 -*-
import os
import ssl
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "smtp.env"
for line in p.read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if s and not s.startswith("#") and "=" in s:
        k, v = s.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")

h = os.environ.get("SKYTYCOON_SMTP_HOST", "smtp.ionos.de")
u = os.environ.get("SKYTYCOON_SMTP_USER", "")
pw = os.environ.get("SKYTYCOON_SMTP_PASSWORD", "")
frm = os.environ.get("SKYTYCOON_SMTP_FROM", u)
port = int(os.environ.get("SKYTYCOON_SMTP_PORT") or "587")
print("host", h, "port", port, "user", u, "pw_len", len(pw))
ctx = ssl.create_default_context()
if port == 465:
    s = smtplib.SMTP_SSL(h, 465, timeout=10, context=ctx)
    s.login(u, pw)
else:
    s = smtplib.SMTP(h, port if port not in (0, 25) else 587, timeout=10)
    s.ehlo()
    s.starttls(context=ctx)
    s.ehlo()
    s.login(u, pw)
print("login_ok")
msg = MIMEText("SMTP test from skytycoon deploy (587 STARTTLS)", "plain", "utf-8")
msg["Subject"] = "SkyTycoon SMTP Test"
msg["From"] = frm
msg["To"] = u
s.sendmail(frm, [u], msg.as_string())
print("send_ok")
s.quit()
