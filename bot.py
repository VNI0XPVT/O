#!/usr/bin/env python3

import sys
import subprocess
import asyncio
import json
import os
import requests
import logging
import sqlite3
import secrets
import string
import threading
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from flask import Flask, request, render_template_string

# =========================================================
# Optional auto installer (you already had this)
# =========================================================

def install_and_import(package, import_name=None):
    if import_name is None:
        import_name = package
    try:
        __import__(import_name)
    except ImportError:
        print(f"'{package}' not found. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"ERROR: Failed to install '{package}'. Please install it manually and run the script again.", file=sys.stderr)
            sys.exit(1)

# Install dependencies (first run me help karta hai - baad me unnecessary)
install_and_import('requests')
install_and_import('pytz')
install_and_import('python-telegram-bot', 'telegram')
install_and_import('Flask', 'flask')

# =========================================================
# Paths / Globals
# =========================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'phone_lookup_bot.db')
SETTINGS_FILE = os.path.join(SCRIPT_DIR, 'data.txt')

# =========================================================
# Logging
# =========================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================================================
# DB setup
# =========================================================

db_lock = threading.Lock()
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# =========================================================
# Config (runtime settings)
# =========================================================

class Config:
    BOT_TOKEN = ""  # Loaded from data.txt
    API_URL = ""  # Loaded from data.txt
    VEHICLE_API_URL = ""  # Loaded from data.txt
    GMAIL_API_URL = ""  # Loaded from data.txt
    ADMIN_PASSWORD = ''  # Loaded from data.txt
    ADMIN_IDS = []  # Loaded from data.txt
    LOG_CHANNEL_ID = None  # Loaded from data.txt
    REQUIRED_CHANNELS = []  # Loaded from data.txt
    ALLOWED_GROUPS = []  # Loaded from data.txt
    CHANNEL_LINKS = []  # Loaded from data.txt

    # Default Limits
    DAILY_FREE_SEARCHES = 0  # Loaded from data.txt
    PRIVATE_SEARCH_COST = 0.0  # Loaded from data.txt
    REFERRAL_BONUS = 0.0  # Loaded from data.txt
    JOINING_BONUS = 0.0  # Loaded from data.txt

    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')  # GMT+5:30

    # Runtime toggles
    BOT_LOCKED = False  # Loaded from data.txt
    MAINTENANCE_MODE = False  # Loaded from data.txt
    GROUP_SEARCHES_OFF = False  # Loaded from data.txt
    BOT_ACTIVE = True  # Loaded from data.txt


def load_settings():
    """Load settings from data.txt into Config"""
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            Config.BOT_TOKEN = settings.get('BOT_TOKEN', "8369296757:AAEU39Rvhw6sZiHrJpayZUJVD4a0WXNfHvg")
            Config.API_URL = settings.get('API_URL', "https://glonova.in/Ddsdddddddee.php/?num=")
            Config.VEHICLE_API_URL = settings.get('VEHICLE_API_URL', "https://glonova.in/RannKxi.php/?vc=")
            Config.GMAIL_API_URL = settings.get('GMAIL_API_URL', "https://glonova.in/Iqo1oPro.php/?email=")
            Config.ADMIN_PASSWORD = settings.get('ADMIN_PASSWORD', 'bm2')
            Config.ADMIN_IDS = settings.get('ADMIN_IDS', [6972508083])
            Config.LOG_CHANNEL_ID = settings.get('LOG_CHANNEL_ID', None)
            Config.REQUIRED_CHANNELS = settings.get('REQUIRED_CHANNELS', [-1001596819852])
            Config.ALLOWED_GROUPS = settings.get('ALLOWED_GROUPS', [-1001596819852])
            Config.CHANNEL_LINKS = settings.get('CHANNEL_LINKS', ["https://t.me/HEROKU_CLUB", "https://t.me/NOBITA_SUPPORT"])
            Config.DAILY_FREE_SEARCHES = settings.get('DAILY_FREE_SEARCHES', 3)
            Config.PRIVATE_SEARCH_COST = settings.get('PRIVATE_SEARCH_COST', 1)
            Config.REFERRAL_BONUS = settings.get('REFERRAL_BONUS', 0.5)
            Config.JOINING_BONUS = settings.get('JOINING_BONUS', 5.0)
            Config.BOT_LOCKED = settings.get('BOT_LOCKED', False)
            Config.MAINTENANCE_MODE = settings.get('MAINTENANCE_MODE', False)
            Config.GROUP_SEARCHES_OFF = settings.get('GROUP_SEARCHES_OFF', False)
            Config.BOT_ACTIVE = settings.get('BOT_ACTIVE', True)
            logger.info("Settings loaded from data.txt")
    except FileNotFoundError:
        logger.warning("data.txt not found. Creating with default settings.")
        save_settings()  # Create default data.txt
    except json.JSONDecodeError:
        logger.error("Error decoding data.txt. Overwriting with default settings.")
        save_settings()  # Overwrite corrupted data.txt


def save_settings():
    """Save current runtime Config values back to data.txt."""
    settings = {
        'BOT_TOKEN': Config.BOT_TOKEN,
        'API_URL': Config.API_URL,
        'VEHICLE_API_URL': Config.VEHICLE_API_URL,
        'GMAIL_API_URL': Config.GMAIL_API_URL,
        'ADMIN_PASSWORD': Config.ADMIN_PASSWORD,
        'ADMIN_IDS': list(Config.ADMIN_IDS),
        'LOG_CHANNEL_ID': Config.LOG_CHANNEL_ID,
        'REQUIRED_CHANNELS': Config.REQUIRED_CHANNELS,
        'ALLOWED_GROUPS': Config.ALLOWED_GROUPS,
        'CHANNEL_LINKS': Config.CHANNEL_LINKS,
        'DAILY_FREE_SEARCHES': Config.DAILY_FREE_SEARCHES,
        'PRIVATE_SEARCH_COST': Config.PRIVATE_SEARCH_COST,
        'REFERRAL_BONUS': Config.REFERRAL_BONUS,
        'JOINING_BONUS': Config.JOINING_BONUS,
        'BOT_LOCKED': Config.BOT_LOCKED,
        'MAINTENANCE_MODE': Config.MAINTENANCE_MODE,
        'GROUP_SEARCHES_OFF': Config.GROUP_SEARCHES_OFF,
        'BOT_ACTIVE': Config.BOT_ACTIVE,
    }
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
    logger.info("Settings saved to data.txt")

# =========================================================
# Flask panel (status on/off)
# =========================================================

app = Flask(__name__)

CONTROL_PANEL_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Bot Control Panel</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 500px; margin: auto; padding: 20px; border: 1px solid #ccc; border-radius: 8px; }
        .status { font-size: 1.2em; margin-bottom: 20px; }
        .status.on { color: green; }
        .status.off { color: red; }
        input[type="password"], button { padding: 10px; margin-top: 10px; width: 100%; box-sizing: border-box; }
        button { background-color: #4CAF50; color: white; border: none; cursor: pointer; }
        button.off { background-color: #f44336; }
        button:hover { opacity: 0.8; }
        .message { margin-top: 15px; color: blue; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Bot Control Panel</h1>
        <div class="status {{ 'on' if bot_active else 'off' }}">
            Bot Status: <strong>{{ 'ON' if bot_active else 'OFF' }}</strong>
        </div>
        <form action="/toggle_bot" method="post">
            <input type="password" name="password" placeholder="Enter password" required>
            <button type="submit" name="action" value="on" class="on">Turn ON</button>
            <button type="submit" name="action" value="off" class="off">Turn OFF</button>
        </form>
        {% if message %}
        <p class="message">{{ message }}</p>
        {% endif %}
    </div>
</body>
</html>
'''

@app.route('/')
def control_panel():
    message = request.args.get('message')
    return render_template_string(CONTROL_PANEL_HTML, bot_active=Config.BOT_ACTIVE, message=message)

@app.route('/toggle_bot', methods=['POST'])
def toggle_bot():
    password = request.form['password']
    action = request.form['action']

    if password != Config.ADMIN_PASSWORD:
        return render_template_string(CONTROL_PANEL_HTML, bot_active=Config.BOT_ACTIVE, message="Invalid password!"), 403

    if action == 'on':
        Config.BOT_ACTIVE = True
        message = "Bot turned ON successfully!"
    elif action == 'off':
        Config.BOT_ACTIVE = False
        message = "Bot turned OFF successfully!"
    else:
        message = "Invalid action."

    if action in ['on', 'off']:
        with db_lock:
            cursor.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)',
                           ('bot_active', str(Config.BOT_ACTIVE)))
            conn.commit()

    return render_template_string(CONTROL_PANEL_HTML, bot_active=Config.BOT_ACTIVE, message=message)

@app.route('/ping')
def ping():
    """Simple check endpoint (good for uptime pingers)."""
    return "hi"

def run_flask_app():
    app.run(host='0.0.0.0', port=5000)

# =========================================================
# DB tables + runtime load from DB tables
# =========================================================

def init_database():
    """Initialize database with all required tables"""
    with db_lock:
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                credits REAL DEFAULT 0,
                daily_searches INTEGER DEFAULT 0,
                last_reset TEXT,
                total_searches INTEGER DEFAULT 0,
                referred_by INTEGER,
                referral_count INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                joined_date TEXT,
                is_verified INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                credits REAL,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                created_at TEXT,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS code_redemptions (
                code TEXT,
                user_id INTEGER,
                redeemed_at TEXT,
                PRIMARY KEY (code, user_id)
            );

            CREATE TABLE IF NOT EXISTS allowed_groups (
                group_id INTEGER PRIMARY KEY,
                group_name TEXT,
                added_at TEXT
            );

            CREATE TABLE IF NOT EXISTS required_channels (
                channel_username TEXT PRIMARY KEY,
                added_at TEXT
            );

            CREATE TABLE IF NOT EXISTS search_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone_number TEXT,
                search_type TEXT,
                timestamp TEXT
            );

            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT
            );
        ''')
        conn.commit()

        # Load settings from bot_settings table (runtime overrides)
        cursor.execute('SELECT * FROM bot_settings')
        settings = cursor.fetchall()
        for setting in settings:
            if setting['key'] == 'log_channel_id' and setting['value']:
                Config.LOG_CHANNEL_ID = int(setting['value'])
            elif setting['key'] == 'daily_free_searches':
                Config.DAILY_FREE_SEARCHES = int(setting['value'])
            elif setting['key'] == 'private_search_cost':
                Config.PRIVATE_SEARCH_COST = float(setting['value'])
            elif setting['key'] == 'referral_bonus':
                Config.REFERRAL_BONUS = float(setting['value'])
            elif setting['key'] == 'bot_locked':
                Config.BOT_LOCKED = (setting['value'].lower() == 'true')
            elif setting['key'] == 'maintenance_mode':
                Config.MAINTENANCE_MODE = (setting['value'].lower() == 'true')
            elif setting['key'] == 'group_searches_off':
                Config.GROUP_SEARCHES_OFF = (setting['value'].lower() == 'true')
            elif setting['key'] == 'bot_active':
                Config.BOT_ACTIVE = (setting['value'].lower() == 'true')

        logger.info(f"Bot settings loaded: GROUP_SEARCHES_OFF = {Config.GROUP_SEARCHES_OFF}")

        # Load allowed groups
        cursor.execute('SELECT group_id FROM allowed_groups')
        db_allowed_groups = [row['group_id'] for row in cursor.fetchall()]
        if db_allowed_groups:
            Config.ALLOWED_GROUPS = db_allowed_groups

        # Load required channels
        cursor.execute('SELECT channel_username FROM required_channels')
        db_required_channels = [row['channel_username'] for row in cursor.fetchall()]
        if db_required_channels:
            Config.REQUIRED_CHANNELS = db_required_channels

        # Load admin IDs
        cursor.execute('SELECT user_id FROM users WHERE is_admin = 1')
        db_admin_ids = [row['user_id'] for row in cursor.fetchall()]
        if db_admin_ids:
            Config.ADMIN_IDS = db_admin_ids

# init DB tables now so they exist before bot starts
init_database()

# =========================================================
# Helpers: users, credits, limits, etc.
# =========================================================

def generate_referral_code(user_id: int) -> str:
    """Generate unique referral code"""
    return f"{user_id}{secrets.token_hex(3)}"[:8]

def generate_redeem_code() -> str:
    """Generate random redeem code"""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))

def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Get or create user in database"""
    with db_lock:
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()

        if not user:
            referral_code = generate_referral_code(user_id)
            now = datetime.now(Config.TIMEZONE).isoformat()
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, referral_code, joined_date, last_reset, credits)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, referral_code, now, now, Config.JOINING_BONUS))
            conn.commit()

            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
        else:
            # Keep username fresh
            if username or first_name:
                cursor.execute(
                    'UPDATE users SET username = ?, first_name = ? WHERE user_id = ?',
                    (username or user['username'], first_name or user['first_name'], user_id)
                )
                conn.commit()

        return dict(user)

def check_daily_reset(user_id: int) -> bool:
    """Reset per-day usage if date changed."""
    with db_lock:
        cursor.execute('SELECT last_reset FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()

        if row:
            last_reset = datetime.fromisoformat(row['last_reset']) if row['last_reset'] else None
            now = datetime.now(Config.TIMEZONE)
            if not last_reset or now.date() > last_reset.date():
                cursor.execute(
                    'UPDATE users SET daily_searches = 0, last_reset = ? WHERE user_id = ?',
                    (now.isoformat(), user_id)
                )
                conn.commit()
                return True
    return False

def set_user_state(user_id: int, state: str, data: str = None):
    with db_lock:
        cursor.execute(
            'INSERT OR REPLACE INTO user_states (user_id, state, data) VALUES (?, ?, ?)',
            (user_id, state, data)
        )
        conn.commit()

def get_user_state(user_id: int):
    with db_lock:
        cursor.execute('SELECT state, data FROM user_states WHERE user_id = ?', (user_id,))
        return cursor.fetchone()

def clear_user_state(user_id: int):
    with db_lock:
        cursor.execute('DELETE FROM user_states WHERE user_id = ?', (user_id,))
        conn.commit()

def check_daily_usage_group(user_id: int) -> bool:
    """Check if user exceeded daily free searches in group."""
    with db_lock:
        cursor.execute('SELECT daily_searches FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        if user:
            return user['daily_searches'] < Config.DAILY_FREE_SEARCHES
    return False

def increment_group_usage_db(user_id: int):
    with db_lock:
        cursor.execute(
            'UPDATE users SET daily_searches = daily_searches + 1 WHERE user_id = ?',
            (user_id,)
        )
        conn.commit()

# =========================================================
# Membership / permissions
# =========================================================

async def check_channel_membership(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if user is member of *all* required channels/groups."""
    for channel in Config.REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            print(f"DEBUG: User {user_id} status in channel {channel}: {member.status}")
            if member.status in ['left', 'kicked']:
                logger.warning(f"User {user_id} is not in channel {channel}. Status: {member.status}")
                return False
            logger.info(f"User {user_id} verified in channel {channel}.")
        except Exception as e:
            logger.error(f"Error checking membership for user {user_id} in channel {channel}: {e}")
            print(f"DEBUG: Exception checking membership for user {user_id} in channel {channel}: {e}")
            return False
    return True

def create_join_keyboard():
    buttons = []
    for i, link in enumerate(Config.CHANNEL_LINKS):
        buttons.append([InlineKeyboardButton(f"Join Channel {i+1}", url=link)])
    buttons.append([InlineKeyboardButton("✅ Verify Membership", callback_data="verify_membership")])
    return InlineKeyboardMarkup(buttons)

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Lookup", callback_data="start_lookup"),
         InlineKeyboardButton("💳 My Credits", callback_data="my_credits")],
        [InlineKeyboardButton("🔑 Redeem Code", callback_data="redeem_code"),
         InlineKeyboardButton("🔗 Invite Friends", callback_data="refer_friends")],
        [InlineKeyboardButton("💡 How It Works", callback_data="how_it_works"),
         InlineKeyboardButton("📈 My Usage", callback_data="my_stats")],
        [InlineKeyboardButton("📞 Contact Owner", url="https://t.me/HIDANCODE")]
    ])

