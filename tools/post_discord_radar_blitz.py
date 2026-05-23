# -*- coding: utf-8 -*-
"""Postet Test-Embed in den Live-Radar-Kanal (Kanal-ID aus smtp.env)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env.deploy").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
for line in (ROOT / "tools" / "skytycoon_server.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import paramiko

remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon")
host = os.environ["SKYTYCOON_DEPLOY_HOST"]
user = os.environ["SKYTYCOON_DEPLOY_USER"]
pw = os.environ["SKYTYCOON_DEPLOY_PASSWORD"]

py = r"""
import os, time, json
import psycopg2
import discord
from discord_bot import BOT_BUILD_TAG, LIVE_RADAR_CHANNEL_ID, WEB_BASE

token = os.environ.get('SKYTYCOON_DISCORD_BOT_TOKEN','').strip()
cid = int(LIVE_RADAR_CHANNEL_ID or '1506143279555809341')
conn = psycopg2.connect(host='127.0.0.1', dbname='skytycoon_prod', user='sky_admin', password='e85OieJLPMV6Nuv', port=5432)
cur = conn.cursor()
cur.execute("INSERT INTO discord_bot_commands (command_type, payload_json, status, created_ts) VALUES ('radar_pilot_online', %s, 'queued', %s)", (json.dumps({'pilot_name':'Radar-Blitz-Test','aircraft':'B738','flight_phase':'AM GATE / PARKING','current_icao':'EDDF','online_count':1}), time.time()))
conn.commit()
conn.close()
print('queued_radar_pilot_online')

import asyncio
class T(discord.Client):
    async def on_ready(self):
        ch = await self.fetch_channel(cid)
        emb = discord.Embed(title='BÄM — RAD-BLITZ TEST', description='Live-Radar Kanal-ID aktiv · '+BOT_BUILD_TAG, color=discord.Color.gold())
        emb.set_footer(text=WEB_BASE)
        await ch.send(embed=emb)
        print('sent_to', cid)
        await self.close()

asyncio.run(T(intents=discord.Intents.default()).start(token))
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pw, timeout=30)
cmd = f"cd {remote} && set -a && . ./smtp.env && set +a && /home/skytycoon/venv/bin/python << 'PYEOF'\n{py}\nPYEOF"
_i, o, e = ssh.exec_command(cmd, timeout=120)
print(o.read().decode("utf-8", "replace"))
err = e.read().decode("utf-8", "replace")
if err.strip():
    print("ERR:", err[:800])
ssh.close()
