from __future__ import annotations

import asyncio
import json
import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any

import aiohttp
import discord
import psycopg2
from discord import app_commands
from discord.ext import commands, tasks
from psycopg2.extras import DictCursor

try:
    from psycopg2.pool import ThreadedConnectionPool
except ImportError:
    ThreadedConnectionPool = None  # type: ignore[misc, assignment]

try:
    from zoneinfo import ZoneInfo

    TZ_SWISS = ZoneInfo("Europe/Zurich")
except Exception:
    TZ_SWISS = timezone(timedelta(hours=1))

_BOT_PG_POOL: ThreadedConnectionPool | None = None
_BOT_PG_POOL_LOCK = threading.Lock()
_CASINO_SPAM_LAST: dict[str, float] = {}
_CASINO_SPAM_SEC = 30.0
PLATIN_SUPPORTER_ROLE = "👑 Platin-Unterstützer"
GOD_ADMIN_ROLE_NAME = (
    os.environ.get("SKYTYCOON_DISCORD_GOD_ADMIN_ROLE_NAME")
    or "👑 Server-Besitzer / God-Admin"
).strip()
GLOBAL_SUPERADMIN_EMAIL = "info@skytycoon.info"
LIVE_FLIGHTS_CHANNEL_NAMES = ("live-flights", "✈️-live-flugbörse", "live-flugbörse")

DISCORD_BOT_TOKEN = (
    os.environ.get("SKYTYCOON_DISCORD_BOT_TOKEN")
    or os.environ.get("DISCORD_BOT_TOKEN")
    or ""
).strip()
DISCORD_CLIENT_ID = (
    os.environ.get("SKYTYCOON_DISCORD_CLIENT_ID") or ""
).strip()
DISCORD_CLIENT_SECRET = (
    os.environ.get("SKYTYCOON_DISCORD_CLIENT_SECRET") or ""
).strip()
DISCORD_GUILD_ID = (
    os.environ.get("SKYTYCOON_DISCORD_GUILD_ID") or ""
).strip()
TARGET_GUILD_ID = int(DISCORD_GUILD_ID or "0")
BOT_BUILD_TAG = "2026-05-21-discord-channel-lockdown-v15"
LIVE_RADAR_CHANNEL_ID = (
    os.environ.get("SKYTYCOON_DISCORD_LIVE_RADAR_CHANNEL_ID")
    or os.environ.get("SKYTYCOON_DISCORD_ADMIN_CHANNEL_ID")
    or "1506143279555809341"
).strip()
TARGET_GUILD = discord.Object(id=TARGET_GUILD_ID)
WEB_BASE = os.environ.get("SKYTYCOON_WEB_BASE", "https://skytycoon.info").rstrip("/")
RULES_REACTION = "✅"

PG_HOST = (os.environ.get("SKYTYCOON_PG_HOST") or "127.0.0.1").strip()
PG_PORT = (os.environ.get("SKYTYCOON_PG_PORT") or "5432").strip()
PG_DATABASE = (os.environ.get("SKYTYCOON_PG_DATABASE") or "skytycoon_prod").strip()
PG_USER = (os.environ.get("SKYTYCOON_PG_USER") or "sky_admin").strip()
PG_PASSWORD = os.environ.get("SKYTYCOON_PG_PASSWORD") or "e85OieJLPMV6Nuv"
PG_DSN = os.environ.get("SKYTYCOON_POSTGRES_DSN") or (
    f"dbname={PG_DATABASE} user={PG_USER} password={PG_PASSWORD} host={PG_HOST} port={PG_PORT}"
)


def get_bot_db_connection():
    """Robuste IONOS-PostgreSQL-Leitung für Discord-Bot (DictCursor)."""
    return psycopg2.connect(
        host=PG_HOST,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
        port=PG_PORT,
        cursor_factory=DictCursor,
    )

I18N: dict[str, dict[str, str]] = {
    "de": {
        "verified_title": "⭐ Pilot verifiziert",
        "verified_body": "Willkommen im SkyTycoon-Netzwerk, Captain {name}. Deine Lifetime-Lizenz wurde bestätigt.",
        "verify_fail": "Kein aktiver SkyTycoon-Pro-Account mit diesem Web-Usernamen gefunden.",
        "flight": "✈️ Flug abgeschlossen",
        "flight_live": "✈️ Live-Abflug",
        "auction": "🔨 UTC-Auktion beendet",
        "wallstreet": "📈 Wallstreet-Ticker",
        "broadcast": "📢 Admin-Ankündigung",
        "oauth_joined": "Discord-Pilot synchronisiert",
        "rules_title": "📜 SkyTycoon Pro — Regelwerk",
        "rules_body": (
            "Willkommen bei **SkyTycoon Pro**!\n\n"
            "1. Respektvoller Umgang im Cockpit und Chat.\n"
            "2. Kein Cheating oder Ausnutzen von Bugs in der main.py.\n"
            "3. Nutze die Handy-App für die Werft.\n\n"
            "Reagiere mit ✅ um die Rolle **👨‍✈️ Flugschüler** zu erhalten."
        ),
        "rules_accepted": "✅ Regeln akzeptiert — Rolle **👨‍✈️ Flugschüler** vergeben.",
        "lb_title": "🏆 SkyTycoon Live-Leaderboard",
        "lb_alliances": "Top-5 Allianzen (Treasury)",
        "lb_pilots": "Top-5 Piloten (Vermögen)",
        "market_title": "🛩 Neues Markt-Inserat",
        "market_daily": "🌅 Tagesmarkt (UTC) aktualisiert",
        "radar_title": "📡 Live-Radar",
        "radar_empty": "Keine aktiven Flüge — starte main.py und hebe ab!",
        "treasury_title": "🏦 Allianz-Treasury Report",
        "casino_no_user": "Kein PostgreSQL-Konto für deinen Discord-Namen. Bitte zuerst /verify.",
        "casino_low": "Nicht genug Credits auf dem Konto.",
        "slots_win": "🎰 JACKPOT! +{amount} CR",
        "slots_lose": "🎰 Kein Treffer. −{amount} CR",
        "blackjack_win": "🃏 Blackjack-Gewinn +{amount} CR",
        "blackjack_lose": "🃏 Verloren −{amount} CR",
        "ticket_open": "🎫 Ticket #{tid} eröffnet — Admin Commander & Mobile APK wurden benachrichtigt.",
        "ticket_reply": "💬 Support-Antwort",
        "rank_sync": "🎖 Rang synchronisiert: {role}",
        "market_condition": "Zustand",
        "market_price": "Preis",
        "market_link": "Zur Website",
        "market_seller": "Verkäufer",
        "casino_balance": "Kontostand",
        "slots_desc": "SkyTycoon Credit-Casino — Einsatz wird sofort in PostgreSQL gebucht.",
        "blackjack_desc": "SkyTycoon Blackjack — Gewinne landen direkt auf deinem Pilotenkonto.",
        "casino_locked": "❌ Zugriff verweigert! Du musst das Casino-Modul zuerst auf der SkyTycoon-Website im Lizenzshop mit deinen Credits freischalten, bevor du hier spielen kannst!",
        "casino_shutdown": "🔴 Das Live-Casino ist vorübergehend gesperrt (Admin Commander).",
        "casino_guide_title": "🎰 SkyTycoon Live-Casino",
        "guide_radar_title": "📡 Live-Radar & FIDS-Funk",
        "guide_radar_body": (
            "**DE:** Dieser Kanal zeigt alle Piloten, die **main.py** mit aktivem **5-Sekunden-Heartbeat** "
            "an IONOS senden. Die Website-Flugtafel (FIDS) und die Weltkarte zählen nur Piloten mit frischem Ping "
            "(unter ~15 s). Status **AM GATE / PARKING** = Standby am Gate ohne aktiven Job.\n\n"
            "**EN:** This channel lists pilots sending a **5-second heartbeat** from **main.py**. "
            "The website FIDS and map count only fresh pings (~15 s). **AM GATE / PARKING** = standby at the gate."
        ),
        "guide_dispatcher_title": "✈️ Custom Dispatcher & Charter",
        "guide_dispatcher_body": (
            "**DE:** Freie Routen **DEP → ARR** in der PC-App (Flugbörse / Charter). Der Server berechnet "
            "Distanz (Haversine/A*), **Credits & XP** — Charter-Vorschau inkl. **+15 % Platin-Dispatch-Bonus**. "
            "Nach „Charter scharfschalten“ landet der Flug in PostgreSQL.\n\n"
            "**EN:** Free **DEP → ARR** routes in the PC app (job board / charter). The server returns "
            "distance, **credits & XP** with a **+15% dispatch bonus** preview. Activating charter persists the flight in PostgreSQL."
        ),
        "guide_gsx_title": "⚙️ GSX Remote Control",
        "guide_gsx_body": (
            "**DE:** Steuere **GSX Pro** aus der PC-App (Platin-Panel): native **SimConnect K-Events** "
            "für **Boarding**, **Catering**, **Deboarding**, **Refuel** — blockierungsfrei im QThreadPool. "
            "Simulator muss verbunden sein.\n\n"
            "**EN:** Control **GSX Pro** from the PC app (Platin panel): native **SimConnect K-Events** for "
            "**boarding**, **catering**, **deboarding**, **refuel** — non-blocking background workers. SimConnect required."
        ),
        "guide_hangar_title": "🛠️ Hangar & Werft",
        "guide_hangar_body": (
            "**DE:** **12 Werftbalken** in main.py: Wartung, Tuning, Teile. Kritische Zustände (<30 %) "
            "werden hier und per Cloud gemeldet. Web-Tuning: **skytycoon.info** → Werft / Tuning (Credits).\n\n"
            "**EN:** **12 hangar bars** in main.py: maintenance, tuning, parts. Critical wear (<30%) is "
            "surfaced here and in the cloud. Web tuning at **skytycoon.info** → shipyard / tuning."
        ),
        "guide_ticket_title": "🎫 Support & Tickets",
        "guide_ticket_body": (
            "**DE:** **`/ticket create`** — privater Kanal + Eintrag in PostgreSQL. Admin-Antworten aus dem "
            "**Admin Commander** mit **KI-Übersetzung DE/EN** (sky_i18n_engine). Kein manuelles /verify mehr — "
            "Konto verknüpfen über **Dashboard → Discord OAuth**.\n\n"
            "**EN:** **`/ticket create`** — private channel + PostgreSQL row. Admin replies from "
            "**Admin Commander** with **AI DE/EN translation**. Link accounts via **dashboard → Discord OAuth**, not /verify."
        ),
        "guide_news_title": "📢 News & Marketing",
        "guide_news_body": (
            "**DE:** Globale News von **Admin Commander** (Marketing-Zentrale) und Versand über **info@skytycoon.info**. "
            "Erscheint auf der Website-Startseite und als Broadcast-Embed hier.\n\n"
            "**EN:** Global news from **Admin Commander** (marketing hub), sent via **info@skytycoon.info**. "
            "Shown on the website homepage and as broadcast embeds here."
        ),
        "oauth_welcome_dm": (
            "**DE:** Willkommen, Captain **{name}**! Dein Web-Konto ist mit Discord verknüpft. "
            "Rolle und Casino-Sync sind aktiv.\n\n"
            "**EN:** Welcome, Captain **{name}**! Your web account is linked to Discord. "
            "Roles and casino sync are active."
        ),
        "verify_deprecated": (
            "**DE:** Manuelles /verify ist abgeschaltet. Öffne **skytycoon.info → Dashboard → Profil** "
            "und klicke **„Konto mit Discord verbinden“** (OAuth2).\n\n"
            "**EN:** Manual /verify is disabled. Open **skytycoon.info → Dashboard → Profile** "
            "and click **„Connect account with Discord“** (OAuth2)."
        ),
        "casino_guide_body": (
            "🎰 Willkommen im SkyTycoon Live-Casino! Hier kannst du deine am PC erflogenen Credits einsetzen!\n\n"
            "Befehle:\n"
            "👉 `/slots <Einsatz>` - Drehe die Walzen! Gewinnchancen bei passenden Flugzeug-Symbolen. (Standardlimit: 50.000 CR)\n"
            "👉 `/blackjack <Einsatz>` - Fordere den Dealer heraus! Gewinne mit einer 21.\n"
            "👉 `/roulette <Zahl> <Einsatz>` - Treffer = 35× Gewinn!\n\n"
            "💎 *High-Roller Tipp:* Schalte im Web-Lizenzshop das High-Roller-Zertifikat frei, um bis zu 1.000.000 CR pro Runde zu setzen!"
        ),
        "casino_cooldown": (
            "🛑 Spielsperre aktiv! Du hast kürzlich abgeräumt. Dein nächster Flug wartet! "
            "Erneuter Zugriff erlaubt ab: **{until}** (Schweizer Zeit)!"
        ),
        "casino_spam": "⏳ Bitte {sec}s warten (Spam-Schutz). / Please wait {sec}s.",
        "stats_title": "📔 Piloten-Logbuch",
        "stats_body": "**{pilot}**\nCredits: `{credits}`\nXP: `{xp}`\nRang: **{rank}**\nFlotte: **{fleet}** Maschinen",
        "lb_cmd_title": "🏆 Top 10 — Reichste Piloten",
        "lb_cmd_empty": "Noch keine Piloten in der Flotte.",
        "roulette_win": "🎡 Zahl **{num}** — JACKPOT +{amount} CR!",
        "roulette_lose": "🎡 Zahl {rolled}, du tipptest {num}. −{amount} CR",
        "platin_alert": "👑 Platin-Unterstützer — Echtgeld-Kauf bestätigt!",
        "platin_body": "**{pilot}** hat SkyTycoon Pro unterstützt. Willkommen in der Platin-Flotte!",
        "anticheat_title": "🛡️ Anti-Cheat-Pranger",
        "anticheat_body": "**{pilot}** — Cloud-Schutzschild: manipulierte Credits erkannt.\nGrund: `{reason}`",
        "invoice_dm": "🧾 Kauf bestätigt: **{item}** — {amount} CR",
        "alliance_voice": "🔊 Allianz-Voice **{name}** erstellt (24h).",
        "ticket_private": "🎫 Privates Ticket #{tid} — nur du und Support sehen diesen Kanal.",
    },
    "en": {
        "verified_title": "⭐ Pilot verified",
        "verified_body": "Welcome to the SkyTycoon network, Captain {name}. Your lifetime license has been confirmed.",
        "verify_fail": "No active SkyTycoon Pro account was found for this web username.",
        "flight": "✈️ Flight completed",
        "flight_live": "✈️ Live departure",
        "auction": "🔨 UTC auction closed",
        "wallstreet": "📈 Wallstreet ticker",
        "broadcast": "📢 Admin announcement",
        "oauth_joined": "Discord pilot synchronized",
        "rules_title": "📜 SkyTycoon Pro — Rules",
        "rules_body": (
            "Welcome to **SkyTycoon Pro**!\n\n"
            "1. Be respectful in the cockpit and chat.\n"
            "2. No cheating or bug exploitation in the main.py.\n"
            "3. Use the mobile app for maintenance.\n\n"
            "React with ✅ to receive the **👨‍✈️ Flugschüler** role."
        ),
        "rules_accepted": "✅ Rules accepted — **👨‍✈️ Flugschüler** role granted.",
        "lb_title": "🏆 SkyTycoon Live Leaderboard",
        "lb_alliances": "Top 5 alliances (treasury)",
        "lb_pilots": "Top 5 pilots (wealth)",
        "market_title": "🛩 New market listing",
        "market_daily": "🌅 Daily market (UTC) refreshed",
        "radar_title": "📡 Live radar",
        "radar_empty": "No active flights — launch main.py and take off!",
        "treasury_title": "🏦 Alliance treasury report",
        "casino_no_user": "No PostgreSQL account for your Discord name. Use /verify first.",
        "casino_low": "Insufficient credits on your account.",
        "slots_win": "🎰 JACKPOT! +{amount} CR",
        "slots_lose": "🎰 No win. −{amount} CR",
        "blackjack_win": "🃏 Blackjack win +{amount} CR",
        "blackjack_lose": "🃏 Lost −{amount} CR",
        "ticket_open": "🎫 Ticket #{tid} opened — Admin Commander & mobile APK notified.",
        "ticket_reply": "💬 Support reply",
        "rank_sync": "🎖 Rank synced: {role}",
        "market_condition": "Condition",
        "market_price": "Price",
        "market_link": "Open website",
        "market_seller": "Seller",
        "casino_balance": "Balance",
        "slots_desc": "SkyTycoon credit casino — bets commit instantly to PostgreSQL.",
        "blackjack_desc": "SkyTycoon blackjack — wins credit your pilot account immediately.",
        "casino_locked": "❌ Access denied! Unlock the casino module in the SkyTycoon web license shop with your credits before playing here!",
        "casino_shutdown": "🔴 The live casino is temporarily frozen (Admin Commander).",
        "casino_guide_title": "🎰 SkyTycoon Live Casino",
        "guide_radar_title": "📡 Live radar & FIDS heartbeat",
        "guide_radar_body": (
            "**DE:** Dieser Kanal zeigt alle Piloten, die **main.py** mit aktivem **5-Sekunden-Heartbeat** "
            "an IONOS senden. Die Website-Flugtafel (FIDS) und die Weltkarte zählen nur Piloten mit frischem Ping "
            "(unter ~15 s). Status **AM GATE / PARKING** = Standby am Gate ohne aktiven Job.\n\n"
            "**EN:** This channel lists pilots sending a **5-second heartbeat** from **main.py**. "
            "The website FIDS and map count only fresh pings (~15 s). **AM GATE / PARKING** = standby at the gate."
        ),
        "guide_dispatcher_title": "✈️ Custom dispatcher & charter",
        "guide_dispatcher_body": (
            "**DE:** Freie Routen **DEP → ARR** in der PC-App (Flugbörse / Charter). Der Server berechnet "
            "Distanz (Haversine/A*), **Credits & XP** — Charter-Vorschau inkl. **+15 % Platin-Dispatch-Bonus**. "
            "Nach „Charter scharfschalten“ landet der Flug in PostgreSQL.\n\n"
            "**EN:** Free **DEP → ARR** routes in the PC app (job board / charter). The server returns "
            "distance, **credits & XP** with a **+15% dispatch bonus** preview. Activating charter persists the flight in PostgreSQL."
        ),
        "guide_gsx_title": "⚙️ GSX remote control",
        "guide_gsx_body": (
            "**DE:** Steuere **GSX Pro** aus der PC-App (Platin-Panel): native **SimConnect K-Events** "
            "für **Boarding**, **Catering**, **Deboarding**, **Refuel** — blockierungsfrei im QThreadPool. "
            "Simulator muss verbunden sein.\n\n"
            "**EN:** Control **GSX Pro** from the PC app (Platin panel): native **SimConnect K-Events** for "
            "**boarding**, **catering**, **deboarding**, **refuel** — non-blocking background workers. SimConnect required."
        ),
        "guide_hangar_title": "🛠️ Hangar & shipyard",
        "guide_hangar_body": (
            "**DE:** **12 Werftbalken** in main.py: Wartung, Tuning, Teile. Kritische Zustände (<30 %) "
            "werden hier und per Cloud gemeldet. Web-Tuning: **skytycoon.info** → Werft / Tuning (Credits).\n\n"
            "**EN:** **12 hangar bars** in main.py: maintenance, tuning, parts. Critical wear (<30%) is "
            "surfaced here and in the cloud. Web tuning at **skytycoon.info** → shipyard / tuning."
        ),
        "guide_ticket_title": "🎫 Support & tickets",
        "guide_ticket_body": (
            "**DE:** **`/ticket create`** — privater Kanal + Eintrag in PostgreSQL. Admin-Antworten aus dem "
            "**Admin Commander** mit **KI-Übersetzung DE/EN** (sky_i18n_engine). Kein manuelles /verify mehr — "
            "Konto verknüpfen über **Dashboard → Discord OAuth**.\n\n"
            "**EN:** **`/ticket create`** — private channel + PostgreSQL row. Admin replies from "
            "**Admin Commander** with **AI DE/EN translation**. Link accounts via **dashboard → Discord OAuth**, not /verify."
        ),
        "guide_news_title": "📢 News & marketing",
        "guide_news_body": (
            "**DE:** Globale News von **Admin Commander** (Marketing-Zentrale) und Versand über **info@skytycoon.info**. "
            "Erscheint auf der Website-Startseite und als Broadcast-Embed hier.\n\n"
            "**EN:** Global news from **Admin Commander** (marketing hub), sent via **info@skytycoon.info**. "
            "Shown on the website homepage and as broadcast embeds here."
        ),
        "oauth_welcome_dm": (
            "**DE:** Willkommen, Captain **{name}**! Dein Web-Konto ist mit Discord verknüpft. "
            "Rolle und Casino-Sync sind aktiv.\n\n"
            "**EN:** Welcome, Captain **{name}**! Your web account is linked to Discord. "
            "Roles and casino sync are active."
        ),
        "verify_deprecated": (
            "**DE:** Manuelles /verify ist abgeschaltet. Öffne **skytycoon.info → Dashboard → Profil** "
            "und klicke **„Konto mit Discord verbinden“** (OAuth2).\n\n"
            "**EN:** Manual /verify is disabled. Open **skytycoon.info → Dashboard → Profile** "
            "and click **„Connect account with Discord“** (OAuth2)."
        ),
        "casino_guide_body": (
            "🎰 Welcome to the SkyTycoon Live-Casino! Bet your hard-earned PC cockpit credits here!\n\n"
            "Commands:\n"
            "👉 `/slots <bet>` - Spin the reels! Win big with matching aircraft icons. (Default limit: 50,000 CR)\n"
            "👉 `/blackjack <bet>` - Challenge the dealer! Win with a 21.\n"
            "👉 `/roulette <number> <bet>` - Exact hit pays 35×!\n\n"
            "💎 *High-Roller Tip:* Unlock the High-Roller License in the web shop to bet up to 1,000,000 CR per round!"
        ),
        "casino_cooldown": (
            "🛑 Play lock active! You recently won big. Next flight awaits! "
            "Access again from: **{until}** (Swiss time)!"
        ),
        "casino_spam": "⏳ Please wait {sec}s (spam protection).",
        "stats_title": "📔 Pilot logbook",
        "stats_body": "**{pilot}**\nCredits: `{credits}`\nXP: `{xp}`\nRank: **{rank}**\nFleet: **{fleet}** aircraft",
        "lb_cmd_title": "🏆 Top 10 — Richest pilots",
        "lb_cmd_empty": "No pilots in the fleet yet.",
        "roulette_win": "🎡 Number **{num}** — JACKPOT +{amount} CR!",
        "roulette_lose": "🎡 Rolled {rolled}, you picked {num}. −{amount} CR",
        "platin_alert": "👑 Platin supporter — real-money purchase confirmed!",
        "platin_body": "**{pilot}** supported SkyTycoon Pro. Welcome to the platinum fleet!",
        "anticheat_title": "🛡️ Anti-cheat alert",
        "anticheat_body": "**{pilot}** — cloud shield: manipulated credits detected.\nReason: `{reason}`",
        "invoice_dm": "🧾 Purchase confirmed: **{item}** — {amount} CR",
        "alliance_voice": "🔊 Alliance voice **{name}** created (24h).",
        "ticket_private": "🎫 Private ticket #{tid} — only you and support can see this channel.",
    },
}


