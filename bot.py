#!/usr/bin/env python3

import sys
import subprocess

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

# Install dependencies
install_and_import('requests')
install_and_import('pytz')
install_and_import('python-telegram-bot', 'telegram')
install_and_import('Flask', 'flask')
# Telegram OSINT Bot - Phone Number Lookup with DM Panel and Referral System
# Enhanced version with features from 555.py and ym2.py.txt
# Version: 3.0

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

# --- Path Configuration ---
# Get the absolute path of the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'phone_lookup_bot.db')
# --- End Path Configuration ---

# Configuration
class Config:
    BOT_TOKEN = "" # Loaded from data.txt
    API_URL = "" # Loaded from data.txt
    VEHICLE_API_URL = "" # Loaded from data.txt
    GMAIL_API_URL = "" # Loaded from data.txt
    ADMIN_PASSWORD = '' # Loaded from data.txt
    ADMIN_IDS = [] # Loaded from data.txt
    LOG_CHANNEL_ID = None # Loaded from data.txt
    REQUIRED_CHANNELS = [] # Loaded from data.txt
    ALLOWED_GROUPS = [] # Loaded from data.txt
    CHANNEL_LINKS = [] # Loaded from data.txt
    
    # Default Limits
    DAILY_FREE_SEARCHES = 0 # Loaded from data.txt
    PRIVATE_SEARCH_COST = 0.0 # Loaded from data.txt
    REFERRAL_BONUS = 0.0 # Loaded from data.txt
    JOINING_BONUS = 0.0 # Loaded from data.txt
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')  # GMT+5:30
    
    # Runtime settings
    BOT_LOCKED = False # Loaded from data.txt
    MAINTENANCE_MODE = False # Loaded from data.txt
    GROUP_SEARCHES_OFF = False # Loaded from data.txt
    BOT_ACTIVE = True # Loaded from data.txt

SETTINGS_FILE = os.path.join(SCRIPT_DIR, 'data.txt')

def load_settings():
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            Config.BOT_TOKEN = settings.get('BOT_TOKEN', "8369296757:AAEU39Rvhw6sZiHrJpayZUJVD4a0WXNfHvg") # Default if not in file
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
        save_settings() # Create default data.txt
    except json.JSONDecodeError:
        logger.error("Error decoding data.txt. Overwriting with default settings.")
        save_settings() # Overwrite corrupted data.txt

def save_settings():
    settings = {
        'BOT_TOKEN': Config.BOT_TOKEN,
        'API_URL': Config.API_URL,
        'VEHICLE_API_URL': Config.VEHICLE_API_URL,
        'GMAIL_API_URL': Config.GMAIL_API_URL,
        'ADMIN_PASSWORD': Config.ADMIN_PASSWORD,
        'ADMIN_IDS': list(Config.ADMIN_IDS), # Convert set to list for JSON
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

# Daily usage tracking for groups is now handled in the database.

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
db_lock = threading.Lock()
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Flask app setup
app = Flask(__name__)

# HTML template for the control panel
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
    """A simple endpoint to keep the bot alive on free hosting plans."""
    return "hi"

def run_flask_app():
    app.run(host='0.0.0.0', port=5000)

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
        
        # Load settings from database (from ym2.py.txt)
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
        
        # Load allowed groups (from ym2.py.txt)
        cursor.execute('SELECT group_id FROM allowed_groups')
        db_allowed_groups = [row['group_id'] for row in cursor.fetchall()]
        if db_allowed_groups: # Only update if there are entries in DB
            Config.ALLOWED_GROUPS = db_allowed_groups
        
        # Load required channels (from ym2.py.txt)
        cursor.execute('SELECT channel_username FROM required_channels')
        db_required_channels = [row['channel_username'] for row in cursor.fetchall()]
        if db_required_channels: # Only update if there are entries in DB
            Config.REQUIRED_CHANNELS = db_required_channels
        
        # Load admin IDs (from ym2.py.txt)
        cursor.execute('SELECT user_id FROM users WHERE is_admin = 1')
        db_admin_ids = [row['user_id'] for row in cursor.fetchall()]
        if db_admin_ids: # Only update if there are entries in DB
            Config.ADMIN_IDS = db_admin_ids

init_database()

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
            now = datetime.now(Config.TIMEZONE).isoformat() # Use Config.TIMEZONE
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, referral_code, joined_date, last_reset, credits)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, referral_code, now, now, Config.JOINING_BONUS))
            conn.commit()
            
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
        else:
            # Update username and first_name if provided
            if username or first_name:
                cursor.execute('UPDATE users SET username = ?, first_name = ? WHERE user_id = ?',
                              (username or user['username'], first_name or user['first_name'], user_id))
                conn.commit()
        
        return dict(user)