def lookup_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Number Lookup", callback_data="lookup_phone"),
         InlineKeyboardButton("🚗 Vehicle Lookup", callback_data="lookup_vehicle")],
        [InlineKeyboardButton("📧 Gmail Lookup", callback_data="lookup_gmail")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ])

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Bot Settings", callback_data="admin_settings"),
         InlineKeyboardButton("⚙️ Management", callback_data="management_panel")],
        [InlineKeyboardButton("🤝 Required Join", callback_data="required_join"),
         InlineKeyboardButton("🎟 Generate Code", callback_data="admin_gen_code")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
         InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👑 Top Referrers", callback_data="admin_top_referrers"),
         InlineKeyboardButton("🚫 Ban/Unban User", callback_data="admin_ban_user")],
        [InlineKeyboardButton("📜 View Logs", callback_data="admin_logs"),
         InlineKeyboardButton("❌ Close", callback_data="close_menu")]
    ])

def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📱 Daily Free Searches: {Config.DAILY_FREE_SEARCHES}", callback_data="edit_daily_free_searches")],
        [InlineKeyboardButton(f"💰 Private Search Cost: {Config.PRIVATE_SEARCH_COST}", callback_data="edit_private_search_cost")],
        [InlineKeyboardButton(f"🤝 Referral Bonus: {Config.REFERRAL_BONUS}", callback_data="edit_referral_bonus")],
        [InlineKeyboardButton(f"📝 Log Channel ID: {Config.LOG_CHANNEL_ID or 'Not Set'}", callback_data="edit_log_channel_id")],
        [InlineKeyboardButton(f"🔒 Bot Locked: {'Yes' if Config.BOT_LOCKED else 'No'}", callback_data="toggle_bot_locked")],
        [InlineKeyboardButton(f"🛠️ Maintenance Mode: {'Yes' if Config.MAINTENANCE_MODE else 'No'}", callback_data="toggle_maintenance_mode")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ])

def manage_groups_keyboard() -> InlineKeyboardMarkup:
    keyboard_list = []
    for group_id in Config.ALLOWED_GROUPS:
        with db_lock:
            cursor.execute("SELECT group_name FROM allowed_groups WHERE group_id = ?", (group_id,))
            group_name = cursor.fetchone()
            group_name = group_name["group_name"] if group_name else f"Group {group_id}"
        keyboard_list.append([InlineKeyboardButton(f"❌ {group_name}", callback_data=f"remove_group_{group_id}")])
    keyboard_list.append([InlineKeyboardButton("➕ Add New Group", callback_data="add_group")])
    keyboard_list.append([InlineKeyboardButton("🔙 Back to Management", callback_data="management_panel")])
    return InlineKeyboardMarkup(keyboard_list)

