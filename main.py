# -*- coding: utf-8 -*-
import telebot
from telebot import types  # <--- YE LINE MISSING THI! Ab fix ho gaya hai.
import subprocess
import os
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import sys
from flask import Flask
from threading import Thread

# --- Flask Keep Alive (Render Required) ---
app = Flask('')

@app.route('/')
def home():
    return "✅ Python Host Server is Running. Hosted by @frexxxy"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR) 
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = '8558338090:AAHE76XYiunsFpARXePMuqXceBri-oir8Ro' # Apna Token yahi rakhein
OWNER_ID = 8448533037 # Agar Admin Panel na chale to /myid command use karein aur ise badlein
YOUR_USERNAME = '@frexxxy'

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
DATABASE_PATH = os.path.join(BASE_DIR, 'bot_data.db')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)

# --- Global Variables ---
bot_scripts = {}  
user_files = {}   
active_users = set()
admin_ids = {OWNER_ID}
bot_locked = False
start_time = time.time()

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
    conn.close()

init_db()
load_data()

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
        except: pass

# --- Keyboards ---
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📤 Upload File", "📂 My Files")
    markup.add("🛑 Active Scripts", "📊 Server Stats")
    markup.add("📞 Support")
    if user_id in admin_ids:
        markup.add("👑 Admin Panel")
    return markup

# ==========================================
#          USER COMMANDS & BUTTONS
# ==========================================

@bot.message_handler(commands=['myid'])
def my_id_command(message):
    bot.reply_to(message, f"Aapka Telegram ID hai: <code>{message.from_user.id}</code>\nAgar Admin Panel open nahi ho raha, toh is ID ko code me OWNER_ID me daal do.", parse_mode='HTML')

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    save_user_to_db(user_id)
    text = (f"👋 Welcome to <b>{YOUR_USERNAME} Host Bot</b>!\n\n"
            f"🚀 I can host your <b>Python (.py)</b> files securely.\n"
            f"⚡ Powered by <code>{YOUR_USERNAME}</code>")
    bot.reply_to(message, text, reply_markup=main_menu(user_id), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "📞 Support")
def support(message):
    bot.reply_to(message, f"📞 <b>Contact Owner:</b> {YOUR_USERNAME}", parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "📊 Server Stats")
def statistics(message):
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime = str(timedelta(seconds=int(time.time() - start_time))).split('.')[0]
    
    for k in list(bot_scripts.keys()):
        if bot_scripts[k]['proc'].poll() is not None:
            del bot_scripts[k]
            
    total_scripts = len(bot_scripts)
    
    msg = (f"📊 <b>Server Statistics ({YOUR_USERNAME})</b>\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"💻 CPU Usage: <code>{cpu}%</code>\n"
           f"💾 RAM Usage: <code>{ram}%</code>\n"
           f"👥 Total Users: <code>{len(active_users)}</code>\n"
           f"🟢 Active Scripts: <code>{total_scripts}</code>\n"
           f"⏰ Uptime: <code>{uptime}</code>")
    bot.reply_to(message, msg, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "📤 Upload File")
def upload_file(message):
    if bot_locked and message.from_user.id not in admin_ids:
        bot.reply_to(message, "🔒 Server is currently under maintenance.")
        return
    bot.reply_to(message, "📂 <b>Send me your Python script file.</b>\nSupported: <code>.py</code>", parse_mode='HTML')

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if bot_locked and message.from_user.id not in admin_ids: return
        
    user_id = message.from_user.id
    save_user_to_db(user_id)
    file_name = message.document.file_name
    
    if not file_name.endswith('.py'):
        bot.reply_to(message, f"❌ Invalid format! Only Python <code>.py</code> files are allowed.", parse_mode='HTML')
        return
        
    try:
        msg = bot.reply_to(message, "⏳ Downloading...")
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        folder = get_user_folder(user_id)
        path = os.path.join(folder, file_name)
        with open(path, 'wb') as f:
            f.write(downloaded)
            
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name) VALUES (?, ?)', (user_id, file_name))
        conn.commit()
        conn.close()
        
        if user_id not in user_files: user_files[user_id] = []
        if file_name not in user_files[user_id]: user_files[user_id].append(file_name)
        
        bot.edit_message_text(f"✅ <b>Saved:</b> <code>{file_name}</code>\nGo to '📂 My Files' to run it.", message.chat.id, msg.message_id, parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, f"❌ Error saving file: {e}")

@bot.message_handler(func=lambda m: m.text == "📂 My Files")
def check_files(message):
    try:
        user_id = message.from_user.id
        files = user_files.get(user_id, [])
        
        if not files:
            bot.reply_to(message, "❌ You have no files.")
            return
            
        for fname in files:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("▶ Run", callback_data=f"run_{fname}"),
                       types.InlineKeyboardButton("📝 Logs", callback_data=f"log_{fname}"),
                       types.InlineKeyboardButton("🗑 Delete", callback_data=f"del_{fname}"))
            bot.send_message(message.chat.id, f"📄 <b>File:</b> <code>{fname}</code>", reply_markup=markup, parse_mode='HTML')
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error checking files: {e}")

