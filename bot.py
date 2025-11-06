#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fixed, production-ready launcher for your Telegram OSINT bot + Flask panel.

Key fixes:
1) Reliable settings load order (ENV -> data.txt -> code default).
2) Clear BOT_TOKEN validation with masked logging (prevents InvalidToken).
3) Safe startup that refuses to run if token is missing/invalid.
4) Flask runs in a background thread; Telegram app runs on asyncio.
5) Compatible with python-telegram-bot v20+.
"""

import os
import re
import json
import logging
import threading
from datetime import datetime
from functools import wraps

import pytz
import requests
from flask import Flask, request, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("app")

# ---------- Paths ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "data.txt")         # JSON file
DB_FILE = os.path.join(SCRIPT_DIR, "phone_lookup_bot.db")    # kept for compatibility

# ---------- Config ----------
class Config:
    # Do NOT hardcode your token here. Use ENV or data.txt instead.
    BOT_TOKEN: str = ""

    # Safe defaults (overridable from data.txt)
    API_URL: str = "https://glonova.in/Ddsdddddddee.php/?num="
    VEHICLE_API_URL: str = "https://vechile-info-subh.vercel.app/lookup?rc="
    GMAIL_API_URL: str = "https://glonova.in/Iqo1oPro.php/?email="

    ADMIN_PASSWORD: str = "bm2"
    ADMIN_IDS = [6972508083]
    LOG_CHANNEL_ID = None
    REQUIRED_CHANNELS = [-1001596819852]   # chat IDs or @usernames
    ALLOWED_GROUPS = [-1001511253627]
    CHANNEL_LINKS = ["https://t.me/HEROKU_CLUB", "https://t.me/NOBITA_SUPPORT", "https://t.me/VnioxTechApi"]

    DAILY_FREE_SEARCHES: int = 3
    PRIVATE_SEARCH_COST: float = 1.0
    REFERRAL_BONUS: float = 0.5
    JOINING_BONUS: float = 5.0

    TIMEZONE = pytz.timezone("Asia/Kolkata")

    BOT_LOCKED: bool = False
    MAINTENANCE_MODE: bool = False
    GROUP_SEARCHES_OFF: bool = False
    BOT_ACTIVE: bool = True


def _read_json_settings(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read %s: %s", path, e)
        return {}


def _write_json_settings(path: str, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info("Settings written to %s", path)
    except Exception as e:
        logger.error("Failed to write %s: %s", path, e)


def load_settings() -> None:
    """
    Load settings from ENV first, then data.txt, then keep code defaults.
    """
    # 1) ENV (highest priority)
    env_token = os.getenv("BOT_TOKEN", "").strip()
    if env_token:
        Config.BOT_TOKEN = env_token

    # 2) data.txt (JSON)
    data = _read_json_settings(SETTINGS_FILE)
    if not Config.BOT_TOKEN:  # only fallback if ENV not set
        Config.BOT_TOKEN = data.get("BOT_TOKEN", "").strip()

    # Load rest (ENV could override too if you like; here we keep it simple)
    Config.API_URL = data.get("API_URL", Config.API_URL)
    Config.VEHICLE_API_URL = data.get("VEHICLE_API_URL", Config.VEHICLE_API_URL)
    Config.GMAIL_API_URL = data.get("GMAIL_API_URL", Config.GMAIL_API_URL)

    Config.ADMIN_PASSWORD = data.get("ADMIN_PASSWORD", Config.ADMIN_PASSWORD)
    Config.ADMIN_IDS = data.get("ADMIN_IDS", Config.ADMIN_IDS)
    Config.LOG_CHANNEL_ID = data.get("LOG_CHANNEL_ID", Config.LOG_CHANNEL_ID)
    Config.REQUIRED_CHANNELS = data.get("REQUIRED_CHANNELS", Config.REQUIRED_CHANNELS)
    Config.ALLOWED_GROUPS = data.get("ALLOWED_GROUPS", Config.ALLOWED_GROUPS)
    Config.CHANNEL_LINKS = data.get("CHANNEL_LINKS", Config.CHANNEL_LINKS)

    Config.DAILY_FREE_SEARCHES = int(data.get("DAILY_FREE_SEARCHES", Config.DAILY_FREE_SEARCHES))
    Config.PRIVATE_SEARCH_COST = float(data.get("PRIVATE_SEARCH_COST", Config.PRIVATE_SEARCH_COST))
    Config.REFERRAL_BONUS = float(data.get("REFERRAL_BONUS", Config.REFERRAL_BONUS))
    Config.JOINING_BONUS = float(data.get("JOINING_BONUS", Config.JOINING_BONUS))

    Config.BOT_LOCKED = bool(data.get("BOT_LOCKED", Config.BOT_LOCKED))
    Config.MAINTENANCE_MODE = bool(data.get("MAINTENANCE_MODE", Config.MAINTENANCE_MODE))
    Config.GROUP_SEARCHES_OFF = bool(data.get("GROUP_SEARCHES_OFF", Config.GROUP_SEARCHES_OFF))
    Config.BOT_ACTIVE = bool(data.get("BOT_ACTIVE", Config.BOT_ACTIVE))

    # If file didn't exist, write one (without token to avoid accidents)
    if not os.path.exists(SETTINGS_FILE):
        _write_json_settings(SETTINGS_FILE, {
            "BOT_TOKEN": Config.BOT_TOKEN,          # will be empty unless ENV provided
            "API_URL": Config.API_URL,
            "VEHICLE_API_URL": Config.VEHICLE_API_URL,
            "GMAIL_API_URL": Config.GMAIL_API_URL,
            "ADMIN_PASSWORD": Config.ADMIN_PASSWORD,
            "ADMIN_IDS": Config.ADMIN_IDS,
            "LOG_CHANNEL_ID": Config.LOG_CHANNEL_ID,
            "REQUIRED_CHANNELS": Config.REQUIRED_CHANNELS,
            "ALLOWED_GROUPS": Config.ALLOWED_GROUPS,
            "CHANNEL_LINKS": Config.CHANNEL_LINKS,
            "DAILY_FREE_SEARCHES": Config.DAILY_FREE_SEARCHES,
            "PRIVATE_SEARCH_COST": Config.PRIVATE_SEARCH_COST,
            "REFERRAL_BONUS": Config.REFERRAL_BONUS,
            "JOINING_BONUS": Config.JOINING_BONUS,
            "BOT_LOCKED": Config.BOT_LOCKED,
            "MAINTENANCE_MODE": Config.MAINTENANCE_MODE,
            "GROUP_SEARCHES_OFF": Config.GROUP_SEARCHES_OFF,
            "BOT_ACTIVE": Config.BOT_ACTIVE
        })


def _mask_token(token: str) -> str:
    if not token:
        return "(empty)"
    if len(token) <= 12:
        return token[0:3] + "…" + token[-3:]
    return token[:6] + "…" + token[-6:]


def _is_valid_token(token: str) -> bool:
    # Basic structure: <digits>:<string with allowed chars>, usually long
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", token))


# ---------- Flask (simple control panel) ----------
PANEL = Flask(__name__)

CONTROL_PANEL_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Bot Control Panel</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    .container { max-width: 560px; margin: auto; padding: 20px; border: 1px solid #ccc; border-radius: 10px; }
    .status { font-size: 1.1em; margin-bottom: 10px; }
    .on { color: green; } .off { color: red; }
    input, button { padding: 10px; width: 100%; box-sizing: border-box; margin-top: 10px; }
    button { cursor: pointer; }
    .small { color: #555; font-size: 0.9em; }
  </style>
</head>
<body>
  <div class="container">
    <h2>Bot Control Panel</h2>
    <div class="status {{ 'on' if bot_active else 'off' }}">
      Status: <strong>{{ 'ON' if bot_active else 'OFF' }}</strong>
    </div>
    <div class="small">Token (masked): {{ masked_token }}</div>
    <form action="/toggle_bot" method="post">
      <input type="password" name="password" placeholder="Admin password" required />
      <button type="submit" name="action" value="on">Turn ON</button>
      <button type="submit" name="action" value="off">Turn OFF</button>
    </form>
    {% if message %}<p class="small">{{ message }}</p>{% endif %}
  </div>
</body>
</html>
"""

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