def manage_channels_keyboard() -> InlineKeyboardMarkup:
    keyboard_list = []
    for channel_username in Config.REQUIRED_CHANNELS:
        keyboard_list.append([InlineKeyboardButton(f"❌ {channel_username}", callback_data=f"remove_channel_{channel_username}")])
    keyboard_list.append([InlineKeyboardButton("➕ Add New Channel", callback_data="add_channel")])
    keyboard_list.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard_list)

def ban_unban_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Ban User", callback_data="ban_user"),
         InlineKeyboardButton("✅ Unban User", callback_data="unban_user")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ])

def require_not_locked(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if Config.MAINTENANCE_MODE and update.effective_user.id not in Config.ADMIN_IDS:
            await update.effective_message.reply_text("🛠️ Bot maintenance chal raha hai.")
            return
        if not Config.BOT_ACTIVE:
            await update.effective_message.reply_text("⛔ Bot inactive hai.")
            return
        if Config.BOT_LOCKED and update.effective_user.id not in Config.ADMIN_IDS:
            await update.effective_message.reply_text("🔒 Bot locked hai.")
            return
        return await func(update, context)
    return wrapper

def callback_membership_required(func):
    """Decorator for callback handlers to check channel membership."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        query = update.callback_query
        user_id = query.from_user.id

        if not await check_channel_membership(context, user_id):
            keyboard = create_join_keyboard()
            await query.edit_message_text(
                "🔒 **Channel Membership Required**\n\n"
                "Please join all required channels to use this bot:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# =========================================================
# API callers + formatters
# =========================================================

async def fetch_osint_data(phone_number: str) -> dict:
    try:
        response = requests.get(f"{Config.API_URL}{phone_number}", timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"API request failed with status code: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"API request exception: {e}")
        return None

async def fetch_vehicle_data(vehicle_number: str) -> dict:
    try:
        url = f"{Config.VEHICLE_API_URL}{vehicle_number}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Vehicle API request failed for {vehicle_number} with status code: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Vehicle API request exception for {vehicle_number}: {e}")
        return None

async def fetch_gmail_data(email: str) -> dict:
    try:
        url = f"{Config.GMAIL_API_URL}{email}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Gmail API request failed for {email} with status code: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Gmail API request exception for {email}: {e}")
        return None

def format_osint_report(data: dict, phone_number: str) -> str:
    if not data or not data.get('success') or 'data' not in data or not data['data'].get('Requested Number Results'):
        return "❌ No valid data found in the API response."

    primary_result = data['data']['Requested Number Results'][0]

    name = primary_result.get('👤 Name', 'Not Found')
    father_name = primary_result.get('👨‍👦 Father Name', 'Not Found')
    address = primary_result.get('🏠 Full Address', 'Not Found')
    alt_number_primary = primary_result.get('📱 Alt Number', 'Not Found')
    sim_state = primary_result.get('📞 Sim/State', 'Not Found')
    aadhar = primary_result.get('🆔 Aadhar Card', 'Not Found')
    email = primary_result.get('📧 Email', 'N/A')

    report = f"""╔══════════════════════════════╗
║    📱   🎯 OSINT Report
╚══════════════════════════════╝
🔍 Searched Number: {phone_number}

┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  📋 PRIMARY INFORMATION  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┛
📱 Mobile: {phone_number}
👤 Name: {name}
👨‍👦 Father Name: {father_name}
🏠 Full Address: {address}
📱 Alt Number: {alt_number_primary}
📞 Sim/State: {sim_state}
🆔 Aadhar Card: {aadhar}"""

    alt_numbers_data = data['data'].get('Also searched full data on Alt Numbers', [])
    if alt_numbers_data:
        report += """

┏━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  🔄 ALTERNATE NUMBERS   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┛"""
        for alt_data in alt_numbers_data:
            alt_num = alt_data.get('Alt Number')
            if not alt_num or not alt_data.get('Results'):
                continue

            alt_result = alt_data['Results'][0]
            alt_name = alt_result.get('👤 Name', 'Not Found')
            alt_father_name = alt_result.get('👨‍👦 Father Name', 'Not Found')
            alt_address = alt_result.get('🏠 Full Address', 'Not Found')
            alt_sim_state = alt_result.get('📞 Sim/State', 'Not Found')
            alt_aadhar = alt_result.get('🆔 Aadhar Card', 'Not Found')

            report += f"""
📲 Alt Number: {alt_num}
  ├ 📱 Mobile: {alt_num}
  ├ 👤 Name: {alt_name}
  ├ 👨‍👦 Father Name: {alt_father_name}
  ├ 🏠 Full Address: {alt_address}
  ├ 📞 Sim/State: {alt_sim_state}
  └ 🆔 Aadhar Card: {alt_aadhar}"""

    report += f"""

🔍 Report Generated: {datetime.now(Config.TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}
⚠️ For Educational Purposes Only"""

    return report

def format_vehicle_report(data: dict, vehicle_number: str) -> str:
    if not data or data.get("status") != 0 or not data.get("data") or not data['data'].get('result'):
        return f"❌ No valid data found for vehicle number: {vehicle_number}"

    res = data['data']['result']

    report = f"""╔══════════════════════════════╗
║    🚗   🎯 Vehicle Report
╚══════════════════════════════╝
🔍 Searched Number: {res.get('regNo', 'N/A')}

┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  👤 OWNER INFORMATION   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┛
👤 Owner Name: {res.get('owner', 'N/A')}
👨‍👦 Father's Name: {res.get('ownerFatherName', 'N/A')}
🏠 Address: {res.get('presentAddress', 'N/A')}

┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  📋 VEHICLE DETAILS     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┛
🏭 Manufacturer: {res.get('vehicleManufacturerName', 'N/A')}
🚘 Model: {res.get('model', 'N/A')}
⛽ Fuel Type: {res.get('type', 'N/A')}
🏍️ Class: {res.get('class', 'N/A')}
🎨 Colour: {res.get('vehicleColour', 'N/A')}
📅 Registration Date: {res.get('regDate', 'N/A')}
🗓️ RC Expiry: {res.get('rcExpiryDate', 'N/A')}
Engine No: {res.get('engine', 'N/A')}
Chassis No: {res.get('chassis', 'N/A')}

┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  📄 OTHER INFORMATION    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┛
🏦 Financer: {res.get('rcFinancer', 'N/A')}
🛡️ Insurance Upto: {res.get('vehicleInsuranceUpto', 'N/A')}
PUCC Upto: {res.get('puccUpto', 'N/A')}
RTO: {res.get('regAuthority', 'N/A')}

🔍 Report Generated: {datetime.now(Config.TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}
⚠️ For Educational Purposes Only"""

    return report

def format_gmail_report(data: dict, email: str) -> str:
    if not data or not data.get('success') or not data.get('data') or not data['data'].get('results'):
        return f"❌ No valid data found for email: {email}"

    results = data['data']['results']
    leakcheck = results.get('leakcheck', {})

    if not leakcheck.get('success') or not leakcheck.get('result'):
        return f"❌ No breach data found for email: {email}"

    report = f"""╔══════════════════════════════╗
║    📧   🎯 Gmail Report
╚══════════════════════════════╝
🔍 Searched Email: {email}

┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  📊 BREACH SUMMARY      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┛
📧 Email: {email}
🔍 Found Breaches: {leakcheck.get('found', 0)}
📊 Quota Remaining: {leakcheck.get('quota', 0)}

┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  🔓 BREACH DETAILS      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┛"""

    for i, result in enumerate(leakcheck['result'], 1):
        password = result.get('password', 'N/A')
        source = result.get('source', {})
        source_name = source.get('name', 'Unknown')
        breach_date = source.get('breach_date', 'Unknown')
        origins = result.get('origin', [])
        origin_text = ', '.join(origins) if origins else 'N/A'

        report += f"""

🔓 Breach #{i}:
  ├ 🔑 Password: {password}
  ├ 🏢 Source: {source_name}
  ├ 📅 Breach Date: {breach_date}
  └ 🌐 Origin: {origin_text}"""

    performance = data['data'].get('performance', {})
    failed_services = performance.get('failed_services', [])
    if failed_services:
        report += f"""

┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  ⚠️  SERVICE STATUS     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┛
❌ Failed Services: {', '.join(failed_services)}"""

    report += f"""

🔍 Report Generated: {datetime.now(Config.TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}
⚠️ For Educational Purposes Only"""

    return report

# =========================================================
# Core bot commands / flows
# =========================================================

@require_not_locked
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /start command """
    user = update.effective_user
    user_id = user.id

    # create/get user
    user_data = get_or_create_user(user_id, user.username, user.first_name)
    check_daily_reset(user_id)

    # handle referral in /start <code>
    if context.args:
        referral_code = context.args[0]
        with db_lock:
            cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (referral_code,))
            referrer = cursor.fetchone()

            if referrer and referrer['user_id'] != user_id and not user_data.get('referred_by'):
                cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (referrer['user_id'], user_id))
                cursor.execute('UPDATE users SET credits = credits + ?, referral_count = referral_count + 1 WHERE user_id = ?',
                               (Config.REFERRAL_BONUS, referrer['user_id']))
                conn.commit()
                try:
                    await context.bot.send_message(
                        referrer['user_id'],
                        f"🎉 You earned {Config.REFERRAL_BONUS} credits from a new referral!"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify referrer {referrer['user_id']}: {e}")

    # private chat
    if update.effective_chat.type == 'private':
        # must be in required channels
        if not await check_channel_membership(context, user_id):
            keyboard = create_join_keyboard()
            await update.message.reply_text(
                "🔒 **Channel Membership Required**\n\n"
                "Please join all required channels to use this bot:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            return

        await update.message.reply_text(
            f"👋 Hello, {user_data['first_name'] or 'User'}!\n\n"
            f"Welcome to the OSINT Phone Lookup Bot.\n\n"
            f"✨ Key Features:\n"
            f"- ✅ Free Lookups in groups: {Config.DAILY_FREE_SEARCHES} per day\n"
            f"- 💳 Private Lookup Cost: {Config.PRIVATE_SEARCH_COST} credit/search\n"
            f"- 🔗 Referral Bonus: {Config.REFERRAL_BONUS} credits per invite\n"
            f"- 🎁 Joining Bonus: {Config.JOINING_BONUS} credits\n\n"
            f"📊 Your Stats:\n"
            f"- 💰 Credits: {user_data['credits']}\n"
            f"- 🔍 Daily Group Searches Used: {user_data['daily_searches']}/{Config.DAILY_FREE_SEARCHES}\n"
            f"- 👥 Referrals: {user_data['referral_count']}\n\n"
            f"🚀 Choose an option:",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
        return

    # group chat
    if update.effective_chat.id in Config.ALLOWED_GROUPS:
        await update.message.reply_text(
            "🤖 **OSINT Phone Lookup Bot**\n\n"
            "Send:\n"
            "• 10-digit phone number\n"
            "• Vehicle number (e.g. `.JH01CW0229`)\n"
            "• Email address\n\n"
            f"⏰ Limit: {Config.DAILY_FREE_SEARCHES} searches/day\n"
            "🔒 Must be in required channels\n",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ This bot only works in authorized groups.\n"
            "Contact admin."
        )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /admin <password> """
    user_id = update.effective_user.id

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not context.args or context.args[0] != Config.ADMIN_PASSWORD:
        await update.message.reply_text("❌ Invalid password.")
        return

    # also require they are in required channels
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\n"
            "As an admin you must also join required channels:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return

    with db_lock:
        cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        if user_id not in Config.ADMIN_IDS:
            Config.ADMIN_IDS.append(user_id)

    await update.message.reply_text(
        "✅ **Admin Access Granted**\n\nWelcome to the admin panel:",
        reply_markup=admin_panel_keyboard(),
        parse_mode='Markdown'
    )

# ---------------------------------------------------------
# lookup handlers (phone / vehicle / gmail)
# ---------------------------------------------------------

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone lookup (group or private depending on chat)."""
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 Bot inactive.")
        return

    msg_text = update.message.text.strip()
    if not (msg_text.isdigit() and len(msg_text) == 10):
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    # maintenance/lock checks for non-admins
    if user_id not in Config.ADMIN_IDS:
        if Config.BOT_LOCKED:
            await update.message.reply_text("🔒 Bot is locked right now.")
            return
        if Config.MAINTENANCE_MODE:
            await update.message.reply_text("🛠 Bot under maintenance.")
            return

    # ensure user and reset daily
    get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)
    check_daily_reset(user_id)

    # group restrictions
    if chat_type != 'private':
        if chat_id not in Config.ALLOWED_GROUPS:
            await update.message.reply_text("❌ Unauthorized group!")
            return
        if Config.GROUP_SEARCHES_OFF:
            await update.message.reply_text(
                f"🔒 Group searches are OFF. Use DM.\n"
                f"https://t.me/{context.bot.username}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Private Chat", url=f"https://t.me/{context.bot.username}")]])
            )
            return
        if not check_daily_usage_group(user_id):
            remaining_time = datetime.now(Config.TIMEZONE).replace(hour=23, minute=59, second=59) - datetime.now(Config.TIMEZONE)
            await update.message.reply_text(
                f"⚠️ Daily limit exceeded!\n"
                f"🕐 Reset in: {str(remaining_time).split('.')[0]}"
            )
            return

    # membership check
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\nJoin first:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return

    processing_msg = await update.message.reply_text(
        "🔍 **Searching OSINT Data...**\n"
        f"📱 Number: `{msg_text}`\n"
        "⏳ Please wait...",
        parse_mode='Markdown'
    )

    osint_data = await fetch_osint_data(msg_text)

    if not osint_data:
        await processing_msg.edit_text(
            "❌ **Search Failed**\nNo data found or API error.",
            parse_mode='Markdown'
        )
        return

    report = format_osint_report(osint_data, msg_text)

    # log the search
    with db_lock:
        if chat_type == 'private':
            # charge credits later down below
            stype = 'private'
        else:
            stype = 'group'
        cursor.execute(
            'INSERT INTO search_logs (user_id, phone_number, search_type, timestamp) VALUES (?, ?, ?, ?)',
            (user_id, msg_text, stype, datetime.now(Config.TIMEZONE).isoformat())
        )
        conn.commit()

    # private chat path = pay credits
    if chat_type == 'private':
        user_data = get_or_create_user(user_id)
        if user_data['credits'] < Config.PRIVATE_SEARCH_COST:
            await processing_msg.delete()
            await update.message.reply_text(
                f"❌ **Insufficient Credits**\n\n"
                f"💰 Required: {Config.PRIVATE_SEARCH_COST} credits\n"
                f"💳 Your balance: {user_data['credits']}\n\n"
                f"Earn credits by referral / redeem code / group usage.",
                reply_markup=main_menu_keyboard(),
                parse_mode='Markdown'
            )
            return

        # deduct credits
        with db_lock:
            cursor.execute(
                'UPDATE users SET credits = credits - ?, total_searches = total_searches + 1 WHERE user_id = ?',
                (Config.PRIVATE_SEARCH_COST, user_id)
            )
            conn.commit()

        await processing_msg.delete()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
        await update.message.reply_text(
            f"`{report}`",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        updated_user = get_or_create_user(user_id)
        await update.message.reply_text(
            f"✅ **Search Complete**\n"
            f"💰 Remaining credits: {updated_user['credits']}",
            parse_mode='Markdown'
        )
    else:
        # group path
        increment_group_usage_db(user_id)

        await processing_msg.delete()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Contact Developer", url="https://t.me/HIDANCODE")]])
        await update.message.reply_text(
            f"`{report}`",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        with db_lock:
            cursor.execute('SELECT daily_searches FROM users WHERE user_id = ?', (user_id,))
            db_user = cursor.fetchone()
        if db_user:
            remaining = Config.DAILY_FREE_SEARCHES - db_user['daily_searches']
            await update.message.reply_text(
                f"✅ **Search Complete**\n"
                f"📊 Remaining searches today: {remaining}/{Config.DAILY_FREE_SEARCHES}",
                parse_mode='Markdown'
            )

async def handle_vehicle_number(update: Update, context: ContextTypes.DEFAULT_TYPE, vehicle_number: str):
    """Vehicle lookup handler (both group + private)"""
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 Bot inactive.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)
    check_daily_reset(user_id)

    # membership
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\nPlease join required channels:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return

    # private: must have credits
    if chat_type == 'private':
        user_data = get_or_create_user(user_id)
        if user_data['credits'] < Config.PRIVATE_SEARCH_COST:
            await update.message.reply_text(
                f"❌ **Insufficient Credits for Vehicle Search**\n\n"
                f"💰 Required: {Config.PRIVATE_SEARCH_COST} credits",
                parse_mode='Markdown'
            )
            return
    else:
        # group path
        if chat_id not in Config.ALLOWED_GROUPS:
            await update.message.reply_text("❌ Unauthorized group!")
            return
        if Config.GROUP_SEARCHES_OFF:
            await update.message.reply_text(
                f"🔒 Group searches OFF. Use DM.\n"
                f"https://t.me/{context.bot.username}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Private Chat", url=f"https://t.me/{context.bot.username}")]])
            )
            return
        if not check_daily_usage_group(user_id):
            await update.message.reply_text("⚠️ Daily limit exceeded!")
            return

    processing_msg = await update.message.reply_text(
        f"🔍 **Searching Vehicle Data...**\n"
        f"Vehicle No: `{vehicle_number}`\n"
        f"⏳ Please wait...",
        parse_mode='Markdown'
    )

    vehicle_data = await fetch_vehicle_data(vehicle_number)

    if not vehicle_data:
        await processing_msg.edit_text(
            "❌ **Search Failed**\nNo data found or API error.",
            parse_mode='Markdown'
        )
        return

    report = format_vehicle_report(vehicle_data, vehicle_number)

    await processing_msg.delete()

    # log
    with db_lock:
        stype = 'private' if chat_type == 'private' else 'group'
        cursor.execute(
            'INSERT INTO search_logs (user_id, phone_number, search_type, timestamp) VALUES (?, ?, ?, ?)',
            (user_id, vehicle_number, stype, datetime.now(Config.TIMEZONE).isoformat())
        )
        conn.commit()

    if chat_type == 'private':
        with db_lock:
            cursor.execute(
                'UPDATE users SET credits = credits - ?, total_searches = total_searches + 1 WHERE user_id = ?',
                (Config.PRIVATE_SEARCH_COST, user_id)
            )
            conn.commit()

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
        await update.message.reply_text(
            f'`{report}`', reply_markup=keyboard, parse_mode='Markdown'
        )

        updated_user = get_or_create_user(user_id)
        await update.message.reply_text(
            f"✅ **Search Complete**\n"
            f"💰 Remaining credits: {updated_user['credits']}",
            parse_mode='Markdown'
        )
    else:
        increment_group_usage_db(user_id)

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Contact Developer", url="https://t.me/HIDANCODE")]])
        await update.message.reply_text(
            f'`{report}`', reply_markup=keyboard, parse_mode='Markdown'
        )

        with db_lock:
            cursor.execute('SELECT daily_searches FROM users WHERE user_id = ?', (user_id,))
            db_user = cursor.fetchone()
        if db_user:
            remaining = Config.DAILY_FREE_SEARCHES - db_user['daily_searches']
            await update.message.reply_text(
                f"✅ **Search Complete**\n"
                f"📊 Remaining searches today: {remaining}/{Config.DAILY_FREE_SEARCHES}",
                parse_mode='Markdown'
            )

