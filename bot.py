cat > bot.py << 'PY'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# VNIOX OSINT Bot — single-file app with:
#   • Force-join (channel verify)
#   • Referral + credits (SQLite)
#   • Logs to channel
#   • Flask control panel (toggle bot ON/OFF)
#   • PTB v20+ compatible

import os
import re
import json
import logging
import threading
import sqlite3
from datetime import datetime
from typing import Tuple, Optional

import pytz
import requests
from flask import Flask, request, render_template_string

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters
)

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("vniox.app")

# ---------------- Paths & Globals ----------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "data.txt")   # JSON
DB_FILE = os.path.join(SCRIPT_DIR, "vniox_bot.db")

# ---------------- Config ----------------
class Config:
    # Token
    BOT_TOKEN: str = ""  # set via ENV BOT_TOKEN or data.txt

    # APIs
    API_URL: str = "https://aetherosint.site/api/index.php?key=MOHSIN&type=mobile&term="
    VEHICLE_API_URL: str = "https://vechile-info-subh.vercel.app/lookup?rc="
    GMAIL_API_URL: str = "https://glonova.in/Iqo1oPro.php/?email="

    # Admin & control
    ADMIN_PASSWORD: str = "bm2"
    ADMIN_IDS: list = [6972508083]
    BOT_ACTIVE: bool = True
    MAINTENANCE_MODE: bool = False

    # Force join
    REQUIRED_CHANNELS: list = []  # e.g. ["@HEROKU_CLUB", -1001596819852]
    CHANNEL_LINKS: list = []      # display links (optional)

    # Credits / referral
    DAILY_FREE_SEARCHES: int = 3
    PRIVATE_SEARCH_COST: float = 1.0
    REFERRAL_BONUS: float = 2.0    # inviter gets
    JOINING_BONUS: float = 1.0     # invitee gets once

    # Logs
    LOG_CHANNEL_ID: Optional[int] = None  # -100xxxxxxxxxxxx or None

    TIMEZONE = pytz.timezone("Asia/Kolkata")


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read %s: %s", path, e)
        return {}