def check_daily_reset(user_id: int) -> bool:
    """Check and reset daily limits"""
    with db_lock:
        cursor.execute('SELECT last_reset FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        if row:
            last_reset = datetime.fromisoformat(row['last_reset']) if row['last_reset'] else None
            now = datetime.now(Config.TIMEZONE) # Use Config.TIMEZONE
            
            if not last_reset or now.date() > last_reset.date():
                cursor.execute('UPDATE users SET daily_searches = 0, last_reset = ? WHERE user_id = ?',
                              (now.isoformat(), user_id))
                conn.commit()
                return True
    return False

def set_user_state(user_id: int, state: str, data: str = None):
    """Set user state for conversation"""
    with db_lock:
        cursor.execute('INSERT OR REPLACE INTO user_states (user_id, state, data) VALUES (?, ?, ?)',
                      (user_id, state, data))
        conn.commit()

def get_user_state(user_id: int):
    """Get user state"""
    with db_lock:
        cursor.execute('SELECT state, data FROM user_states WHERE user_id = ?', (user_id,))
        return cursor.fetchone()

def clear_user_state(user_id: int):
    """Clear user state"""
    with db_lock:
        cursor.execute('DELETE FROM user_states WHERE user_id = ?', (user_id,))
        conn.commit()

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


async def check_channel_membership(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if user is member of all required channels (from car.py.txt)"""
    for channel in Config.REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            print(f"DEBUG: User {user_id} status in channel {channel}: {member.status}") # Added debug print
            if member.status in ['left', 'kicked']:
                logger.warning(f"User {user_id} is not in channel {channel}. Status: {member.status}")
                return False
            logger.info(f"User {user_id} successfully verified in channel {channel}.")
        except Exception as e:
            logger.error(f"Error checking membership for user {user_id} in channel {channel}: {e}")
            print(f"DEBUG: Exception checking membership for user {user_id} in channel {channel}: {e}") # Added debug print
            return False
    return True

def create_join_keyboard():
    """Create keyboard with channel join buttons (from car.py.txt)"""
    keyboard = []
    for i, link in enumerate(Config.CHANNEL_LINKS):
        keyboard.append([InlineKeyboardButton(f"Join Channel {i+1}", url=link)])
    
    keyboard.append([InlineKeyboardButton("✅ Verify Membership", callback_data="verify_membership")])
    return InlineKeyboardMarkup(keyboard)

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard (from ym2.py.txt) - adapted for python-telegram-bot"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Lookup", callback_data="start_lookup"),
         InlineKeyboardButton("💳 My Credits", callback_data="my_credits")],
        [InlineKeyboardButton("🔑 Redeem Code", callback_data="redeem_code"),
         InlineKeyboardButton("🔗 Invite Friends", callback_data="refer_friends")],
        [InlineKeyboardButton("💡 How It Works", callback_data="how_it_works"),
         InlineKeyboardButton("📈 My Usage", callback_data="my_stats")],
        [InlineKeyboardButton("📞 Contact Owner", url="https://t.me/HIDANCODE")]
    ])
    return keyboard

def lookup_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing lookup type."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Number Lookup", callback_data="lookup_phone"),
         InlineKeyboardButton("🚗 Vehicle Lookup", callback_data="lookup_vehicle")],
        [InlineKeyboardButton("📧 Gmail Lookup", callback_data="lookup_gmail")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ])
    return keyboard

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Admin panel keyboard (from ym2.py.txt) - adapted for python-telegram-bot"""
    keyboard = InlineKeyboardMarkup([
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
    return keyboard

def settings_keyboard() -> InlineKeyboardMarkup:
    """Settings keyboard (from ym2.py.txt) - adapted for python-telegram-bot"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📱 Daily Free Searches: {Config.DAILY_FREE_SEARCHES}", callback_data="edit_daily_free_searches")],
        [InlineKeyboardButton(f"💰 Private Search Cost: {Config.PRIVATE_SEARCH_COST}", callback_data="edit_private_search_cost")],
        [InlineKeyboardButton(f"🤝 Referral Bonus: {Config.REFERRAL_BONUS}", callback_data="edit_referral_bonus")],
        [InlineKeyboardButton(f"📝 Log Channel ID: {Config.LOG_CHANNEL_ID or 'Not Set'}", callback_data="edit_log_channel_id")],
        [InlineKeyboardButton(f"🔒 Bot Locked: {'Yes' if Config.BOT_LOCKED else 'No'}", callback_data="toggle_bot_locked")],
        [InlineKeyboardButton(f"🛠️ Maintenance Mode: {'Yes' if Config.MAINTENANCE_MODE else 'No'}", callback_data="toggle_maintenance_mode")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ])
    return keyboard

def manage_groups_keyboard() -> InlineKeyboardMarkup:
    """Manage groups keyboard (from ym2.py.txt) - adapted for python-telegram-bot"""
    keyboard_list = []
    for group_id in Config.ALLOWED_GROUPS:
        with db_lock:
            cursor.execute("SELECT group_name FROM allowed_groups WHERE group_id = ?", (group_id,))
            group_name = cursor.fetchone()
            group_name = group_name["group_name"] if group_name else f"Group {group_id}"
        keyboard_list.append([InlineKeyboardButton(f"❌ {group_name}", callback_data=f"remove_group_{group_id}")])
    keyboard_list.append([InlineKeyboardButton("➕ Add New Group", callback_data="add_group")])
    keyboard_list.append([InlineKeyboardButton("🔙 Back to Management", callback_data="management_panel")])
    keyboard = InlineKeyboardMarkup(keyboard_list)
    return keyboard

def manage_channels_keyboard() -> InlineKeyboardMarkup:
    """Manage channels keyboard (from ym2.py.txt) - adapted for python-telegram-bot"""
    keyboard_list = []
    for channel_username in Config.REQUIRED_CHANNELS:
        keyboard_list.append([InlineKeyboardButton(f"❌ {channel_username}", callback_data=f"remove_channel_{channel_username}")])
    keyboard_list.append([InlineKeyboardButton("➕ Add New Channel", callback_data="add_channel")])
    keyboard_list.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
    keyboard = InlineKeyboardMarkup(keyboard_list)
    return keyboard

def ban_unban_keyboard() -> InlineKeyboardMarkup:
    """Ban/Unban user keyboard (from ym2.py.txt) - adapted for python-telegram-bot"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Ban User", callback_data="ban_user"),
         InlineKeyboardButton("✅ Unban User", callback_data="unban_user")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ])
    return keyboard

def check_daily_usage_group(user_id: int) -> bool:
    """Check if user has exceeded daily limit in groups from the database."""
    # The daily reset is handled by check_daily_reset() which is called before this.
    with db_lock:
        cursor.execute('SELECT daily_searches FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        if user:
            return user['daily_searches'] < Config.DAILY_FREE_SEARCHES
    return False # Failsafe



def increment_group_usage_db(user_id: int):
    """Increment user's daily usage count for group searches in database (from 555.py)"""
    with db_lock:
        cursor.execute('UPDATE users SET daily_searches = daily_searches + 1 WHERE user_id = ?', (user_id,))
        conn.commit()

async def fetch_osint_data(phone_number: str) -> dict:
    """Fetch OSINT data from API"""
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
    """Fetch Vehicle data from API"""
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
    """Fetch Gmail data from API"""
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
    """Format OSINT data into the required report format (from car.py.txt, slightly adapted from ym2.py.txt for better formatting)"""
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
    """Format vehicle data into a readable report."""
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
    """Format Gmail data into a readable report."""
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    user_id = user.id
    
    # Check if bot is active
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 The bot is currently inactive. Please try again later.")
        return

    # Check if bot is locked or in maintenance mode (for non-admins)
    if user_id not in Config.ADMIN_IDS:
        if Config.BOT_LOCKED:
            await update.message.reply_text("🔒 The bot is currently locked. Please try again later.")
            return
        if Config.MAINTENANCE_MODE:
            await update.message.reply_text("🛠️ The bot is currently under maintenance. Please try again later.")
            return
    
    # Create or get user data
    user_data = get_or_create_user(user_id, user.username, user.first_name)
    check_daily_reset(user_id)
    
    # Handle referral codes
    if context.args:
        referral_code = context.args[0]
        with db_lock:
            cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (referral_code,))
            referrer = cursor.fetchone()
            
            if referrer and referrer['user_id'] != user_id and not user_data['referred_by']:
                cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (referrer['user_id'], user_id))
                cursor.execute('UPDATE users SET credits = credits + ?, referral_count = referral_count + 1 WHERE user_id = ?', (Config.REFERRAL_BONUS, referrer['user_id']))
                conn.commit()
                try:
                    await context.bot.send_message(referrer['user_id'], f"🎉 You earned {Config.REFERRAL_BONUS} credits from a new referral!")
                except Exception as e:
                    logger.error(f"Failed to notify referrer {referrer['user_id']}: {e}")

    if update.effective_chat.type == 'private':
        # Add channel membership check here
        if not await check_channel_membership(context, user_id):
            keyboard = create_join_keyboard()
            await update.message.reply_text(
                "🔒 **Channel Membership Required**\n\n" \
                "Please join all required channels to use this bot:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            return # Important: stop execution if not a member
        
        await update.message.reply_text(
            f"👋 Hello, {user_data['first_name'] or 'User'}!\n\n" 
            f"Welcome to the OSINT Phone Lookup Bot. Your ultimate tool for phone number intelligence.\n\n" 
            f"✨ Key Features:\n" 
            f"-   ✅ Free Lookups: Get {Config.DAILY_FREE_SEARCHES} complimentary lookups daily in authorized groups.\n" 
            f"-   💳 Private Searches: Each lookup in private chat costs {Config.PRIVATE_SEARCH_COST} credit.\n" 
            f"-   🔗 Earn Credits: Invite friends and earn {Config.REFERRAL_BONUS} credits per successful referral!\n"
            f"-   🎁 Joining Bonus: New users get {Config.JOINING_BONUS} credits for free!\n\n" 
            f"📊 Your Current Stats:\n" 
            f"-   💰 Credits Balance: {user_data['credits']}\n" 
            f"-   🔍 Daily Group Searches Used: {user_data['daily_searches']}/{Config.DAILY_FREE_SEARCHES}\n" 
            f"-   👥 Total Referrals: {user_data['referral_count']}\n\n" 
            f"🚀 Ready to start? Use the buttons below to navigate:",
            reply_markup=main_menu_keyboard(), # Use new main menu keyboard
            parse_mode='Markdown'
        )
    elif update.effective_chat.id in Config.ALLOWED_GROUPS:
        await update.message.reply_text(
            "🤖 **OSINT Phone Lookup Bot**\n\n" \
            "Send a 10-digit phone number, vehicle number (e.g., `.JH01CW0229`), or email address to get a report.\n" \
            f"⏰ Limit: {Config.DAILY_FREE_SEARCHES} searches per day\n" \
            "🔒 Channel membership required\n\n" \
            "Examples: `9876543210`, `.MH01AB1234`, or `example@gmail.com`",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ This bot only works in authorized groups.\n"
            "Contact group admins for access."
        )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command handler"""
    user_id = update.effective_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    if not context.args or context.args[0] != Config.ADMIN_PASSWORD:
        await update.message.reply_text("❌ Invalid password.")
        return
    
    # Add channel membership check here for admins
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\n"
            "As an admin, you also need to be a member of all required channels to access the admin panel.\n"
            "Please join all required channels:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return # Important: stop execution if not a member
    
    with db_lock:
        cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        if user_id not in Config.ADMIN_IDS:
            Config.ADMIN_IDS.append(user_id) # Add to runtime config
    
    await update.message.reply_text(
        "✅ **Admin Access Granted**\n\nWelcome to the admin panel:",
        reply_markup=admin_panel_keyboard(),
        parse_mode='Markdown'
    )



async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number messages"""
    # Check if bot is active
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 The bot is currently inactive. Please try again later.")
        return

    # Check if it's a private chat
    if update.effective_chat.type == 'private':
        await handle_phone_number_in_private(update, context)
        return
    
    # Check if group is allowed
    if update.effective_chat.id not in Config.ALLOWED_GROUPS:
        await update.message.reply_text("❌ Unauthorized group!")
        return
    
    # Check if group searches are turned off
    if Config.GROUP_SEARCHES_OFF:
        await update.message.reply_text(
            f"🔒 Group searches are currently locked. Please use the bot in DM for searches.\n" 
            f"Click here to start a private chat: @{context.bot.username}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Private Chat", url=f"https://t.me/{context.bot.username}")]])
        )
        return
    
    message_text = update.message.text.strip()
    
    # Check if it's a 10-digit phone number
    if not (message_text.isdigit() and len(message_text) == 10):
        return  # Ignore non-phone number messages
    
    user_id = update.effective_user.id

    # Check if bot is locked or in maintenance mode (for non-admins)
    if user_id not in Config.ADMIN_IDS:
        if Config.BOT_LOCKED:
            await update.message.reply_text("🔒 The bot is currently locked. Please try again later.")
            return
        if Config.MAINTENANCE_MODE:
            await update.message.reply_text("🛠️ The bot is currently under maintenance. Please try again later.")
            return
    
    # Create or get user data
    get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)
    check_daily_reset(user_id)
    
    # Check daily usage limit
    if not check_daily_usage_group(user_id):
        remaining_time = datetime.now(Config.TIMEZONE).replace(hour=23, minute=59, second=59) - datetime.now(Config.TIMEZONE)
        await update.message.reply_text(
            f"⚠️ Daily limit exceeded!\n"
            f"🕐 Reset in: {str(remaining_time).split('.')[0]}"
        )
        return
    
    # Check channel membership (KEEP THIS MECHANISM)
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\n"
            "Please join all required channels to use this bot:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return
    
    # Show processing message
    processing_msg = await update.message.reply_text(
        "🔍 **Searching OSINT Data...**\n"
        "📱 Number: `{}`\n"
        "⏳ Please wait...".format(message_text),
        parse_mode='Markdown'
    )
    
    # Fetch OSINT data
    osint_data = await fetch_osint_data(message_text)
    
    if osint_data:
        # Format and send report
        report = format_osint_report(osint_data, message_text)
        
        # Increment usage count
        increment_group_usage_db(user_id)
        
        # Log search
        with db_lock:
            cursor.execute('INSERT INTO search_logs (user_id, phone_number, search_type, timestamp) VALUES (?, ?, ?, ?)',
                          (user_id, message_text, 'group', datetime.now(Config.TIMEZONE).isoformat()))
            conn.commit()
        
        # Delete processing message and send report
        await processing_msg.delete()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Contact Developer", url="https://t.me/HIDANCODE")]])
        await update.message.reply_text(
            f"`{report}`",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        # Send usage info
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
    else:
        await processing_msg.edit_text(
            "❌ **Search Failed**\n"
            "No data found for this number or API error occurred.\n"
            "Please try again later.",
            parse_mode='Markdown'
        )

async def handle_phone_number_in_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number messages in private chats"""
    message_text = update.message.text.strip()
    
    # Check if it's a 10-digit phone number
    if not (message_text.isdigit() and len(message_text) == 10):
        return
    
    user_id = update.effective_user.id
    user_data = get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)
    check_daily_reset(user_id)
    
    # Check channel membership
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\n"
            "Please join all required channels to use this bot:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return
    
    # Check if user has enough credits
    if user_data['credits'] < Config.PRIVATE_SEARCH_COST:
        await update.message.reply_text(
            f"❌ **Insufficient Credits**\n\n"
            f"💰 Required: {Config.PRIVATE_SEARCH_COST} credits\n"
            f"💳 Your balance: {user_data['credits']} credits\n\n"
            f"🎁 Get credits by:\n"
            f"• Inviting friends (referral system)\n"
            f"• Redeeming codes\n"
            f"• Using free searches in groups",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    # Show processing message
    processing_msg = await update.message.reply_text(
        "🔍 **Searching OSINT Data...**\n"
        "📱 Number: `{}`\n"
        "⏳ Please wait...".format(message_text),
        parse_mode='Markdown'
    )
    
    # Fetch OSINT data
    osint_data = await fetch_osint_data(message_text)
    
    if osint_data:
        # Deduct credits
        with db_lock:
            cursor.execute('UPDATE users SET credits = credits - ? WHERE user_id = ?', (Config.PRIVATE_SEARCH_COST, user_id))
            conn.commit()
        
        # Log search
        with db_lock:
            cursor.execute('INSERT INTO search_logs (user_id, phone_number, search_type, timestamp) VALUES (?, ?, ?, ?)',
                          (user_id, message_text, 'private', datetime.now(Config.TIMEZONE).isoformat()))
            conn.commit()
        
        # Format and send report
        report = format_osint_report(osint_data, message_text)
        
        # Delete processing message and send report
        await processing_msg.delete()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
        await update.message.reply_text(
            f"`{report}`",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        # Send updated credit info
        updated_user = get_or_create_user(user_id)
        await update.message.reply_text(
            f"✅ **Search Complete**\n"
            f"💰 Remaining credits: {updated_user['credits']}",
            parse_mode='Markdown'
        )
    else:
        await processing_msg.edit_text(
            "❌ **Search Failed**\n"
            "No data found for this number or API error occurred.\n"
            "Please try again later.",
            parse_mode='Markdown'
        )


async def handle_vehicle_number(update: Update, context: ContextTypes.DEFAULT_TYPE, vehicle_number: str):
    """Handle vehicle number messages"""
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 The bot is currently inactive. Please try again later.")
        return

    user_id = update.effective_user.id
    get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)

    # Membership check
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\nPlease join all required channels to use this bot:",
            reply_markup=keyboard, parse_mode='Markdown'
        )
        return

    # Private chat: check credits
    if update.effective_chat.type == 'private':
        user_data = get_or_create_user(user_id)
        if user_data['credits'] < Config.PRIVATE_SEARCH_COST:
            await update.message.reply_text(
                f"❌ **Insufficient Credits for Vehicle Search**\n\n" 
                f"💰 Required: {Config.PRIVATE_SEARCH_COST} credits",
                parse_mode='Markdown'
            )
            return
    # Group chat: check daily limit
    elif update.effective_chat.id in Config.ALLOWED_GROUPS:
        if Config.GROUP_SEARCHES_OFF:
            await update.message.reply_text(
                f"🔒 Group searches are currently locked. Please use the bot in DM for searches.\n" 
                f"Click here to start a private chat: @{context.bot.username}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Private Chat", url=f"https://t.me/{context.bot.username}")]])
            )
            return

        if not check_daily_usage_group(user_id):
            await update.message.reply_text("⚠️ Daily limit exceeded!")
            return
    else: # Unauthorized group
        await update.message.reply_text("❌ Unauthorized group!")
        return

    processing_msg = await update.message.reply_text(
        f"🔍 **Searching Vehicle Data...**\n"
        f"Vehicle No: `{vehicle_number}`\n"
        f"⏳ Please wait...",
        parse_mode='Markdown'
    )

    vehicle_data = await fetch_vehicle_data(vehicle_number)

    if vehicle_data:
        report = format_vehicle_report(vehicle_data, vehicle_number)
        
        await processing_msg.delete()

        if update.effective_chat.type == 'private':
            with db_lock:
                cursor.execute('UPDATE users SET credits = credits - ? WHERE user_id = ?', (Config.PRIVATE_SEARCH_COST, user_id))
                conn.commit()
            
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
            await update.message.reply_text(f'`{report}`', reply_markup=keyboard, parse_mode='Markdown')

            updated_user = get_or_create_user(user_id)
            await update.message.reply_text(
                f"✅ **Search Complete**\n"
                f"💰 Remaining credits: {updated_user['credits']}",
                parse_mode='Markdown'
            )
        else: # Group
            increment_group_usage_db(user_id)
            
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Contact Developer", url="https://t.me/HIDANCODE")]])
            await update.message.reply_text(f'`{report}`', reply_markup=keyboard, parse_mode='Markdown')

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
    else:
        await processing_msg.edit_text(
            "❌ **Search Failed**\nNo data found for this vehicle number or API error occurred.",
            parse_mode='Markdown'
        )

async def handle_gmail_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    """Handle Gmail lookup messages"""
    if not Config.BOT_ACTIVE:
        await update.message.reply_text("🔒 The bot is currently inactive. Please try again later.")
        return

    user_id = update.effective_user.id
    get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)

    # Membership check
    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\nPlease join all required channels to use this bot:",
            reply_markup=keyboard, parse_mode='Markdown'
        )
        return

    # Private chat: check credits
    if update.effective_chat.type == 'private':
        user_data = get_or_create_user(user_id)
        if user_data['credits'] < Config.PRIVATE_SEARCH_COST:
            await update.message.reply_text(
                f"❌ **Insufficient Credits for Gmail Search**\n\n" 
                f"💰 Required: {Config.PRIVATE_SEARCH_COST} credits",
                parse_mode='Markdown'
            )
            return
    # Group chat: check daily limit
    elif update.effective_chat.id in Config.ALLOWED_GROUPS:
        if Config.GROUP_SEARCHES_OFF:
            await update.message.reply_text(
                f"🔒 Group searches are currently locked. Please use the bot in DM for searches.\n" 
                f"Click here to start a private chat: @{context.bot.username}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Private Chat", url=f"https://t.me/{context.bot.username}")]])
            )
            return

        if not check_daily_usage_group(user_id):
            await update.message.reply_text("⚠️ Daily limit exceeded!")
            return
    else: # Unauthorized group
        await update.message.reply_text("❌ Unauthorized group!")
        return

    processing_msg = await update.message.reply_text(
        f"🔍 **Searching Gmail Data...**\n"
        f"📧 Email: `{email}`\n"
        f"⏳ Please wait...",
        parse_mode='Markdown'
    )

    gmail_data = await fetch_gmail_data(email)

    if gmail_data:
        report = format_gmail_report(gmail_data, email)
        
        await processing_msg.delete()

        # Log the search
        with db_lock:
            cursor.execute('INSERT INTO search_logs (user_id, phone_number, search_type, timestamp) VALUES (?, ?, ?, ?)',
                          (user_id, email, 'gmail', datetime.now(Config.TIMEZONE).isoformat()))
            conn.commit()

        if update.effective_chat.type == 'private':
            with db_lock:
                cursor.execute('UPDATE users SET credits = credits - ?, total_searches = total_searches + 1 WHERE user_id = ?', (Config.PRIVATE_SEARCH_COST, user_id))
                conn.commit()
            
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
            await update.message.reply_text(f'`{report}`', reply_markup=keyboard, parse_mode='Markdown')

            updated_user = get_or_create_user(user_id)
            await update.message.reply_text(
                f"✅ **Search Complete**\n"
                f"💰 Remaining credits: {updated_user['credits']}",
                parse_mode='Markdown'
            )
        else: # Group
            increment_group_usage_db(user_id)
            with db_lock:
                cursor.execute('UPDATE users SET total_searches = total_searches + 1 WHERE user_id = ?', (user_id,))
                conn.commit()
            
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Contact Developer", url="https://t.me/HIDANCODE")]])
            await update.message.reply_text(f'`{report}`', reply_markup=keyboard, parse_mode='Markdown')

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
    else:
        await processing_msg.edit_text(
            "❌ **Search Failed**\nNo data found for this email or API error occurred.",
            parse_mode='Markdown'
        )

async def handle_gmail_input(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    """Handle Gmail input from state"""
    user_id = update.effective_user.id
    clear_user_state(user_id)
    
    # Basic email validation
    if '@' not in email or '.' not in email or email.count('@') != 1:
        await update.message.reply_text(
            "❌ **Invalid Email Format**\n\n"
            "Please enter a valid email address.",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    await handle_gmail_lookup(update, context, email.lower().strip())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
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
    elif data == "how_it_works": # New from ym2.py.txt
        await how_it_works_callback(update, context)
    elif data == "admin_panel": # New from ym2.py.txt
        await admin_panel_callback(update, context)
    elif data == "admin_settings":
        await admin_settings_callback(update, context)
    elif data == "management_panel":
        await management_panel_callback(update, context)
    elif data == "manage_groups":
        await admin_groups_callback(update, context) # Reusing existing function
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
    elif data == "admin_top_referrers": # New from ym2.py.txt
        await admin_top_referrers_callback(update, context)
    elif data == "admin_ban_user": # New from ym2.py.txt
        await admin_ban_user_callback(update, context)
    elif data == "admin_logs": # New from ym2.py.txt
        await admin_logs_callback(update, context)
    elif data.startswith("remove_group_"): # New from ym2.py.txt
        group_id = int(data.split('_')[2])
        await remove_group_callback(update, context, group_id)
    elif data == "add_group": # New from ym2.py.txt
        await add_group_callback(update, context)
    elif data.startswith("remove_channel_"): # New from ym2.py.txt
        channel_username = data.split('_')[2]
        await remove_channel_callback(update, context, channel_username)
    elif data == "add_channel": # New from ym2.py.txt
        await add_channel_callback(update, context)
    elif data == "ban_user": # New from ym2.py.txt
        await ban_user_callback(update, context)
    elif data == "unban_user": # New from ym2.py.txt
        await unban_user_callback(update, context)
    elif data == "close_menu":
        await query.delete_message()
    elif data.startswith("edit_") or data.startswith("toggle_"): # New from ym2.py.txt
        await handle_settings_callback(update, context)

async def verify_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verify membership button callback"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if await check_channel_membership(context, user_id):
        await query.edit_message_text(
            "✅ **Membership Verified!**\n"
            "You can now use all the bot\'s lookup features.",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            "❌ **Verification Failed**\n"
            "Please join all required channels first.",
            reply_markup=create_join_keyboard(),
            parse_mode='Markdown'
        )

@callback_membership_required
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_or_create_user(user_id)

    # This text is now identical to the /start command's message
    message_text = (
        f"👋 Hello, {user_data['first_name'] or 'User'}!\n\n"
        f"Welcome to the OSINT Phone Lookup Bot. Your ultimate tool for phone number intelligence.\n\n"
        f"✨ Key Features:\n"
        f"-   ✅ Free Lookups: Get {Config.DAILY_FREE_SEARCHES} complimentary lookups daily in authorized groups.\n"
        f"-   💳 Private Searches: Each lookup in private chat costs {Config.PRIVATE_SEARCH_COST} credit.\n"
        f"-   🔗 Earn Credits: Invite friends and earn {Config.REFERRAL_BONUS} credits per successful referral!\n"
        f"-   🎁 Joining Bonus: New users get {Config.JOINING_BONUS} credits for free!\n\n"
        f"📊 Your Current Stats:\n"
        f"-   💰 Credits Balance: {user_data['credits']}\n"
        f"-   🔍 Daily Group Searches Used: {user_data['daily_searches']}/{Config.DAILY_FREE_SEARCHES}\n"
        f"-   👥 Total Referrals: {user_data['referral_count']}\n\n"
        f"🚀 Ready to start? Use the buttons below to navigate:"
    )

    await query.edit_message_text(
        text=message_text,
        reply_markup=main_menu_keyboard(),
        parse_mode='Markdown'
    )

@callback_membership_required
async def start_lookup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the lookup type selection menu."""
    query = update.callback_query
    await query.edit_message_text(
        text="<b>Please choose the type of lookup you want to perform:</b>",
        reply_markup=lookup_menu_keyboard(),
        parse_mode='HTML'
    )

@callback_membership_required
async def lookup_phone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Number Lookup' button, prompting for a phone number."""
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
    """Handles the 'Vehicle Lookup' button, prompting for a vehicle number."""
    query = update.callback_query
    user_id = query.from_user.id
    set_user_state(user_id, "waiting_vehicle_number")
    await query.edit_message_text(
        "<b>Enter a vehicle number to search, prefixed with a dot.</b>\n" 
        "Example: <code>.JH01CW0229</code>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]])
    )

@callback_membership_required
async def lookup_gmail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Gmail Lookup' button, prompting for an email."""
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
    """Show user credits"""
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_or_create_user(user_id)
    
    await query.edit_message_text(
        f"💰 **Your Credits**\n\n"
        f"💳 Current Balance: {user_data['credits']} credits\n"
        f"🔄 Daily Searches Used: {user_data['daily_searches']}/{Config.DAILY_FREE_SEARCHES}\n"
        f"📊 Total Searches: {user_data['total_searches']}\n"
        f"🤝 Referrals: {user_data['referral_count']}\n\n"
        f"💡 **How to earn credits:**\n"
        f"• Invite friends: {Config.REFERRAL_BONUS} credits per referral\n"
        f"• Redeem codes from admin\n"
        f"• Use free searches in groups",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

@callback_membership_required
async def redeem_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle redeem code callback"""
    query = update.callback_query
    user_id = query.from_user.id
    
    set_user_state(user_id, "waiting_redeem_code")
    
    await query.edit_message_text(
        "🎁 **Redeem Code**\n\n"
        "📝 Send the redeem code to claim your credits.\n"
        "⏰ You have 60 seconds to enter the code.\n\n"
        "💡 Get codes from admin or special events.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

@callback_membership_required
async def refer_friends_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show referral information"""
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_or_create_user(user_id)
    
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"
    
    await query.edit_message_text(
        f"🤝 **Invite Friends**\n\n"
        f"🎁 Earn {Config.REFERRAL_BONUS} credits for each friend you invite!\n"
        f"👥 Your referrals: {user_data['referral_count']}\n\n"
        f"🔗 **Your referral link:**\n"
        f"`{referral_link}`\n\n"
        f"📋 **Your referral code:**\n"
        f"`{user_data['referral_code']}`\n\n"
        f"💡 Share this link with friends to earn credits!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

@callback_membership_required
async def my_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_or_create_user(user_id)
    
    # Get search logs
    with db_lock:
        cursor.execute('SELECT COUNT(*) as total, search_type FROM search_logs WHERE user_id = ? GROUP BY search_type', (user_id,))
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
    """Show how it works information (from ym2.py.txt)"""
    query = update.callback_query
    await query.edit_message_text(
        "📜 **How It Works**\n\n"
        "This bot allows you to perform OSINT lookups for phone numbers.\n\n"
        "**In Private Chat:**\n"
        f"- Each search costs {Config.PRIVATE_SEARCH_COST} credit.\n"
        f"- Earn credits by inviting friends ({Config.REFERRAL_BONUS} per referral) or redeeming codes.\n\n"
        "**In Authorized Groups:**\n"
        f"- You get {Config.DAILY_FREE_SEARCHES} free searches per day.\n"
        "- Channel membership is required to use the bot in groups.\n\n"        "Send a 10-digit phone number or a vehicle number (e.g., `.JH01CW0229`) to start a search!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel (from ym2.py.txt)"""
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

# Admin callback handlers
def required_join_keyboard() -> InlineKeyboardMarkup:
    keyboard_list = []
    # Display current required channels
    keyboard_list.append([InlineKeyboardButton("Required Channels:", callback_data="dummy")])
    for channel_username in Config.REQUIRED_CHANNELS:
        keyboard_list.append([InlineKeyboardButton(f"❌ {channel_username}", callback_data=f"remove_channel_{channel_username}")])
    keyboard_list.append([InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")])

    # Display current allowed groups
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
        "Manage channels and groups that users must join or are allowed in.",
        reply_markup=required_join_keyboard(),
        parse_mode='Markdown'
    )

def management_options_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Manage Groups", callback_data="manage_groups")],
        [InlineKeyboardButton("➕ Add Admin", callback_data="add_admin")],
        [InlineKeyboardButton(f"🚫 Group Searches: {'OFF' if Config.GROUP_SEARCHES_OFF else 'ON'}", callback_data="toggle_group_searches")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ])
    return keyboard

async def management_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    await query.edit_message_text(
        "⚙️ **Management Panel**\n\n"
        "Select an option to manage bot operations:",
        reply_markup=management_options_keyboard(),
        parse_mode='Markdown'
    )

async def admin_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin settings (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    await query.edit_message_text(
        "⚙️ **Bot Settings**\n\n"
        "Configure various bot parameters here.",
        reply_markup=settings_keyboard(),
        parse_mode='Markdown'
    )


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle settings modifications (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    if data == "toggle_bot_locked":
        Config.BOT_LOCKED = not Config.BOT_LOCKED
        with db_lock:
            cursor.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)', ('bot_locked', str(Config.BOT_LOCKED)))
            conn.commit()
        await query.answer(f"Bot Locked: {'Yes' if Config.BOT_LOCKED else 'No'}")
        await admin_settings_callback(update, context)
    elif data == "toggle_maintenance_mode":
        Config.MAINTENANCE_MODE = not Config.MAINTENANCE_MODE
        with db_lock:
            cursor.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)', ('maintenance_mode', str(Config.MAINTENANCE_MODE)))
            conn.commit()
        await query.answer(f"Maintenance Mode: {'Yes' if Config.MAINTENANCE_MODE else 'No'}")
        await admin_settings_callback(update, context)
    elif data.startswith("edit_"):
        setting_key = data.replace("edit_", "")
        set_user_state(user_id, "waiting_setting_value", setting_key)
        await query.edit_message_text(
            f"📝 **Edit {setting_key.replace('_', ' ').title()}**\n\n"
            f"Please send the new value for {setting_key.replace('_', ' ').title()}:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_settings")]]),
            parse_mode='Markdown'
        )