async def handle_gmail_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    """Email (breach) lookup handler."""
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 Bot inactive.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)
    check_daily_reset(user_id)

    # membership first
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\nPlease join required channels:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return

    # private costs credit
    if chat_type == 'private':
        user_data = get_or_create_user(user_id)
        if user_data['credits'] < Config.PRIVATE_SEARCH_COST:
            await update.message.reply_text(
                f"❌ **Insufficient Credits for Gmail Search**\n\n"
                f"💰 Required: {Config.PRIVATE_SEARCH_COST} credits",
                parse_mode='Markdown'
            )
            return
    else:
        # group
        if chat_id not in Config.ALLOWED_GROUPS:
            await update.message.reply_text("❌ Unauthorized group!")
            return
        if Config.GROUP_SEARCHES_OFF:
            await update.message.reply_text(
                f"🔒 Group searches are OFF. Use DM.\n"
                f"https://t.me/{context.bot.username}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Private Chat", url=f"https://t.me/{context.bot.username}")]])
            )
            return
        if not check_daily_usage_group(user_id):
            await update.message.reply_text("⚠️ Daily limit exceeded!")
            return

    processing_msg = await update.message.reply_text(
        f"🔍 **Searching Gmail Data...**\n"
        f"📧 Email: `{email}`\n"
        f"⏳ Please wait...",
        parse_mode='Markdown'
    )

    gmail_data = await fetch_gmail_data(email)

    if not gmail_data:
        await processing_msg.edit_text(
            "❌ **Search Failed**\nNo data found or API error.",
            parse_mode='Markdown'
        )
        return

    report = format_gmail_report(gmail_data, email)

    await processing_msg.delete()

    # log the search
    with db_lock:
        stype = 'private' if chat_type == 'private' else 'gmail'
        cursor.execute(
            'INSERT INTO search_logs (user_id, phone_number, search_type, timestamp) VALUES (?, ?, ?, ?)',
            (user_id, email, stype, datetime.now(Config.TIMEZONE).isoformat())
        )
        conn.commit()

    if chat_type == 'private':
        with db_lock:
            cursor.execute(
                'UPDATE users SET credits = credits - ?, total_searches = total_searches + 1 WHERE user_id = ?',
                (Config.PRIVATE_SEARCH_COST, user_id)
            )
            conn.commit()

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
        await update.message.reply_text(
            f'`{report}`', reply_markup=keyboard, parse_mode='Markdown'
        )

        updated_user = get_or_create_user(user_id)
        await update.message.reply_text(
            f"✅ **Search Complete**\n"
            f"💰 Remaining credits: {updated_user['credits']}",
            parse_mode='Markdown'
        )

    else:
        increment_group_usage_db(user_id)
        with db_lock:
            cursor.execute(
                'UPDATE users SET total_searches = total_searches + 1 WHERE user_id = ?',
                (user_id,)
            )
            conn.commit()

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Contact Developer", url="https://t.me/HIDANCODE")]])
        await update.message.reply_text(
            f'`{report}`', reply_markup=keyboard, parse_mode='Markdown'
        )

        with db_lock:
            cursor.execute('SELECT daily_searches FROM users WHERE user_id = ?', (user_id,))
            db_user = cursor.fetchone()
        if db_user:
            remaining = Config.DAILY_FREE_SEARCHES - db_user['daily_searches']
            await update.message.reply_text(
                f"✅ **Search Complete**\n"
                f"📊 Remaining searches today: {remaining}/{Config.DAILY_FREE_SEARCHES}",
                parse_mode='Markdown'
            )

