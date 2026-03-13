# -*- coding: utf-8 -*-
import telebot
import subprocess
import os
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import logging
import threading
import sys

# --- Flask Keep Alive (Render ke liye) ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "I am Alive! @frexxxy Host Bot is Running."

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = '8558338090:AAH2RDOUHj4BJBOcPXl17CYNvdFs_X0ojuY'
OWNER_ID = 8448533037
ADMIN_ID = 8448533037
YOUR_USERNAME = '@frexxxy'

# Directories
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
DATABASE_PATH = os.path.join(BASE_DIR, 'bot_data.db')

# Limits & Allowed Files
ALLOWED_EXTENSIONS = ['.py', '.java', '.jar']

# Ensure Directories Exist
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)

# Initialize Bot
bot = telebot.TeleBot(TOKEN)

# --- Global Variables ---
bot_scripts = {}  # { "user_id_filename": {'proc': subprocess, 'log': filepath} }
user_files = {}   
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
start_time = time.time()

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database Management ---
def init_db():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_files (user_id INTEGER, file_name TEXT, PRIMARY KEY (user_id, file_name))''')
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    c.execute('SELECT user_id, file_name FROM user_files')
    for uid, fname in c.fetchall():
        if uid not in user_files: user_files[uid] = []
        user_files[uid].append(fname)
        
    c.execute('SELECT user_id FROM active_users')
    for row in c.fetchall():
        active_users.add(row[0])
    
    logger.info(f"Loaded {len(active_users)} users from database.")
    conn.close()

init_db()
load_data()

# --- Helper Functions ---
def get_user_folder(user_id):
    path = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path

def save_user_to_db(user_id):
    if user_id not in active_users:
        active_users.add(user_id)
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB Error: {e}")

# --- Keyboards ---
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("📤 Upload File")
    btn2 = types.KeyboardButton("📂 My Files")
    btn3 = types.KeyboardButton("🛑 Active Scripts")
    btn4 = types.KeyboardButton("📊 Server Stats")
    btn5 = types.KeyboardButton("📞 Support")
    
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    markup.add(btn5)
    
    if user_id in admin_ids:
        markup.add(types.KeyboardButton("👑 Admin Panel"))
        
    return markup

# ==========================================
#          USER COMMANDS & BUTTONS
# ==========================================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    save_user_to_db(user_id)
    text = (f"👋 Welcome to **{YOUR_USERNAME} Host Bot**!\n\n"
            f"🚀 I can host your **Python (.py)** and **Java (.java / .jar)** files 24/7 on high-speed servers.\n\n"
            f"Select an option below to get started.")
    bot.reply_to(message, text, reply_markup=main_menu(user_id), parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📞 Support")
def support(message):
    bot.reply_to(message, f"📞 **Contact Owner:** {YOUR_USERNAME}\nDM for support, queries, or premium hosting.", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📊 Server Stats")
def statistics(message):
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime = str(timedelta(seconds=int(time.time() - start_time))).split('.')[0]
    total_scripts = len(bot_scripts)
    
    msg = (f"📊 **Bot & Server Statistics**\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"💻 **CPU Usage:** {cpu}%\n"
           f"💾 **RAM Usage:** {ram}%\n"
           f"👥 **Total Users:** {len(active_users)}\n"
           f"🟢 **Running Scripts:** {total_scripts}\n"
           f"⏰ **Uptime:** {uptime}\n"
           f"⚡ **Hosted By:** {YOUR_USERNAME}")
    bot.reply_to(message, msg, parse_mode='Markdown')

# --- FILE UPLOAD ---
@bot.message_handler(func=lambda m: m.text == "📤 Upload File")
def upload_file(message):
    if bot_locked and message.from_user.id not in admin_ids:
        bot.reply_to(message, "🔒 Bot is currently locked by Admin for maintenance.")
        return
    bot.reply_to(message, "📂 **Send me your script file.**\nSupported formats: `.py`, `.java`, `.jar`", parse_mode='Markdown')

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if bot_locked and message.from_user.id not in admin_ids:
        return
        
    user_id = message.from_user.id
    save_user_to_db(user_id)
    file_name = message.document.file_name
    
    if not any(file_name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        bot.reply_to(message, f"❌ Invalid format! Only {', '.join(ALLOWED_EXTENSIONS)} are allowed.")
        return
        
    try:
        msg = bot.reply_to(message, "⏳ Downloading file...")
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        folder = get_user_folder(user_id)
        path = os.path.join(folder, file_name)
        with open(path, 'wb') as f:
            f.write(downloaded)
            
        # Update DB & Memory
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name) VALUES (?, ?)', (user_id, file_name))
        conn.commit()
        conn.close()
        
        if user_id not in user_files: user_files[user_id] = []
        if file_name not in user_files[user_id]: user_files[user_id].append(file_name)
        
        bot.edit_message_text(f"✅ **File Saved Successfully:** `{file_name}`\nGo to '📂 My Files' to run it.", message.chat.id, msg.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# --- FILE MANAGER ---
@bot.message_handler(func=lambda m: m.text == "📂 My Files")
def check_files(message):
    user_id = message.from_user.id
    files = user_files.get(user_id, [])
    
    if not files:
        bot.reply_to(message, "❌ You haven't uploaded any files yet.")
        return
        
    for fname in files:
        markup = types.InlineKeyboardMarkup()
        btn_run = types.InlineKeyboardButton("▶ Run", callback_data=f"run_{fname}")
        btn_log = types.InlineKeyboardButton("📝 Logs", callback_data=f"log_{fname}")
        btn_del = types.InlineKeyboardButton("🗑 Delete", callback_data=f"del_{fname}")
        markup.add(btn_run, btn_log, btn_del)
        
        bot.send_message(message.chat.id, f"📄 **File:** `{fname}`", reply_markup=markup, parse_mode='Markdown')

# --- ACTIVE SCRIPTS (STOP SYSTEM) ---
@bot.message_handler(func=lambda m: m.text == "🛑 Active Scripts")
def active_scripts(message):
    user_id = message.from_user.id
    active_count = 0
    
    for key, info in list(bot_scripts.items()):
        if key.startswith(str(user_id)):
            active_count += 1
            fname = info['name']
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⏹ Stop Script", callback_data=f"stop_{fname}"))
            bot.send_message(message.chat.id, f"🟢 **Running:** `{fname}`\n⚙️ PID: `{info['proc'].pid}`", reply_markup=markup, parse_mode='Markdown')
            
    if active_count == 0:
        bot.reply_to(message, "🚫 You have no running scripts.")

# --- CALLBACK HANDLERS (RUN, LOG, DEL, STOP) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    folder = get_user_folder(user_id)
    
    try:
        action, filename = data.split("_", 1)
        filepath = os.path.join(folder, filename)
        key = f"{user_id}_{filename}"
        
        if action == "run":
            if key in bot_scripts:
                bot.answer_callback_query(call.id, "⚠️ Already running! Stop it first.", show_alert=True)
                return
                
            log_path = os.path.join(folder, f"{filename}.log")
            log_file = open(log_path, "a")
            
            # Identify Command based on extension
            if filename.endswith('.py'):
                cmd = ["python3", filepath]
            elif filename.endswith('.jar'):
                cmd = ["java", "-jar", filepath]
            elif filename.endswith('.java'):
                cmd = ["java", filepath] # Works for Java 11+
            
            proc = subprocess.Popen(cmd, cwd=folder, stdout=log_file, stderr=subprocess.STDOUT)
            bot_scripts[key] = {'proc': proc, 'log': log_path, 'name': filename}
            
            bot.answer_callback_query(call.id, "✅ Script Started!")
            bot.send_message(call.message.chat.id, f"🚀 **Started:** `{filename}`\nUse '🛑 Active Scripts' to stop it.", parse_mode='Markdown')

        elif action == "stop":
            if key in bot_scripts:
                bot_scripts[key]['proc'].terminate()
                del bot_scripts[key]
                bot.answer_callback_query(call.id, "🛑 Script Stopped!")
                bot.edit_message_text(f"🛑 **Stopped:** `{filename}`", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
            else:
                bot.answer_callback_query(call.id, "⚠️ Script is not running.")

        elif action == "log":
            log_path = os.path.join(folder, f"{filename}.log")
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    lines = f.readlines()
                    last_lines = "".join(lines[-15:]) if lines else "Logs are empty."
                bot.send_message(call.message.chat.id, f"📝 **Logs for `{filename}`:**\n```\n{last_lines}\n```", parse_mode='Markdown')
            else:
                bot.answer_callback_query(call.id, "⚠️ No logs found.", show_alert=True)

        elif action == "del":
            if key in bot_scripts:
                bot.answer_callback_query(call.id, "⚠️ Stop the script before deleting!", show_alert=True)
                return
            if os.path.exists(filepath): os.remove(filepath)
            log_path = os.path.join(folder, f"{filename}.log")
            if os.path.exists(log_path): os.remove(log_path)
            
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM user_files WHERE user_id=? AND file_name=?", (user_id, filename))
            conn.commit()
            conn.close()
            
            user_files[user_id] = [f for f in user_files.get(user_id, []) if f != filename]
            bot.answer_callback_query(call.id, "🗑 Deleted!")
            bot.edit_message_text(f"🗑 `{filename}` has been deleted.", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
            
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {e}")

# ==========================================
#          ADMIN ONLY BUTTONS
# ==========================================

@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
def admin_panel(message):
    if message.from_user.id not in admin_ids: return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
    btn2 = types.InlineKeyboardButton("💻 Send Command", callback_data="admin_shell")
    btn3 = types.InlineKeyboardButton("🔒 Lock/Unlock Bot", callback_data="admin_lock")
    btn4 = types.InlineKeyboardButton("🟢 All Running Codes", callback_data="admin_codes")
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.reply_to(message, f"👑 **Admin Panel ({YOUR_USERNAME})**\nChoose an action:", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    if call.from_user.id not in admin_ids: return
    action = call.data.split("_")[1]
    
    if action == "lock":
        global bot_locked
        bot_locked = not bot_locked
        status = "LOCKED 🔒" if bot_locked else "UNLOCKED 🔓"
        bot.answer_callback_query(call.id, f"Bot is now {status}")
        bot.send_message(call.message.chat.id, f"✅ Bot is now **{status}**.", parse_mode='Markdown')
        
    elif action == "codes":
        if not bot_scripts:
            bot.send_message(call.message.chat.id, "🚫 No scripts are currently running.")
            return
        msg = "🟢 **All Running Scripts:**\n"
        for key, info in bot_scripts.items():
            uid = key.split('_')[0]
            msg += f"👤 User: `{uid}` | 📄 File: `{info['name']}` | PID: `{info['proc'].pid}`\n"
        bot.send_message(call.message.chat.id, msg, parse_mode='Markdown')

    elif action == "broadcast":
        msg = bot.send_message(call.message.chat.id, "📝 **Send the message to broadcast:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, perform_broadcast)
        
    elif action == "shell":
        msg = bot.send_message(call.message.chat.id, "💻 **Enter Terminal Command:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, execute_shell)

def perform_broadcast(message):
    if message.content_type != 'text':
        bot.reply_to(message, "❌ Broadcast cancelled. Text only allowed.")
        return
    count = 0
    total = len(active_users)
    sent_msg = bot.reply_to(message, f"📢 Starting broadcast to {total} users...")
    for uid in active_users:
        try:
            bot.send_message(uid, f"📢 **Announcement from {YOUR_USERNAME}:**\n\n{message.text}", parse_mode='Markdown')
            count += 1
            time.sleep(0.05)
        except: pass
    bot.edit_message_text(f"✅ Broadcast complete.\nSent to {count}/{total} users.", sent_msg.chat.id, sent_msg.message_id)

def execute_shell(message):
    if message.from_user.id not in admin_ids: return
    try:
        result = subprocess.check_output(message.text, shell=True, stderr=subprocess.STDOUT)
        output = result.decode('utf-8')
        if len(output) > 4000:
            with open("output.txt", "w") as f: f.write(output)
            with open("output.txt", "rb") as f: bot.send_document(message.chat.id, f)
        else:
            bot.reply_to(message, f"```\n{output}\n```", parse_mode='Markdown')
    except subprocess.CalledProcessError as e:
        bot.reply_to(message, f"❌ Error:\n{e.output.decode()}", parse_mode='Markdown')

# --- Start the Bot ---
if __name__ == "__main__":
    keep_alive()
    logger.info("Bot Started...")
    print(f"✅ {YOUR_USERNAME} Bot is Ready for Render!")
    bot.infinity_polling(skip_pending=True)