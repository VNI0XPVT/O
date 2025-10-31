#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Safe Demo Telegram Bot (2-file setup)
- No PII/OSINT lookups.
- Mock responses only.
- Inline menu + simple state flow.
- Works with polling (no webhook).

Run:
  export BOT_TOKEN="123456:REPLACE_WITH_YOUR_TOKEN"
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  python bot.py
"""

import os
import asyncio
import logging
from datetime import datetime
import pytz

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ========= BASIC CONFIG =========
TIMEZONE = pytz.timezone("Asia/Kolkata")
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # set this before running
BOT_NAME_FOR_LINK = None  # auto-filled after app starts
DAILY_FREE_SEARCHES = 3
PRIVATE_SEARCH_COST = 1
REFERRAL_BONUS = 0.0
JOINING_BONUS = 0.0

# In-memory "credits" & "usage" (demo only; no DB)
USERS = {}  # user_id -> {"credits": float, "daily_used": int, "last_date": "YYYY-MM-DD"}

# ========= LOGGING =========
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger("safe-demo-bot")


# ========= KEYBOARDS =========
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Lookup", callback_data="start_lookup"),
         InlineKeyboardButton("💳 My Credits", callback_data="my_credits")],
        [InlineKeyboardButton("💡 How It Works", callback_data="how_it_works")]
    ])


def lookup_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Number Lookup", callback_data="lookup_phone"),
         InlineKeyboardButton("🚗 Vehicle Lookup", callback_data="lookup_vehicle")],
        [InlineKeyboardButton("📧 Email Lookup", callback_data="lookup_email")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ])


# ========= HELPERS =========
def _today_str() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def _ensure_user(user_id: int):
    rec = USERS.get(user_id)
    if not rec:
        USERS[user_id] = {
            "credits": JOINING_BONUS,
            "daily_used": 0,
            "last_date": _today_str()
        }
    else:
        # daily reset
        if rec["last_date"] != _today_str():
            rec["daily_used"] = 0
            rec["last_date"] = _today_str()


def _demo_phone_report(number: str) -> str:
    # MOCK, no PII
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    return (
        "╔══════════════════════════════╗\n"
        "║    📱   🎯 Phone Report (DEMO)\n"
        "╚══════════════════════════════╝\n"
        f"🔍 Searched Number: {number}\n\n"
        "┏━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  📋 BASIC SUMMARY      ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "• Format check: ✅\n"
        "• Risk level: Low (demo)\n"
        "• Note: This is sample data only.\n\n"
        f"🕒 Generated: {now} IST\n"
        "⚠️ Educational demo — no real OSINT."
    )


def _demo_vehicle_report(vno: str) -> str:
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    return (
        "╔══════════════════════════════╗\n"
        "║    🚗   🎯 Vehicle Report (DEMO)\n"
        "╚══════════════════════════════╝\n"
        f"🔍 Searched Number: {vno}\n\n"
        "┏━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  📋 VEHICLE SUMMARY    ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "• Class: N/A (demo)\n"
        "• Fuel: N/A (demo)\n"
        "• Insurance: N/A (demo)\n\n"
        f"🕒 Generated: {now} IST\n"
        "⚠️ Educational demo — no real OSINT."
    )


def _demo_email_report(email: str) -> str:
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    return (
        "╔══════════════════════════════╗\n"
        "║    📧   🎯 Email Report (DEMO)\n"
        "╚══════════════════════════════╝\n"
        f"🔍 Searched Email: {email}\n\n"
        "┏━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  📋 BREACH SUMMARY     ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "• Found breaches: 0 (demo)\n"
        "• Tip: Use strong, unique passwords + 2FA.\n\n"
        f"🕒 Generated: {now} IST\n"
        "⚠️ Educational demo — no real OSINT."
    )


# ========= HANDLERS =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    _ensure_user(user.id)

    text = (
        f"👋 Hello, {user.first_name or 'User'}!\n\n"
        "Welcome to the *Safe Demo* Lookup Bot.\n"
        f"• Free group-like demo: {DAILY_FREE_SEARCHES} lookups/day\n"
        f"• Private lookup cost (demo): {PRIVATE_SEARCH_COST} credit\n"
        "• No real OSINT — only mock data.\n\n"
        "Use the buttons below:"
    )
    if update.effective_chat:
        await update.message.reply_text(text, reply_markup=main_menu_kb(), parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 *Help*\n\n"
        "• Use /start to open the main menu.\n"
        "• This is a safe demo; it does not access real OSINT APIs.\n"
        "• Enter:\n"
        "  - 10-digit number → demo phone report\n"
        "  - .MH01AB1234 → demo vehicle report\n"
        "  - email@example.com → demo email report\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    _ensure_user(uid)

    if data == "main_menu":
        await query.edit_message_text(
            "Main menu:", reply_markup=main_menu_kb()
        )
        return

    if data == "start_lookup":
        context.user_data["state"] = None
        await query.edit_message_text(
            "<b>Choose lookup type:</b>", reply_markup=lookup_menu_kb(), parse_mode="HTML"
        )
        return

    if data == "lookup_phone":
        context.user_data["state"] = "waiting_phone"
        await query.edit_message_text(
            "<b>Send a 10-digit phone number.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]),
            parse_mode="HTML"
        )
        return

    if data == "lookup_vehicle":
        context.user_data["state"] = "waiting_vehicle"
        await query.edit_message_text(
            "<b>Send a vehicle number prefixed with a dot.</b>\nExample: <code>.MH01AB1234</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]),
            parse_mode="HTML"
        )
        return

    if data == "lookup_email":
        context.user_data["state"] = "waiting_email"
        await query.edit_message_text(
            "<b>Send an email address.</b>\nExample: <code>example@gmail.com</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]),
            parse_mode="HTML"
        )
        return

    if data == "my_credits":
        rec = USERS[uid]
        await query.edit_message_text(
            f"💳 *Your Credits*\n\n"
            f"• Current balance: {rec['credits']}\n"
            f"• Daily used: {rec['daily_used']}/{DAILY_FREE_SEARCHES}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
            parse_mode="Markdown"
        )
        return

    if data == "how_it_works":
        await query.edit_message_text(
            "📜 *How It Works*\n\n"
            "This bot is a *safe demo*. It returns mock summaries only.\n"
            "No personal/sensitive data is fetched or shown.\n",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
            parse_mode="Markdown"
        )
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    _ensure_user(user.id)
    rec = USERS[user.id]

    # simple daily reset already handled in _ensure_user
    state = context.user_data.get("state")

    text = (update.message.text or "").strip()

    # Vehicle (prefixed with '.')
    if text.startswith(".") and (state in (None, "waiting_vehicle")):
        vno = text[1:].strip().upper()
        if not vno:
            return
        # Daily free check
        if rec["daily_used"] >= DAILY_FREE_SEARCHES and rec["credits"] < PRIVATE_SEARCH_COST:
            await update.message.reply_text(
                "⚠️ Daily limit exceeded and insufficient credits (demo)."
            )
            return

        # Charge (demo)
        if rec["daily_used"] >= DAILY_FREE_SEARCHES:
            rec["credits"] -= PRIVATE_SEARCH_COST
        else:
            rec["daily_used"] += 1

        report = _demo_vehicle_report(vno)
        await update.message.reply_text(f"`{report}`", parse_mode="Markdown")
        context.user_data["state"] = None
        return

    # Email
    if ("@" in text and "." in text) and (state in (None, "waiting_email")):
        email = text.lower()
        if email.count("@") != 1:
            await update.message.reply_text("❌ Invalid email format.")
            return

        if rec["daily_used"] >= DAILY_FREE_SEARCHES and rec["credits"] < PRIVATE_SEARCH_COST:
            await update.message.reply_text(
                "⚠️ Daily limit exceeded and insufficient credits (demo)."
            )
            return

        if rec["daily_used"] >= DAILY_FREE_SEARCHES:
            rec["credits"] -= PRIVATE_SEARCH_COST
        else:
            rec["daily_used"] += 1

        report = _demo_email_report(email)
        await update.message.reply_text(f"`{report}`", parse_mode="Markdown")
        context.user_data["state"] = None
        return

    # Phone (10-digit)
    if text.isdigit() and len(text) == 10 and (state in (None, "waiting_phone")):
        if rec["daily_used"] >= DAILY_FREE_SEARCHES and rec["credits"] < PRIVATE_SEARCH_COST:
            await update.message.reply_text(
                "⚠️ Daily limit exceeded and insufficient credits (demo)."
            )
            return

        if rec["daily_used"] >= DAILY_FREE_SEARCHES:
            rec["credits"] -= PRIVATE_SEARCH_COST
        else:
            rec["daily_used"] += 1

        report = _demo_phone_report(text)
        await update.message.reply_text(f"`{report}`", parse_mode="Markdown")
        context.user_data["state"] = None
        return

    # Otherwise ignore or guide
    await update.message.reply_text(
        "Send:\n• 10-digit number\n• .MH01AB1234\n• email@example.com\n(or use the menu)"
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled error", exc_info=context.error)


# ========= MAIN =========
def main():
    if not BOT_TOKEN:
        raise SystemExit("ERROR: Set BOT_TOKEN environment variable before running.")

    application = Application.builder().token(BOT_TOKEN).build()

    # Fill bot username for deep-link (if needed later)
    async def _set_name(app: Application):
        nonlocal BOT_NAME_FOR_LINK
        me = await app.bot.get_me()
        BOT_NAME_FOR_LINK = me.username

    application.post_init = _set_name

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    application.add_error_handler(on_error)

    log.info("Starting Safe Demo Bot (polling)…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