# =========================================================
# Callback query handlers (menus, admin, etc.)
# =========================================================

async def verify_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if await check_channel_membership(context, user_id):
        await query.edit_message_text(
            "✅ **Membership Verified!**\nYou can now use the bot.",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            "❌ **Verification Failed**\nJoin all required channels first.",
            reply_markup=create_join_keyboard(),
            parse_mode='Markdown'
        )

@callback_membership_required
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_or_create_user(user_id)

    message_text = (
        f"👋 Hello, {user_data['first_name'] or 'User'}!\n\n"
        f"Welcome to the OSINT Phone Lookup Bot.\n\n"
        f"✨ Key Features:\n"
        f"- ✅ Free Lookups in groups: {Config.DAILY_FREE_SEARCHES} per day\n"
        f"- 💳 Private Lookup Cost: {Config.PRIVATE_SEARCH_COST} credit/search\n"
        f"- 🔗 Referral Bonus: {Config.REFERRAL_BONUS} credits per invite\n"
        f"- 🎁 Joining Bonus: {Config.JOINING_BONUS} credits\n\n"
        f"📊 Your Stats:\n"
        f"- 💰 Credits: {user_data['credits']}\n"
        f"- 🔍 Daily Group Searches Used: {user_data['daily_searches']}/{Config.DAILY_FREE_SEARCHES}\n"
        f"- 👥 Referrals: {user_data['referral_count']}\n\n"
        f"🚀 Choose an option:"
    )

    await query.edit_message_text(
        text=message_text,
        reply_markup=main_menu_keyboard(),
        parse_mode='Markdown'
    )

@callback_membership_required
async def start_lookup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text(
        text="<b>Please choose the type of lookup you want to perform:</b>",
        reply_markup=lookup_menu_keyboard(),
        parse_mode='HTML'
    )

@callback_membership_required
async def lookup_phone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    set_user_state(user_id, "waiting_phone_number")
    await query.edit_message_text(
        "<b>Enter a 10-digit phone number to search.</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]),
        parse_mode='HTML'
    )

@callback_membership_required
async def lookup_vehicle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    set_user_state(user_id, "waiting_vehicle_number")
    await query.edit_message_text(
        "<b>Enter a vehicle number to search, prefixed with a dot.</b>\n"
        "Example: <code>.JH01CW0229</code>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]),
        parse_mode='HTML'
    )

@callback_membership_required
async def lookup_gmail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    set_user_state(user_id, "waiting_gmail")
    await query.edit_message_text(
        "<b>Enter an email address to search for breaches.</b>\n"
        "Example: <code>example@gmail.com</code>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]),
        parse_mode='HTML'
    )