def _write_json(path: str, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to write %s: %s", path, e)


def load_settings() -> None:
    # ENV first
    env_token = os.getenv("BOT_TOKEN", "").strip()
    if env_token:
        Config.BOT_TOKEN = env_token

    data = _read_json(SETTINGS_FILE)

    if not Config.BOT_TOKEN:
        Config.BOT_TOKEN = data.get("BOT_TOKEN", "").strip()

    # Merge others
    Config.API_URL = data.get("API_URL", Config.API_URL)
    Config.VEHICLE_API_URL = data.get("VEHICLE_API_URL", Config.VEHICLE_API_URL)
    Config.GMAIL_API_URL = data.get("GMAIL_API_URL", Config.GMAIL_API_URL)

    Config.ADMIN_PASSWORD = data.get("ADMIN_PASSWORD", Config.ADMIN_PASSWORD)
    Config.ADMIN_IDS = data.get("ADMIN_IDS", Config.ADMIN_IDS)
    Config.BOT_ACTIVE = data.get("BOT_ACTIVE", Config.BOT_ACTIVE)
    Config.MAINTENANCE_MODE = data.get("MAINTENANCE_MODE", Config.MAINTENANCE_MODE)

    Config.REQUIRED_CHANNELS = data.get("REQUIRED_CHANNELS", Config.REQUIRED_CHANNELS)
    Config.CHANNEL_LINKS = data.get("CHANNEL_LINKS", Config.CHANNEL_LINKS)

    Config.DAILY_FREE_SEARCHES = int(data.get("DAILY_FREE_SEARCHES", Config.DAILY_FREE_SEARCHES))
    Config.PRIVATE_SEARCH_COST = float(data.get("PRIVATE_SEARCH_COST", Config.PRIVATE_SEARCH_COST))
    Config.REFERRAL_BONUS = float(data.get("REFERRAL_BONUS", Config.REFERRAL_BONUS))
    Config.JOINING_BONUS = float(data.get("JOINING_BONUS", Config.JOINING_BONUS))

    cfg_log = data.get("LOG_CHANNEL_ID", Config.LOG_CHANNEL_ID)
    Config.LOG_CHANNEL_ID = int(cfg_log) if cfg_log not in (None, "") else None

    # Create data.txt if not exists
    if not os.path.exists(SETTINGS_FILE):
        _write_json(SETTINGS_FILE, {
            "BOT_TOKEN": Config.BOT_TOKEN,
            "API_URL": Config.API_URL,
            "VEHICLE_API_URL": Config.VEHICLE_API_URL,
            "GMAIL_API_URL": Config.GMAIL_API_URL,
            "ADMIN_PASSWORD": Config.ADMIN_PASSWORD,
            "ADMIN_IDS": Config.ADMIN_IDS,
            "BOT_ACTIVE": Config.BOT_ACTIVE,
            "MAINTENANCE_MODE": Config.MAINTENANCE_MODE,
            "REQUIRED_CHANNELS": Config.REQUIRED_CHANNELS,
            "CHANNEL_LINKS": Config.CHANNEL_LINKS,
            "DAILY_FREE_SEARCHES": Config.DAILY_FREE_SEARCHES,
            "PRIVATE_SEARCH_COST": Config.PRIVATE_SEARCH_COST,
            "REFERRAL_BONUS": Config.REFERRAL_BONUS,
            "JOINING_BONUS": Config.JOINING_BONUS,
            "LOG_CHANNEL_ID": Config.LOG_CHANNEL_ID
        })


def _mask_token(token: str) -> str:
    if not token:
        return "(empty)"
    return token[:6] + "…" + token[-6:] if len(token) > 12 else token


def _is_valid_token(token: str) -> bool:
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", token or ""))


# ---------------- DB ----------------
db_lock = threading.Lock()
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def init_db():
    with db_lock:
        cur.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            credits REAL DEFAULT 0,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            joined_date TEXT
        );

        CREATE TABLE IF NOT EXISTS usage (
            user_id INTEGER,
            date TEXT,
            searches INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        );
        ''')
        conn.commit()


def get_or_create_user(user_id: int, username: str, first_name: str) -> sqlite3.Row:
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            "INSERT INTO users (user_id, username, first_name, credits, referral_code, joined_date) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, username, first_name, 0.0, str(user_id), datetime.now(Config.TIMEZONE).isoformat())
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()


def add_credits(user_id: int, amount: float) -> None:
    with db_lock:
        cur.execute("UPDATE users SET credits = COALESCE(credits,0) + ? WHERE user_id=?", (amount, user_id))
        conn.commit()


def set_referred_by(user_id: int, inviter_id: int) -> bool:
    with db_lock:
        cur.execute("SELECT referred_by FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if not row or row["referred_by"] or inviter_id == user_id:
            return False
        cur.execute("UPDATE users SET referred_by=? WHERE user_id=?", (inviter_id, user_id))
        cur.execute("UPDATE users SET referral_count = COALESCE(referral_count,0)+1 WHERE user_id=?", (inviter_id,))
        conn.commit()
        return True


def get_daily_usage(user_id: int, date_str: str) -> int:
    with db_lock:
        cur.execute("SELECT searches FROM usage WHERE user_id=? AND date=?", (user_id, date_str))
        row = cur.fetchone()
        return row["searches"] if row else 0


def increment_usage(user_id: int, date_str: str) -> None:
    with db_lock:
        cur.execute("SELECT searches FROM usage WHERE user_id=? AND date=?", (user_id, date_str))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE usage SET searches=searches+1 WHERE user_id=? AND date=?", (user_id, date_str))
        else:
            cur.execute("INSERT INTO usage (user_id, date, searches) VALUES (?,?,1)", (user_id, date_str))
        conn.commit()


# ---------------- Flask panel ----------------
PANEL = Flask(__name__)

CONTROL_PANEL_HTML = '''
<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Bot Control Panel</title>
<style>
body{font-family:Arial;margin:20px;}
.container{max-width:560px;margin:auto;padding:20px;border:1px solid #ccc;border-radius:10px}
.status{font-size:1.1em;margin-bottom:10px}.on{color:green}.off{color:red}
input,button{padding:10px;width:100%;box-sizing:border-box;margin-top:10px}button{cursor:pointer}
.small{color:#555;font-size:.9em}
</style></head><body>
<div class="container">
<h2>Bot Control Panel</h2>
<div class="status {{ 'on' if bot_active else 'off' }}">Status: <b>{{ 'ON' if bot_active else 'OFF' }}</b></div>
<div class="small">Token (masked): {{ masked_token }}</div>
<form action="/toggle_bot" method="post">
<input type="password" name="password" placeholder="Admin password" required/>
<button type="submit" name="action" value="on">Turn ON</button>
<button type="submit" name="action" value="off">Turn OFF</button>
</form>
{% if message %}<p class="small">{{ message }}</p>{% endif %}
</div></body></html>
'''

@PANEL.get("/")
def control_panel():
    return render_template_string(
        CONTROL_PANEL_HTML,
        bot_active=Config.BOT_ACTIVE,
        masked_token=_mask_token(Config.BOT_TOKEN),
        message=None
    )

@PANEL.post("/toggle_bot")
def toggle_bot():
    password = request.form.get("password", "")
    action = request.form.get("action", "")
    if password != Config.ADMIN_PASSWORD:
        return render_template_string(CONTROL_PANEL_HTML, bot_active=Config.BOT_ACTIVE,
                                      masked_token=_mask_token(Config.BOT_TOKEN),
                                      message="Invalid password!"), 403
    if action == "on":
        Config.BOT_ACTIVE = True
        msg = "Bot turned ON."
    elif action == "off":
        Config.BOT_ACTIVE = False
        msg = "Bot turned OFF."
    else:
        msg = "Unknown action."
    return render_template_string(CONTROL_PANEL_HTML, bot_active=Config.BOT_ACTIVE,
                                  masked_token=_mask_token(Config.BOT_TOKEN),
                                  message=msg)

@PANEL.get("/ping")
def ping():
    return "ok"


def run_panel():
    logger.info("Starting Flask on 0.0.0.0:5000")
    PANEL.run(host="0.0.0.0", port=5000)


# ---------------- Helpers ----------------
def local_date_str() -> str:
    return datetime.now(Config.TIMEZONE).strftime("%Y-%m-%d")


def is_member_tuple(val) -> Tuple[Optional[int], Optional[str]]:
    if isinstance(val, int):
        return (val, None)
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("@"):
            return (None, f"https://t.me/{s[1:]}")
        if "t.me/" in s:
            return (None, s)
    return (None, None)


async def check_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not Config.REQUIRED_CHANNELS:
        return True
    user_id = update.effective_user.id
    bot = context.bot

    not_joined_links = []
    for ch in Config.REQUIRED_CHANNELS:
        if isinstance(ch, int):
            try:
                m = await bot.get_chat_member(ch, user_id)
                if m.status in ("left", "kicked"):
                    not_joined_links.append(f"https://t.me/c/{str(ch).replace('-100','')}")
            except Exception:
                not_joined_links.append("https://t.me/")
        else:
            not_joined_links.append(is_member_tuple(ch)[1] or "https://t.me/")

    if not_joined_links:
        kb = [[InlineKeyboardButton("✅ Join Channel", url=l)] for l in not_joined_links]
        kb.append([InlineKeyboardButton("🔄 I've Joined", callback_data="recheck_join")])
        await update.effective_message.reply_text(
            "🚧 *Access Locked*\nJoin the channels below to continue:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        return False
    return True


async def send_log(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    cid = Config.LOG_CHANNEL_ID
    if not cid:
        return
    try:
        await context.bot.send_message(chat_id=cid, text=text[:4000])
    except Exception as e:
        logger.warning("Failed to log to channel: %s", e)


def fetch_mobile_info(number: str) -> str:
    url = f"{Config.API_URL}{number}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        try:
            data = r.json()
            name = data.get("name") or data.get("Name") or data.get("owner") or "N/A"
            circle = data.get("circle") or data.get("Circle") or data.get("state") or "N/A"
            alt = data.get("alt_mobile") or data.get("alt") or ""
            addr = data.get("address") or data.get("Address") or ""
            parts = [f"👤 Name: {name}", f"🌐 Circle/State: {circle}"]
            if alt:
                parts.append(f"📞 Alt: {alt}")
            if addr:
                parts.append(f"🏠 Address: {addr}")
            return "\n".join(parts) or "No details found."
        except ValueError:
            t = r.text.strip()
            return t if t else "No details found."
    except requests.RequestException as e:
        return f"API error: {e}"


# ---------------- Telegram Handlers ----------------
async def cb_recheck_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_force_join(update, context):
        await update.effective_message.reply_text("✅ Verification passed! Continue using the bot.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    msg = update.effective_message

    get_or_create_user(u.id, u.username or "", u.first_name or "")

    # Referral via /start <inviter_id>
    if context.args:
        try:
            inviter_id = int(context.args[0])
            if set_referred_by(u.id, inviter_id):
                add_credits(inviter_id, Config.REFERRAL_BONUS)
                add_credits(u.id, Config.JOINING_BONUS)
                await send_log(context, f"🎯 Referral: {inviter_id} invited {u.id}. +{Config.REFERRAL_BONUS} / +{Config.JOINING_BONUS}")
        except ValueError:
            pass

    if not await check_force_join(update, context):
        return

    await msg.reply_text(
        "👋 *Welcome to VNIOX Intelligence Bot*\n"
        "🔍 Send any Indian mobile number to lookup\n\n"
        "Commands:\n"
        "• /wallet — Check credits\n"
        "• /refer — Your invite link\n"
        "• /grant <uid> <credits> — (Admin) Add credits\n"
        "• /help — Help & examples",
        parse_mode="Markdown"
    )

    await send_log(context, f"🚀 Start by {u.id} (@{u.username or 'n/a'})")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *How to use:*\n"
        "• Send a 10-digit mobile number (e.g., 98XXXXXXXX)\n"
        "• /wallet — shows your credit balance\n"
        "• /refer — get your invite link\n",
        parse_mode="Markdown"
    )


def _digits_only(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.BOT_ACTIVE:
        return
    if not await check_force_join(update, context):
        return

    text = (update.message.text or "").strip()
    digits = _digits_only(text)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[-10:]
    if len(digits) == 10:
        today = local_date_str()
        used = get_daily_usage(update.effective_user.id, today)
        if used >= Config.DAILY_FREE_SEARCHES:
            with db_lock:
                cur.execute("SELECT credits FROM users WHERE user_id=?", (update.effective_user.id,))
                row = cur.fetchone()
                balance = float(row["credits"] or 0.0)
            if balance < Config.PRIVATE_SEARCH_COST:
                await update.message.reply_text(
                    f"⚠️ Daily free limit reached.\n"
                    f"You need {Config.PRIVATE_SEARCH_COST} credit. Balance: {balance}.\n"
                    f"Use /refer to earn credits."
                )
                return
            add_credits(update.effective_user.id, -Config.PRIVATE_SEARCH_COST)

        await update.message.reply_text("⏳ Fetching details...")
        result = fetch_mobile_info(digits)
        await update.message.reply_text(result[:4000])

        increment_usage(update.effective_user.id, today)
        await send_log(context, f"🔎 Search by {update.effective_user.id} — {digits}")
        return

    await update.message.reply_text("❓ Send a 10-digit mobile number, or /help")


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db_lock:
        cur.execute("SELECT credits, referral_count FROM users WHERE user_id=?", (update.effective_user.id,))
        row = cur.fetchone()
        if not row:
            bal = 0.0
            refc = 0
        else:
            bal = float(row["credits"] or 0.0)
            refc = int(row["referral_count"] or 0)
    await update.message.reply_text(
        f"👛 *Wallet*\nBalance: {bal} credits\nReferrals: {refc}\n"
        f"Daily free searches: {Config.DAILY_FREE_SEARCHES}",
        parse_mode="Markdown"
    )


async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start={update.effective_user.id}"
    await update.message.reply_text(
        f"🔗 *Your referral link:*\n{link}\n\n"
        f"Invite friends and earn +{Config.REFERRAL_BONUS} credit.\n"
        f"New users get +{Config.JOINING_BONUS} joining bonus.",
        parse_mode="Markdown"
    )


async def cmd_grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in Config.ADMIN_IDS:
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /grant <user_id> <credits>")
        return
    try:
        uid = int(context.args[0])
        amt = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid arguments.")
        return
    add_credits(uid, amt)
    await update.message.reply_text(f"✅ Granted {amt} credits to {uid}.")
    await send_log(context, f"🧾 Grant: {amt} → {uid} by {update.effective_user.id}")


def build_app() -> Application:
    load_settings()
    init_db()

    masked = _mask_token(Config.BOT_TOKEN)
    logger.info("Using BOT_TOKEN: %s", masked)
    if not _is_valid_token(Config.BOT_TOKEN):
        logger.critical("Invalid/missing token. Set ENV BOT_TOKEN or data.txt BOT_TOKEN.")
        raise SystemExit(2)

    app = Application.builder().token(Config.BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(cb_recheck_join, pattern="^recheck_join$"))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("wallet", cmd_wallet))
    app.add_handler(CommandHandler("refer", cmd_refer))
    app.add_handler(CommandHandler("grant", cmd_grant))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


def main():
    # Start Flask panel in background so polling can run
    threading.Thread(target=run_panel, daemon=True).start()

    application = build_app()
    logger.info("Starting Telegram bot polling…")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
    except Exception as e:
        logger.exception("Polling crashed: %s", e)
        raise


if __name__ == "__main__":
    main()
PY