@dataclass(frozen=True)
class RoleSpec:
    name: str
    color: discord.Color


ROLE_SPECS = (
    RoleSpec("⭐ Verifizierter Pilot", discord.Color.gold()),
    RoleSpec(PLATIN_SUPPORTER_ROLE, discord.Color.from_rgb(212, 175, 55)),
    RoleSpec("🤝 Allianz-CEO", discord.Color.blue()),
    RoleSpec("👨‍✈️ Flugschüler", discord.Color.dark_grey()),
    RoleSpec("👑 Tycoon des Monats", discord.Color.from_rgb(212, 175, 55)),
    RoleSpec("✈️ Co-Pilot", discord.Color.teal()),
    RoleSpec("🎖️ Kapitän", discord.Color.from_rgb(33, 150, 243)),
    RoleSpec("👑 Legende der Lüfte", discord.Color.purple()),
)

CHANNEL_LAYOUT = {
    "📢 INTRADAY INFORMATION": ("📢-ankündigungen", "📜-regeln-rules"),
    "✈️ SKYTYCOON OPERATIONS": (
        "✈️-live-flugbörse",
        "live-flights",
        "🔨-utc-auktionsalarm",
        "📈-wallstreet-ticker",
        "🤖-bot-verifizierung",
    ),
    "🌐 COMMUNITY LIVE": (
        "🛩-gebrauchtbörse",
        "📡-live-radar",
        "✈️-custom-dispatcher",
        "⚙️-gsx-remote-control",
        "🛠️-hangar-werft",
        "🏦-allianz-bank",
        "🎫-support-tickets",
        "📢-news-updates",
        "🎰-casino-lounge",
        "🎰-casino",
    ),
}

# Kanalname → (state_key, title_i18n_key, body_i18n_key)
CHANNEL_GUIDE_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("📡-live-radar", "guide_live_radar", "guide_radar_title", "guide_radar_body"),
    (
        "✈️-custom-dispatcher",
        "guide_custom_dispatcher",
        "guide_dispatcher_title",
        "guide_dispatcher_body",
    ),
    (
        "⚙️-gsx-remote-control",
        "guide_gsx_remote",
        "guide_gsx_title",
        "guide_gsx_body",
    ),
    ("🛠️-hangar-werft", "guide_hangar_werft", "guide_hangar_title", "guide_hangar_body"),
    (
        "🎫-support-tickets",
        "guide_support_tickets",
        "guide_ticket_title",
        "guide_ticket_body",
    ),
    ("📢-news-updates", "guide_news_updates", "guide_news_title", "guide_news_body"),
)


def _build_rank_milestones() -> tuple[tuple[float, str], ...]:
    try:
        import skytycoon_prestige_pack as prestige

        return tuple(
            (float(r["min_miles"]), str(r["discord_role"]))
            for r in prestige.rank_catalog_full()
        )
    except Exception:
        return (
            (0, "👨‍✈️ Flugschüler"),
            (15000, "✈️ Co-Pilot"),
            (50000, "🎖️ Kapitän"),
            (150000, "👑 Legende der Lüfte"),
        )


RANK_MILESTONES: tuple[tuple[float, str], ...] = _build_rank_milestones()