async def admin_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage allowed groups (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    await query.edit_message_text(
        "👥 **Manage Allowed Groups**\n\n"
        "Add or remove groups that can use the bot.",
        reply_markup=manage_groups_keyboard(),
        parse_mode='Markdown'
    )

async def remove_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, group_id: int):
    """Remove a group (from ym2.py.txt)"""
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
    """Add a new group (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    set_user_state(user_id, "waiting_group_id")
    await query.edit_message_text(
        "➕ **Add New Group**\n\n"
        "Please send the ID of the group to add. You can get the group ID by forwarding a message from the group to @getidsbot.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="required_join")]]),
        parse_mode='Markdown'
    )

async def admin_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage required channels (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    await query.edit_message_text(
        "📢 **Manage Required Channels**\n\n"
        "Add or remove channels that users must join.",
        reply_markup=manage_channels_keyboard(),
        parse_mode='Markdown'
    )

async def remove_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_username: str):
    """Remove a channel (from ym2.py.txt)"""
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
    """Add a new channel (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    set_user_state(user_id, "waiting_channel_username")
    await query.edit_message_text(
        "➕ **Add New Channel**\n\n"
        "Please send the username of the channel (e.g., `@mychannel`).",
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
        "➕ **Add New Admin**\n\n" 
        "Please send the User ID of the user to add as admin.",
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
        cursor.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)', ('group_searches_off', str(Config.GROUP_SEARCHES_OFF)))
        conn.commit()
    
    await query.answer(f"Group Searches: {'OFF' if Config.GROUP_SEARCHES_OFF else 'ON'}")
    await management_panel_callback(update, context) # Redirect back to management panel

async def admin_gen_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate redeem code"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    set_user_state(user_id, "admin_gen_code")
    
    await query.edit_message_text(
        "🎟 **Generate Redeem Code**\n\nSend in format: credits,max_uses\nExample: 10,5 (10 credits, max 5 uses)",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]])
    )

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin statistics"""
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
        f"📈 Bot is running smoothly!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    set_user_state(user_id, "admin_broadcast")
    
    await query.edit_message_text(
        "📢 **Broadcast Message**\n\n"
        "📝 Send the message you want to broadcast to all users.\n"
        "⚠️ This will send the message to ALL registered users.\n\n"
        "⏰ You have 60 seconds to enter the message.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def admin_top_referrers_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top referrers (from ym2.py.txt)"""
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
                # Escape HTML to prevent parsing errors with special characters in usernames
                display_name = username.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
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
    """Ban/Unban user menu (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    await query.edit_message_text(
        "🚫 **Ban/Unban User**\n\n"
        "Select an action:",
        reply_markup=ban_unban_keyboard(),
        parse_mode='Markdown'
    )

async def admin_logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View logs (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return
    
    if not Config.LOG_CHANNEL_ID:
        await query.edit_message_text(
            "❌ **Log Channel Not Set**\n\n"
            "Please set the log channel ID in bot settings first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
            parse_mode='Markdown'
        )
        return
    
    await query.edit_message_text(
        f"📜 **Bot Logs**\n\n"
        f"Logs are sent to the configured log channel: `{Config.LOG_CHANNEL_ID}`.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages based on user state"""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    chat_type = update.effective_chat.type

    state_data = get_user_state(user_id)
    state = state_data['state'] if state_data else None

    # Vehicle Number Logic
    if message_text.startswith('.'):
        vehicle_number = message_text[1:].strip().upper()
        if vehicle_number:
            # In groups, process directly. In DMs, only if requested.
            if chat_type != 'private' or state == 'waiting_vehicle_number':
                if state == 'waiting_vehicle_number': clear_user_state(user_id)
                await handle_vehicle_number(update, context, vehicle_number)
                return
    
    # Gmail Logic
    if '@' in message_text and '.' in message_text:
        # Basic email validation
        email = message_text.lower().strip()
        if email.count('@') == 1 and len(email.split('@')[0]) > 0 and len(email.split('@')[1]) > 2:
            # In groups, process directly. In DMs, only if requested.
            if chat_type != 'private' or state == 'waiting_gmail':
                if state == 'waiting_gmail': clear_user_state(user_id)
                await handle_gmail_lookup(update, context, email)
                return
    
    # Phone Number Logic
    if message_text.isdigit() and len(message_text) == 10:
        # In groups, process directly. In DMs, only if requested.
        if chat_type != 'private' or state == 'waiting_phone_number':
            if state == 'waiting_phone_number': clear_user_state(user_id)
            await handle_phone_number(update, context)
            return

    # State-based handlers for other inputs (redeem code, etc.)
    if state:
        if state == "waiting_redeem_code":
            await handle_redeem_code_input(update, context, message_text)
        elif state == "waiting_gmail":
            await handle_gmail_input(update, context, message_text)
        elif state == "admin_gen_code":
            await handle_admin_gen_code_input(update, context, message_text)
        elif state == "admin_broadcast":
            await handle_admin_broadcast_input(update, context, message_text)
        elif state == "waiting_setting_value": # New from ym2.py.txt
            await handle_setting_value_input(update, context, message_text, state_data['data'])
        elif state == "waiting_group_id": # New from ym2.py.txt
            await handle_add_group_input(update, context, message_text)
        elif state == "waiting_channel_username": # New from ym2.py.txt
            await handle_add_channel_input(update, context, message_text)
        elif state == "waiting_ban_user_id": # New from ym2.py.txt
            await handle_ban_user_input(update, context, message_text)
        elif state == "waiting_unban_user_id": # New from ym2.py.txt
            await handle_unban_user_input(update, context, message_text)
        elif state == "waiting_admin_id":
            await handle_admin_id_input(update, context, message_text)