@callback_membership_required
async def show_credits_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_or_create_user(user_id)

    await query.edit_message_text(
        f"💰 **Your Credits**\n\n"
        f"💳 Current Balance: {user_data['credits']} credits\n"
        f"🔄 Daily Searches Used: {user_data['daily_searches']}/{Config.DAILY_FREE_SEARCHES}\n"
        f"📊 Total Searches: {user_data['total_searches']}\n"
        f"🤝 Referrals: {user_data['referral_count']}\n\n"
        f"💡 Ways to earn:\n"
        f"• Invite friends ({Config.REFERRAL_BONUS} credits each)\n"
        f"• Redeem codes\n"
        f"• Use free searches in groups",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

@callback_membership_required
async def redeem_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    set_user_state(user_id, "waiting_redeem_code")

    await query.edit_message_text(
        "🎁 **Redeem Code**\n\n"
        "📝 Send the redeem code to claim credits.\n"
        "⏰ You have 60 seconds.\n\n"
        "💡 Get codes from admin / giveaways.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

@callback_membership_required
async def refer_friends_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_or_create_user(user_id)

    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"

    await query.edit_message_text(
        f"🤝 **Invite Friends**\n\n"
        f"🎁 Earn {Config.REFERRAL_BONUS} credits per referral!\n"
        f"👥 Your referrals: {user_data['referral_count']}\n\n"
        f"🔗 **Your referral link:**\n"
        f"`{referral_link}`\n\n"
        f"📋 **Your referral code:**\n"
        f"`{user_data['referral_code']}`\n\n"
        f"Share and earn credits 🔥",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

@callback_membership_required
async def my_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_or_create_user(user_id)

    with db_lock:
        cursor.execute(
            'SELECT COUNT(*) as total, search_type FROM search_logs WHERE user_id = ? GROUP BY search_type',
            (user_id,)
        )
        search_stats = cursor.fetchall()

    stats_text = ""
    for stat in search_stats:
        stats_text += f"• {stat['search_type'].title()}: {stat['total']}\n"
    if not stats_text:
        stats_text = "• No searches yet\n"

    await query.edit_message_text(
        f"📊 **Your Statistics**\n\n"
        f"👤 User ID: {user_id}\n"
        f"📅 Joined: {user_data['joined_date'][:10] if user_data['joined_date'] else 'Unknown'}\n"
        f"💰 Credits: {user_data['credits']}\n"
        f"🔄 Daily Searches: {user_data['daily_searches']}/{Config.DAILY_FREE_SEARCHES}\n"
        f"🤝 Referrals: {user_data['referral_count']}\n\n"
        f"📈 **Search History:**\n"
        f"{stats_text}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

@callback_membership_required
async def how_it_works_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text(
        "📜 **How It Works**\n\n"
        "This bot does OSINT lookups.\n\n"
        "**In Private Chat:**\n"
        f"- Each search costs {Config.PRIVATE_SEARCH_COST} credit.\n"
        f"- Earn credits by inviting friends ({Config.REFERRAL_BONUS} each) or redeeming codes.\n\n"
        "**In Authorized Groups:**\n"
        f"- You get {Config.DAILY_FREE_SEARCHES} free searches daily.\n"
        "- You must join required channels.\n\n"
        "Send a 10-digit phone number, a vehicle number like `.JH01CW0229`, or an email.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    await query.edit_message_text(
        "✅ **Admin Access Granted**\n\nWelcome to the admin panel:",
        reply_markup=admin_panel_keyboard(),
        parse_mode='Markdown'
    )

def required_join_keyboard() -> InlineKeyboardMarkup:
    keyboard_list = []
    keyboard_list.append([InlineKeyboardButton("Required Channels:", callback_data="dummy")])
    for channel_username in Config.REQUIRED_CHANNELS:
        keyboard_list.append([InlineKeyboardButton(f"❌ {channel_username}", callback_data=f"remove_channel_{channel_username}")])
    keyboard_list.append([InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")])

    keyboard_list.append([InlineKeyboardButton("Allowed Groups:", callback_data="dummy")])
    for group_id in Config.ALLOWED_GROUPS:
        with db_lock:
            cursor.execute("SELECT group_name FROM allowed_groups WHERE group_id = ?", (group_id,))
            group_name = cursor.fetchone()
            group_name = group_name["group_name"] if group_name else f"Group {group_id}"
        keyboard_list.append([InlineKeyboardButton(f"❌ {group_name}", callback_data=f"remove_group_{group_id}")])
    keyboard_list.append([InlineKeyboardButton("➕ Add Group", callback_data="add_group")])

    keyboard_list.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard_list)

async def required_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    await query.edit_message_text(
        "🤝 **Required Join Configuration**\n\n"
        "Manage channels and allowed groups.",
        reply_markup=required_join_keyboard(),
        parse_mode='Markdown'
    )

def management_options_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Manage Groups", callback_data="manage_groups")],
        [InlineKeyboardButton("➕ Add Admin", callback_data="add_admin")],
        [InlineKeyboardButton(f"🚫 Group Searches: {'OFF' if Config.GROUP_SEARCHES_OFF else 'ON'}", callback_data="toggle_group_searches")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ])

async def management_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    await query.edit_message_text(
        "⚙️ **Management Panel**\n\n"
        "Select an option:",
        reply_markup=management_options_keyboard(),
        parse_mode='Markdown'
    )

async def admin_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    await query.edit_message_text(
        "⚙️ **Bot Settings**\n\nConfigure bot parameters below.",
        reply_markup=settings_keyboard(),
        parse_mode='Markdown'
    )

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    if data == "toggle_bot_locked":
        Config.BOT_LOCKED = not Config.BOT_LOCKED
        with db_lock:
            cursor.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)',
                           ('bot_locked', str(Config.BOT_LOCKED)))
            conn.commit()
        await query.answer(f"Bot Locked: {'Yes' if Config.BOT_LOCKED else 'No'}")
        await admin_settings_callback(update, context)

    elif data == "toggle_maintenance_mode":
        Config.MAINTENANCE_MODE = not Config.MAINTENANCE_MODE
        with db_lock:
            cursor.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)',
                           ('maintenance_mode', str(Config.MAINTENANCE_MODE)))
            conn.commit()
        await query.answer(f"Maintenance Mode: {'Yes' if Config.MAINTENANCE_MODE else 'No'}")
        await admin_settings_callback(update, context)

    elif data.startswith("edit_"):
        setting_key = data.replace("edit_", "")
        set_user_state(user_id, "waiting_setting_value", setting_key)
        await query.edit_message_text(
            f"📝 **Edit {setting_key.replace('_', ' ').title()}**\n\n"
            f"Please send the new value:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_settings")]]),
            parse_mode='Markdown'
        )

async def admin_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    await query.edit_message_text(
        "👥 **Manage Allowed Groups**\n\nAdd/remove groups allowed to use the bot.",
        reply_markup=manage_groups_keyboard(),
        parse_mode='Markdown'
    )

async def remove_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, group_id: int):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    with db_lock:
        cursor.execute('DELETE FROM allowed_groups WHERE group_id = ?', (group_id,))
        conn.commit()
        if group_id in Config.ALLOWED_GROUPS:
            Config.ALLOWED_GROUPS.remove(group_id)

    await query.answer(f"Group {group_id} removed.")
    await required_join_callback(update, context)

async def add_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "waiting_group_id")
    await query.edit_message_text(
        "➕ **Add New Group**\n\nSend the group ID.\nYou can get group ID via @getidsbot.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="required_join")]]),
        parse_mode='Markdown'
    )

async def admin_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    await query.edit_message_text(
        "📢 **Manage Required Channels**\n\nAdd/remove channels users MUST join.",
        reply_markup=manage_channels_keyboard(),
        parse_mode='Markdown'
    )

async def remove_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_username: str):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    with db_lock:
        cursor.execute('DELETE FROM required_channels WHERE channel_username = ?', (channel_username,))
        conn.commit()
        if channel_username in Config.REQUIRED_CHANNELS:
            Config.REQUIRED_CHANNELS.remove(channel_username)

    await query.answer(f"Channel {channel_username} removed.")
    await required_join_callback(update, context)

async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "waiting_channel_username")
    await query.edit_message_text(
        "➕ **Add New Channel**\n\nSend @channelusername",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="required_join")]]),
        parse_mode='Markdown'
    )

async def add_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "waiting_admin_id")
    await query.edit_message_text(
        "➕ **Add New Admin**\n\nSend the User ID with `.userid` prefix.\nExample: `.userid123456789`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="management_panel")]]),
        parse_mode='Markdown'
    )

async def toggle_group_searches_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    Config.GROUP_SEARCHES_OFF = not Config.GROUP_SEARCHES_OFF
    with db_lock:
        cursor.execute(
            'INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)',
            ('group_searches_off', str(Config.GROUP_SEARCHES_OFF))
        )
        conn.commit()

    await query.answer(f"Group Searches: {'OFF' if Config.GROUP_SEARCHES_OFF else 'ON'}")
    await management_panel_callback(update, context)

async def admin_gen_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "admin_gen_code")

    await query.edit_message_text(
        "🎟 **Generate Redeem Code**\n\nSend in format: credits,max_uses\nExample: 10,5",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]])
    )

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    with db_lock:
        cursor.execute('SELECT COUNT(*) as total_users FROM users')
        total_users = cursor.fetchone()['total_users']

        cursor.execute('SELECT COUNT(*) as total_searches FROM search_logs')
        total_searches = cursor.fetchone()['total_searches']

        cursor.execute('SELECT COUNT(*) as active_codes FROM redeem_codes WHERE is_active = 1')
        active_codes = cursor.fetchone()['active_codes']

        cursor.execute('SELECT SUM(credits) as total_credits FROM users')
        total_credits = cursor.fetchone()['total_credits'] or 0

        cursor.execute('SELECT COUNT(*) as banned_users FROM users WHERE is_banned = 1')
        banned_users = cursor.fetchone()['banned_users']

        cursor.execute('SELECT COUNT(*) as verified_users FROM users WHERE is_verified = 1')
        verified_users = cursor.fetchone()['verified_users']

        cursor.execute('SELECT COUNT(*) as admin_users FROM users WHERE is_admin = 1')
        admin_users = cursor.fetchone()['admin_users']

        cursor.execute('SELECT SUM(referral_count) as total_referrals FROM users')
        total_referrals = cursor.fetchone()['total_referrals'] or 0

        cursor.execute('SELECT COUNT(*) as total_redeemed_codes FROM code_redemptions')
        total_redeemed_codes = cursor.fetchone()['total_redeemed_codes']

    await query.edit_message_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"🔍 Total Searches: {total_searches}\n"
        f"💰 Total Credits: {total_credits:.2f}\n"
        f"🎟 Active Codes: {active_codes}\n"
        f"🚫 Banned Users: {banned_users}\n"
        f"✅ Verified Users: {verified_users}\n"
        f"👨‍💻 Admin Users: {admin_users}\n"
        f"🤝 Total Referrals: {total_referrals}\n"
        f"🎁 Total Redeemed Codes: {total_redeemed_codes}\n\n"
        f"📈 Bot running smoothly.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "admin_broadcast")

    await query.edit_message_text(
        "📢 **Broadcast Message**\n\n"
        "📝 Send the message to broadcast to ALL users.\n"
        "⚠️ Will go to all users / groups / channels.\n"
        "⏰ You have 60 seconds.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def admin_top_referrers_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    with db_lock:
        cursor.execute('SELECT user_id, username, referral_count FROM users ORDER BY referral_count DESC LIMIT 10')
        top_referrers = cursor.fetchall()

    message = "<b>👑 Top 10 Referrers</b>\n\n"
    if top_referrers:
        for i, referrer in enumerate(top_referrers):
            username = referrer['username']
            if username:
                display_name = (
                    username
                    .replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;')
                )
            else:
                display_name = referrer['user_id']
            message += f"{i+1}. {display_name} - {referrer['referral_count']} referrals\n"
    else:
        message += "No referrers yet."

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
        parse_mode='HTML'
    )