@bot.message_handler(func=lambda m: m.text == "🛑 Active Scripts")
def active_scripts(message):
    user_id = message.from_user.id
    active_count = 0
    
    for key, info in list(bot_scripts.items()):
        if key.startswith(str(user_id)):
            if info['proc'].poll() is None: 
                active_count += 1
                fname = info['name']
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("⏹ Stop Script", callback_data=f"stop_{fname}"))
                bot.send_message(message.chat.id, f"🟢 <b>Running:</b> <code>{fname}</code>\n⚙️ PID: <code>{info['proc'].pid}</code>", reply_markup=markup, parse_mode='HTML')
            else:
                del bot_scripts[key] 
            
    if active_count == 0:
        bot.reply_to(message, "🚫 No active scripts.")

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
                if bot_scripts[key]['proc'].poll() is None:
                    bot.answer_callback_query(call.id, "⚠️ Already running!", show_alert=True)
                    return
                else:
                    del bot_scripts[key]
                
            log_path = os.path.join(folder, f"{filename}.log")
            log_file = open(log_path, "a")
            
            cmd = [sys.executable, filepath]
            
            proc = subprocess.Popen(cmd, cwd=folder, stdout=log_file, stderr=subprocess.STDOUT)
            bot_scripts[key] = {'proc': proc, 'log': log_path, 'name': filename}
            
            bot.answer_callback_query(call.id, "✅ Started!")
            bot.send_message(call.message.chat.id, f"🚀 <b>Started:</b> <code>{filename}</code>", parse_mode='HTML')

        elif action == "stop":
            if key in bot_scripts and bot_scripts[key]['proc'].poll() is None:
                bot_scripts[key]['proc'].terminate()
                del bot_scripts[key]
                bot.answer_callback_query(call.id, "🛑 Stopped!")
                bot.edit_message_text(f"🛑 <b>Stopped:</b> <code>{filename}</code>", call.message.chat.id, call.message.message_id, parse_mode='HTML')
            else:
                if key in bot_scripts: del bot_scripts[key]
                bot.answer_callback_query(call.id, "⚠️ Not running or already stopped.")

        elif action == "log":
            log_path = os.path.join(folder, f"{filename}.log")
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    lines = f.readlines()
                    last_lines = "".join(lines[-15:]) if lines else "Empty logs."
                bot.send_message(call.message.chat.id, f"📝 <b>Logs (<code>{filename}</code>):</b>\n<pre>{last_lines}</pre>", parse_mode='HTML')
            else:
                bot.answer_callback_query(call.id, "⚠️ No logs found.", show_alert=True)

        elif action == "del":
            if key in bot_scripts and bot_scripts[key]['proc'].poll() is None:
                bot.answer_callback_query(call.id, "⚠️ Stop script first!", show_alert=True)
                return
            if os.path.exists(filepath): os.remove(filepath)
            
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM user_files WHERE user_id=? AND file_name=?", (user_id, filename))
            conn.commit()
            conn.close()
            
            if user_id in user_files and filename in user_files[user_id]:
                user_files[user_id].remove(filename)
                
            bot.answer_callback_query(call.id, "🗑 Deleted!")
            bot.edit_message_text(f"🗑 <code>{filename}</code> deleted.", call.message.chat.id, call.message.message_id, parse_mode='HTML')
            
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Action failed: {e}")

# ==========================================
#          ADMIN ONLY BUTTONS
# ==========================================

@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
def admin_panel(message):
    if message.from_user.id not in admin_ids: 
        bot.reply_to(message, "❌ Aap admin nahi ho. Apna ID check karne ke liye /myid bhejein.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
               types.InlineKeyboardButton("🔒 Lock/Unlock", callback_data="admin_lock"))
    markup.add(types.InlineKeyboardButton("🟢 Active Codes", callback_data="admin_codes"))
    
    bot.reply_to(message, f"👑 <b>Admin Panel ({YOUR_USERNAME})</b>", reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    if call.from_user.id not in admin_ids: return
    action = call.data.split("_")[1]
    
    if action == "lock":
        global bot_locked
        bot_locked = not bot_locked
        status = "LOCKED 🔒" if bot_locked else "UNLOCKED 🔓"
        bot.send_message(call.message.chat.id, f"✅ Server is now <b>{status}</b>.", parse_mode='HTML')
        
    elif action == "codes":
        active_found = False
        msg = "🟢 <b>All Running Scripts:</b>\n"
        for key, info in list(bot_scripts.items()):
            if info['proc'].poll() is None:
                active_found = True
                uid = key.split('_')[0]
                msg += f"👤 User: <code>{uid}</code> | 📄 File: <code>{info['name']}</code>\n"
            else:
                del bot_scripts[key]
                
        if not active_found:
            msg = "🚫 No active codes running right now."
        bot.send_message(call.message.chat.id, msg, parse_mode='HTML')

    elif action == "broadcast":
        msg = bot.send_message(call.message.chat.id, "📝 <b>Send message to broadcast:</b>", parse_mode='HTML')
        bot.register_next_step_handler(msg, perform_broadcast)

def perform_broadcast(message):
    if message.content_type != 'text': return
    count = 0
    sent_msg = bot.reply_to(message, "📢 Broadcasting...")
    for uid in active_users:
        try:
            bot.send_message(uid, f"📢 <b>Update from {YOUR_USERNAME}:</b>\n\n{message.text}", parse_mode='HTML')
            count += 1
            time.sleep(0.05)
        except: pass
    bot.edit_message_text(f"✅ Sent to {count} users.", sent_msg.chat.id, sent_msg.message_id)

if __name__ == "__main__":
    keep_alive()
    print(f"✅ {YOUR_USERNAME} Pure Python Bot is Ready!")
    bot.infinity_polling(skip_pending=True)