async def handle_redeem_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    """Handle redeem code input"""
    user_id = update.effective_user.id

    if not await check_channel_membership(context, user_id):
        keyboard = create_join_keyboard()
        await update.message.reply_text(
            "🔒 **Channel Membership Required**\n\n"
            "Please join all required channels to redeem codes.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return

    clear_user_state(user_id)
    
    with db_lock:
        # Check if code exists and is active
        cursor.execute('SELECT * FROM redeem_codes WHERE code = ? AND is_active = 1', (code,))
        redeem_code = cursor.fetchone()
        
        if not redeem_code:
            await update.message.reply_text(
                "❌ **Invalid Code**\n\n"
                "The code you entered is invalid or expired.",
                reply_markup=main_menu_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        # Check if user already redeemed this code
        cursor.execute('SELECT * FROM code_redemptions WHERE code = ? AND user_id = ?', (code, user_id))
        already_redeemed = cursor.fetchone()
        
        if already_redeemed:
            await update.message.reply_text(
                "❌ **Already Redeemed**\n\n"
                "You have already redeemed this code.",
                reply_markup=main_menu_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        # Check if code has reached max uses
        if redeem_code['used_count'] >= redeem_code['max_uses']:
            await update.message.reply_text(
                "❌ **Code Expired**\n\n"
                "This code has reached its maximum usage limit.",
                reply_markup=main_menu_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        # Redeem the code
        cursor.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', (redeem_code['credits'], user_id))
        cursor.execute('UPDATE redeem_codes SET used_count = used_count + 1 WHERE code = ?', (code,))
        cursor.execute('INSERT INTO code_redemptions (code, user_id, redeemed_at) VALUES (?, ?, ?)',
                      (code, user_id, datetime.now(Config.TIMEZONE).isoformat()))
        conn.commit()
    
    await update.message.reply_text(
        f"✅ **Code Redeemed Successfully!**\n\n"
        f"💰 You received {redeem_code['credits']} credits!\n"
        f"🎉 Enjoy your searches!",
        reply_markup=main_menu_keyboard(),
        parse_mode='Markdown'
    )

async def handle_admin_gen_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    """Handle admin generate code input"""
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
            cursor.execute('INSERT INTO redeem_codes (code, credits, max_uses, created_at) VALUES (?, ?, ?, ?)',
                          (code, credits, max_uses, datetime.now(Config.TIMEZONE).isoformat()))
            conn.commit()
        
        await update.message.reply_text(
            f"✅ **Code Generated!**\n\n"
            f"🎟 Code: `{code}`\n"
            f"💰  Credits: `{credits}`\n"
            f"👥  Max Uses: `{max_uses}`",
            parse_mode='Markdown'
        )
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ **Invalid format**\n\n" 
            "Please use the format: `credits,max_uses`\n" 
            "Example: `10,5`",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )

async def handle_admin_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    """Handle admin broadcast input with confirmation"""
    user_id = update.effective_user.id
    
    if user_id not in Config.ADMIN_IDS:
        return

    # Store message and ask for confirmation
    set_user_state(user_id, "waiting_broadcast_confirm", message_text)
    
    # Get target counts
    with db_lock:
        cursor.execute('SELECT COUNT(*) as count FROM users')
        user_count = cursor.fetchone()['count']
    group_count = len(Config.ALLOWED_GROUPS)
    channel_count = len(Config.REQUIRED_CHANNELS)
    target_desc = f"{user_count} users, {group_count} groups, and {channel_count} channels"

    await update.message.reply_text(
        f"✅ **Confirm Broadcast**\n\n"
        f"Your message will be sent to **{target_desc}**.\n\n"
        f"**Message Preview:**\n---\n{message_text}\n---\n\n"
        f"Do you want to proceed?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Send", callback_data="broadcast_confirm_send")],
            [InlineKeyboardButton("❌ No, Cancel", callback_data="admin_panel")]
        ]),
        parse_mode='Markdown'
    )