def tr(lang: str, key: str, **kwargs: Any) -> str:
    text = I18N.get(lang, I18N["de"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


def tr_bilingual(key: str, **kwargs: Any) -> str:
    return tr("de", key, **kwargs) + "\n\n" + tr("en", key, **kwargs)


def build_gold_guide_embed(title_key: str, body_key: str) -> discord.Embed:
    """Schwarz/Gold Handbuch-Embed (DE + EN)."""
    embed = discord.Embed(
        title=tr("de", title_key) + " / " + tr("en", title_key),
        description=tr_bilingual(body_key)[:4000],
        color=discord.Color.from_rgb(212, 175, 55),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=f"SkyTycoon Pro Handbuch · {BOT_BUILD_TAG} · DE/EN")
    return embed


async def _channel_guide_already_present(
    ch: discord.TextChannel, bot: commands.Bot, state_key: str
) -> bool:
    stored = channel_state_get(state_key)
    if stored.isdigit():
        try:
            msg = await ch.fetch_message(int(stored))
            if msg.author and msg.author.id == bot.user.id and msg.embeds:
                return True
        except discord.DiscordException:
            pass
    try:
        pins = await ch.pins()
        for msg in pins:
            if msg.author and msg.author.id == bot.user.id and msg.embeds:
                foot = str(msg.embeds[0].footer.text or "")
                if "Handbuch" in foot or "Handbook" in foot:
                    channel_state_set(state_key, str(msg.id))
                    return True
    except discord.DiscordException:
        pass
    return False


async def ensure_pinned_channel_guide(
    ch: discord.TextChannel, state_key: str, embed: discord.Embed, bot: commands.Bot
) -> None:
    await replace_pinned_bot_message(ch, state_key, embed)
    mid = channel_state_get(state_key)
    if not mid.isdigit():
        return
    try:
        msg = await ch.fetch_message(int(mid))
        await msg.pin()
    except discord.DiscordException:
        pass


async def setup_channel_guide_embeds(
    guild: discord.Guild, bot: commands.Bot
) -> None:
    """Beim Start: fehlende DE/EN Gold-Handbücher pro Kanal anlegen und pinnen."""
    for ch_name, state_key, title_key, body_key in CHANNEL_GUIDE_SPECS:
        try:
            ch: discord.TextChannel | None
            if ch_name == "📡-live-radar":
                ch = await channel_live_radar(guild, bot)
            else:
                ch = channel(guild, ch_name)
            if ch is None:
                print(f"SkyTycoon guide skip (missing channel): {ch_name}")
                continue
            if await _channel_guide_already_present(ch, bot, state_key):
                continue
            embed = build_gold_guide_embed(title_key, body_key)
            await ensure_pinned_channel_guide(ch, state_key, embed, bot)
            print(f"SkyTycoon guide pinned: {ch_name}")
        except Exception as exc:  # noqa: BLE001
            print(f"SkyTycoon guide failed {ch_name}: {exc}")


class _PooledBotConn:
    def __init__(self, conn: Any, pool: ThreadedConnectionPool) -> None:
        self._conn = conn
        self._pool = pool
        self._done = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def close(self) -> None:
        if self._done:
            return
        self._done = True
        try:
            self._pool.putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass


def _bot_pg_pool() -> ThreadedConnectionPool | None:
    global _BOT_PG_POOL
    if ThreadedConnectionPool is None:
        return None
    with _BOT_PG_POOL_LOCK:
        if _BOT_PG_POOL is None:
            _BOT_PG_POOL = ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                host=PG_HOST,
                database=PG_DATABASE,
                user=PG_USER,
                password=PG_PASSWORD,
                port=PG_PORT,
                cursor_factory=DictCursor,
            )
        return _BOT_PG_POOL


def pg_conn():
    pool = _bot_pg_pool()
    if pool is not None:
        return _PooledBotConn(pool.getconn(), pool)
    return get_bot_db_connection()


def _pg_rollback(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def _fmt_swiss_until(ts: Any) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        dt = ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    else:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            return str(ts)[:32]
    return dt.astimezone(TZ_SWISS).strftime("%d.%m.%Y %H:%M")


def _ensure_users_casino_cooldown(conn: Any) -> None:
    with conn.cursor() as cur:
        try:
            cur.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS casino_cooldown TIMESTAMPTZ;"
            )
            conn.commit()
        except psycopg2.Error:
            _pg_rollback(conn)


def _casino_cooldown_active(hid: str) -> tuple[bool, str]:
    conn = pg_conn()
    try:
        _ensure_users_casino_cooldown(conn)
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                "SELECT casino_cooldown FROM users WHERE hardware_id = %s LIMIT 1;",
                (hid,),
            )
            row = cur.fetchone()
            conn.commit()
        if not row:
            return False, ""
        raw = row.get("casino_cooldown") if isinstance(row, dict) else row[0]
        if raw is None:
            return False, ""
        if isinstance(raw, datetime):
            until = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        else:
            until = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if until > datetime.now(timezone.utc):
            return True, _fmt_swiss_until(until)
        return False, ""
    except psycopg2.Error:
        _pg_rollback(conn)
        return False, ""
    finally:
        conn.close()


def _casino_set_winner_cooldown(hid: str) -> None:
    conn = pg_conn()
    try:
        _ensure_users_casino_cooldown(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET casino_cooldown = CURRENT_TIMESTAMP + INTERVAL '2 days'
                WHERE hardware_id = %s;
                """,
                (hid,),
            )
            conn.commit()
    except psycopg2.Error:
        _pg_rollback(conn)
    finally:
        conn.close()


def _casino_spam_ok(discord_uid: str) -> bool:
    uid = str(discord_uid or "")
    now = time.time()
    last = _CASINO_SPAM_LAST.get(uid, 0.0)
    if now - last < _CASINO_SPAM_SEC:
        return False
    _CASINO_SPAM_LAST[uid] = now
    return True


def _bilingual_ticket_text(text: str) -> tuple[str, str]:
    try:
        from tools.sky_i18n_engine import bilingual_pair

        return bilingual_pair(text)
    except Exception:
        raw = (text or "").strip()
        return raw, raw


def fetchone(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    conn = pg_conn()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None
    except psycopg2.Error:
        _pg_rollback(conn)
        return None
    finally:
        conn.close()


def fetchall(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = pg_conn()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows
    except psycopg2.Error:
        _pg_rollback(conn)
        return []
    finally:
        conn.close()


def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    conn = pg_conn()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(query, params)
            conn.commit()
    except psycopg2.Error:
        _pg_rollback(conn)
        raise
    finally:
        conn.close()


def ensure_discord_tables() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS discord_bot_commands (
            id SERIAL PRIMARY KEY,
            command_type VARCHAR(64) NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status VARCHAR(32) NOT NULL DEFAULT 'queued',
            created_ts DOUBLE PRECISION DEFAULT 0,
            processed_ts DOUBLE PRECISION DEFAULT 0,
            error TEXT DEFAULT ''
        );
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS discord_channel_state (
            channel_key VARCHAR(64) PRIMARY KEY,
            message_id VARCHAR(32) NOT NULL DEFAULT '',
            updated_ts DOUBLE PRECISION NOT NULL DEFAULT 0
        );
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS discord_rules_log (
            discord_user_id VARCHAR(128) PRIMARY KEY,
            hardware_id VARCHAR(128) NOT NULL DEFAULT '',
            accepted_ts DOUBLE PRECISION NOT NULL DEFAULT 0
        );
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            id SERIAL PRIMARY KEY,
            hardware_id VARCHAR(128) NOT NULL DEFAULT '',
            discord_user_id VARCHAR(128) NOT NULL DEFAULT '',
            discord_channel_id VARCHAR(128) NOT NULL DEFAULT '',
            status VARCHAR(32) NOT NULL DEFAULT 'open',
            pilot_name TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            last_message_ts DOUBLE PRECISION NOT NULL DEFAULT 0
        );
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS support_messages (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL DEFAULT 0,
            hardware_id VARCHAR(128) NOT NULL DEFAULT '',
            sender VARCHAR(32) NOT NULL DEFAULT 'pilot',
            message_text TEXT NOT NULL DEFAULT '',
            message_de TEXT NOT NULL DEFAULT '',
            message_en TEXT NOT NULL DEFAULT '',
            ts DOUBLE PRECISION NOT NULL DEFAULT 0
        );
        """
    )
    for alt in (
        "ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS message_de TEXT NOT NULL DEFAULT '';",
        "ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS message_en TEXT NOT NULL DEFAULT '';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS casino_cooldown TIMESTAMPTZ;",
    ):
        try:
            execute(alt)
        except Exception:
            pass
    execute(
        """
        CREATE TABLE IF NOT EXISTS discord_admin_commands (
            id SERIAL PRIMARY KEY,
            command_type VARCHAR(64) NOT NULL,
            target_user TEXT NOT NULL DEFAULT '',
            val1 TEXT NOT NULL DEFAULT '',
            val2 TEXT NOT NULL DEFAULT '',
            processed INTEGER NOT NULL DEFAULT 0,
            created_ts DOUBLE PRECISION NOT NULL DEFAULT 0,
            processed_ts DOUBLE PRECISION NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT ''
        );
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS discord_casino_state (
            state_key VARCHAR(64) PRIMARY KEY,
            state_value TEXT NOT NULL DEFAULT '',
            updated_ts DOUBLE PRECISION NOT NULL DEFAULT 0
        );
        """
    )


def channel_state_get(key: str) -> str:
    row = fetchone(
        "SELECT message_id FROM discord_channel_state WHERE channel_key = %s LIMIT 1;",
        (key[:64],),
    )
    return str(row["message_id"] or "") if row else ""


def channel_state_set(key: str, message_id: str) -> None:
    execute(
        """
        INSERT INTO discord_channel_state (channel_key, message_id, updated_ts)
        VALUES (%s, %s, %s)
        ON CONFLICT (channel_key) DO UPDATE SET
            message_id = EXCLUDED.message_id,
            updated_ts = EXCLUDED.updated_ts;
        """,
        (key[:64], str(message_id)[:32], time.time()),
    )


def user_wealth(hid: str) -> float:
    row = fetchone(
        """
        SELECT COALESCE(credits, money, 0) AS wealth
        FROM users WHERE hardware_id = %s LIMIT 1;
        """,
        (hid,),
    )
    return float(row["wealth"] or 0) if row else 0.0


def user_by_discord_name(name: str) -> dict[str, Any] | None:
    return fetchone(
        """
        SELECT hardware_id, username, COALESCE(credits, money, 0) AS credits,
               license_status
        FROM users
        WHERE LOWER(username) = LOWER(%s)
        ORDER BY COALESCE(credits, money, 0) DESC
        LIMIT 1;
        """,
        (name.strip()[:120],),
    )


def user_by_discord_id(discord_user_id: str) -> dict[str, Any] | None:
    return fetchone(
        """
        SELECT u.hardware_id, u.username, COALESCE(u.credits, u.money, 0) AS credits,
               u.license_status
        FROM discord_oauth_links d
        JOIN users u ON u.hardware_id = d.hardware_id
        WHERE d.discord_user_id = %s
        LIMIT 1;
        """,
        (str(discord_user_id).strip()[:128],),
    )


def user_for_interaction(interaction: discord.Interaction) -> dict[str, Any] | None:
    uid = str(getattr(interaction.user, "id", "") or "")
    if uid:
        linked = user_by_discord_id(uid)
        if linked:
            return linked
    return user_by_discord_name(str(getattr(interaction.user, "display_name", "") or ""))


def debit_credits(hid: str, amount: float) -> bool:
    amount = max(0.0, float(amount))
    row = fetchone(
        """
        UPDATE users
        SET credits = GREATEST(0, COALESCE(credits, money, 0) - %s),
            money = GREATEST(0, COALESCE(money, 0) - %s)
        WHERE hardware_id = %s
          AND COALESCE(credits, money, 0) >= %s
        RETURNING hardware_id;
        """,
        (amount, amount, hid, amount),
    )
    return bool(row)


def credit_credits(hid: str, amount: float) -> None:
    amount = max(0.0, float(amount))
    execute(
        """
        UPDATE users
        SET credits = COALESCE(credits, money, 0) + %s,
            money = COALESCE(money, 0) + %s
        WHERE hardware_id = %s;
        """,
        (amount, amount, hid),
    )


def rank_role_for_miles(miles: float) -> str:
    role = RANK_MILESTONES[0][1]
    for threshold, name in RANK_MILESTONES:
        if miles >= threshold:
            role = name
    return role


def rank_role_for_rank_name(rank_name: str, miles: float = 0.0, prestige_level: int = 0) -> str:
    """Map Admin-Commander / API rank names to Discord milestone roles (20 ranks)."""
    rn = str(rank_name or "").strip().lower()
    try:
        import skytycoon_prestige_pack as prestige

        for r in prestige.rank_catalog_full():
            if rn and (rn in str(r.get("name", "")).lower() or rn in str(r.get("name_en", "")).lower()):
                return str(r["discord_role"])
        resolved = prestige.resolve_rank(float(miles), int(prestige_level))
        return str(resolved.get("discord_role") or RANK_MILESTONES[-1][1])
    except Exception:
        pass
    if "kaiser" in rn or "legende" in rn or "tycoon" in rn:
        return RANK_MILESTONES[-1][1]
    if "kapit" in rn:
        return "🎖️ Kapitän"
    if "co-pilot" in rn or "copilot" in rn:
        return "✈️ Co-Pilot"
    return rank_role_for_miles(miles)


def user_has_mod_casino(hid: str) -> bool:
    try:
        import skytycoon_prestige_pack as prestige

        return prestige.pg_has_module(hid, "mod_casino")
    except Exception:
        return False


def casino_max_bet(hid: str) -> int:
    try:
        import skytycoon_prestige_pack as prestige

        return int(prestige._casino_max_bet(hid))
    except Exception:
        return 50_000


def casino_is_frozen() -> bool:
    try:
        import skytycoon_prestige_pack as prestige

        return prestige._casino_frozen()
    except Exception:
        return False


def fetch_rank_sync_rows() -> list[dict[str, Any]]:
    try:
        return fetchall(
            """
            SELECT u.hardware_id, u.username,
                   COALESCE(u.miles, 0) AS miles,
                   COALESCE(u.pilot_rank, '') AS pilot_rank,
                   COALESCE(u.prestige_level, 0) AS prestige_level,
                   d.discord_user_id
            FROM users u
            INNER JOIN discord_oauth_links d ON d.hardware_id = u.hardware_id
            WHERE d.discord_user_id IS NOT NULL AND d.discord_user_id != '';
            """
        )
    except psycopg2.Error:
        return fetchall(
            """
            SELECT u.hardware_id, u.username, 0::double precision AS miles,
                   ''::text AS pilot_rank, 0 AS prestige_level, d.discord_user_id
            FROM users u
            INNER JOIN discord_oauth_links d ON d.hardware_id = u.hardware_id
            WHERE d.discord_user_id IS NOT NULL AND d.discord_user_id != '';
            """
        )


def fetch_alliance_treasury_rows() -> list[dict[str, Any]]:
    try:
        return fetchall(
            """
            SELECT alliance_id, name,
                   COALESCE(bank_balance, credits, 0) AS treasury
            FROM alliances
            ORDER BY COALESCE(bank_balance, credits, 0) DESC NULLS LAST
            LIMIT 10;
            """
        )
    except psycopg2.Error:
        return fetchall(
            """
            SELECT alliance_id, name, COALESCE(credits, 0) AS treasury
            FROM alliances
            ORDER BY COALESCE(credits, 0) DESC NULLS LAST
            LIMIT 10;
            """
        )