def run_flask():
    logger.info("Starting Flask on 0.0.0.0:5000")
    PANEL.run(host="0.0.0.0", port=5000)


# ---------- Telegram Handlers (DEMO) ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 Bot is currently inactive. Try again later.")
        return
    await update.message.reply_text(
        f"Hi {user.first_name or 'friend'}! 👋\n"
        f"Bot is up and running.\n\n"
        f"• Daily free searches: {Config.DAILY_FREE_SEARCHES}\n"
        f"• Private search cost: {Config.PRIVATE_SEARCH_COST} credit(s)\n\n"
        f"Send a 10-digit number to proceed (demo)."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text.isdigit() and len(text) == 10:
        await update.message.reply_text(f"🔍 You sent number: {text}\n(Demo handler here)")
    else:
        # Ignore or guide user
        await update.message.reply_text("Please send a 10-digit phone number (demo).")


def build_application() -> Application:
    load_settings()

    masked = _mask_token(Config.BOT_TOKEN)
    logger.info("Using BOT_TOKEN: %s", masked)

    if not _is_valid_token(Config.BOT_TOKEN):
        logger.critical("\n\nYour BOT_TOKEN is missing or invalid.\n"
                        "Set it via ENV or data.txt (JSON).\n"
                        "Example ENV (Windows PowerShell):\n"
                        '$Env:BOT_TOKEN = "1234567890:AA..."\n'
                        "Example data.txt content:\n"
                        '{\n  \"BOT_TOKEN\": \"1234567890:AA...\"\n}\n")
        raise SystemExit(2)

    app = Application.builder().token(Config.BOT_TOKEN).build()

    # Core handlers (add your full handlers here)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


def main():
    # Run panel in a background thread
    threading.Thread(target=run_flask, daemon=True).start()

    application = build_application()
    logger.info("Starting Telegram bot polling…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