async def admin_ban_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    await query.edit_message_text(
        "🚫 **Ban/Unban User**\n\nSelect an action:",
        reply_markup=ban_unban_keyboard(),
        parse_mode='Markdown'
    )

async def admin_logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    if not Config.LOG_CHANNEL_ID:
        await query.edit_message_text(
            "❌ **Log Channel Not Set**\n\n"
            "Please set LOG_CHANNEL_ID first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
            parse_mode='Markdown'
        )
        return

    await query.edit_message_text(
        f"📜 **Bot Logs**\n\n"
        f"Logs are sent to configured log channel: `{Config.LOG_CHANNEL_ID}`.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

# =========================================================
# State-based input handlers
# =========================================================

async def handle_redeem_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    user_id = update.effective_user.id

    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\n"
            "Join all required channels before redeeming codes.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return

    clear_user_state(user_id)

    with db_lock:
        # Check code
        cursor.execute('SELECT * FROM redeem_codes WHERE code = ? AND is_active = 1', (code,))
        redeem_code = cursor.fetchone()

        if not redeem_code:
            await update.message.reply_text(
                "❌ **Invalid Code**\n\n"
                "The code is invalid or expired.",
                reply_markup=main_menu_keyboard(),
                parse_mode='Markdown'
            )
            return

        # Already redeemed?
        cursor.execute('SELECT * FROM code_redemptions WHERE code = ? AND user_id = ?', (code, user_id))
        already_redeemed = cursor.fetchone()
        if already_redeemed:
            await update.message.reply_text(
                "❌ **Already Redeemed**\n\nYou already used this code.",
                reply_markup=main_menu_keyboard(),
                parse_mode='Markdown'
            )
            return

        # Max uses?
        if redeem_code['used_count'] >= redeem_code['max_uses']:
            await update.message.reply_text(
                "❌ **Code Expired**\n\nThis code reached max usage.",
                reply_markup=main_menu_keyboard(),
                parse_mode='Markdown'
            )
            return

        # Redeem
        cursor.execute(
            'UPDATE users SET credits = credits + ? WHERE user_id = ?',
            (redeem_code['credits'], user_id)
        )
        cursor.execute(
            'UPDATE redeem_codes SET used_count = used_count + 1 WHERE code = ?',
            (code,)
        )
        cursor.execute(
            'INSERT INTO code_redemptions (code, user_id, redeemed_at) VALUES (?, ?, ?)',
            (code, user_id, datetime.now(Config.TIMEZONE).isoformat())
        )
        conn.commit()

    await update.message.reply_text(
        f"✅ **Code Redeemed!**\n\n"
        f"💰 You received {redeem_code['credits']} credits!\n"
        f"🎉 Enjoy your searches!",
        reply_markup=main_menu_keyboard(),
        parse_mode='Markdown'
    )

async def handle_admin_gen_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        return

    try:
        credits_str, max_uses_str = message_text.split(',')
        credits = float(credits_str.strip())
        max_uses = int(max_uses_str.strip())

        if credits <= 0 or max_uses <= 0:
            raise ValueError("Credits and max uses must be positive.")

        code = generate_redeem_code()

        with db_lock:
            cursor.execute(
                'INSERT INTO redeem_codes (code, credits, max_uses, created_at) VALUES (?, ?, ?, ?)',
                (code, credits, max_uses, datetime.now(Config.TIMEZONE).isoformat())
            )
            conn.commit()

        await update.message.reply_text(
            f"✅ **Code Generated!**\n\n"
            f"🎟 Code: `{code}`\n"
            f"💰 Credits: `{credits}`\n"
            f"👥 Max Uses: `{max_uses}`",
            parse_mode='Markdown'
        )
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ **Invalid format**\n\n"
            "Use: `credits,max_uses`\nExample: `10,5`",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )

async def handle_admin_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id

    if user_id not in Config.ADMIN_IDS:
        clear_user_state(user_id)
        return

    # Save message so next callback can send it everywhere
    set_user_state(user_id, "waiting_broadcast_confirm", message_text)

    with db_lock:
        cursor.execute('SELECT COUNT(*) as count FROM users')
        user_count = cursor.fetchone()['count']
    group_count = len(Config.ALLOWED_GROUPS)
    channel_count = len(Config.REQUIRED_CHANNELS)
    target_desc = f"{user_count} users, {group_count} groups, {channel_count} channels"

    await update.message.reply_text(
        f"✅ **Confirm Broadcast**\n\n"
        f"This will send to **{target_desc}**.\n\n"
        f"**Message Preview:**\n---\n{message_text}\n---\n\n"
        f"Send now?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Send", callback_data="broadcast_confirm_send")],
            [InlineKeyboardButton("❌ No, Cancel", callback_data="admin_panel")]
        ]),
        parse_mode='Markdown'
    )

async def broadcast_confirm_send_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    state_data = get_user_state(user_id)
    if not state_data or state_data['state'] != 'waiting_broadcast_confirm':
        await query.edit_message_text(
            "No pending broadcast. Please start again.",
            reply_markup=admin_panel_keyboard()
        )
        return

    message_text = state_data['data']
    clear_user_state(user_id)

    with db_lock:
        cursor.execute('SELECT user_id FROM users')
        all_users = [row['user_id'] for row in cursor.fetchall()]
    all_groups = Config.ALLOWED_GROUPS
    all_channels = Config.REQUIRED_CHANNELS
    targets = all_users + all_groups + all_channels

    await query.edit_message_text(
        f"📢 Broadcasting to {len(targets)} targets..."
    )

    success_count = 0
    fail_count = 0
    for target_id in targets:
        try:
            await context.bot.send_message(
                target_id,
                f"📢 **Broadcast Message**\n\n{message_text}",
                parse_mode='Markdown'
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to {target_id}: {e}")
            fail_count += 1
        await asyncio.sleep(0.1)

    await query.edit_message_text(
        f"✅ **Broadcast Complete**\n\n"
        f"📤 Sent: {success_count}\n"
        f"❌ Failed: {fail_count}\n"
        f"👥 Total Targets: {len(targets)}",
        reply_markup=admin_panel_keyboard(),
        parse_mode='Markdown'
    )

async def handle_setting_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE, value_text: str, setting_key: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return

    try:
        if setting_key == "daily_free_searches":
            Config.DAILY_FREE_SEARCHES = int(value_text)
        elif setting_key == "private_search_cost":
            Config.PRIVATE_SEARCH_COST = float(value_text)
        elif setting_key == "referral_bonus":
            Config.REFERRAL_BONUS = float(value_text)
        elif setting_key == "log_channel_id":
            Config.LOG_CHANNEL_ID = int(value_text)

        with db_lock:
            cursor.execute(
                'INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)',
                (setting_key, value_text)
            )
            conn.commit()

        await update.message.reply_text(
            f"✅ {setting_key.replace('_', ' ').title()} updated to `{value_text}`.",
            reply_markup=settings_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid value. Please enter a valid number.",
            reply_markup=settings_keyboard(),
            parse_mode='Markdown'
        )

async def handle_add_group_input(update: Update, context: ContextTypes.DEFAULT_TYPE, group_id_text: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return

    try:
        group_id = int(group_id_text)
        with db_lock:
            cursor.execute(
                'INSERT INTO allowed_groups (group_id, group_name, added_at) VALUES (?, ?, ?)',
                (group_id, f"Group {group_id}", datetime.now(Config.TIMEZONE).isoformat())
            )
            conn.commit()
            if group_id not in Config.ALLOWED_GROUPS:
                Config.ALLOWED_GROUPS.append(group_id)

        await update.message.reply_text(
            f"✅ Group `{group_id}` added.",
            reply_markup=required_join_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid group ID. Must be an integer.",
            reply_markup=required_join_keyboard(),
            parse_mode='Markdown'
        )
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Group already exists.",
            reply_markup=required_join_keyboard(),
            parse_mode='Markdown'
        )

async def handle_add_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_username: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return

    if not channel_username.startswith('@'):
        await update.message.reply_text(
            "❌ Invalid channel username. Use `@channelname`.",
            reply_markup=required_join_keyboard(),
            parse_mode='Markdown'
        )
        return

    try:
        with db_lock:
            cursor.execute(
                'INSERT INTO required_channels (channel_username, added_at) VALUES (?, ?)',
                (channel_username, datetime.now(Config.TIMEZONE).isoformat())
            )
            conn.commit()
            if channel_username not in Config.REQUIRED_CHANNELS:
                Config.REQUIRED_CHANNELS.append(channel_username)

        await update.message.reply_text(
            f"✅ Channel `{channel_username}` added.",
            reply_markup=required_join_keyboard(),
            parse_mode='Markdown'
        )
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Channel already exists.",
            reply_markup=required_join_keyboard(),
            parse_mode='Markdown'
        )