async def sync_slash_commands_to_guild(bot: commands.Bot) -> list[app_commands.AppCommand]:
    """Guild-Sync: Slash-Befehle sind sofort sichtbar (globaler Sync kann bis zu 1h dauern)."""
    bot.tree.copy_global_to(guild=TARGET_GUILD)
    synced = await bot.tree.sync(guild=TARGET_GUILD)
    names = ", ".join(sorted(cmd.name for cmd in synced)) or "—"
    print(f"SkyTycoon guild slash sync ({TARGET_GUILD_ID}): {len(synced)} → {names}")
    return list(synced)


class SkyTycoonDiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.message_content = False
        intents.reactions = True
        super().__init__(command_prefix="!", intents=intents)
        self.configured_guild_ids: set[int] = set()
        self.last_seen: dict[str, float] = {
            "flight": time.time() - 3600,
            "auction": time.time() - 3600,
            "wallstreet": time.time() - 3600,
            "p2p": 0.0,
            "daily_market": "",
        }
        self.rules_message_ids: set[int] = set()

    async def setup_hook(self) -> None:
        ensure_discord_tables()
        self.tree.add_command(radar_command)
        self.tree.add_command(slots_command)
        self.tree.add_command(blackjack_command)
        self.tree.add_command(roulette_command)
        self.tree.add_command(stats_command)
        self.tree.add_command(leaderboard_command)
        self.tree.add_command(ticket_group)
        await sync_slash_commands_to_guild(self)
        self.postgres_ticker_loop.start()
        self.command_queue_loop.start()
        self.hourly_leaderboard_loop.start()
        self.market_poll_loop.start()
        self.radar_live_loop.start()
        self.treasury_report_loop.start()
        self.rank_sync_loop.start()
        self.discord_admin_loop.start()
        self.wallstreet_leaderboard_loop.start()

    async def on_ready(self) -> None:
        await sync_slash_commands_to_guild(self)
        guild = await self._resolve_guild()
        if guild is not None:
            await self.run_guild_setup(guild)
            try:
                await apply_official_channel_lockdown(guild)
                await setup_channel_guide_embeds(guild, self)
                await refresh_hourly_leaderboard(guild)
                await refresh_radar_channel(guild, self)
                await refresh_treasury_channel(guild)
            except Exception as exc:  # noqa: BLE001
                print(f"SkyTycoon Discord startup refresh: {exc}")
        print(f"SkyTycoon Discord Brain online as {self.user}")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if guild.id == int(DISCORD_GUILD_ID):
            await self.run_guild_setup(guild)
            print(f"SkyTycoon Discord auto setup completed for guild {guild.id}")

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if str(payload.emoji) != RULES_REACTION:
            return
        if payload.user_id == self.user.id:
            return
        mid = str(payload.message_id)
        if mid not in {channel_state_get("rules_embed"), *map(str, self.rules_message_ids)}:
            stored = channel_state_get("rules_embed")
            if stored and stored != mid:
                return
        guild = self.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.DiscordException:
                return
        student = discord.utils.get(guild.roles, name="👨‍✈️ Flugschüler")
        if student and student not in member.roles:
            await member.add_roles(student, reason="SkyTycoon rules accepted")
        execute(
            """
            INSERT INTO discord_rules_log (discord_user_id, hardware_id, accepted_ts)
            VALUES (%s, %s, %s)
            ON CONFLICT (discord_user_id) DO UPDATE SET accepted_ts = EXCLUDED.accepted_ts;
            """,
            (str(payload.user_id), str(member.display_name)[:128], time.time()),
        )
        try:
            await member.send(tr_bilingual("rules_accepted")[:1900])
        except discord.DiscordException:
            pass

    async def _resolve_guild(self) -> discord.Guild | None:
        guild = self.get_guild(int(DISCORD_GUILD_ID))
        if guild is None:
            try:
                guild = await self.fetch_guild(int(DISCORD_GUILD_ID))
            except discord.DiscordException as exc:
                print(f"SkyTycoon guild fetch failed: {exc}")
        if guild is None:
            guild = target_guild(self)
        return guild

    async def run_guild_setup(self, guild: discord.Guild) -> None:
        if guild.id in self.configured_guild_ids:
            return
        await ensure_guild_structure(guild)
        try:
            await sync_slash_commands_to_guild(self)
        except discord.DiscordException as exc:
            print(f"SkyTycoon guild slash sync warning: {exc}")
        await post_rules_embed(guild, self)
        await post_casino_guide_embed(guild, self)
        await apply_official_channel_lockdown(guild)
        await setup_channel_guide_embeds(guild, self)
        self.configured_guild_ids.add(guild.id)

    @tasks.loop(seconds=25)
    async def postgres_ticker_loop(self) -> None:
        for guild in self.guilds:
            await emit_recent_flights(guild, self.last_seen)
            await emit_recent_auctions(guild, self.last_seen)
            await emit_recent_wallstreet(guild, self.last_seen)

    @tasks.loop(seconds=20)
    async def crisis_alert_queue_loop(self) -> None:
        await consume_crisis_discord_queue(self)

    @tasks.loop(seconds=3)
    async def command_queue_loop(self) -> None:
        await consume_discord_command_queue(self)

    @tasks.loop(minutes=60)
    async def hourly_leaderboard_loop(self) -> None:
        await asyncio.sleep(5)
        for guild in self.guilds:
            await refresh_hourly_leaderboard(guild)

    @tasks.loop(seconds=45)
    async def market_poll_loop(self) -> None:
        for guild in self.guilds:
            await poll_market_channels(guild, self.last_seen)

    @tasks.loop(seconds=30)
    async def radar_live_loop(self) -> None:
        for guild in self.guilds:
            await refresh_radar_channel(guild, self)
            await poll_live_flight_departures(guild, self.last_seen)

    @tasks.loop(hours=1)
    async def treasury_report_loop(self) -> None:
        await asyncio.sleep(8)
        for guild in self.guilds:
            await refresh_treasury_channel(guild)

    @tasks.loop(seconds=3)
    async def rank_sync_loop(self) -> None:
        guild = target_guild(self)
        if guild is None:
            return
        await sync_pilot_rank_roles(guild)

    @tasks.loop(seconds=2)
    async def discord_admin_loop(self) -> None:
        await consume_discord_admin_commands(self)

    @tasks.loop(seconds=8)
    async def wallstreet_leaderboard_loop(self) -> None:
        """Wallstreet-Ticker nach Flug-Credits/Meilen (~8s) aktualisieren."""
        guild = target_guild(self)
        if guild is None:
            return
        await refresh_hourly_leaderboard(guild)


async def ensure_guild_structure(guild: discord.Guild) -> None:
    try:
        roles = await guild.fetch_roles()
    except discord.DiscordException:
        roles = list(getattr(guild, "roles", []) or [])
    try:
        channels = await guild.fetch_channels()
    except discord.DiscordException:
        channels = list(getattr(guild, "channels", []) or [])
    categories = [c for c in channels if isinstance(c, discord.CategoryChannel)]
    text_channels = [c for c in channels if isinstance(c, discord.TextChannel)]
    for role_spec in ROLE_SPECS:
        if discord.utils.get(roles, name=role_spec.name) is None:
            role = await guild.create_role(name=role_spec.name, color=role_spec.color, reason="SkyTycoon auto setup")
            roles.append(role)
    for _, rname in RANK_MILESTONES:
        if discord.utils.get(roles, name=rname) is None:
            role = await guild.create_role(name=rname, color=discord.Color.dark_teal(), reason="SkyTycoon rank role")
            roles.append(role)
    student = discord.utils.get(roles, name="👨‍✈️ Flugschüler")
    overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False)}
    if student:
        overwrites[student] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    for category_name, channel_names in CHANNEL_LAYOUT.items():
        category = discord.utils.get(categories, name=category_name)
        if category is None:
            category = await guild.create_category(category_name, overwrites=overwrites, reason="SkyTycoon auto setup")
            categories.append(category)
        for channel_name in channel_names:
            if discord.utils.get(text_channels, name=channel_name) is None:
                ch = await guild.create_text_channel(channel_name, category=category, reason="SkyTycoon auto setup")
                text_channels.append(ch)


def target_guild(bot: commands.Bot) -> discord.Guild | None:
    gid_raw = os.environ.get("DISCORD_GUILD_ID", DISCORD_GUILD_ID).strip()
    if gid_raw.isdigit():
        guild = bot.get_guild(int(gid_raw))
        if guild is not None:
            return guild
    return bot.guilds[0] if bot.guilds else None


def channel(guild: discord.Guild, name: str) -> discord.TextChannel | None:
    return discord.utils.get(guild.text_channels, name=name)


def channel_live_flights(guild: discord.Guild) -> discord.TextChannel | None:
    for nm in LIVE_FLIGHTS_CHANNEL_NAMES:
        ch = channel(guild, nm)
        if ch is not None:
            return ch
    return None


LOCKDOWN_CHANNEL_NAMES: tuple[str, ...] = (
    "📢-ankündigungen",
    "📢-news-updates",
    "🤖-bot-verifizierung",
)
VERIFY_CHANNEL_NAME = "🤖-bot-verifizierung"


def _lockdown_channel_ids_from_env() -> tuple[int, ...]:
    ids: list[int] = []
    for key in (
        "SKYTYCOON_DISCORD_ANNOUNCEMENTS_CHANNEL_ID",
        "SKYTYCOON_DISCORD_NEWS_CHANNEL_ID",
        "SKYTYCOON_DISCORD_VERIFY_CHANNEL_ID",
    ):
        raw = (os.environ.get(key) or "").strip()
        if raw.isdigit():
            ids.append(int(raw))
    return tuple(ids)


async def apply_official_channel_lockdown(guild: discord.Guild) -> None:
    """@everyone: lesen + Slash nur im Verifizierungskanal — kein Text-Spam."""
    everyone = guild.default_role
    targets: dict[int, discord.TextChannel] = {}
    for name in LOCKDOWN_CHANNEL_NAMES:
        ch = channel(guild, name)
        if ch is not None:
            targets[ch.id] = ch
    for cid in _lockdown_channel_ids_from_env():
        ch = guild.get_channel(cid)
        if isinstance(ch, discord.TextChannel):
            targets[ch.id] = ch
    if not targets:
        print("SkyTycoon channel lockdown: no target channels found")
        return
    for ch in targets.values():
        is_verify = ch.name == VERIFY_CHANNEL_NAME
        ow = discord.PermissionOverwrite(
            view_channel=True,
            read_messages=True,
            send_messages=False,
            send_messages_in_threads=False,
            create_public_threads=False,
            create_private_threads=False,
            add_reactions=False,
        )
        if is_verify:
            ow.use_application_commands = True
        else:
            ow.use_application_commands = False
        try:
            await ch.set_permissions(
                everyone,
                overwrite=ow,
                reason="SkyTycoon official channel lockdown",
            )
            print(f"SkyTycoon channel lockdown applied: {ch.name}")
        except discord.DiscordException as exc:
            print(f"SkyTycoon channel lockdown failed {ch.name}: {exc}")


async def channel_live_radar(
    guild: discord.Guild, bot: commands.Bot
) -> discord.TextChannel | None:
    """Live-Radar per Kanal-ID (smtp.env) oder Fallback auf Kanalname."""
    cid_raw = (
        os.environ.get("SKYTYCOON_DISCORD_LIVE_RADAR_CHANNEL_ID")
        or os.environ.get("SKYTYCOON_DISCORD_ADMIN_CHANNEL_ID")
        or LIVE_RADAR_CHANNEL_ID
    ).strip()
    if cid_raw.isdigit():
        ch = bot.get_channel(int(cid_raw))
        if isinstance(ch, discord.TextChannel):
            return ch
        try:
            fetched = await bot.fetch_channel(int(cid_raw))
            if isinstance(fetched, discord.TextChannel):
                return fetched
        except discord.DiscordException:
            pass
    return channel(guild, "📡-live-radar") or channel_live_flights(guild)


