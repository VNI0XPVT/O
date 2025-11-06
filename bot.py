#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
app.py — Single-file, production-style Telegram OSINT bot + Flask panel.

Choices applied (you answered "B"):
1) Fancy start message
2) Channel join OFF (free use)
3) Phone lookup API: aetherosint.site

Run:
    python app.py
Control panel:
    http://127.0.0.1:5000/   (password default: bm2)

Token load priority: ENV BOT_TOKEN -> data.txt (JSON) -> exit if missing/invalid
"""

import os
import re
import json
import logging
import threading
from typing import Optional
from datetime import datetime

import pytz
import requests
from flask import Flask, request, render_template_string
from telegram import Update
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
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "data.txt")  # JSON file

# ---------- Config ----------
class Config:
    BOT_TOKEN: str = ""

    # Applied API selection "B"
    API_URL: str = "https://aetherosint.site/api/index.php?key=MOHSIN&type=mobile&term="
    VEHICLE_API_URL: str = "https://vechile-info-subh.vercel.app/lookup?rc="
    GMAIL_API_URL: str = "https://glonova.in/Iqo1oPro.php/?email="

    ADMIN_PASSWORD: str = "bm2"
    ADMIN_IDS = [6972508083]
    LOG_CHANNEL_ID = None
    REQUIRED_CHANNELS = []   # Channel join OFF
    CHANNEL_LINKS = []

    DAILY_FREE_SEARCHES: int = 3
    PRIVATE_SEARCH_COST: float = 1.0

    TIMEZONE = pytz.timezone("Asia/Kolkata")
    BOT_ACTIVE: bool = True
    MAINTENANCE_MODE: bool = False


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
    env_token = os.getenv("BOT_TOKEN", "").strip()
    if env_token:
        Config.BOT_TOKEN = env_token

    data = _read_json_settings(SETTINGS_FILE)
    if not Config.BOT_TOKEN:
        Config.BOT_TOKEN = data.get("BOT_TOKEN", "").strip()

    # Merge other settings (optional overrides)
    Config.API_URL = data.get("API_URL", Config.API_URL)
    Config.VEHICLE_API_URL = data.get("VEHICLE_API_URL", Config.VEHICLE_API_URL)
    Config.GMAIL_API_URL = data.get("GMAIL_API_URL", Config.GMAIL_API_URL)
    Config.ADMIN_PASSWORD = data.get("ADMIN_PASSWORD", Config.ADMIN_PASSWORD)
    Config.ADMIN_IDS = data.get("ADMIN_IDS", Config.ADMIN_IDS)
    Config.LOG_CHANNEL_ID = data.get("LOG_CHANNEL_ID", Config.LOG_CHANNEL_ID)
    Config.DAILY_FREE_SEARCHES = int(data.get("DAILY_FREE_SEARCHES", Config.DAILY_FREE_SEARCHES))
    Config.PRIVATE_SEARCH_COST = float(data.get("PRIVATE_SEARCH_COST", Config.PRIVATE_SEARCH_COST))
    Config.BOT_ACTIVE = bool(data.get("BOT_ACTIVE", Config.BOT_ACTIVE))
    Config.MAINTENANCE_MODE = bool(data.get("MAINTENANCE_MODE", Config.MAINTENANCE_MODE))

    if not os.path.exists(SETTINGS_FILE):
        _write_json_settings(SETTINGS_FILE, {
            "BOT_TOKEN": Config.BOT_TOKEN,
            "API_URL": Config.API_URL,
            "VEHICLE_API_URL": Config.VEHICLE_API_URL,
            "GMAIL_API_URL": Config.GMAIL_API_URL,
            "ADMIN_PASSWORD": Config.ADMIN_PASSWORD,
            "ADMIN_IDS": Config.ADMIN_IDS,
            "LOG_CHANNEL_ID": Config.LOG_CHANNEL_ID,
            "DAILY_FREE_SEARCHES": Config.DAILY_FREE_SEARCHES,
            "PRIVATE_SEARCH_COST": Config.PRIVATE_SEARCH_COST,
            "BOT_ACTIVE": Config.BOT_ACTIVE,
            "MAINTENANCE_MODE": Config.MAINTENANCE_MODE
        })


def _mask_token(token: str) -> str:
    if not token:
        return "(empty)"
    if len(token) <= 12:
        return token[0:3] + "…" + token[-3:]
    return token[:6] + "…" + token[-6:]


def _is_valid_token(token: str) -> bool:
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", token))


# ---------- Flask Panel ----------
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


# ---------- Helper: API calls ----------
def fetch_mobile_info(number: str) -> str:
    """Call the aetherosint mobile API, return a readable string."""
    url = f"{Config.API_URL}{number}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        # API sometimes returns JSON/text. Try JSON first.
        try:
            data = r.json()
            # Build simple summary if known keys
            name = data.get("name") or data.get("Name") or data.get("owner") or "N/A"
            circle = data.get("circle") or data.get("Circle") or data.get("state") or "N/A"
            alt = data.get("alt_mobile") or data.get("alt") or ""
            addr = data.get("address") or data.get("Address") or ""
            parts = [f"👤 Name: {name}", f"🌐 Circle/State: {circle}"]
            if alt: parts.append(f"📞 Alt: {alt}")
            if addr: parts.append(f"🏠 Address: {addr}")
            return "\n".join(parts) or "No details found."
        except ValueError:
            # Not JSON; return text
            t = r.text.strip()
            return t if t else "No details found."
    except requests.RequestException as e:
        return f"API error: {e}"


def fetch_vehicle_info(rc: str) -> str:
    url = f"{Config.VEHICLE_API_URL}{rc}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.text.strip() or "No data."
    except requests.RequestException as e:
        return f"API error: {e}"


def fetch_email_info(email: str) -> str:
    url = f"{Config.GMAIL_API_URL}{email}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.text.strip() or "No data."
    except requests.RequestException as e:
        return f"API error: {e}"


# ---------- Telegram Handlers ----------
from telegram.ext import ApplicationBuilder

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 Bot is currently inactive. Try again later.")
        return
    # Fancy start message
    await update.message.reply_text(
        "👋 **Welcome to VNIOX Intelligence Bot**\n"
        "🔍 *Send any Indian mobile number to lookup*\n\n"
        "Commands:\n"
        "• /vehicle <RC> — Vehicle info\n"
        "• /email <email> — Email OSINT\n"
        "• /help — Help & examples",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *How to use:*\n"
        "• Send a 10-digit mobile number (e.g., 98XXXXXXXX)\n"
        "• /vehicle DL1ABC1234\n"
        "• /email someone@gmail.com",
        parse_mode="Markdown"
    )


def _digits_from_text(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.BOT_ACTIVE:
        return
    text = (update.message.text or "").strip()

    # Try number detection
    digits = _digits_from_text(text)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[-10:]
    if len(digits) == 10:
        await update.message.reply_text("⏳ Fetching details...")
        result = fetch_mobile_info(digits)
        await update.message.reply_text(result[:4000])
        return

    await update.message.reply_text("❓ Send a 10-digit mobile number, or use /help")


async def cmd_vehicle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /vehicle <RC>")
        return
    rc = args[0].upper()
    await update.message.reply_text("⏳ Fetching vehicle info...")
    result = fetch_vehicle_info(rc)
    await update.message.reply_text(result[:4000])


async def cmd_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /email <email>")
        return
    email = args[0]
    await update.message.reply_text("⏳ Fetching email info...")
    result = fetch_email_info(email)
    await update.message.reply_text(result[:4000])


def build_application() -> Application:
    load_settings()
    masked = _mask_token(Config.BOT_TOKEN)
    logger.info("Using BOT_TOKEN: %s", masked)

    if not _is_valid_token(Config.BOT_TOKEN):
        logger.critical("Invalid or missing BOT_TOKEN. Set via ENV or data.txt")
        raise SystemExit(2)

    app = Application.builder().token(Config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("vehicle", cmd_vehicle))
    app.add_handler(CommandHandler("email", cmd_email))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


# ---------- Main ----------
def run_flask():
    logger.info("Starting Flask on 0.0.0.0:5000")
    PANEL.run(host="0.0.0.0", port=5000)


def main():
    threading.Thread(target=run_flask, daemon=True).start()
    application = build_application()
    logger.info("Starting Telegram bot polling…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