async def ban_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "waiting_ban_user_id")
    await query.edit_message_text(
        "🚫 **Ban User**\n\nSend the User ID to ban.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def handle_ban_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id_text: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return

    try:
        target_user_id = int(target_user_id_text)
        with db_lock:
            cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (target_user_id,))
            conn.commit()

        await update.message.reply_text(
            f"✅ User `{target_user_id}` banned.",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID. Must be integer.",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )

async def unban_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "waiting_unban_user_id")
    await query.edit_message_text(
        "✅ **Unban User**\n\nSend the User ID to unban.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def handle_unban_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id_text: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return

    try:
        target_user_id = int(target_user_id_text)
        with db_lock:
            cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (target_user_id,))
            conn.commit()

        await update.message.reply_text(
            f"✅ User `{target_user_id}` unbanned.",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID. Must be integer.",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )

async def handle_admin_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id_text: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return

    if not target_user_id_text.startswith(".userid"):
        await update.message.reply_text(
            "❌ Invalid format. Use `.userid123456789`.",
            reply_markup=management_options_keyboard(),
            parse_mode='Markdown'
        )
        return

    id_string = target_user_id_text[len(".userid"):]
    try:
        target_user_id = int(id_string)
        with db_lock:
            cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (target_user_id,))
            conn.commit()
            if target_user_id not in Config.ADMIN_IDS:
                Config.ADMIN_IDS.append(target_user_id)

        await update.message.reply_text(
            f"✅ User `{target_user_id}` is now admin.",
            reply_markup=management_options_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid ID. After `.userid` must be a number.",
            reply_markup=management_options_keyboard(),
            parse_mode='Markdown'
        )

# =========================================================
# /help command
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "🤖 **OSINT Phone Lookup Bot Help**\n\n"
            "🔍 Private Chat:\n"
            f"• Each lookup costs {Config.PRIVATE_SEARCH_COST} credit\n"
            f"• Earn credits via referral ({Config.REFERRAL_BONUS} each), redeem codes, joining bonus ({Config.JOINING_BONUS})\n\n"
            "🏢 Groups:\n"
            f"• {Config.DAILY_FREE_SEARCHES} free searches per day\n"
            "• Only in authorized groups\n"
            "• Must join required channels\n\n"
            "📱 Usage:\n"
            "• Send a 10-digit phone number\n"
            "• Send a vehicle number like `.JH01CW0229`\n"
            "• Send an email for breach lookup",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
        return

    if update.effective_chat.id not in Config.ALLOWED_GROUPS:
        await update.message.reply_text("❌ Bot only works in authorized groups!")
        return

    help_text = (
        f"🤖 **OSINT Phone Lookup Bot Help**\n\n"
        "📱 How to use:\n"
        "• Send a 10-digit phone number (e.g., 9876543210)\n"
        "• Send a vehicle number (e.g., .JH01CW0229)\n"
        "• Send an email address (e.g., example@gmail.com)\n\n"
        "⚠️ Restrictions:\n"
        f"• {Config.DAILY_FREE_SEARCHES} searches per user per day\n"
        "• Works only in authorized groups\n"
        "• Channel membership required\n\n"
        "🔗 Required:\n"
        "• Join all channels to unlock bot access\n"
        "• Click verify after joining\n\n"
        "⚡ Commands:\n"
        "/start - Start the bot\n"
        "/help - Help menu\n\n"
        "🔒 Privacy:\n"
        "For educational purposes only."
    )

    await update.message.reply_text(help_text, parse_mode='Markdown')

# =========================================================
# State router / text handler
# =========================================================

async def handle_gmail_input(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    # simple validation
    if '@' not in email or '.' not in email or email.count('@') != 1:
        await update.message.reply_text(
            "❌ **Invalid Email Format**\n\n"
            "Please enter a valid email address.",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
        return

    await handle_gmail_lookup(update, context, email.lower().strip())

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all plain text messages based on state + content."""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    chat_type = update.effective_chat.type

    state_data = get_user_state(user_id)
    state = state_data['state'] if state_data else None

    # Vehicle format: starts with '.'
    if message_text.startswith('.'):
        vehicle_number = message_text[1:].strip().upper()
        if vehicle_number:
            if chat_type != 'private' or state == 'waiting_vehicle_number':
                if state == 'waiting_vehicle_number':
                    clear_user_state(user_id)
                await handle_vehicle_number(update, context, vehicle_number)
                return

    # Email format basic
    if '@' in message_text and '.' in message_text:
        email = message_text.lower().strip()
        if email.count('@') == 1 and len(email.split('@')[0]) > 0 and len(email.split('@')[1]) > 2:
            if chat_type != 'private' or state == 'waiting_gmail':
                if state == 'waiting_gmail':
                    clear_user_state(user_id)
                await handle_gmail_lookup(update, context, email)
                return

    # Phone number 10 digit
    if message_text.isdigit() and len(message_text) == 10:
        if chat_type != 'private' or state == 'waiting_phone_number':
            if state == 'waiting_phone_number':
                clear_user_state(user_id)
            await handle_phone_number(update, context)
            return

    # state-based (admin + redeem + etc.)
    if state:
        if state == "waiting_redeem_code":
            await handle_redeem_code_input(update, context, message_text)
        elif state == "waiting_gmail":
            await handle_gmail_input(update, context, message_text)
        elif state == "admin_gen_code":
            await handle_admin_gen_code_input(update, context, message_text)
        elif state == "admin_broadcast":
            await handle_admin_broadcast_input(update, context, message_text)
        elif state == "waiting_setting_value":
            await handle_setting_value_input(update, context, message_text, state_data['data'])
        elif state == "waiting_group_id":
            await handle_add_group_input(update, context, message_text)
        elif state == "waiting_channel_username":
            await handle_add_channel_input(update, context, message_text)
        elif state == "waiting_ban_user_id":
            await handle_ban_user_input(update, context, message_text)
        elif state == "waiting_unban_user_id":
            await handle_unban_user_input(update, context, message_text)
        elif state == "waiting_admin_id":
            await handle_admin_id_input(update, context, message_text)
        elif state == "waiting_broadcast_confirm":
            # user typed instead of clicking confirm button -> ignore here
            await update.message.reply_text(
                "Please confirm using the buttons.",
                parse_mode='Markdown'
            )

# =========================================================
# Callback dispatcher
# =========================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data == "verify_membership":
        await verify_membership_callback(update, context)
    elif data == "main_menu":
        await show_main_menu(update, context)
    elif data == "start_lookup":
        await start_lookup_callback(update, context)
    elif data == "lookup_phone":
        await lookup_phone_callback(update, context)
    elif data == "lookup_vehicle":
        await lookup_vehicle_callback(update, context)
    elif data == "lookup_gmail":
        await lookup_gmail_callback(update, context)
    elif data == "my_credits":
        await show_credits_callback(update, context)
    elif data == "redeem_code":
        await redeem_code_callback(update, context)
    elif data == "refer_friends":
        await refer_friends_callback(update, context)
    elif data == "my_stats":
        await my_stats_callback(update, context)
    elif data == "how_it_works":
        await how_it_works_callback(update, context)
    elif data == "admin_panel":
        await admin_panel_callback(update, context)
    elif data == "admin_settings":
        await admin_settings_callback(update, context)
    elif data == "management_panel":
        await management_panel_callback(update, context)
    elif data == "manage_groups":
        await admin_groups_callback(update, context)
    elif data == "add_admin":
        await add_admin_callback(update, context)
    elif data == "toggle_group_searches":
        await toggle_group_searches_callback(update, context)
    elif data == "required_join":
        await required_join_callback(update, context)
    elif data == "admin_gen_code":
        await admin_gen_code_callback(update, context)
    elif data == "admin_stats":
        await admin_stats_callback(update, context)
    elif data == "admin_broadcast":
        await admin_broadcast_callback(update, context)
    elif data == "broadcast_confirm_send":
        await broadcast_confirm_send_callback(update, context)
    elif data == "admin_top_referrers":
        await admin_top_referrers_callback(update, context)
    elif data == "admin_ban_user":
        await admin_ban_user_callback(update, context)
    elif data == "admin_logs":
        await admin_logs_callback(update, context)
    elif data.startswith("remove_group_"):
        group_id = int(data.split('_')[2])
        await remove_group_callback(update, context, group_id)
    elif data == "add_group":
        await add_group_callback(update, context)
    elif data.startswith("remove_channel_"):
        channel_username = data.split('_')[2]
        await remove_channel_callback(update, context, channel_username)
    elif data == "add_channel":
        await add_channel_callback(update, context)
    elif data == "ban_user":
        await ban_user_callback(update, context)
    elif data == "unban_user":
        await unban_user_callback(update, context)
    elif data == "close_menu":
        await query.delete_message()
    elif data.startswith("edit_") or data.startswith("toggle_"):
        await handle_settings_callback(update, context)

# =========================================================
# main()
# =========================================================

def main():
    # start Flask panel in background
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()

    # sanity check: token
    if not Config.BOT_TOKEN or Config.BOT_TOKEN.strip() == "":
        raise RuntimeError("❌ BOT_TOKEN missing. Put it in data.txt under BOT_TOKEN.")

    # build telegram app
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))

    # callback query handler (inline buttons)
    application.add_handler(CallbackQueryHandler(callback_handler))

    # any text (numbers, vehicle, emails, state inputs)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    logger.info("Starting Enhanced OSINT Bot with DM Panel...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# =========================================================
# entrypoint
# =========================================================

if __name__ == '__main__':
    load_settings()  # load token + config from data.txt
    main()