async def _casino_gate(interaction: discord.Interaction, hid: str) -> bool:
    """False = blockiert (Cooldown/Spam/Modul)."""
    blocked, until = _casino_cooldown_active(hid)
    if blocked:
        embed = discord.Embed(
            title="🛑 Casino Lockdown",
            description=tr_bilingual("casino_cooldown", until=until),
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return False
    if not _casino_spam_ok(str(interaction.user.id)):
        sec = int(_CASINO_SPAM_SEC)
        await interaction.followup.send(tr_bilingual("casino_spam", sec=sec), ephemeral=True)
        return False
    return True


async def replace_pinned_bot_message(
    ch: discord.TextChannel, state_key: str, embed: discord.Embed
) -> None:
    old_id = channel_state_get(state_key)
    if old_id.isdigit():
        try:
            old = await ch.fetch_message(int(old_id))
            await old.delete()
        except discord.DiscordException:
            pass
    msg = await ch.send(embed=embed)
    channel_state_set(state_key, str(msg.id))


async def post_rules_embed(guild: discord.Guild, bot: SkyTycoonDiscordBot) -> None:
    ch = channel(guild, "📜-regeln-rules")
    if ch is None:
        return
    embed = discord.Embed(
        title=tr("de", "rules_title") + " / " + tr("en", "rules_title"),
        description=tr_bilingual("rules_body"),
        color=discord.Color.from_rgb(212, 175, 55),
    )
    embed.set_footer(text="SkyTycoon Pro · DE/EN")
    old_id = channel_state_get("rules_embed")
    if old_id.isdigit():
        try:
            old = await ch.fetch_message(int(old_id))
            await old.delete()
        except discord.DiscordException:
            pass
    msg = await ch.send(embed=embed)
    channel_state_set("rules_embed", str(msg.id))
    bot.rules_message_ids.add(msg.id)
    try:
        await msg.add_reaction(RULES_REACTION)
    except discord.DiscordException:
        pass


def build_leaderboard_embed() -> discord.Embed:
    alliances = fetchall(
        """
        SELECT name, COALESCE(credits, 0) AS bal,
               (SELECT COUNT(*) FROM alliance_members m WHERE m.alliance_id = a.alliance_id) AS members
        FROM alliances a
        ORDER BY COALESCE(credits, 0) DESC NULLS LAST
        LIMIT 5;
        """
    )
    pilots = fetchall(
        """
        SELECT username, COALESCE(credits, money, 0) AS wealth
        FROM users
        WHERE username IS NOT NULL AND username != '' AND username != 'ADMIN_MASTER'
        ORDER BY wealth DESC NULLS LAST
        LIMIT 5;
        """
    )
    embed = discord.Embed(
        title=tr("de", "lb_title") + " / " + tr("en", "lb_title"),
        color=discord.Color.from_rgb(212, 175, 55),
        timestamp=discord.utils.utcnow(),
    )
    if alliances:
        lines_a = []
        for i, a in enumerate(alliances, 1):
            lines_a.append(f"**{i}.** {a.get('name', '?')} — `{float(a.get('bal') or 0):,.0f}` CR · {int(a.get('members') or 0)} members")
        embed.add_field(name=tr("de", "lb_alliances") + " / " + tr("en", "lb_alliances"), value="\n".join(lines_a)[:1024], inline=False)
    if pilots:
        lines_p = []
        for i, p in enumerate(pilots, 1):
            lines_p.append(f"**{i}.** {p.get('username', 'Pilot')} — `{float(p.get('wealth') or 0):,.0f}` CR")
        embed.add_field(name=tr("de", "lb_pilots") + " / " + tr("en", "lb_pilots"), value="\n".join(lines_p)[:1024], inline=False)
    embed.set_footer(text=f"{WEB_BASE} · PostgreSQL Live")
    return embed


async def refresh_hourly_leaderboard(guild: discord.Guild) -> None:
    ch = channel(guild, "📈-wallstreet-ticker")
    if ch is None:
        return
    await replace_pinned_bot_message(ch, "wallstreet_leaderboard", build_leaderboard_embed())


def _discord_phase_is_standby(phase: str) -> bool:
    p = str(phase or "").strip().lower()
    if not p:
        return True
    return any(x in p for x in ("gate", "parking", "standby", "parked", "boarding", "vorber"))


def _discord_phase_is_in_flight(phase: str) -> bool:
    p = str(phase or "").strip().lower()
    if _discord_phase_is_standby(p):
        return False
    if p in ("in_flight", "in-flight", "in flight"):
        return True
    return p in (
        "reiseflug",
        "cruise",
        "climb",
        "steigflug",
        "approach",
        "endanflug",
        "descent",
        "sinkflug",
    ) or "flight" in p


async def poll_live_flight_departures(guild: discord.Guild, last_seen: dict[str, Any]) -> None:
    """SimConnect-Abflüge → #live-flights / ✈️-live-flugbörse."""
    ch = channel_live_flights(guild)
    if ch is None:
        return
    if "live_flight_phase" not in last_seen:
        last_seen["live_flight_phase"] = {}
    phase_map: dict[str, str] = last_seen["live_flight_phase"]
    cutoff = time.time() - 18
    rows = fetchall(
        """
        SELECT hardware_id, pilot_name, route, aircraft, flight_phase, origin_icao, destination_icao
        FROM radar_positions
        WHERE COALESCE(NULLIF(last_heartbeat, 0), ts) >= %s AND COALESCE(status, 'ONLINE') = 'ONLINE'
        ORDER BY COALESCE(NULLIF(last_heartbeat, 0), ts) DESC LIMIT 40;
        """,
        (cutoff,),
    )
    for r in rows or []:
        hid = str(r.get("hardware_id") or "").strip()
        if not hid:
            continue
        phase = str(r.get("flight_phase") or "")
        prev = str(phase_map.get(hid) or "")
        phase_map[hid] = phase
        if _discord_phase_is_standby(phase):
            continue
        if not _discord_phase_is_in_flight(phase):
            continue
        if prev and _discord_phase_is_in_flight(prev):
            continue
        pilot = str(r.get("pilot_name") or "Pilot")
        route = (
            f"{r.get('origin_icao', '')}-{r.get('destination_icao', '')}".strip("-")
            or str(r.get("route") or "—")
        )
        embed = discord.Embed(
            title=tr("de", "flight_live") + " / " + tr("en", "flight_live"),
            description=(
                f"**DE:** ✈️ {pilot} ist jetzt **IN FLIGHT** ({route}).\n"
                f"**EN:** ✈️ {pilot} is now **IN FLIGHT** ({route})."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(name="Aircraft", value=str(r.get("aircraft") or "—"), inline=True)
        embed.add_field(name="Phase", value=phase[:64], inline=True)
        await ch.send(embed=embed)


async def refresh_radar_channel(
    guild: discord.Guild, bot: commands.Bot | None = None
) -> None:
    ch = await channel_live_radar(guild, bot)
    if ch is None:
        return
    cutoff = time.time() - 18
    rows = fetchall(
        """
        SELECT rp.pilot_name, rp.route, rp.aircraft, rp.alt, rp.ground_speed, rp.flight_phase,
               rp.origin_icao, rp.destination_icao, rp.lat, rp.lon, rp.hardware_id,
               COALESCE(u.callsign_prefix, '') AS callsign_prefix
        FROM radar_positions rp
        LEFT JOIN users u ON u.hardware_id = rp.hardware_id
        WHERE COALESCE(NULLIF(rp.last_heartbeat, 0), rp.ts) >= %s
          AND COALESCE(rp.status, 'ONLINE') = 'ONLINE'
        ORDER BY COALESCE(NULLIF(rp.last_heartbeat, 0), rp.ts) DESC LIMIT 12;
        """,
        (cutoff,),
    )
    embed = discord.Embed(
        title=tr("de", "radar_title") + " / " + tr("en", "radar_title"),
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    if not rows:
        embed.description = tr_bilingual("radar_empty")
    else:
        lines = []
        for r in rows:
            route = f"{r.get('origin_icao', '')}-{r.get('destination_icao', '')}".strip("-") or str(r.get("route") or "—")
            pilot = str(r.get("pilot_name") or "Pilot").strip()
            hid = str(r.get("hardware_id") or "").strip()
            phase = str(r.get("flight_phase") or "")
            if hid:
                try:
                    import skytycoon_prestige_pack as prestige

                    pilot = prestige.pg_display_pilot_name(hid, pilot)
                except Exception:
                    prefix = str(r.get("callsign_prefix") or "").strip()
                    if prefix and not pilot.startswith(prefix):
                        pilot = f"{prefix} {pilot}"[:120]
            standby = _discord_phase_is_standby(phase)
            badge = "🟡 **STANDBY** · " if standby else ""
            phase_txt = "STANDBY / GATE" if standby else phase[:48]
            lines.append(
                f"{badge}**{pilot}** · {r.get('aircraft', 'AC')} · {route}\n"
                f"`{int(float(r.get('alt') or 0)):,} ft` · `{int(float(r.get('ground_speed') or 0))} kt` · {phase_txt}"
            )
        embed.description = "\n\n".join(lines)[:4000]
        embed.color = discord.Color.gold() if any(
            _discord_phase_is_standby(str(r.get("flight_phase") or "")) for r in rows
        ) else discord.Color.green()
    embed.add_field(
        name="Map",
        value=f"[🗺 Interactive radar]({WEB_BASE}/market/radar)",
        inline=False,
    )
    embed.set_footer(text=f"{WEB_BASE} · Live 18s · {BOT_BUILD_TAG}")
    await replace_pinned_bot_message(ch, "live_radar", embed)


async def refresh_treasury_channel(guild: discord.Guild) -> None:
    ch = channel(guild, "🏦-allianz-bank")
    if ch is None:
        return
    rows = fetch_alliance_treasury_rows()
    embed = discord.Embed(
        title=tr("de", "treasury_title") + " / " + tr("en", "treasury_title"),
        color=discord.Color.from_rgb(212, 175, 55),
    )
    if rows:
        lines = []
        for i, r in enumerate(rows, 1):
            lines.append(f"**{i}.** {r.get('name', '?')} — `{float(r.get('treasury') or 0):,.0f}` CR")
        embed.description = "\n".join(lines)[:4000]
    await replace_pinned_bot_message(ch, "alliance_treasury", embed)
    if rows:
        top_name = str(rows[0].get("name") or "")
        tycoon_role = discord.utils.get(guild.roles, name="👑 Tycoon des Monats")
        if tycoon_role:
            ceo_row = fetchone(
                """
                SELECT m.hardware_id FROM alliance_members m
                JOIN alliances a ON a.alliance_id = m.alliance_id
                WHERE a.name = %s AND m.role IN ('CEO', 'ceo')
                LIMIT 1;
                """,
                (top_name,),
            )
            if ceo_row:
                link = fetchone(
                    "SELECT discord_user_id FROM discord_oauth_links WHERE hardware_id = %s LIMIT 1;",
                    (str(ceo_row["hardware_id"]),),
                )
                if link and str(link.get("discord_user_id") or "").isdigit():
                    try:
                        member = await guild.fetch_member(int(link["discord_user_id"]))
                        for m in guild.members:
                            if tycoon_role in m.roles and m.id != member.id:
                                await m.remove_roles(tycoon_role, reason="Tycoon rotation")
                        if tycoon_role not in member.roles:
                            await member.add_roles(tycoon_role, reason="Top alliance treasury")
                    except discord.DiscordException:
                        pass


async def poll_market_channels(guild: discord.Guild, last_seen: dict[str, Any]) -> None:
    ch = channel(guild, "🛩-gebrauchtbörse")
    if ch is None:
        return
    rows = fetchall(
        """
        SELECT id, owner_username, price_per_day, status, end_time_utc, aircraft_id
        FROM p2p_listings
        WHERE COALESCE(status, 'active') IN ('active', 'open', 'listed')
        ORDER BY id DESC LIMIT 20;
        """
    )
    max_id = int(last_seen.get("p2p") or 0)
    for row in rows:
        lid = int(row.get("id") or 0)
        if lid <= max_id:
            continue
        last_seen["p2p"] = max(max_id, lid)
        cond_pct = 85.0
        part = fetchone(
            """
            SELECT COALESCE(condition, 85) AS condition, part_name, price
            FROM parts_market
            WHERE seller_username = %s
            ORDER BY created_ts DESC NULLS LAST
            LIMIT 1;
            """,
            (str(row.get("owner_username") or ""),),
        )
        if part:
            cond_pct = float(part.get("condition") or 85)
        embed = discord.Embed(
            title=tr("de", "market_title") + " / " + tr("en", "market_title"),
            color=discord.Color.from_rgb(212, 175, 55),
        )
        embed.add_field(
            name=tr("de", "market_seller") + " / " + tr("en", "market_seller"),
            value=str(row.get("owner_username") or "Pilot"),
            inline=True,
        )
        embed.add_field(
            name=tr("de", "market_condition") + " / " + tr("en", "market_condition"),
            value=f"{cond_pct:.0f} %",
            inline=True,
        )
        embed.add_field(
            name=tr("de", "market_price") + " / " + tr("en", "market_price"),
            value=f"{int(row.get('price_per_day') or 0):,} CR / Tag",
            inline=True,
        )
        embed.add_field(
            name=tr("de", "market_link") + " / " + tr("en", "market_link"),
            value=f"[{WEB_BASE}/market/leasing]({WEB_BASE}/market/leasing) · [{WEB_BASE}/werft/auctions]({WEB_BASE}/werft/auctions)",
            inline=False,
        )
        await ch.send(embed=embed)
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    if last_seen.get("daily_market") != day_key:
        deals = fetchall(
            "SELECT item_name, price_credits, trend_pct FROM daily_market WHERE status = 'active' ORDER BY price_credits DESC LIMIT 5;"
        )
        if deals:
            embed = discord.Embed(
                title=tr("de", "market_daily") + " / " + tr("en", "market_daily"),
                color=discord.Color.blue(),
            )
            embed.description = "\n".join(
                f"• **{d.get('item_name', '?')}** — {int(d.get('price_credits') or 0):,} CR ({float(d.get('trend_pct') or 0):+.1f}%)"
                for d in deals
            )[:4000]
            embed.add_field(name="Shop", value=f"{WEB_BASE}/market/daily_auctions", inline=False)
            await ch.send(embed=embed)
        last_seen["daily_market"] = day_key


async def apply_rank_role_to_member(
    guild: discord.Guild,
    member: discord.Member,
    miles: float,
    pilot_rank: str = "",
    prestige_level: int = 0,
) -> str:
    target = rank_role_for_rank_name(pilot_rank, miles, prestige_level)
    rank_roles = {name for _, name in RANK_MILESTONES}
    target_role = discord.utils.get(guild.roles, name=target)
    if not target_role:
        return target
    for rname in rank_roles:
        role = discord.utils.get(guild.roles, name=rname)
        if role and role in member.roles and role.id != target_role.id:
            await member.remove_roles(role, reason="SkyTycoon rank sync")
    if target_role not in member.roles:
        await member.add_roles(target_role, reason="SkyTycoon rank sync PostgreSQL")
    return target


async def sync_one_member_rank(guild: discord.Guild, hardware_id: str) -> None:
    hid = str(hardware_id or "").strip()[:128]
    if not hid:
        return
    row = fetchone(
        """
        SELECT u.hardware_id, COALESCE(u.miles, 0) AS miles,
               COALESCE(u.pilot_rank, '') AS pilot_rank,
               COALESCE(u.prestige_level, 0) AS prestige_level,
               d.discord_user_id
        FROM users u
        LEFT JOIN discord_oauth_links d ON d.hardware_id = u.hardware_id
        WHERE u.hardware_id = %s
        LIMIT 1;
        """,
        (hid,),
    )
    if not row:
        row = fetchone(
            """
            SELECT u.hardware_id, 0::double precision AS miles,
                   ''::text AS pilot_rank, 0 AS prestige_level, d.discord_user_id
            FROM users u
            LEFT JOIN discord_oauth_links d ON d.hardware_id = u.hardware_id
            WHERE u.hardware_id = %s
            LIMIT 1;
            """,
            (hid,),
        )
    if not row:
        return
    uid = str(row.get("discord_user_id") or "")
    if not uid.isdigit():
        return
    try:
        member = await guild.fetch_member(int(uid))
        await apply_rank_role_to_member(
            guild,
            member,
            float(row.get("miles") or 0),
            str(row.get("pilot_rank") or ""),
            int(row.get("prestige_level") or 0),
        )
    except discord.DiscordException:
        pass


async def sync_pilot_rank_roles(guild: discord.Guild) -> None:
    for row in fetch_rank_sync_rows():
        uid = str(row.get("discord_user_id") or "")
        if not uid.isdigit():
            continue
        try:
            member = await guild.fetch_member(int(uid))
            await apply_rank_role_to_member(
                guild,
                member,
                float(row.get("miles") or 0),
                str(row.get("pilot_rank") or ""),
                int(row.get("prestige_level") or 0),
            )
        except discord.DiscordException:
            continue


async def post_casino_guide_embed(guild: discord.Guild, bot: commands.Bot) -> None:
    ch = channel(guild, "🎰-casino") or channel(guild, "🎰-casino-lounge")
    if ch is None:
        return
    key = "casino_guide"
    if channel_state_get(key):
        return
    embed = discord.Embed(
        title=tr("de", "casino_guide_title") + " / " + tr("en", "casino_guide_title"),
        description=tr("de", "casino_guide_body") + "\n\n---\n\n" + tr("en", "casino_guide_body"),
        color=discord.Color.from_rgb(212, 175, 55),
    )
    embed.set_footer(text="SkyTycoon Pro · PostgreSQL Live-Casino")
    msg = await ch.send(embed=embed)
    channel_state_set(key, str(msg.id))


async def consume_discord_admin_commands(bot: commands.Bot) -> None:
    rows = fetchall(
        """
        SELECT id, command_type, target_user, val1, val2
        FROM discord_admin_commands
        WHERE processed = 0
        ORDER BY id ASC
        LIMIT 10;
        """
    )
    guild = target_guild(bot)
    if guild is None:
        return
    for row in rows:
        cid = int(row["id"])
        ctype = str(row.get("command_type") or "").upper()
        target = str(row.get("target_user") or "").strip()
        val1 = str(row.get("val1") or "")
        val2 = str(row.get("val2") or "")
        try:
            if ctype == "EMBED_ANNOUNCEMENT":
                ch = channel(guild, "📢-ankündigungen")
                if ch:
                    color = discord.Color.gold()
                    if val2.lower() in ("red", "rot"):
                        color = discord.Color.red()
                    elif val2.lower() in ("blue", "blau"):
                        color = discord.Color.blue()
                    embed = discord.Embed(title="📢 SkyTycoon", description=val1[:1800], color=color)
                    await ch.send(embed=embed)
            elif ctype == "CASINO_SHUTDOWN":
                execute(
                    """
                    INSERT INTO discord_casino_state (state_key, state_value, updated_ts)
                    VALUES ('frozen', %s, %s)
                    ON CONFLICT (state_key) DO UPDATE SET state_value = EXCLUDED.state_value;
                    """,
                    (val1 or "1", time.time()),
                )
            elif ctype == "PAYPAL_PLATIN":
                await handle_paypal_platin_alert(guild, {"pilot_name": val1, "discord_user_id": target, "hardware_id": val2})
            elif ctype == "ANTI_CHEAT_PRANGER":
                await handle_anti_cheat_pranger(
                    guild,
                    {"pilot_name": val1, "reason": val2, "discord_user_id": target},
                )
            elif ctype == "ALLIANCE_VOICE":
                await handle_alliance_voice_sync(guild, {"alliance_name": val1, "leader_discord_id": target})
            elif ctype == "BAN_USER":
                uid = target if target.isdigit() else ""
                if not uid:
                    link = fetchone(
                        "SELECT discord_user_id FROM discord_oauth_links d JOIN users u ON u.hardware_id = d.hardware_id WHERE LOWER(u.username) = LOWER(%s) LIMIT 1;",
                        (target[:120],),
                    )
                    uid = str(link.get("discord_user_id") or "") if link else ""
                if uid.isdigit():
                    member = await guild.fetch_member(int(uid))
                    await member.ban(reason="SkyTycoon Admin Commander")
            elif ctype == "MUTE_USER":
                uid = target if target.isdigit() else ""
                if not uid and target:
                    link = fetchone(
                        "SELECT discord_user_id FROM discord_oauth_links d JOIN users u ON u.hardware_id = d.hardware_id WHERE LOWER(u.username) = LOWER(%s) LIMIT 1;",
                        (target[:120],),
                    )
                    uid = str(link.get("discord_user_id") or "") if link else ""
                if uid.isdigit():
                    member = await guild.fetch_member(int(uid))
                    until = datetime.now(timezone.utc) + timedelta(hours=24)
                    await member.timeout(until, reason="SkyTycoon Admin mute")
            execute(
                "UPDATE discord_admin_commands SET processed = 1, processed_ts = %s WHERE id = %s;",
                (time.time(), cid),
            )
        except Exception as exc:  # noqa: BLE001
            execute(
                "UPDATE discord_admin_commands SET processed = 1, processed_ts = %s, error = %s WHERE id = %s;",
                (time.time(), str(exc)[:900], cid),
            )


CRISIS_QUEUE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "server_logs", "crisis_discord_queue.jsonl"
)


async def consume_crisis_discord_queue(bot: commands.Bot) -> None:
    """Server schreibt Krisen in JSONL — Bot postet rotes Embed in #news-updates."""
    if not os.path.isfile(CRISIS_QUEUE_FILE):
        return
    try:
        with open(CRISIS_QUEUE_FILE, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return
    if not lines:
        return
    try:
        with open(CRISIS_QUEUE_FILE, "w", encoding="utf-8") as fh:
            fh.write("")
    except OSError:
        return
    for guild in bot.guilds:
        ch = channel(guild, "📢-news-updates")
        if ch is None:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            embed = discord.Embed(
                title="🚨 KRISEN-ALARM / CRISIS ALERT",
                description=(
                    f"**{ev.get('title_de', '')}**\n"
                    f"**{ev.get('title_en', '')}**\n"
                    f"ICAO `{ev.get('airport_icao', '????')}` · "
                    f"{ev.get('crisis_type', '')} · Intensität {ev.get('intensity', '?')}"
                ),
                color=discord.Color.red(),
            )
            embed.add_field(
                name="Web-Radar",
                value=f"{WEB_BASE}/market/weather",
                inline=False,
            )
            try:
                await ch.send(embed=embed)
            except discord.DiscordException:
                pass


async def handle_paypal_platin_alert(guild: discord.Guild, payload: dict[str, Any]) -> None:
    uid = str(payload.get("discord_user_id") or "").strip()
    pilot = str(payload.get("pilot_name") or payload.get("username") or "Captain")[:80]
    role = discord.utils.get(guild.roles, name=PLATIN_SUPPORTER_ROLE)
    if uid.isdigit() and role:
        try:
            member = await guild.fetch_member(int(uid))
            await member.add_roles(role, reason="SkyTycoon PayPal Platin")
        except discord.DiscordException:
            pass
    ch = channel(guild, "📢-ankündigungen") or channel_live_flights(guild)
    if ch:
        embed = discord.Embed(
            title=tr("de", "platin_alert") + " / " + tr("en", "platin_alert"),
            description=tr_bilingual("platin_body", pilot=pilot),
            color=discord.Color.from_rgb(212, 175, 55),
        )
        await ch.send(content="@everyone", embed=embed, allowed_mentions=discord.AllowedMentions(everyone=True))


async def handle_radar_pilot_online(
    guild: discord.Guild, payload: dict[str, Any], bot: commands.Bot | None = None
) -> None:
    """Live-Radar: Pilot erscheint auf FIDS — animiertes Embed im Radar-Kanal."""
    pilot = str(payload.get("pilot_name") or "Pilot").strip()[:80]
    ac = str(payload.get("aircraft") or "B738")[:120]
    phase = str(payload.get("flight_phase") or "AM GATE / PARKING")[:64]
    icao = str(payload.get("current_icao") or "STANDBY")[:8]
    online_n = int(payload.get("online_count") or 0)
    ch = await channel_live_radar(guild, bot) or channel_live_flights(guild)
    if ch is None:
        return
    pulse = ("🟢", "📡", "✈️", "🛫")
    title_de = f"{pulse[0]} Live-Radar · Pilot online"
    title_en = f"{pulse[1]} Live radar · pilot online"
    embed = discord.Embed(
        title=f"{title_de} / {title_en}",
        description=(
            f"**DE:** **{pilot}** ist jetzt auf der Live-Flugtafel "
            f"({online_n} Pilot{'en' if online_n != 1 else ''} online).\n"
            f"**EN:** **{pilot}** is now on the live flight board "
            f"({online_n} pilot{'s' if online_n != 1 else ''} online)."
        ),
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Aircraft / Typ", value=ac, inline=True)
    embed.add_field(name="Phase", value=phase, inline=True)
    embed.add_field(name="ICAO", value=icao, inline=True)
    embed.set_footer(
        text=f"{WEB_BASE} · {pulse[2]}→{pulse[3]} Überschall-Sync · {BOT_BUILD_TAG}"
    )
    await ch.send(embed=embed)
    await refresh_radar_channel(guild, bot)


async def handle_anti_cheat_pranger(guild: discord.Guild, payload: dict[str, Any]) -> None:
    pilot = str(payload.get("pilot_name") or "Unknown")[:80]
    reason = str(payload.get("reason") or payload.get("cheat_code") or "cloud_shield")[:200]
    uid = str(payload.get("discord_user_id") or "").strip()
    ch = channel(guild, "📢-ankündigungen") or channel(guild, "🤖-bot-verifizierung")
    if ch:
        embed = discord.Embed(
            title=tr("de", "anticheat_title") + " / " + tr("en", "anticheat_title"),
            description=tr_bilingual("anticheat_body", pilot=pilot, reason=reason),
            color=discord.Color.red(),
        )
        await ch.send(embed=embed)
    if uid.isdigit():
        try:
            member = await guild.fetch_member(int(uid))
            await member.timeout(
                datetime.now(timezone.utc) + timedelta(days=7),
                reason=f"Anti-Cheat: {reason}",
            )
        except discord.DiscordException:
            pass


async def handle_alliance_voice_sync(guild: discord.Guild, payload: dict[str, Any]) -> None:
    name = str(payload.get("alliance_name") or "Alliance")[:48]
    leader_id = str(payload.get("leader_discord_id") or payload.get("discord_user_id") or "")
    cat = discord.utils.get(guild.categories, name="🌐 COMMUNITY LIVE")
    overwrites: dict[Any, Any] = {
        guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
        guild.me: discord.PermissionOverwrite(connect=True, manage_channels=True),
    }
    if leader_id.isdigit():
        try:
            leader = await guild.fetch_member(int(leader_id))
            overwrites[leader] = discord.PermissionOverwrite(connect=True, speak=True)
        except discord.DiscordException:
            pass
    try:
        vc = await guild.create_voice_channel(
            f"🔊-{name[:20]}",
            category=cat,
            overwrites=overwrites,
            reason="SkyTycoon alliance voice (24h)",
        )
        ch = channel(guild, "🏦-allianz-bank")
        if ch:
            await ch.send(tr_bilingual("alliance_voice", name=name) + f"\n<#{vc.id}>")
    except discord.DiscordException:
        pass


async def handle_purchase_invoice_dm(bot: commands.Bot, payload: dict[str, Any]) -> None:
    uid = str(payload.get("discord_user_id") or "").strip()
    item = str(payload.get("item") or payload.get("product") or "Purchase")[:120]
    amount = int(float(payload.get("amount") or payload.get("credits") or 0))
    if not uid.isdigit():
        return
    try:
        user = await bot.fetch_user(int(uid))
        await user.send(tr_bilingual("invoice_dm", item=item, amount=amount))
    except discord.DiscordException:
        pass


async def ensure_god_admin_role(guild: discord.Guild) -> discord.Role:
    """Höchste Admin-Rolle — Gold, hoist, möglichst weit oben."""
    role = discord.utils.get(guild.roles, name=GOD_ADMIN_ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=GOD_ADMIN_ROLE_NAME,
            color=discord.Color.gold(),
            hoist=True,
            mentionable=True,
            reason="SkyTycoon global superadmin",
        )
    try:
        me = guild.me
        if me and me.top_role:
            target_pos = max(1, me.top_role.position - 1)
            if role.position < target_pos:
                await role.edit(
                    position=target_pos,
                    color=discord.Color.gold(),
                    hoist=True,
                    reason="SkyTycoon God-Admin top rank",
                )
    except discord.DiscordException:
        pass
    return role


async def sync_oauth_member(bot: commands.Bot, payload: dict[str, Any]) -> None:
    guild = target_guild(bot)
    if guild is None:
        raise RuntimeError("discord_guild_not_found")
    user_id = str(payload.get("discord_user_id") or "").strip()
    access_token = str(payload.get("access_token") or "").strip()
    username = str(payload.get("web_username") or "SkyTycoon Pilot").strip()[:32]
    portal_email = str(payload.get("portal_email") or "").strip().lower()
    is_superadmin = bool(payload.get("is_superadmin")) or (
        portal_email == GLOBAL_SUPERADMIN_EMAIL
    )
    verified_ok = bool(payload.get("license_active")) or is_superadmin
    if not user_id or not access_token:
        raise RuntimeError("missing_discord_user_or_token")
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", DISCORD_BOT_TOKEN).strip()
    verified = discord.utils.get(guild.roles, name="⭐ Verifizierter Pilot")
    student = discord.utils.get(guild.roles, name="👨‍✈️ Flugschüler")
    platin = discord.utils.get(guild.roles, name=PLATIN_SUPPORTER_ROLE)
    god_admin = await ensure_god_admin_role(guild) if is_superadmin else None
    role_ids: list[int] = []
    if is_superadmin and god_admin:
        role_ids.append(int(god_admin.id))
    if verified_ok and verified:
        role_ids.append(int(verified.id))
    elif student and not is_superadmin:
        role_ids.append(int(student.id))
    if verified_ok and platin:
        role_ids.append(int(platin.id))
    async with aiohttp.ClientSession() as session:
        async with session.put(
            f"https://discord.com/api/v10/guilds/{guild.id}/members/{user_id}",
            headers={"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"},
            json={"access_token": access_token, "nick": username, "roles": role_ids},
            timeout=15,
        ) as resp:
            if resp.status not in (200, 201, 204):
                txt = await resp.text()
                raise RuntimeError(f"discord_join_failed:{resp.status}:{txt[:180]}")
    member = await guild.fetch_member(int(user_id))
    try:
        await member.edit(nick=username, reason="SkyTycoon OAuth nickname sync")
    except discord.DiscordException:
        pass
    if verified_ok and verified:
        await member.add_roles(verified, reason="SkyTycoon OAuth license verified")
    if verified_ok and platin and platin not in member.roles:
        await member.add_roles(platin, reason="SkyTycoon OAuth Platin sync")
    if is_superadmin and god_admin and god_admin not in member.roles:
        await member.add_roles(god_admin, reason="SkyTycoon God-Admin OAuth")
    if verified_ok and student and student in member.roles:
        await member.remove_roles(student, reason="SkyTycoon OAuth license verified")
    try:
        if is_superadmin:
            await member.send(
                "👑 **DE:** Willkommen, Server-Besitzer! God-Admin-Rolle ist aktiv.\n"
                "👑 **EN:** Welcome, server owner! God-Admin role is active."
            )
        else:
            await member.send(tr_bilingual("oauth_welcome_dm", name=username)[:1900])
    except discord.DiscordException:
        pass
    ch = channel(guild, "🤖-bot-verifizierung")
    admin_ch_id = (
        os.environ.get("SKYTYCOON_DISCORD_ADMIN_CHANNEL_ID") or "1506143279555809341"
    ).strip()
    admin_ch = guild.get_channel(int(admin_ch_id)) if admin_ch_id.isdigit() else None
    if is_superadmin and admin_ch:
        fest = discord.Embed(
            title="👑 God-Admin verbunden / God-Admin linked",
            description=(
                f"**{username}** (`{GLOBAL_SUPERADMIN_EMAIL}`) → <@{user_id}>\n"
                "DE: Höchste Server-Rolle vergeben · EN: Top server role granted."
            ),
            color=discord.Color.gold(),
        )
        await admin_ch.send(embed=fest)
    if ch:
        embed = discord.Embed(
            title=tr("de", "oauth_joined") + " / " + tr("en", "oauth_joined"),
            description=f"**{username}** → <@{user_id}>",
            color=discord.Color.gold() if verified_ok else discord.Color.dark_grey(),
        )
        await ch.send(embed=embed)


async def consume_discord_command_queue(bot: commands.Bot) -> None:
    ensure_discord_tables()
    rows = fetchall(
        """
        SELECT id, command_type, payload_json
        FROM discord_bot_commands
        WHERE status = 'queued'
        ORDER BY id ASC
        LIMIT 12;
        """
    )
    for row in rows:
        cid = int(row["id"])
        execute("UPDATE discord_bot_commands SET status = 'processing' WHERE id = %s;", (cid,))
        try:
            payload = json.loads(str(row.get("payload_json") or "{}"))
            ctype = str(row.get("command_type") or "")
            if ctype == "oauth_member_sync":
                await sync_oauth_member(bot, payload)
            elif ctype == "admin_broadcast":
                guild = target_guild(bot)
                ch = channel(guild, "📢-ankündigungen") if guild else None
                if ch is None:
                    raise RuntimeError("announcement_channel_missing")
                msg = str(payload.get("message") or "").strip()[:1800]
                severity = str(payload.get("severity") or "info").lower()
                color = discord.Color.gold()
                if severity in ("warn", "warning", "maintenance"):
                    color = discord.Color.orange()
                elif severity in ("critical", "error"):
                    color = discord.Color.red()
                embed = discord.Embed(
                    title="⚠️ " + tr("de", "broadcast") + " / " + tr("en", "broadcast"),
                    description=msg,
                    color=color,
                )
                embed.set_footer(text="Admin Commander · SkyTycoon Pro")
                await ch.send(embed=embed)
            elif ctype == "rank_sync":
                guild = target_guild(bot)
                if guild:
                    hid = str(payload.get("hardware_id") or "")
                    await sync_one_member_rank(guild, hid)
                    ch = channel(guild, "🤖-bot-verifizierung")
                    if ch and payload.get("rank_name"):
                        embed = discord.Embed(
                            title=tr("de", "rank_sync", role=payload.get("rank_name", ""))
                            + " / "
                            + tr("en", "rank_sync", role=payload.get("rank_name", "")),
                            color=discord.Color.gold(),
                        )
                        await ch.send(embed=embed)
            elif ctype == "msfs_crash_recovery":
                guild = target_guild(bot)
                ch = channel(guild, "✈️-live-flugbörse") if guild else None
                if ch:
                    pilot = str(payload.get("pilot_name") or "Pilot")
                    pct = float(payload.get("progress_pct") or 0)
                    cr = float(payload.get("credits") or 0)
                    nm = float(payload.get("miles") or 0)
                    route = str(payload.get("route") or "—")
                    embed = discord.Embed(
                        title="🚨 MSFS-Absturz / MSFS crash",
                        description=(
                            f"**DE:** MSFS-Absturz bei **{pilot}** erkannt! "
                            f"Die Blackbox hat **{pct:.0f}%** der Flugstrecke gesichert "
                            f"({route}). **+{cr:,.0f} CR** und **+{nm:,.1f} NM** gutgeschrieben.\n\n"
                            f"**EN:** MSFS crash for **{pilot}**. Blackbox secured **{pct:.0f}%** "
                            f"of route ({route}). **+{cr:,.0f} CR** and **+{nm:,.1f} NM** credited."
                        ),
                        color=discord.Color.red(),
                    )
                    embed.set_footer(text=f"{WEB_BASE}/player/career_backup")
                    await ch.send(embed=embed)
            elif ctype == "msfs_crash_insurance":
                guild = target_guild(bot)
                ch = channel(guild, "🏦-allianz-bank") if guild else None
                if ch is None and guild:
                    ch = channel(guild, "✈️-live-flugbörse")
                if ch:
                    pilot = str(payload.get("pilot_name") or "Pilot")
                    cr = float(payload.get("credits") or 0)
                    nm = float(payload.get("miles") or 0)
                    embed = discord.Embed(
                        title="🛡️ Vollkasko-Wunder / Full coverage",
                        description=(
                            f"**DE:** Aviation-Vollkasko für **{pilot}** — **100%** Crash-Rettung: "
                            f"+{cr:,.0f} CR, +{nm:,.1f} NM.\n\n"
                            f"**EN:** Full coverage for **{pilot}** — **100%** crash recovery: "
                            f"+{cr:,.0f} CR, +{nm:,.1f} NM."
                        ),
                        color=discord.Color.gold(),
                    )
                    await ch.send(embed=embed)
            elif ctype == "paypal_platin_alert":
                guild = target_guild(bot)
                if guild:
                    await handle_paypal_platin_alert(guild, payload)
            elif ctype == "radar_pilot_online":
                guild = target_guild(bot)
                if guild:
                    await handle_radar_pilot_online(guild, payload, bot)
            elif ctype == "anti_cheat_pranger":
                guild = target_guild(bot)
                if guild:
                    await handle_anti_cheat_pranger(guild, payload)
            elif ctype == "alliance_voice_sync":
                guild = target_guild(bot)
                if guild:
                    await handle_alliance_voice_sync(guild, payload)
            elif ctype == "purchase_invoice_dm":
                await handle_purchase_invoice_dm(bot, payload)
            elif ctype == "admin_ban_user":
                guild = target_guild(bot)
                if guild:
                    uid = str(payload.get("discord_user_id") or "").strip()
                    uname = str(payload.get("username") or "").strip()[:120]
                    if not uid and uname:
                        link = fetchone(
                            """
                            SELECT discord_user_id FROM discord_oauth_links d
                            JOIN users u ON u.hardware_id = d.hardware_id
                            WHERE lower(trim(u.username)) = lower(trim(%s))
                            LIMIT 1;
                            """,
                            (uname,),
                        )
                        uid = str(link.get("discord_user_id") or "") if link else ""
                    if uid.isdigit():
                        try:
                            member = await guild.fetch_member(int(uid))
                            await member.ban(
                                reason="SkyTycoon Admin Commander — permanent delete",
                                delete_message_seconds=0,
                            )
                        except discord.DiscordException:
                            pass
            elif ctype == "ticket_reply":
                guild = target_guild(bot)
                ch_id = str(payload.get("discord_channel_id") or "")
                txt = str(payload.get("message") or "").strip()[:1900]
                if guild and ch_id.isdigit():
                    try:
                        tch = await bot.fetch_channel(int(ch_id))
                        if isinstance(tch, discord.TextChannel):
                            embed = discord.Embed(
                                title=tr("de", "ticket_reply") + " / " + tr("en", "ticket_reply"),
                                description=txt,
                                color=discord.Color.blue(),
                            )
                            await tch.send(embed=embed)
                    except discord.DiscordException:
                        pass
                elif guild:
                    ch = channel(guild, "🎫-support-tickets")
                    if ch:
                        embed = discord.Embed(
                            title=tr("de", "ticket_reply") + " / " + tr("en", "ticket_reply"),
                            description=f"**{payload.get('pilot_name', 'Pilot')}**\n{txt}",
                            color=discord.Color.blue(),
                        )
                        await ch.send(embed=embed)
            execute(
                "UPDATE discord_bot_commands SET status = 'done', processed_ts = %s WHERE id = %s;",
                (time.time(), cid),
            )
        except Exception as exc:  # noqa: BLE001
            execute(
                "UPDATE discord_bot_commands SET status = 'error', processed_ts = %s, error = %s WHERE id = %s;",
                (time.time(), str(exc)[:1000], cid),
            )


def _license_active(status: Any) -> bool:
    s = str(status or "").strip().lower()
    return s in ("1", "active", "activated", "true", "yes", "lifetime", "pro")


@app_commands.command(
    name="verify",
    description="Deprecated — use website OAuth / Veraltet — Web-OAuth nutzen",
)
async def verify_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        tr_bilingual("verify_deprecated")[:1900],
        ephemeral=True,
    )


@app_commands.command(name="radar", description="Live METAR/runway/crosswind from PostgreSQL / Live-Radar")
@app_commands.describe(icao="Airport ICAO (optional)")
async def radar_command(interaction: discord.Interaction, icao: str = "") -> None:
    await interaction.response.defer(ephemeral=False)
    lang = "en" if str(interaction.locale or "").lower().startswith("en") else "de"
    icao_c = (icao or "EDDF").strip().upper()[:4]
    wind_txt = runway_txt = xwind_txt = "—"
    pilots_n = 0
    try:
        rows = fetchall(
            """
            SELECT pilot_name, aircraft_model, flight_phase, ground_speed, origin_icao, destination_icao
            FROM radar_positions
            WHERE status = 'ONLINE' OR COALESCE(ground_speed, 0) > 30
            ORDER BY ts DESC LIMIT 12;
            """
        )
        pilots_n = len(rows or [])
    except Exception:
        rows = []
    try:
        metar_row = fetchone(
            "SELECT metar_raw, wind_dir, wind_kt, active_runway, crosswind_kt, headwind_kt FROM airport_metar_cache WHERE icao = %s LIMIT 1;",
            (icao_c,),
        )
        if not metar_row:
            metar_row = fetchone(
                "SELECT metar_raw, wind_dir, wind_kt FROM metar_cache WHERE icao = %s LIMIT 1;",
                (icao_c,),
            )
        if metar_row:
            wind_txt = f"{metar_row.get('wind_dir', '—')}° / {metar_row.get('wind_kt', '—')} kt"
            runway_txt = str(metar_row.get("active_runway") or "—")
            xw = metar_row.get("crosswind_kt")
            hw = metar_row.get("headwind_kt")
            if xw is not None:
                xwind_txt = f"XW {float(xw):.0f} kt · HW {float(hw or 0):.0f} kt"
    except Exception:
        pass
    title = tr(lang, "radar_title")
    embed = discord.Embed(title=title, color=discord.Color.gold())
    embed.add_field(name="ICAO", value=icao_c, inline=True)
    embed.add_field(name="Wind", value=wind_txt[:64], inline=True)
    embed.add_field(name="Runway", value=runway_txt[:32], inline=True)
    embed.add_field(name="Crosswind", value=xwind_txt[:64], inline=False)
    embed.add_field(
        name="Live pilots",
        value=str(pilots_n) if lang == "en" else f"{pilots_n} aktiv",
        inline=True,
    )
    embed.add_field(
        name="Link",
        value=f"[Radar]({WEB_BASE}/market/radar)",
        inline=True,
    )
    if rows:
        lines = []
        for r in rows[:5]:
            lines.append(
                f"**{r.get('pilot_name') or 'Pilot'}** · {r.get('aircraft_model') or '—'} · "
                f"{r.get('origin_icao') or '?'}→{r.get('destination_icao') or '?'}"
            )
        embed.description = "\n".join(lines)[:1800]
    else:
        embed.description = tr(lang, "radar_empty")
    await interaction.followup.send(embed=embed)


@app_commands.command(name="slots", description="Credit casino slots / SkyTycoon Slots")
@app_commands.describe(bet="Bet in credits (100 up to 50k / 1M High-Roller)")
async def slots_command(interaction: discord.Interaction, bet: int) -> None:
    await interaction.response.defer(ephemeral=True)
    if casino_is_frozen():
        await interaction.followup.send(tr_bilingual("casino_shutdown"), ephemeral=True)
        return
    user = user_for_interaction(interaction)
    if not user:
        await interaction.followup.send(tr_bilingual("casino_no_user"), ephemeral=True)
        return
    hid = str(user["hardware_id"])
    if not user_has_mod_casino(hid):
        embed = discord.Embed(
            title="🎰 Casino",
            description=tr_bilingual("casino_locked"),
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    max_bet = casino_max_bet(hid)
    if bet < 100 or bet > max_bet:
        await interaction.followup.send(
            f"Einsatz 100–{max_bet:,} CR / Bet 100–{max_bet:,} CR",
            ephemeral=True,
        )
        return
    amount = float(bet)
    if not await _casino_gate(interaction, hid):
        return
    if user_wealth(hid) < amount or not debit_credits(hid, amount):
        await interaction.followup.send(tr_bilingual("casino_low"), ephemeral=True)
        return
    roll = random.random()
    if roll < 0.12:
        win = amount * 3
        credit_credits(hid, win)
        _casino_set_winner_cooldown(hid)
        msg = tr_bilingual("slots_win", amount=int(win))
    else:
        msg = tr_bilingual("slots_lose", amount=int(amount))
    bal = user_wealth(hid)
    await interaction.followup.send(
        f"{tr_bilingual('slots_desc')}\n\n{msg}\n\n{tr('de', 'casino_balance')}: `{bal:,.0f}` CR",
        ephemeral=True,
    )


@app_commands.command(name="blackjack", description="Credit casino blackjack")
@app_commands.describe(bet="Bet in credits (100 up to 50k / 1M High-Roller)")
async def blackjack_command(interaction: discord.Interaction, bet: int) -> None:
    await interaction.response.defer(ephemeral=True)
    if casino_is_frozen():
        await interaction.followup.send(tr_bilingual("casino_shutdown"), ephemeral=True)
        return
    user = user_for_interaction(interaction)
    if not user:
        await interaction.followup.send(tr_bilingual("casino_no_user"), ephemeral=True)
        return
    hid = str(user["hardware_id"])
    if not user_has_mod_casino(hid):
        embed = discord.Embed(
            title="🎰 Casino",
            description=tr_bilingual("casino_locked"),
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    max_bet = casino_max_bet(hid)
    if bet < 100 or bet > max_bet:
        await interaction.followup.send(
            f"Einsatz 100–{max_bet:,} CR / Bet 100–{max_bet:,} CR",
            ephemeral=True,
        )
        return
    amount = float(bet)
    if not await _casino_gate(interaction, hid):
        return
    if user_wealth(hid) < amount or not debit_credits(hid, amount):
        await interaction.followup.send(tr_bilingual("casino_low"), ephemeral=True)
        return
    player = random.randint(12, 21)
    dealer = random.randint(16, 21)
    if player >= dealer:
        win = amount * 2
        credit_credits(hid, win)
        _casino_set_winner_cooldown(hid)
        msg = tr_bilingual("blackjack_win", amount=int(win))
    else:
        msg = tr_bilingual("blackjack_lose", amount=int(amount))
    await interaction.followup.send(
        f"{tr_bilingual('blackjack_desc')}\n\n{msg}\nPlayer {player} vs Dealer {dealer}\n"
        f"{tr('de', 'casino_balance')}: `{user_wealth(hid):,.0f}` CR",
        ephemeral=True,
    )


def _pilot_stats(hid: str, username: str) -> dict[str, Any]:
    row = fetchone(
        """
        SELECT COALESCE(credits, money, 0) AS credits,
               COALESCE(xp, 0) AS xp,
               COALESCE(pilot_rank, '') AS pilot_rank,
               COALESCE(miles, 0) AS miles
        FROM users WHERE hardware_id = %s LIMIT 1;
        """,
        (hid,),
    )
    fleet_n = 0
    try:
        fr = fetchone(
            "SELECT COUNT(*)::int AS n FROM fleet WHERE hardware_id = %s;",
            (hid,),
        )
        fleet_n = int(fr.get("n") or 0) if fr else 0
    except Exception:
        pass
    credits = float(row.get("credits") or 0) if row else 0.0
    xp = float(row.get("xp") or 0) if row else 0.0
    miles = float(row.get("miles") or 0) if row else 0.0
    rank = str(row.get("pilot_rank") or "") if row else ""
    if not rank:
        rank = rank_role_for_miles(miles)
    return {
        "pilot": username,
        "credits": credits,
        "xp": int(xp),
        "rank": rank,
        "fleet": fleet_n,
    }


@app_commands.command(name="stats", description="Pilot logbook / Piloten-Logbuch (PostgreSQL)")
async def stats_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    user = user_for_interaction(interaction)
    if not user:
        await interaction.followup.send(tr_bilingual("casino_no_user"), ephemeral=True)
        return
    st = _pilot_stats(str(user["hardware_id"]), str(user.get("username") or "Pilot"))
    embed = discord.Embed(
        title=tr("de", "stats_title") + " / " + tr("en", "stats_title"),
        description=tr_bilingual(
            "stats_body",
            pilot=st["pilot"],
            credits=f"{st['credits']:,.0f}",
            xp=st["xp"],
            rank=st["rank"],
            fleet=st["fleet"],
        ),
        color=discord.Color.from_rgb(100, 181, 246),
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


@app_commands.command(name="leaderboard", description="Top 10 richest pilots / Top 10 Piloten")
async def leaderboard_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=False)
    rows = fetchall(
        """
        SELECT username, COALESCE(credits, money, 0) AS wealth,
               COALESCE(xp, 0) AS xp
        FROM users
        WHERE COALESCE(credits, money, 0) > 0
        ORDER BY COALESCE(credits, money, 0) DESC
        LIMIT 10;
        """
    )
    embed = discord.Embed(
        title=tr("de", "lb_cmd_title") + " / " + tr("en", "lb_cmd_title"),
        color=discord.Color.from_rgb(212, 175, 55),
        timestamp=discord.utils.utcnow(),
    )
    if not rows:
        embed.description = tr_bilingual("lb_cmd_empty")
    else:
        lines = []
        for i, r in enumerate(rows, 1):
            lines.append(
                f"**{i}.** {r.get('username', 'Pilot')} — `{float(r.get('wealth') or 0):,.0f}` CR · "
                f"XP `{int(float(r.get('xp') or 0)):,}`"
            )
        embed.description = "\n".join(lines)[:4000]
    await interaction.followup.send(embed=embed)


@app_commands.command(name="roulette", description="Roulette — exact number pays 35× / Zahl 35×")
@app_commands.describe(number="Number 0-36 / Zahl 0-36", bet="Bet in credits / Einsatz")
async def roulette_command(interaction: discord.Interaction, number: int, bet: int) -> None:
    await interaction.response.defer(ephemeral=True)
    if casino_is_frozen():
        await interaction.followup.send(tr_bilingual("casino_shutdown"), ephemeral=True)
        return
    user = user_for_interaction(interaction)
    if not user:
        await interaction.followup.send(tr_bilingual("casino_no_user"), ephemeral=True)
        return
    hid = str(user["hardware_id"])
    if not user_has_mod_casino(hid):
        embed = discord.Embed(
            title="🎡 Roulette",
            description=tr_bilingual("casino_locked"),
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    num = max(0, min(36, int(number)))
    max_bet = casino_max_bet(hid)
    if bet < 100 or bet > max_bet:
        await interaction.followup.send(
            f"Einsatz 100–{max_bet:,} CR / Bet 100–{max_bet:,} CR",
            ephemeral=True,
        )
        return
    amount = float(bet)
    if not await _casino_gate(interaction, hid):
        return
    if user_wealth(hid) < amount or not debit_credits(hid, amount):
        await interaction.followup.send(tr_bilingual("casino_low"), ephemeral=True)
        return
    rolled = random.randint(0, 36)
    if rolled == num:
        win = amount * 35
        credit_credits(hid, win)
        _casino_set_winner_cooldown(hid)
        msg = tr_bilingual("roulette_win", num=num, amount=int(win))
    else:
        msg = tr_bilingual("roulette_lose", rolled=rolled, num=num, amount=int(amount))
    await interaction.followup.send(
        f"{msg}\n\n{tr('de', 'casino_balance')}: `{user_wealth(hid):,.0f}` CR",
        ephemeral=True,
    )


ticket_group = app_commands.Group(name="ticket", description="Support tickets / Support-Tickets")


@ticket_group.command(name="create", description="Private support channel / Privates Support-Ticket")
@app_commands.describe(subject="Subject / Betreff", message="Message / Nachricht")
async def ticket_create_command(
    interaction: discord.Interaction, subject: str, message: str
) -> None:
    await interaction.response.defer(ephemeral=True)
    subject_c = subject.strip()[:120] or "Support"
    msg_c = message.strip()[:3500]
    if not msg_c:
        await interaction.followup.send("Message required / Nachricht erforderlich.", ephemeral=True)
        return
    user = user_for_interaction(interaction)
    hid = str(user["hardware_id"]) if user else str(interaction.user.id)[:128]
    pilot = str(user["username"]) if user else interaction.user.display_name
    msg_de, msg_en = _bilingual_ticket_text(msg_c)
    ts = time.time()
    guild = interaction.guild
    private_ch_id = ""
    if guild and isinstance(interaction.user, discord.Member):
        cat = discord.utils.get(guild.categories, name="🌐 COMMUNITY LIVE")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        try:
            private_ch = await guild.create_text_channel(
                f"ticket-{interaction.user.display_name[:12].lower().replace(' ', '-')}",
                category=cat,
                overwrites=overwrites,
                reason="SkyTycoon support ticket",
            )
            private_ch_id = str(private_ch.id)
        except discord.DiscordException:
            private_ch_id = ""
    row = fetchone(
        """
        INSERT INTO support_tickets (
            hardware_id, discord_user_id, discord_channel_id, status, pilot_name, subject, last_message_ts
        ) VALUES (%s, %s, %s, 'OPEN', %s, %s, %s)
        RETURNING id;
        """,
        (hid, str(interaction.user.id), private_ch_id, pilot, subject_c, ts),
    )
    tid = int(row["id"]) if row else 0
    execute(
        """
        INSERT INTO support_messages (
            ticket_id, hardware_id, sender, message_text, message_de, message_en, ts
        ) VALUES (%s, %s, 'pilot', %s, %s, %s, %s);
        """,
        (tid, hid, msg_c, msg_de, msg_en, ts),
    )
    if guild:
        ch = channel(guild, "🎫-support-tickets")
        if ch:
            embed = discord.Embed(
                title=f"🔔 OPEN #{tid} — {subject_c}",
                description=f"{msg_c[:500]}\n\n**DE:** {msg_de[:400]}\n**EN:** {msg_en[:400]}",
                color=discord.Color.red(),
            )
            embed.set_author(name=pilot)
            if private_ch_id:
                embed.add_field(name="Private", value=f"<#{private_ch_id}>")
            post = await ch.send(embed=embed)
            if not private_ch_id:
                execute(
                    "UPDATE support_tickets SET discord_channel_id = %s WHERE id = %s;",
                    (str(post.channel.id), tid),
                )
        if private_ch_id:
            try:
                pch = await interaction.client.fetch_channel(int(private_ch_id))
                if isinstance(pch, discord.TextChannel):
                    await pch.send(
                        tr_bilingual("ticket_private", tid=tid) + f"\n\n{msg_c[:3500]}"
                    )
            except discord.DiscordException:
                pass
    await interaction.followup.send(tr_bilingual("ticket_open", tid=tid), ephemeral=True)


async def emit_recent_flights(guild: discord.Guild, last_seen: dict[str, float]) -> None:
    ch = channel(guild, "✈️-live-flugbörse")
    if ch is None:
        return
    rows = fetchall(
        "SELECT hardware_id, pilot_name, route_json, created_ts FROM flight_tracks WHERE completed = 1 AND created_ts > %s ORDER BY created_ts ASC LIMIT 5;",
        (last_seen["flight"],),
    )
    for row in rows:
        last_seen["flight"] = max(last_seen["flight"], float(row.get("created_ts") or 0))
        embed = discord.Embed(title=tr("de", "flight") + " / " + tr("en", "flight"), color=discord.Color.green())
        embed.add_field(name="Pilot", value=str(row.get("pilot_name") or row.get("hardware_id") or "Pilot"), inline=True)
        embed.add_field(name="OFP", value=str(row.get("route_json") or "{}")[:900], inline=False)
        await ch.send(embed=embed)


async def emit_recent_auctions(guild: discord.Guild, last_seen: dict[str, float]) -> None:
    ch = channel(guild, "🔨-utc-auktionsalarm")
    if ch is None:
        return
    rows = fetchall(
        "SELECT auction_id, aircraft_model, highest_bid, end_ts FROM utc_auctions WHERE end_ts > %s AND end_ts <= %s ORDER BY end_ts ASC LIMIT 5;",
        (last_seen["auction"], time.time()),
    )
    for row in rows:
        last_seen["auction"] = max(last_seen["auction"], float(row.get("end_ts") or 0))
        embed = discord.Embed(title=tr("de", "auction") + " / " + tr("en", "auction"), color=discord.Color.orange())
        embed.add_field(name="Aircraft", value=str(row.get("aircraft_model") or "Asset"), inline=True)
        embed.add_field(name="Bid", value=f"{float(row.get('highest_bid') or 0):,.0f} CR", inline=True)
        await ch.send(embed=embed)


async def emit_recent_wallstreet(guild: discord.Guild, last_seen: dict[str, float]) -> None:
    ch = channel(guild, "📈-wallstreet-ticker")
    if ch is None:
        return
    rows = fetchall(
        "SELECT alliance_id, share_price, updated_ts FROM alliance_stocks WHERE updated_ts > %s ORDER BY updated_ts ASC LIMIT 5;",
        (last_seen["wallstreet"],),
    )
    for row in rows:
        last_seen["wallstreet"] = max(last_seen["wallstreet"], float(row.get("updated_ts") or 0))
        embed = discord.Embed(title=tr("de", "wallstreet") + " / " + tr("en", "wallstreet"), color=discord.Color.blue())
        embed.add_field(name="Alliance", value=str(row.get("alliance_id") or "?"), inline=True)
        embed.add_field(name="Share", value=f"{float(row.get('share_price') or 0):,.2f} CR", inline=True)
        await ch.send(embed=embed)


if __name__ == "__main__":
    token = os.environ.get("DISCORD_BOT_TOKEN", DISCORD_BOT_TOKEN).strip()
    if not token or token == "HIER_DEIN_KOPIERTES_TOKEN_EINTRAGEN":
        raise SystemExit("Bitte DISCORD_BOT_TOKEN setzen oder oben in discord_bot.py eintragen.")
    SkyTycoonDiscordBot().run(token)