async def broadcast_confirm_send_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback to confirm and send the broadcast."""
    query = update.callback_query
    user_id = query.from_user.id

    state_data = get_user_state(user_id)
    if not state_data or state_data['state'] != 'waiting_broadcast_confirm':
        await query.edit_message_text("Could not find broadcast message. Please start over.", reply_markup=admin_panel_keyboard())
        return

    message_text = state_data['data']
    clear_user_state(user_id)

    # Get targets
    with db_lock:
        cursor.execute('SELECT user_id FROM users')
        all_users = [row['user_id'] for row in cursor.fetchall()]
    all_groups = Config.ALLOWED_GROUPS
    all_channels = Config.REQUIRED_CHANNELS
    targets = all_users + all_groups + all_channels

    await query.edit_message_text(f"📢 Broadcasting to {len(targets)} targets... Please wait.")

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
    """Handle input for setting values (from ym2.py.txt)"""
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
            cursor.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)', (setting_key, value_text))
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
    """Handle adding a new group (from ym2.py.txt)"""
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return
    
    try:
        group_id = int(group_id_text)
        with db_lock:
            cursor.execute('INSERT INTO allowed_groups (group_id, group_name, added_at) VALUES (?, ?, ?)',
                          (group_id, f"Group {group_id}", datetime.now(Config.TIMEZONE).isoformat()))
            conn.commit()
            if group_id not in Config.ALLOWED_GROUPS:
                Config.ALLOWED_GROUPS.append(group_id)
        
        await update.message.reply_text(
            f"✅ Group `{group_id}` added to allowed groups.",
            reply_markup=required_join_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid group ID. Please enter a valid integer.",
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
    """Handle adding a new channel (from ym2.py.txt)"""
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return
    
    if not channel_username.startswith('@'):
        await update.message.reply_text(
            "❌ Invalid channel username. Please include '@' (e.g., `@mychannel`).",
            reply_markup=required_join_keyboard(),
            parse_mode='Markdown'
        )
        return

    try:
        with db_lock:
            cursor.execute('INSERT INTO required_channels (channel_username, added_at) VALUES (?, ?)',
                          (channel_username, datetime.now(Config.TIMEZONE).isoformat()))
            conn.commit()
            if channel_username not in Config.REQUIRED_CHANNELS:
                Config.REQUIRED_CHANNELS.append(channel_username)
        
        await update.message.reply_text(
            f"✅ Channel `{channel_username}` added to required channels.",
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
    """Prompt for user ID to ban (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "waiting_ban_user_id")
    await query.edit_message_text(
        "🚫 **Ban User**\n\n"
        "Please send the User ID to ban.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def handle_ban_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id_text: str):
    """Handle banning a user (from ym2.py.txt)"""
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
            f"✅ User `{target_user_id}` has been banned.",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID. Please enter a valid integer.",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )

async def unban_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt for user ID to unban (from ym2.py.txt)"""
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in Config.ADMIN_IDS:
        await query.answer("❌ Access denied", show_alert=True)
        return

    set_user_state(user_id, "waiting_unban_user_id")
    await query.edit_message_text(
        "✅ **Unban User**\n\n"
        "Please send the User ID to unban.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def handle_unban_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id_text: str):
    """Handle unbanning a user (from ym2.py.txt)"""
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
            f"✅ User `{target_user_id}` has been unbanned.",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID. Please enter a valid integer.",
            reply_markup=admin_panel_keyboard(),
            parse_mode='Markdown'
        )

async def handle_admin_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id_text: str):
    user_id = update.effective_user.id
    clear_user_state(user_id)

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Access denied.")
        return
    
    # Check for the .userid prefix
    if not target_user_id_text.startswith(".userid"):
        await update.message.reply_text(
            "❌ Invalid format. Please enter the User ID with the `.userid` prefix (e.g., `.userid123456789`).",
            reply_markup=management_options_keyboard(),
            parse_mode='Markdown'
        )
        return

    # Extract the ID after the prefix
    id_string = target_user_id_text[len(".userid"):]

    try:
        target_user_id = int(id_string)
        with db_lock:
            cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (target_user_id,))
            conn.commit()
            if target_user_id not in Config.ADMIN_IDS:
                Config.ADMIN_IDS.append(target_user_id)
        
        await update.message.reply_text(
            f"✅ User `{target_user_id}` has been added as admin.",
            reply_markup=management_options_keyboard(),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID. Please ensure the ID after `.userid` is a valid integer.",
            reply_markup=management_options_keyboard(),
            parse_mode='Markdown'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "🤖 **OSINT Phone Lookup Bot Help**\n\n"
            "🔍 **Private Chat Features:**\n"
            f"• Search using credits ({Config.PRIVATE_SEARCH_COST} credit per search)\n"
            f"• Earn credits through referrals ({Config.REFERRAL_BONUS} per referral)\n"
            f"• Get {Config.JOINING_BONUS} credits joining bonus\n"
            "• Redeem codes for credits\n"
            "• View your statistics\n\n"
            "🏢 **Group Features:**\n"
            f"• {Config.DAILY_FREE_SEARCHES} free searches per day\n"
            "• Channel membership required\n"
            "• Works only in authorized groups\n\n"
            "💡 **How to earn credits:**\n"
            "• Invite friends using your referral link\n"
            "• Redeem codes from admin\n"
            "• Use free searches in groups\n\n"
            "📱 **Usage:**\n"
            "• Send a 10-digit phone number for OSINT lookup\n"
            "• Send a vehicle number (e.g., .JH01CW0229) for vehicle info\n"
            "• Send an email address for breach lookup",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    if update.effective_chat.id not in Config.ALLOWED_GROUPS:
        await update.message.reply_text("❌ Bot only works in authorized groups!")
        return
    
    help_text = f"""🤖 **OSINT Phone Lookup Bot Help**

📱 How to use:
• Send a 10-digit phone number (e.g., 9876543210)
• Send a vehicle number (e.g., .JH01CW0229)
• Send an email address (e.g., example@gmail.com)
• Get detailed reports instantly

⚠️ Restrictions:
• {Config.DAILY_FREE_SEARCHES} searches per user per day
• Works only in authorized groups
• Channel membership required

🔗 Required Channels:
• Join all channels to unlock bot access
• Click verify after joining all

📊 Features:
• Real-time phone number lookup
• Vehicle information lookup
• Email breach lookup
• Formatted reports
• Daily usage tracking
• Security features

⚡ Commands:
/start - Start the bot
/help - Show this help message

🔒 Privacy:
This bot is for educational purposes only."""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    """Main function to run the bot"""
    # Start Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True # Allow main program to exit even if thread is still running
    flask_thread.start()

    # Create application
    application = Application.builder().token(Config.BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Start the bot
    logger.info("Starting Enhanced OSINT Bot with DM Panel...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    load_settings()
    main()

