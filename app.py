import os
import re
import threading
import time
import hmac
import hashlib
import json
import sqlite3
import csv
import io
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, MenuButtonWebApp

# --- Flask Server Setup ---
app = Flask(__name__)

# ለሁሉም ጥያቄዎች CORS እንዲሰራ የሚፈቅድ
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --- SQLite Database Setup ---
def init_db():
    conn = sqlite3.connect('database.sqlite')
    c = conn.cursor()
    # 1. የተጠቃሚዎች ሰንጠረዥ
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id TEXT PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        coins INTEGER DEFAULT 300,
        downloads INTEGER DEFAULT 0,
        ads_watched INTEGER DEFAULT 0,
        questions_answered INTEGER DEFAULT 0,
        app_opened INTEGER DEFAULT 0,
        bot_interactions INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        lang TEXT DEFAULT 'am',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # ነባር ዳታቤዝ ካለ አዲሶቹን አምዶች በራስ-ሰር ይጨምራል
    try:
        c.execute('ALTER TABLE users ADD COLUMN questions_answered INTEGER DEFAULT 0')
    except Exception:
        pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN app_opened INTEGER DEFAULT 0')
    except Exception:
        pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0')
    except Exception:
        pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN bot_interactions INTEGER DEFAULT 0')
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'am'")
    except Exception:
        pass

    # 2. የተከፈቱ ፈተናዎች እና ኖቶች ሰንጠረዥ (Bypass መከላከያ)
    c.execute('''CREATE TABLE IF NOT EXISTS unlocked_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT,
        file_key TEXT,
        unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(telegram_id, file_key)
    )''')
    
    # 3. የአስተያየቶች ሰንጠረዥ (.txt ፋይልን ሙሉ በሙሉ የሚተካ)
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT,
        first_name TEXT,
        username TEXT,
        message TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # 4. የተሰጡ Reactions ሰንጠረዥ
    c.execute('''CREATE TABLE IF NOT EXISTS reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT,
        first_name TEXT,
        username TEXT,
        message_id INTEGER,
        emoji TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()

init_db()

# --- CONFIGURATION (Environment Variables) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID", "7105615214")
WEB_APP_URL = "https://abrhamamsalu248-cpu.github.io/Bahirab-Quiz/"
EXAMS_CHANNEL = "@BahirabAcademy"
MODULES_CHANNEL = "@bahirabquiz"

bot = telebot.TeleBot(BOT_TOKEN)
user_languages = {}

# የተጠቃሚውን ቋንቋ ማግኛ ረዳት ፈንክሽን
def get_user_lang(user_id):
    uid_str = str(user_id)
    if uid_str in user_languages:
        return user_languages[uid_str]
    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT lang FROM users WHERE telegram_id = ?', (uid_str,))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            user_languages[uid_str] = row[0]
            return row[0]
    except Exception:
        pass
    return "am"

# የቴሌግራም initData ትክክለኛነት ማረጋገጫ (Anti-Cheat Verification)
def verify_telegram_data(init_data):
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop('hash', None)
        if not received_hash:
            return None

        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calc_hash == received_hash:
            return json.loads(parsed.get('user', '{}'))
    except Exception as e:
        print(f"Verify error: {e}")
    return None

def track_user_db(user):
    try:
        user_id = str(user.id)
        name = (user.first_name or "Student").replace("|", "-").replace("\n", " ")
        username = f"@{user.username}" if user.username else "No Username"
        
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('''INSERT INTO users (telegram_id, first_name, username, coins, is_blocked)
                     VALUES (?, ?, ?, 300, 0)
                     ON CONFLICT(telegram_id) DO UPDATE SET 
                     first_name=excluded.first_name, 
                     username=excluded.username,
                     is_blocked=0''', (user_id, name, username))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB User Tracking error: {e}")

# የቦት በተን ንክኪዎችን መዝጋቢ
def record_bot_interaction(user_id):
    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('UPDATE users SET bot_interactions = bot_interactions + 1 WHERE telegram_id = ?', (str(user_id),))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Interaction record error: {e}")

@app.route('/')
def home():
    return "Bahirab Quiz Hub Server is Running 24/7!"

# 1. የተጠቃሚውን ነጥብ እና የተከፈቱ ኖቶችን ማመሳሰል (ኖቶች ብቻ ቋሚ ስለሆኑ እነሱን ብቻ ያወጣል)
@app.route('/api/user/sync', methods=['POST'])
def sync_user():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user = verify_telegram_data(data.get('initData'))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = str(user.get('id'))
        first_name = user.get('first_name', 'Student')
        username = f"@{user.get('username')}" if user.get('username') else "No Username"

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT coins, questions_answered FROM users WHERE telegram_id = ?', (user_id,))
        row = c.fetchone()

        if row:
            coins = row[0]
            q_count = row[1] or 0
            c.execute('UPDATE users SET first_name = ?, username = ?, is_blocked = 0, app_opened = app_opened + 1 WHERE telegram_id = ?', (first_name, username, user_id))
        else:
            coins = 300
            q_count = 0
            c.execute('INSERT INTO users (telegram_id, first_name, username, coins, questions_answered, app_opened, is_blocked) VALUES (?, ?, ?, ?, ?, 1, 0)', (user_id, first_name, username, coins, q_count))
            
        c.execute("SELECT file_key FROM unlocked_materials WHERE telegram_id = ? AND file_key LIKE 'note_%'", (user_id,))
        unlocked_items = [r[0] for r in c.fetchall()]

        conn.commit()
        conn.close()
        return jsonify({
            "coins": coins, 
            "questions_answered": q_count,
            "unlocked": unlocked_items
        }), 200
    except Exception as e:
        print(f"Sync error: {e}")
        return jsonify({"error": "Server error"}), 500

# 2. የጥያቄ መልስ ነጥብ መመዝገቢያ (Quiz Answer Reward/Deduct)
@app.route('/api/quiz/submit-answer', methods=['POST'])
def handle_quiz_answer():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user = verify_telegram_data(data.get('initData'))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = str(user.get('id'))
        is_correct = bool(data.get('isCorrect', False))
        coin_change = 5 if is_correct else -5

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT coins, questions_answered FROM users WHERE telegram_id = ?', (user_id,))
        row = c.fetchone()
        
        if not row:
            conn.close()
            return jsonify({"error": "User not found"}), 404

        new_coins = max(0, row[0] + coin_change)
        new_q_count = (row[1] or 0) + 1
        c.execute('UPDATE users SET coins = ?, questions_answered = ? WHERE telegram_id = ?', (new_coins, new_q_count, user_id))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "coins": new_coins, "questions_answered": new_q_count}), 200
    except Exception as e:
        print(f"Quiz submit error: {e}")
        return jsonify({"error": "Server error"}), 500

# 3. የማስታወቂያ ነጥብ መቀበያ (Ads Reward - ሁለቱም Adsgram ስለሆኑ 150 ይሰጣል)
@app.route('/api/ads/reward', methods=['POST'])
def claim_ad_reward():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user = verify_telegram_data(data.get('initData'))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = str(user.get('id'))
        reward = 150

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT coins FROM users WHERE telegram_id = ?', (user_id,))
        row = c.fetchone()
        
        if not row:
            conn.close()
            return jsonify({"error": "User not found"}), 404

        new_coins = row[0] + reward
        c.execute('UPDATE users SET coins = ?, ads_watched = ads_watched + 1 WHERE telegram_id = ?', (new_coins, user_id))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "coins": new_coins}), 200
    except Exception as e:
        print(f"Ad reward error: {e}")
        return jsonify({"error": "Server error"}), 500

# 4. ነጥብ መቀነስ/መጨመር (Legacy Endpoint Support)
@app.route('/api/user/update-coins', methods=['POST'])
def update_user_coins():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user = verify_telegram_data(data.get('initData'))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = str(user.get('id'))
        amount = int(data.get('amount', 0))

        if amount > 150 or amount < -500:
            return jsonify({"error": "Invalid amount"}), 400

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT coins FROM users WHERE telegram_id = ?', (user_id,))
        row = c.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "User not found"}), 404

        new_coins = max(0, row[0] + amount)
        c.execute('UPDATE users SET coins = ? WHERE telegram_id = ?', (new_coins, user_id))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "coins": new_coins}), 200
    except Exception as e:
        print(f"Update coins error: {e}")
        return jsonify({"error": "Server error"}), 500

# 5. ፈተና፣ ሞጁል (100 Coins)፣ Teacher Guide (200 Coins) ወይም Note (500 Coins) መክፈቻ API
@app.route('/api/user/unlock-material', methods=['POST'])
def unlock_material_api():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user = verify_telegram_data(data.get('initData'))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = str(user.get('id'))
        first_name = user.get('first_name', 'Student')
        username = f"@{user.get('username')}" if user.get('username') else "No Username"
        file_key = str(data.get('fileKey', ''))

        is_note = file_key.startswith("note_") or data.get('cost') == 500

        # የዋጋ ስሌት
        if is_note:
            cost = 500
            item_type = "📖 Course Note"
        elif file_key.startswith("guide_"):
            cost = 200
            item_type = "📖 Teacher Guide"
        else:
            cost = 100
            item_type = "📥 Exam / Module"

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()

        # 💡 ኖት ከሆነ ብቻ ቀድሞ የተገዛ መሆኑን ቼክ ያደርጋል (ኖት ብቻ ቋሚ ስለሆነ)
        if is_note:
            c.execute('SELECT 1 FROM unlocked_materials WHERE telegram_id = ? AND file_key = ?', (user_id, file_key))
            if c.fetchone():
                c.execute('SELECT coins FROM users WHERE telegram_id = ?', (user_id,))
                current_coins = c.fetchone()[0]
                conn.close()
                return jsonify({"success": True, "coins": current_coins, "fileKey": file_key}), 200

        # ለፈተናዎች፣ ሞጁሎች እና Teacher Guides ሁልጊዜ ሳንቲም ይቀንሳል
        c.execute('SELECT coins FROM users WHERE telegram_id = ?', (user_id,))
        row = c.fetchone()

        if not row or row[0] < cost:
            conn.close()
            return jsonify({"success": False, "message": f"በቂ Coins የለዎትም! ({cost} Coins ያስፈልጋል)"}), 400

        new_coins = row[0] - cost
        c.execute('UPDATE users SET coins = ? WHERE telegram_id = ?', (new_coins, user_id))
        c.execute('INSERT OR REPLACE INTO unlocked_materials (telegram_id, file_key) VALUES (?, ?)', (user_id, file_key))
        conn.commit()
        conn.close()

        # 🔔 ለአድሚኑ የሚላከውን መልእክት በጀርባ (Background Thread) ማስተላለፍ (ምላሹ እንዳይዘገይ)
        def send_admin_alert():
            try:
                admin_alert = (
                    f"🎉 <b>አዲስ ማቴሪያል ተከፈተ!</b> ({item_type})\n\n"
                    f"👤 <b>ተማሪ፦</b> {first_name} ({username})\n"
                    f"🆔 <b>ID፦</b> <code>{user_id}</code>\n"
                    f"📚 <b>የከፈተው፦</b> <code>{file_key}</code>\n"
                    f"🪙 <b>የተከፈለው፦</b> {cost} Coins\n"
                    f"💰 <b>የቀረው Coins፦</b> {new_coins}"
                )
                bot.send_message(int(ADMIN_ID), admin_alert, parse_mode="HTML")
            except Exception as alert_err:
                print(f"Admin unlock alert error: {alert_err}")

        threading.Thread(target=send_admin_alert).start()

        return jsonify({"success": True, "coins": new_coins, "fileKey": file_key}), 200
    except Exception as e:
        print(f"Unlock error: {e}")
        return jsonify({"error": "Server error"}), 500

# 6. Ad Tracking API
@app.route('/api/track-ad', methods=['POST'])
def track_ad_view():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_id = data.get('user_id')
        if user_id:
            conn = sqlite3.connect('database.sqlite')
            c = conn.cursor()
            c.execute('UPDATE users SET ads_watched = ads_watched + 1 WHERE telegram_id = ?', (str(user_id),))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "user_id": user_id}), 200
    except Exception as e:
        print(f"Track ad error: {e}")
    return jsonify({"status": "error"}), 400

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ቋሚ የ Menu Button ማዘጋጃ
try:
    bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            type="web_app",
            text="📚 Open App",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )
    )
except Exception as e:
    print(f"Menu button setup error: {e}")

EXAMS = {
    # --- EXAMS FROM @BahirabAcademy & @bahirabquiz ---
    "global_trend_2015": {"name": "Global Trend Final Exam 2015", "msg_id": 3, "type": "file", "channel": EXAMS_CHANNEL},
    "history_2015": {"name": "History Mid Exam 2015", "msg_id": 4, "type": "file", "channel": EXAMS_CHANNEL},
    "geography_final": {"name": "Geography Final Exam", "msg_id": 5, "type": "file", "channel": EXAMS_CHANNEL},
    "emerging_tech_mid": {"name": "Emerging Technology Mid Exam", "msg_id": 6, "type": "file", "channel": EXAMS_CHANNEL},
    "civics_mid": {"name": "Civics Mid Exam", "msg_id": 7, "type": "file", "channel": EXAMS_CHANNEL},
    "logic_final": {"name": "Logic Final Exam", "msg_id": 8, "type": "file", "channel": EXAMS_CHANNEL},
    "freshman_app": {"name": "Freshman Modules and Exams Application", "msg_id": 9, "type": "file", "channel": EXAMS_CHANNEL},
    "inclusiveness_2014": {"name": "Inclusiveness Mid Exam 2014", "msg_id": 12, "type": "file", "channel": EXAMS_CHANNEL},
    "psychology_mid": {"name": "General Psychology Mid Exam", "msg_id": 13, "type": "file", "channel": EXAMS_CHANNEL},
    "chemistry_mid": {"name": "General Chemistry Mid Exam", "msg_id": 14, "type": "file", "channel": EXAMS_CHANNEL},
    "geography_2014": {"name": "Geography Mid Exam 2014", "msg_id": 15, "type": "file", "channel": EXAMS_CHANNEL},
    "physics_mid": {"name": "General Physics Mid Exam", "msg_id": 17, "type": "file", "channel": EXAMS_CHANNEL},
    "logic_mid": {"name": "Logic Mid Exam", "msg_id": 18, "type": "file", "channel": EXAMS_CHANNEL},
    "applied_math_mid": {"name": "Applied Mathematics Mid Exam", "msg_id": 21, "type": "file", "channel": EXAMS_CHANNEL},
    "cpp_mid": {"name": "C++ BDU Mid Exam", "msg_id": 22, "type": "file", "channel": EXAMS_CHANNEL},
    "history_mid_2016": {"name": "History Mid Exam 2016", "msg_id": 23, "type": "file", "channel": EXAMS_CHANNEL},
    "emerging_tech_2016": {"name": "Emerging Technology Mid Exam 2016", "msg_id": 24, "type": "file", "channel": EXAMS_CHANNEL},
    "global_trend_2016": {"name": "Global Trend Mid Exam 2016", "msg_id": 26, "type": "file", "channel": EXAMS_CHANNEL},
    "anthro_mid_2016": {"name": "Anthropology Mid Exam 2016", "msg_id": 28, "type": "file", "channel": EXAMS_CHANNEL},
    "econ_mid_2016": {"name": "Economic Mid Exam 2016", "msg_id": 29, "type": "file", "channel": EXAMS_CHANNEL},
    "history_final_2016": {"name": "History Final Exam 2016", "msg_id": 30, "type": "file", "channel": EXAMS_CHANNEL},
    "econ_final_2016": {"name": "Economics Final Exam 2016", "msg_id": 31, "type": "file", "channel": EXAMS_CHANNEL},
    "anthro_final_2016": {"name": "Anthropology Final Exam 2016", "msg_id": 32, "type": "file", "channel": EXAMS_CHANNEL},
    "emerging_tech_final": {"name": "Emerging Technology Final Exam", "msg_id": 34, "type": "file", "channel": EXAMS_CHANNEL},
    "math_social_mid": {"name": "Mathematics For Social Mid Exam", "msg_id": 35, "type": "file", "channel": EXAMS_CHANNEL},
    "math_social_mid_2016": {"name": "Mathematics For Social Mid Exam 2016", "msg_id": 37, "type": "file", "channel": EXAMS_CHANNEL},
    "geography_mid_2016": {"name": "Geography Mid Exam 2016", "msg_id": 38, "type": "file", "channel": EXAMS_CHANNEL},
    "applied_math_one_final": {"name": "Applied Mathematics One Final Exam", "msg_id": 46, "type": "file", "channel": EXAMS_CHANNEL},
    "moral_civic_mid_2016": {"name": "Moral and Civic Education Mid Exam 2016", "msg_id": 149, "type": "file", "channel": EXAMS_CHANNEL},
    "geography_mid_2016_b": {"name": "Geography Mid Exam 2016", "msg_id": 150, "type": "file", "channel": EXAMS_CHANNEL},
    "geography_mid_other": {"name": "Geography Mid Exam 2016 Other Semester", "msg_id": 151, "type": "file", "channel": EXAMS_CHANNEL},
    "logic_mid_2016": {"name": "Logic Mid Exam 2016", "msg_id": 152, "type": "file", "channel": EXAMS_CHANNEL},
    "history_mid_b": {"name": "History Mid Exam", "msg_id": 153, "type": "file", "channel": EXAMS_CHANNEL},
    "entrepreneurship_mid_2016": {"name": "Entrepreneurship Mid Exam 2016", "msg_id": 155, "type": "file", "channel": EXAMS_CHANNEL},
    "history_final_2015_b": {"name": "History Final Exam 2015", "msg_id": 163, "type": "file", "channel": EXAMS_CHANNEL},
    "math_natural_final": {"name": "Mathematics For Natural Final Exam", "msg_id": 165, "type": "file", "channel": EXAMS_CHANNEL},
    
    # 🔄 በፋይል የተተኩት 11ዱ ፈተናዎች (@bahirabquiz)
    "geography_final_2016": {"name": "Geography Final Exam 2016", "msg_id": 20, "type": "file", "channel": MODULES_CHANNEL},
    "math_final_2016": {"name": "Mathematics Final Exam 2016", "msg_id": 21, "type": "file", "channel": MODULES_CHANNEL},
    "global_final_179": {"name": "Global Final Exam", "msg_id": 22, "type": "file", "channel": MODULES_CHANNEL},
    "civics_final_187": {"name": "Civics Final Exam", "msg_id": 23, "type": "file", "channel": MODULES_CHANNEL},
    "civics_final_192": {"name": "Civics Final Exam", "msg_id": 24, "type": "file", "channel": MODULES_CHANNEL},
    "geography_final_213": {"name": "Geography Final Exam", "msg_id": 25, "type": "file", "channel": MODULES_CHANNEL},
    "emerging_tech_2014": {"name": "Emerging Technology Final Exam 2014", "msg_id": 26, "type": "file", "channel": MODULES_CHANNEL},
    "logic_final_219": {"name": "Logic Final Exam", "msg_id": 27, "type": "file", "channel": MODULES_CHANNEL},
    "logic_final_818": {"name": "Logic Final Exam 2017", "msg_id": 28, "type": "file", "channel": MODULES_CHANNEL},
    "comm_skills_one_823": {"name": "Communication Skills One English Final Exam 2017", "msg_id": 29, "type": "file", "channel": MODULES_CHANNEL},
    "logic_final_802": {"name": "Logic Final Exam", "msg_id": 30, "type": "file", "channel": MODULES_CHANNEL},

    "history_final_academy": {"name": "History Final Exam", "msg_id": 168, "type": "file", "channel": EXAMS_CHANNEL},
    "applied_math_one_final_b": {"name": "Applied Mathematics One Final Exam", "msg_id": 169, "type": "file", "channel": EXAMS_CHANNEL},
    "history_final_2016_2": {"name": "History 2016 Final Exam", "msg_id": 170, "type": "file", "channel": EXAMS_CHANNEL},
    "math_social_final": {"name": "Mathematics For Social Final Exam", "msg_id": 171, "type": "file", "channel": EXAMS_CHANNEL},
    "comm_skills_final": {"name": "Communication Skills One English Final Exam", "msg_id": 174, "type": "file", "channel": EXAMS_CHANNEL},
    "psychology_final": {"name": "General Psychology Final Exam", "msg_id": 175, "type": "file", "channel": EXAMS_CHANNEL},
    "global_final_176": {"name": "Global Final Exam", "msg_id": 176, "type": "file", "channel": EXAMS_CHANNEL},
    "global_trend_2015_b": {"name": "Global Trend Final Exam 2015", "msg_id": 177, "type": "file", "channel": EXAMS_CHANNEL},
    "civics_final_2016": {"name": "Civics Final Exam 2016", "msg_id": 180, "type": "file", "channel": EXAMS_CHANNEL},
    "civics_final_2023": {"name": "Civics Final Exam 2023", "msg_id": 182, "type": "file", "channel": EXAMS_CHANNEL},
    "moral_civic_final_193": {"name": "Moral & Civic Education Final Exam", "msg_id": 193, "type": "file", "channel": EXAMS_CHANNEL},
    "econ_final_2016_b": {"name": "Economics Final Exam 2016", "msg_id": 196, "type": "file", "channel": EXAMS_CHANNEL},
    "econ_final_2013": {"name": "Economics Final Exam 2013", "msg_id": 197, "type": "file", "channel": EXAMS_CHANNEL},
    "econ_final_2015": {"name": "Economics Final Exam 2015", "msg_id": 198, "type": "file", "channel": EXAMS_CHANNEL},
    "emerging_tech_2015": {"name": "Emerging Technology Final Exam 2015", "msg_id": 202, "type": "file", "channel": EXAMS_CHANNEL},
    "emerging_tech_203": {"name": "Emerging Technology Final Exam", "msg_id": 203, "type": "file", "channel": EXAMS_CHANNEL},
    "geography_final_204": {"name": "Geography Final Exam", "msg_id": 204, "type": "file", "channel": EXAMS_CHANNEL},
    "entrepreneurship_final_2016": {"name": "Entrepreneurship Final Exam 2016", "msg_id": 215, "type": "file", "channel": EXAMS_CHANNEL},
    "entrepreneurship_final_2015": {"name": "Entrepreneurship Final Exam 2015", "msg_id": 216, "type": "file", "channel": EXAMS_CHANNEL},
    "logic_final_2014": {"name": "Logic Final Exam 2014", "msg_id": 220, "type": "file", "channel": EXAMS_CHANNEL},
    "logic_final_2021": {"name": "Logic Final Exam 2021", "msg_id": 221, "type": "file", "channel": EXAMS_CHANNEL},
    "anthro_final_2015": {"name": "Anthropology Final Exam 2015", "msg_id": 222, "type": "file", "channel": EXAMS_CHANNEL},
    "anthro_final_2016_b": {"name": "Anthropology Final Exam 2016", "msg_id": 223, "type": "file", "channel": EXAMS_CHANNEL},
    "physics_final_224": {"name": "General Physics Final Exam", "msg_id": 224, "type": "file", "channel": EXAMS_CHANNEL},
    "logic_final_2017": {"name": "Logic Final Exam 2017", "msg_id": 226, "type": "file", "channel": EXAMS_CHANNEL},
    "geography_final_2017": {"name": "Geography Final Exam 2017", "msg_id": 227, "type": "file", "channel": EXAMS_CHANNEL},
    "anthro_mid_2017": {"name": "Anthropology Mid Exam 2017", "msg_id": 318, "type": "file", "channel": EXAMS_CHANNEL},
    "critical_thinking_mid_2017": {"name": "Critical Thinking Mid Exam 2017", "msg_id": 319, "type": "file", "channel": EXAMS_CHANNEL},
    "global_trend_mid_2017": {"name": "Global Trend Mid Exam 2017", "msg_id": 320, "type": "file", "channel": EXAMS_CHANNEL},
    "geography_mid_2017": {"name": "Geography Mid Exam 2017", "msg_id": 321, "type": "file", "channel": EXAMS_CHANNEL},
    "econ_mid_2017": {"name": "Economics Mid Exam 2017", "msg_id": 322, "type": "file", "channel": EXAMS_CHANNEL},
    "moral_civic_mid_323": {"name": "Moral and Civic Education Mid Exam 2016", "msg_id": 323, "type": "file", "channel": EXAMS_CHANNEL},
    "math_social_mid_325": {"name": "Mathematics Mid Exam For Social", "msg_id": 325, "type": "file", "channel": EXAMS_CHANNEL},
    "comm_english_two_2016": {"name": "Communication English Skills Two Mid Exam 2016", "msg_id": 326, "type": "file", "channel": EXAMS_CHANNEL},
    "comm_english_two_b": {"name": "Communication English Skills Two Mid Exam", "msg_id": 327, "type": "file", "channel": EXAMS_CHANNEL},
    "comm_english_two_2017": {"name": "Communication English Skills Two Mid Exam 2016/17", "msg_id": 328, "type": "file", "channel": EXAMS_CHANNEL},
    "history_mid_2017": {"name": "History Mid Exam 2017", "msg_id": 329, "type": "file", "channel": EXAMS_CHANNEL},
    "psychology_330": {"name": "General Psychology Material / Exam", "msg_id": 330, "type": "file", "channel": EXAMS_CHANNEL},
    "comm_english_two_final_406": {"name": "Communication English Skills Two Final Exam 2017", "msg_id": 406, "type": "file", "channel": EXAMS_CHANNEL},
    "global_trend_final_790": {"name": "Global Trend Final Exam 2017", "msg_id": 790, "type": "file", "channel": EXAMS_CHANNEL},
    "entrepreneurship_final_785": {"name": "Entrepreneurship Final Exam 2017", "msg_id": 785, "type": "file", "channel": EXAMS_CHANNEL},
    "psychology_final_793": {"name": "General Psychology Final Exam 2017", "msg_id": 793, "type": "file", "channel": EXAMS_CHANNEL},
    "psychology_final_794": {"name": "General Psychology Final Exam 2017 Other Semester", "msg_id": 794, "type": "file", "channel": EXAMS_CHANNEL},
    "logic_final_808": {"name": "Logic Final Exam 2017", "msg_id": 808, "type": "file", "channel": EXAMS_CHANNEL},
    "logic_final_809": {"name": "Logic Final Exam 2017 Other Semester", "msg_id": 809, "type": "file", "channel": EXAMS_CHANNEL},
    "econ_final_814": {"name": "Economics Final Exam 2017", "msg_id": 814, "type": "file", "channel": EXAMS_CHANNEL},
    "comm_skills_one_822": {"name": "Communication Skills One English Final Exam", "msg_id": 822, "type": "file", "channel": EXAMS_CHANNEL},
    "comm_skills_one_827": {"name": "Communication Skills One English Final Exam 2017", "msg_id": 827, "type": "file", "channel": EXAMS_CHANNEL},
    "psychology_final_2016": {"name": "General Psychology Final Exam", "msg_id": 175, "type": "file", "channel": EXAMS_CHANNEL},
    "english_final_2016": {"name": "Communication Skills English Final Exam", "msg_id": 174, "type": "file", "channel": EXAMS_CHANNEL},
    "english_mid_2016": {"name": "Communication English Skills Two Mid Exam", "msg_id": 326, "type": "file", "channel": EXAMS_CHANNEL},
    "civics_final_2015": {"name": "Civics Final Exam 2016", "msg_id": 180, "type": "file", "channel": EXAMS_CHANNEL},
    "civics_mid_2016": {"name": "Civics Mid Exam 2016", "msg_id": 149, "type": "file", "channel": EXAMS_CHANNEL},
    "global_final_2016": {"name": "Global Final Exam", "msg_id": 176, "type": "file", "channel": EXAMS_CHANNEL},
    "global_mid_2016": {"name": "Global Trend Mid Exam 2016", "msg_id": 26, "type": "file", "channel": EXAMS_CHANNEL},
    "emerging_final_2016": {"name": "Emerging Technology Final Exam", "msg_id": 34, "type": "file", "channel": EXAMS_CHANNEL},
    "emerging_mid_2016": {"name": "Emerging Technology Mid Exam 2016", "msg_id": 24, "type": "file", "channel": EXAMS_CHANNEL},

    # --- 18 FRESHMAN MODULES FROM @bahirabquiz ---
    "mod_anthro": {"name": "Anthropology Freshman Module", "msg_id": 2, "type": "file", "channel": MODULES_CHANNEL},
    "mod_entrepreneurship": {"name": "Entrepreneurship Freshman Module", "msg_id": 3, "type": "file", "channel": MODULES_CHANNEL},
    "mod_physics": {"name": "General Physics Freshman Module", "msg_id": 4, "type": "file", "channel": MODULES_CHANNEL},
    "mod_global": {"name": "Global Affairs Freshman Module", "msg_id": 5, "type": "file", "channel": MODULES_CHANNEL},
    "mod_inclusiveness": {"name": "Inclusiveness Freshman Module", "msg_id": 6, "type": "file", "channel": MODULES_CHANNEL},
    "mod_psychology": {"name": "General Psychology Freshman Module", "msg_id": 7, "type": "file", "channel": MODULES_CHANNEL},
    "mod_fitness": {"name": "Physical Fitness Freshman Module", "msg_id": 8, "type": "file", "channel": MODULES_CHANNEL},
    "mod_geography": {"name": "Geography of Ethiopia and The Horn Module", "msg_id": 9, "type": "file", "channel": MODULES_CHANNEL},
    "mod_biology": {"name": "General Biology Freshman Module", "msg_id": 10, "type": "file", "channel": MODULES_CHANNEL},
    "mod_chemistry": {"name": "General Chemistry Freshman Module", "msg_id": 11, "type": "file", "channel": MODULES_CHANNEL},
    "mod_english_one": {"name": "Communicative English Language Skills I Module", "msg_id": 12, "type": "file", "channel": MODULES_CHANNEL},
    "mod_history": {"name": "History of Ethiopia and The Horn Module", "msg_id": 13, "type": "file", "channel": MODULES_CHANNEL},
    "mod_economics": {"name": "Introduction to Economics Freshman Module", "msg_id": 14, "type": "file", "channel": MODULES_CHANNEL},
    "mod_logic": {"name": "Logic and Critical Thinking Module", "msg_id": 15, "type": "file", "channel": MODULES_CHANNEL},
    "mod_english_two": {"name": "Communicative English Skills II Module", "msg_id": 16, "type": "file", "channel": MODULES_CHANNEL},
    "mod_civics": {"name": "Moral and Citizenship Education Module", "msg_id": 17, "type": "file", "channel": MODULES_CHANNEL},
    "mod_math_natural": {"name": "Mathematics for Natural Science Module", "msg_id": 18, "type": "file", "channel": MODULES_CHANNEL},
    "mod_math_social": {"name": "Mathematics for Social Sciences Module", "msg_id": 19, "type": "file", "channel": MODULES_CHANNEL},

    # --- TEACHER GUIDES FROM @bahirabquiz ---
    "guide_economics": {"name": "Economics Teacher Guide", "msg_id": 31, "type": "file", "channel": MODULES_CHANNEL},
    "guide_mathematics": {"name": "Mathematics Teacher Guide", "msg_id": 32, "type": "file", "channel": MODULES_CHANNEL}
}

def get_main_keyboard(lang="am"):
    btn_text = "🔍 ተጨማሪ ጥያቄዎች ያግኙ (Open App)" if lang == "am" else "🔍 Get More Questions & Exams"
    lang_btn_text = "🌐 ቋንቋ ቀይሩ (Change)" if lang == "am" else "🌐 Change Lang"
    feedback_btn_text = "💬 አስተያየት (Feedback)" if lang == "am" else "💬 Feedback"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text=btn_text, web_app=WebAppInfo(url=WEB_APP_URL)))
    keyboard.add(
        InlineKeyboardButton(text=lang_btn_text, callback_data="change_lang"),
        InlineKeyboardButton(text=feedback_btn_text, callback_data="give_feedback")
    )
    return keyboard

def get_lang_selection_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(text="🇪🇹 አማርኛ", callback_data="lang_am"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")
    )
    return keyboard

# --- STATS COMMAND (SQLite Analytics with App Open, Blocked, Reactions & Interactions Count) ---
@bot.message_handler(commands=['stats', 'States', 'stat'])
def handle_stats(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT COUNT(*), SUM(downloads), SUM(ads_watched), SUM(questions_answered), SUM(app_opened), SUM(bot_interactions) FROM users')
        totals = c.fetchone()
        total_u = totals[0] or 0
        total_d = totals[1] or 0
        total_a = totals[2] or 0
        total_q = totals[3] or 0
        total_app_opens = totals[4] or 0
        total_bot_clicks = totals[5] or 0

        c.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
        blocked_count = c.fetchone()[0] or 0
        active_users_count = total_u - blocked_count

        c.execute('SELECT COUNT(*) FROM users WHERE app_opened > 0')
        active_app_users = c.fetchone()[0] or 0
        bot_only_count = total_u - active_app_users

        c.execute('SELECT COUNT(*) FROM reactions')
        total_reactions = c.fetchone()[0] or 0

        c.execute('SELECT telegram_id, first_name, username, coins, questions_answered, downloads, ads_watched, app_opened, bot_interactions, is_blocked FROM users ORDER BY created_at DESC LIMIT 20')
        recent_users = c.fetchall()
        conn.close()

        lines = []
        for u in recent_users:
            uid, name, uname, coins, q_ans, dl, ads, app_op, b_intr, is_blk = u[0], u[1], u[2], u[3], u[4] or 0, u[5] or 0, u[6] or 0, u[7] or 0, u[8] or 0, u[9] or 0
            status_tag = "🚫 [BLOCKED]" if is_blk == 1 else "🟢 [ACTIVE]"
            lines.append(
                f"• `{uid}` | 👤 {name} ({uname}) {status_tag}\n"
                f"   ↳ 📱 አፑን የከፈተው፦ {app_op} ጊዜ | 🔘 የቦት ንክኪ፦ {b_intr} ጊዜ\n"
                f"   ↳ 🪙 {coins} Coins | ✍️ {q_ans} ጥያቄዎች | 📥 {dl} ውርዶች | 📺 {ads} አዶች"
            )
        user_list_str = "\n\n".join(lines) if lines else "ምንም ተጠቃሚ የለም"
        
        stats_msg = (
            "📊 <b>Bahirab Bot & App Analytics</b>\n\n"
            f"👥 <b>ጠቅላላ ተጠቃሚዎች፦</b> {total_u}\n"
            f"🟢 <b>ንቁ ተጠቃሚዎች (Active)፦</b> {active_users_count}\n"
            f"🚫 <b>ቦቱን ያገዱ (Blocked)፦</b> {blocked_count}\n"
            f"📱 <b>አፑን የከፈቱ ተጠቃሚዎች፦</b> {active_app_users}\n"
            f"🔄 <b>አፑ የተከፈተበት ድምር፦</b> {total_app_opens} ጊዜ\n"
            f"🔘 <b>የቦት በተን ንክኪዎች ድምር፦</b> {total_bot_clicks} ጊዜ\n"
            f"🤖 <b>ቦት ብቻ የተጠቀሙ፦</b> {bot_only_count}\n"
            f"✍️ <b>ጠቅላላ የተመለሱ ጥያቄዎች፦</b> {total_q}\n"
            f"📥 <b>አጠቃላይ የተወረዱ ፈተናዎች፦</b> {total_d}\n"
            f"📺 <b>የታዩ ማስታወቂያዎች፦</b> {total_a}\n"
            f"💖 <b>የተሰጡ Reactions፦</b> {total_reactions} ጊዜ\n\n"
            f"📝 <b>የቅርብ ተጠቃሚዎች ዝርዝር፦</b>\n\n{user_list_str}"
        )
        bot.send_message(message.chat.id, stats_msg, parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"Stats Error: {e}")

# 🚀 የተሟላ የተማሪ ፕሮፋይል ካርድ መመልከቻ (/find <USER_ID>)
@bot.message_handler(commands=['find'])
def find_sqlite_user(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ አጠቃቀም፦\n`/find <USER_ID>`\n\nምሳሌ፦\n`/find 7097060497`", parse_mode="Markdown")
        return

    target_id = parts[1].strip().replace("`", "").replace('"', '').replace("'", "")

    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('''
            SELECT telegram_id, first_name, username, coins, downloads, 
                   ads_watched, questions_answered, app_opened, 
                   bot_interactions, is_blocked, lang, created_at 
            FROM users WHERE telegram_id = ?
        ''', (target_id,))
        user = c.fetchone()

        c.execute('SELECT file_key FROM unlocked_materials WHERE telegram_id = ?', (target_id,))
        unlocked_rows = c.fetchall()
        unlocked_list = [r[0] for r in unlocked_rows]
        conn.close()

        if not user:
            bot.reply_to(message, f"❌ ID `{target_id}` ያለው ተጠቃሚ በዳታቤዝ ውስጥ አልተገኘም።", parse_mode="Markdown")
            return

        uid, name, uname, coins, dl, ads, q_ans, app_op, b_intr, is_blk, lang_pref, created = user
        status_str = "🚫 የታገደ (Blocked)" if is_blk == 1 else "🟢 ንቁ (Active)"
        materials_str = ", ".join(unlocked_list) if unlocked_list else "ምንም አልከፈተም"

        user_card = (
            f"👤 <b>የተጠቃሚ ሙሉ ዝርዝር መረጃ (User Profile)፦</b>\n\n"
            f"• <b>ስም፦</b> {name}\n"
            f"• <b>Username፦</b> {uname}\n"
            f"• <b>Telegram ID፦</b> <code>{uid}</code>\n"
            f"• <b>ሁኔታ (Status)፦</b> {status_str}\n"
            f"• <b>የመረጠው ቋንቋ፦</b> {lang_pref.upper() if lang_pref else 'AM'}\n\n"
            f"📊 <b>የእንቅስቃሴና የቦት አጠቃቀም መረጃ፦</b>\n"
            f"  ↳ 📱 <b>አፑን የከፈተበት ብዛት፦</b> {app_op or 0} ጊዜ\n"
            f"  ↳ 🔘 <b>የቦት በተን ንክኪዎች፦</b> {b_intr or 0} ጊዜ\n"
            f"  ↳ 🪙 <b>ያለው ሳንቲም (Coins)፦</b> {coins} Coins\n"
            f"  ↳ ✍️ <b>የመለሳቸው ጥያቄዎች፦</b> {q_ans or 0}\n"
            f"  ↳ 📥 <b>ያወረዳቸው ፈተናዎች፦</b> {dl or 0} ጊዜ\n"
            f"  ↳ 📺 <b>ያያቸው ማስታወቂያዎች፦</b> {ads or 0} ጊዜ\n\n"
            f"📚 <b>የከፈታቸው ማቴሪያሎች፦</b>\n<code>{materials_str}</code>\n\n"
            f"🕒 <b>የተመዘገበበት ቀን፦</b> <i>{created}</i>"
        )

        reply_kb = InlineKeyboardMarkup()
        reply_kb.add(InlineKeyboardButton(text="↩️ ለተጠቃሚው መልስ ስጥ (Reply)", callback_data=f"admin_reply_{uid}"))

        bot.send_message(
            message.chat.id,
            user_card,
            parse_mode="HTML",
            reply_markup=reply_kb
        )

    except Exception as e:
        bot.reply_to(message, f"❌ ስህተት፦ {e}")

# 🚀 አዲስ፦ ቦቱን Block ያደረጉ ተጠቃሚዎችን ዝርዝር ማሳያ (/blocked)
@bot.message_handler(commands=['blocked'])
def list_blocked_users(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT telegram_id, first_name, username FROM users WHERE is_blocked = 1 ORDER BY created_at DESC')
        rows = c.fetchall()
        conn.close()

        if not rows:
            bot.reply_to(message, "✅ እስካሁን ቦቱን Block ያደረገ ምንም ተጠቃሚ የለም!")
            return

        lines = [f"• `{r[0]}` | 👤 {r[1]} ({r[2]})" for r in rows]
        bot.send_message(
            message.chat.id,
            f"🚫 <b>ቦቱን Block ያደረጉ ተጠቃሚዎች ({len(rows)})፦</b>\n\n" + "\n".join(lines),
            parse_mode="HTML"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ ስህተት፦ {e}")

# 🚀 አዲስ፦ የተሰጡ Reactions ዝርዝር መመልከቻ (/reactions)
@bot.message_handler(commands=['reactions'])
def list_recent_reactions(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT telegram_id, first_name, username, emoji, created_at FROM reactions ORDER BY id DESC LIMIT 30')
        rows = c.fetchall()
        conn.close()

        if not rows:
            bot.reply_to(message, "⚠️ እስካሁን ምንም የተሰጠ Reaction የለም።")
            return

        lines = [f"• {r[3]} | 👤 <b>{r[1]}</b> ({r[2]}) | <code>{r[0]}</code>\n  ↳ 🕒 <i>{r[4]}</i>" for r in rows]
        bot.send_message(
            message.chat.id,
            f"💖 <b>የቅርብ ጊዜ Reactions ዝርዝር ({len(rows)})፦</b>\n\n" + "\n\n".join(lines),
            parse_mode="HTML"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ ስህተት፦ {e}")

# 🚀 አዲስ፦ የተከፈቱ ኖቶችና ማቴሪያሎች ሙሉ ዝርዝር መመልከቻ ትዕዛዝ (/unlocked)
@bot.message_handler(commands=['unlocked', 'purchases'])
def list_all_unlocked(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('''
            SELECT u.telegram_id, u.first_name, u.username, um.file_key, um.unlocked_at 
            FROM unlocked_materials um
            LEFT JOIN users u ON um.telegram_id = u.telegram_id
            ORDER BY um.unlocked_at DESC LIMIT 40
        ''')
        rows = c.fetchall()
        conn.close()

        if not rows:
            bot.reply_to(message, "⚠️ እስካሁን ምንም የተከፈተ ኖት ወይም ማቴሪያል የለም።")
            return

        lines = []
        for r in rows:
            uid, name, uname, fkey, udate = r[0], r[1] or "Student", r[2] or "No Username", r[3], r[4]
            lines.append(f"• 👤 <b>{name}</b> ({uname}) | <code>{uid}</code>\n  ↳ 📚 <code>{fkey}</code> ({udate})")

        msg_text = "📋 <b>የተከፈቱ ኖቶችና ማቴሪያሎች ዝርዝር፦</b>\n\n" + "\n\n".join(lines)
        bot.send_message(message.chat.id, msg_text, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ ስህተት፦ {e}")

# --- EXPORT COMMAND (Backup .sqlite & CSV) ---
@bot.message_handler(commands=['export'])
def export_sqlite_users(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    try:
        # 1. database.sqlite ፋይልን በቀጥታ መላክ
        if os.path.exists('database.sqlite'):
            with open('database.sqlite', 'rb') as f:
                bot.send_document(
                    message.chat.id,
                    f,
                    caption="💾 የ SQLite ዳታቤዝ ሙሉ Backup ፋይል (database.sqlite)"
                )

        # 2. በ Excel/WPS የሚከፈት CSV ፋይል አዘጋጅቶ መላክ
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT * FROM users')
        rows = c.fetchall()
        headers = [desc[0] for desc in c.description]
        conn.close()

        if not rows:
            bot.reply_to(message, "⚠️ በዳታቤዙ ውስጥ ምንም የተመዘገበ ተጠቃሚ የለም።")
            return

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(headers)
        writer.writerows(rows)

        bio = io.BytesIO(csv_buffer.getvalue().encode('utf-8'))
        bio.name = "all_users.csv"

        bot.send_document(
            message.chat.id,
            bio,
            caption=f"📊 የሁሉም ተጠቃሚዎች ዝርዝር CSV ሪፖርት (ጠቅላላ፦ {len(rows)} ተጠቃሚዎች)"
        )

    except Exception as e:
        bot.reply_to(message, f"❌ ስህተት ተፈጥሯል፦ {e}")

# 🚀 የድሮውን ዳታቤዝ ከአዲሱ ጋር ማዋሃጃ / መጨመሪያ (Database Merge)
@bot.message_handler(content_types=['document'])
def handle_db_merge(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    doc = message.document
    if doc.file_name.endswith('.sqlite') or doc.file_name.endswith('.db'):
        try:
            file_info = bot.get_file(doc.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            temp_filename = "temp_uploaded.sqlite"
            with open(temp_filename, 'wb') as temp_f:
                temp_f.write(downloaded_file)

            main_conn = sqlite3.connect('database.sqlite')
            main_c = main_conn.cursor()

            main_c.execute('SELECT COUNT(*) FROM users')
            before_count = main_c.fetchone()[0]

            main_c.execute(f"ATTACH DATABASE '{temp_filename}' AS old_db")

            # 1. በአዲሱ ዳታቤዝ ውስጥ የሌሉ የድሮ ተጠቃሚዎችን ብቻ መርጦ መጨመር
            main_c.execute('''
                INSERT OR IGNORE INTO users (
                    telegram_id, first_name, username, coins, 
                    downloads, ads_watched, questions_answered, 
                    app_opened, bot_interactions, is_blocked, lang, created_at
                )
                SELECT 
                    telegram_id, first_name, username, coins, 
                    downloads, ads_watched, questions_answered, 
                    app_opened, 0, 0, 'am', created_at 
                FROM old_db.users
            ''')

            # 2. ቀድመው የተከፈቱ ማቴሪያሎችን ሳያጠፋ ማዋሃድ
            try:
                main_c.execute('''
                    INSERT OR IGNORE INTO unlocked_materials (telegram_id, file_key, unlocked_at)
                    SELECT telegram_id, file_key, unlocked_at FROM old_db.unlocked_materials
                ''')
            except Exception:
                pass

            main_conn.commit()

            main_c.execute('SELECT COUNT(*) FROM users')
            after_count = main_c.fetchone()[0]

            main_c.execute("DETACH DATABASE old_db")
            main_conn.close()

            if os.path.exists(temp_filename):
                os.remove(temp_filename)

            added_users = after_count - before_count
            bot.reply_to(
                message,
                f"✅ <b>ዳታቤዙ በተሳካ ሁኔታ ተዋህዷል (Merged)!</b>\n\n"
                f"➕ <b>አዲስ የተጨመሩ የድሮ ተጠቃሚዎች፦</b> {added_users}\n"
                f"👥 <b>አጠቃላይ አሁን በዳታቤዝ ያሉ ተጠቃሚዎች፦</b> {after_count}",
                parse_mode="HTML"
            )
        except Exception as e:
            bot.reply_to(message, f"❌ ዳታቤዙን ማዋሃድ አልተቻለም፦ {e}")

# --- 📢 BROADCAST COMMAND (መልዕክት ለሁሉም ተጠቃሚዎች መላኪያ) ---
@bot.message_handler(commands=['broadcast', 'announce'])
def broadcast_prompt(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    sent = bot.reply_to(
        message, 
        "📢 <b>የብሮድካስት መልዕክት ማስተላለፊያ</b>\n\n"
        "ለሁሉም ተማሪዎች የሚተላለፈውን መልዕክት ጽፈህ ላክ (ጽሑፍ፣ ፎቶ ከነ ጽሑፉ ወይም ቪዲዮ ሊሆን ይችላል)፦",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(sent, send_broadcast_message)

def send_broadcast_message(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    if message.text and message.text.startswith('/'):
        bot.reply_to(message, "❌ የብሮድካስት ስራው ተሰርዟል።")
        return

    status_msg = bot.reply_to(message, "⏳ መልዕክቱ ለሁሉም ተጠቃሚዎች በመላክ ላይ ነው... እባክህ በትዕግስት ጠብቅ።")

    def broadcast_worker():
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT telegram_id FROM users')
        users = c.fetchall()
        conn.close()

        success = 0
        failed = 0

        for (uid,) in users:
            try:
                bot.copy_message(
                    chat_id=int(uid),
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
                success += 1
                time.sleep(0.05)
            except Exception as e:
                failed += 1
                err_str = str(e).lower()
                if "blocked" in err_str or "deactivated" in err_str or "chat not found" in err_str:
                    try:
                        conn_b = sqlite3.connect('database.sqlite')
                        c_b = conn_b.cursor()
                        c_b.execute('UPDATE users SET is_blocked = 1 WHERE telegram_id = ?', (str(uid),))
                        conn_b.commit()
                        conn_b.close()
                    except Exception:
                        pass

        report = (
            "✅ <b>ብሮድካስት በተሳካ ሁኔታ ተጠናቋል!</b>\n\n"
            f"👥 ጠቅላላ ተጠቃሚዎች፦ {len(users)}\n"
            f"✔️ የደረሳቸው፦ {success}\n"
            f"❌ ያልደረሳቸው (ቦቱን የዘጉ/ያገዱ)፦ {failed}"
        )
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                text=report,
                parse_mode="HTML"
            )
        except Exception:
            bot.send_message(message.chat.id, report, parse_mode="HTML")

    threading.Thread(target=broadcast_worker).start()

# --- 📥 IMPORT USERS FROM TEXT COMMAND (/import_text, /import_stats) ---
@bot.message_handler(commands=['import_text', 'import_stats'])
def import_from_stats_text(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    target_text = ""
    if message.reply_to_message and message.reply_to_message.text:
        target_text = message.reply_to_message.text
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            target_text = parts[1]
        else:
            sent = bot.reply_to(
                message, 
                "✍️ እባክህ ያንን የተጠቃሚዎች ዝርዝር የያዘውን ጽሑፍ ኮፒ አድርገህ እዚህ ላክልኝ (ወይም መልዕክቱን Reply አድርገህ `/import_text` በለው)፦"
            )
            bot.register_next_step_handler(sent, process_pasted_text)
            return

    save_parsed_users(message, target_text)

def process_pasted_text(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    if message.text and message.text.startswith('/'):
        bot.reply_to(message, "❌ ተሰርዟል።")
        return
    save_parsed_users(message, message.text or "")

def save_parsed_users(message, text):
    blocks = re.split(r'\n(?=•\s*[`\d])', text)
    if len(blocks) <= 1 and not text.strip().startswith('•'):
        blocks = text.split('\n\n')

    conn = sqlite3.connect('database.sqlite')
    c = conn.cursor()
    added_count = 0
    updated_count = 0

    for block in blocks:
        id_match = re.search(r'[`•\s](\d{8,12})[`\s|]', block) or re.search(r'(\d{8,12})', block)
        if not id_match:
            continue
        user_id = id_match.group(1).strip()

        name_match = re.search(r'\|\s*(?:👤\s*)?([^(|\n]+)', block)
        name = name_match.group(1).strip() if name_match else "Student"

        user_match = re.search(r'@([A-Za-z0-9_]+)', block)
        if user_match:
            username = f"@{user_match.group(1).strip()}"
        else:
            username = "No Username"

        coins_match = re.search(r'(\d+)\s*Coins', block)
        coins = int(coins_match.group(1)) if coins_match else 300

        q_match = re.search(r'(\d+)\s*ጥያቄዎች', block)
        q_ans = int(q_match.group(1)) if q_match else 0

        dl_match = re.search(r'(\d+)\s*ውርዶች', block)
        dl = int(dl_match.group(1)) if dl_match else 0

        ad_match = re.search(r'(\d+)\s*አዶች', block)
        ads = int(ad_match.group(1)) if ad_match else 0

        c.execute('''
            INSERT INTO users (telegram_id, first_name, username, coins, downloads, ads_watched, questions_answered, app_opened, is_blocked)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)
            ON CONFLICT(telegram_id) DO UPDATE SET
                first_name = excluded.first_name,
                username = excluded.username,
                coins = excluded.coins
        ''', (user_id, name, username, coins, dl, ads, q_ans))

        if c.rowcount > 0:
            added_count += 1
        else:
            updated_count += 1

    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        f"✅ <b>ተጠቃሚዎች በተሳካ ሁኔታ ተመዝግበዋል!</b>\n\n"
        f"👥 <b>ጠቅላላ የተጨመሩ/የተስተካከሉ፦</b> {added_count + updated_count} ተማሪዎች\n\n"
        f"አሁን <code>/stats</code> በማለት የተጠቃሚዎችን ቁጥር ማረጋገጥ ትችላለህ።",
        parse_mode="HTML"
    )

# --- 🚫 REAL-TIME BOT BLOCK & UNBLOCK TRACKING ---
@bot.my_chat_member_handler()
def handle_my_chat_member_update(update):
    try:
        user = update.from_user
        if not user:
            return
        user_id = str(user.id)
        name = (user.first_name or "Student").replace("|", "-").replace("\n", " ")
        username = f"@{user.username}" if user.username else "No Username"
        new_status = update.new_chat_member.status

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()

        if new_status == 'kicked':
            c.execute('UPDATE users SET is_blocked = 1 WHERE telegram_id = ?', (user_id,))
            conn.commit()
            conn.close()

            def alert_block():
                try:
                    alert = (
                        f"🚫 <b>ቦቱ ተዘግቷል (Bot Blocked)!</b>\n\n"
                        f"👤 <b>ተጠቃሚ፦</b> {name} ({username})\n"
                        f"🆔 <b>ID፦</b> <code>{user_id}</code>\n"
                        f"⚠️ ተጠቃሚው ቦቱን Block አድርጎታል!"
                    )
                    bot.send_message(int(ADMIN_ID), alert, parse_mode="HTML")
                except Exception as e:
                    print(f"Block alert error: {e}")
            threading.Thread(target=alert_block).start()

        elif new_status in ['member', 'administrator']:
            c.execute('UPDATE users SET is_blocked = 0 WHERE telegram_id = ?', (user_id,))
            conn.commit()
            conn.close()

            def alert_unblock():
                try:
                    alert = (
                        f"🟢 <b>ቦቱ ተከፍቷል (Bot Unblocked)!</b>\n\n"
                        f"👤 <b>ተጠቃሚ፦</b> {name} ({username})\n"
                        f"🆔 <b>ID፦</b> <code>{user_id}</code>\n"
                        f"✨ ተጠቃሚው ቦቱን መልሶ ከፍቶታል!"
                    )
                    bot.send_message(int(ADMIN_ID), alert, parse_mode="HTML")
                except Exception as e:
                    print(f"Unblock alert error: {e}")
            threading.Thread(target=alert_unblock).start()
        else:
            conn.close()
    except Exception as e:
        print(f"Chat member update error: {e}")

# --- 💖 MESSAGE REACTION TRACKING (EMOJI LISTENER) ---
@bot.message_reaction_handler()
def handle_message_reactions(update):
    try:
        user = getattr(update, 'user', None) or getattr(update, 'from_user', None)
        if not user:
            return
        user_id = str(user.id)
        name = (user.first_name or "Student").replace("|", "-").replace("\n", " ")
        username = f"@{user.username}" if user.username else "No Username"

        new_reactions = getattr(update, 'new_reaction', []) or []
        emojis = []
        for r in new_reactions:
            if hasattr(r, 'emoji'):
                emojis.append(r.emoji)
            elif isinstance(r, dict) and 'emoji' in r:
                emojis.append(r['emoji'])
        
        emoji_str = " ".join(emojis)
        if not emoji_str:
            return

        msg_id = getattr(update, 'message_id', 0)

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('''INSERT INTO reactions (telegram_id, first_name, username, message_id, emoji)
                     VALUES (?, ?, ?, ?, ?)''', (user_id, name, username, msg_id, emoji_str))
        conn.commit()
        conn.close()

        def notify_reaction():
            try:
                alert = (
                    f"💖 <b>አዲስ Reaction ተሰጥቷል!</b>\n\n"
                    f"👤 <b>ተጠቃሚ፦</b> {name} ({username})\n"
                    f"🆔 <b>ID፦</b> <code>{user_id}</code>\n"
                    f"✨ <b>Reaction፦</b> {emoji_str}\n"
                    f"📩 <b>የመልዕክት ID፦</b> {msg_id}"
                )
                bot.send_message(int(ADMIN_ID), alert, parse_mode="HTML")
            except Exception as e:
                print(f"Reaction alert error: {e}")
        threading.Thread(target=notify_reaction).start()

    except Exception as e:
        print(f"Reaction handler error: {e}")

# --- FEEDBACK BUTTON & HANDLER ---
@bot.callback_query_handler(func=lambda call: call.data == "give_feedback")
def feedback_prompt(call):
    chat_id = call.message.chat.id
    record_bot_interaction(call.from_user.id)
    lang = get_user_lang(call.from_user.id)
    
    bot.clear_step_handler_by_chat_id(chat_id=chat_id)
    
    prompt_text = (
        "✍️ እባክዎ ስለ ቦቱ፣ ፈተናዎች ወይም ማቴሪያሎች ያሎትን አስተያየት ወይም ጥያቄ ከዚህ በታች ይጻፉልን:"
        if lang == "am" else
        "✍️ Please type your feedback, suggestion, or question below:"
    )
    sent_msg = bot.send_message(chat_id, prompt_text)
    bot.register_next_step_handler(sent_msg, save_and_forward_feedback)

def save_and_forward_feedback(message):
    user = message.from_user
    record_bot_interaction(user.id)
    feedback_text = message.text or ""
    chat_id = message.chat.id
    lang = get_user_lang(user.id)
    
    if feedback_text.startswith('/'):
        if feedback_text.startswith('/start'):
            handle_start(message)
        return

    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('INSERT INTO feedback (telegram_id, first_name, username, message) VALUES (?, ?, ?, ?)',
                  (str(user.id), user.first_name, f"@{user.username}" if user.username else "No Username", feedback_text))
        conn.commit()
        conn.close()
    except Exception as err:
        print(f"DB log error: {err}")

    admin_notification = (
        "📩 አዲስ አስተያየት መጣ! (New Feedback)\n\n"
        f"👤 ከ: {user.first_name} (@{user.username if user.username else 'No Username'})\n"
        f"🆔 ID: `{user.id}`\n\n"
        f"💬 አስተያየት፦\n{feedback_text}"
    )
    
    reply_kb = InlineKeyboardMarkup()
    reply_kb.add(InlineKeyboardButton(text="↩️ ለተጠቃሚው መልስ ስጥ (Reply)", callback_data=f"admin_reply_{user.id}"))
    
    try:
        bot.send_message(int(ADMIN_ID), admin_notification, reply_markup=reply_kb)
    except Exception as e:
        print(f"Admin forward warning: {e}")

    success_msg = (
        "✅ እናመሰግናለን! አስተያየትዎ በተሳካ ሁኔታ ደርሶናል።"
        if lang == "am" else
        "✅ Thank you! Your feedback has been successfully sent."
    )
    bot.reply_to(message, success_msg, reply_markup=get_main_keyboard(lang))

# --- ADMIN REPLY BUTTON & COMMAND LOGIC ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_reply_"))
def admin_reply_prompt(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "ይህ ተግባር ለአድሚን ብቻ ነው!")
        return

    target_user_id = call.data.replace("admin_reply_", "")
    sent = bot.send_message(
        call.message.chat.id,
        f"✍️ ለተጠቃሚው (ID: `{target_user_id}`) የሚልኩትን መልስ ጽፈው ይላኩ፦"
    )
    bot.register_next_step_handler(sent, send_admin_reply_to_user, target_user_id)

def send_admin_reply_to_user(message, target_user_id):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
        
    reply_text = message.text or ""
    if not reply_text:
        bot.reply_to(message, "⚠️ ባዶ መልእክት መላክ አይቻልም።")
        return

    try:
        user_lang = get_user_lang(target_user_id)
        header = "📩 ከአስተዳዳሪው የተላከ መልስ፦\n\n" if user_lang == "am" else "📩 Reply from Admin:\n\n"
        bot.send_message(int(target_user_id), header + reply_text, reply_markup=get_main_keyboard(user_lang))
        bot.reply_to(message, f"✅ መልስዎ ለተጠቃሚው (ID: {target_user_id}) በተሳካ ሁኔታ ተልኳል!")
    except Exception as e:
        bot.reply_to(message, f"❌ መልሱን መላክ አልተቻለም፦ {e}")

@bot.message_handler(commands=['reply'])
def handle_reply_command(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "⚠️ አጠቃቀም፦\n`/reply <USER_ID>` <የመልስ_ጽሁፍ>\n\nምሳሌ፦\n`/reply 12345678 ሰላም፣ ፈተናው ተስተካክሏል!`")
        return

    target_user_id = parts[1]
    reply_text = parts[2]

    try:
        user_lang = get_user_lang(target_user_id)
        header = "📩 ከአስተዳዳሪው የተላከ መልስ፦\n\n" if user_lang == "am" else "📩 Reply from Admin:\n\n"
        bot.send_message(int(target_user_id), header + reply_text, reply_markup=get_main_keyboard(user_lang))
        bot.reply_to(message, f"✅ መልስዎ ለተጠቃሚው (ID: {target_user_id}) በተሳካ ሁኔታ ተልኳል!")
    except Exception as e:
        bot.reply_to(message, f"❌ መልሱን መላክ አልተቻለም፦ {e}")

# --- LANGUAGE SELECTION ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_") or call.data == "change_lang")
def handle_language_choice(call):
    chat_id = call.message.chat.id
    record_bot_interaction(call.from_user.id)
    if call.data == "change_lang":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="🌐 Please choose your language / እባክዎ ቋንቋ ይምረጡ:",
            reply_markup=get_lang_selection_keyboard()
        )
        return

    selected_lang = "am" if call.data == "lang_am" else "en"
    user_languages[str(chat_id)] = selected_lang
    user_languages[str(call.from_user.id)] = selected_lang

    try:
        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('UPDATE users SET lang = ? WHERE telegram_id = ?', (selected_lang, str(call.from_user.id)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Language DB save error: {e}")

    if selected_lang == "am":
        text = (
            "✅ ቋንቋ ወደ አማርኛ ተቀይሯል!\n\n"
            "እንኳን ወደ Bahirab Quiz & Study Hub በደህና መጣችሁ።\n"
            "የተዘጋጁ የትምህርት ፈተናዎችንና ማቴሪያሎችን ለማግኘት ከታች ያለውን በተን ተጫኑ፦"
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=get_main_keyboard("am")
        )
    else:
        text = (
            "✅ Language set to English!\n\n"
            "Welcome to Bahirab Quiz & Study Hub.\n"
            "Click the button below to access study materials and exams:"
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=get_main_keyboard("en")
        )

# --- START COMMAND (with Major Bypass Check & One-Time Token Burn for Non-Notes) ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    user = message.from_user
    
    track_user_db(user)
    record_bot_interaction(user.id)
    
    text_parts = message.text.split()
    
    if len(text_parts) > 1:
        file_key = text_parts[1]
        lang = get_user_lang(user.id)
        user_id = str(user.id)
        
        if file_key in EXAMS:
            conn = sqlite3.connect('database.sqlite')
            c = conn.cursor()
            c.execute('SELECT 1 FROM unlocked_materials WHERE telegram_id = ? AND file_key = ?', (user_id, file_key))
            is_unlocked = c.fetchone()

            if not is_unlocked:
                conn.close()
                required_coins = 200 if str(file_key).startswith("guide_") else 100
                msg = (
                    f"⚠️ ይህንን ማቴሪያል ለማውረድ መጀመሪያ በ Mini App ውስጥ በ {required_coins} Coins መክፈት አለብዎት!"
                    if lang == "am" else
                    f"⚠️ Please unlock this material for {required_coins} Coins in the Mini App first!"
                )
                bot.send_message(chat_id, msg, reply_markup=get_main_keyboard(lang))
                return

            if not file_key.startswith("note_"):
                c.execute('DELETE FROM unlocked_materials WHERE telegram_id = ? AND file_key = ?', (user_id, file_key))

            c.execute('UPDATE users SET downloads = downloads + 1 WHERE telegram_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            exam = EXAMS[file_key]
            channel_to_use = exam.get("channel", EXAMS_CHANNEL)
            clean_channel_username = channel_to_use.replace("@", "")
            
            if exam["type"] == "link":
                post_url = f"https://t.me/{clean_channel_username}/{exam['msg_id']}"
                link_keyboard = InlineKeyboardMarkup()
                open_btn_text = "📖 ፈተናውን በቻናሉ ክፈቱ" if lang == "am" else "📖 Open in Channel"
                more_btn_text = "🔍 ተጨማሪ ጥያቄዎች ያግኙ" if lang == "am" else "🔍 Get More Questions"
                link_keyboard.add(InlineKeyboardButton(text=open_btn_text, url=post_url))
                link_keyboard.add(InlineKeyboardButton(text=more_btn_text, web_app=WebAppInfo(url=WEB_APP_URL)))
                msg = (
                    f"📖 {exam['name']}\n\n🔗 ፈተናውን ለማግኘት ከታች ያለውን ሊንክ ይጫኑ፦\n👉 {post_url}"
                    if lang == "am" else
                    f"📖 {exam['name']}\n\n🔗 Click the link below to access the exam:\n👉 {post_url}"
                )
                bot.send_message(chat_id, msg, reply_markup=link_keyboard)
            else:
                file_notice = (
                    f"📥 {exam['name']}\n\n✨ ፋይሉ ከታች ተልኮላችኋል 👇"
                    if lang == "am" else
                    f"📥 {exam['name']}\n\n✨ Your file has been sent below 👇"
                )
                bot.send_message(chat_id, file_notice)
                try:
                    bot.copy_message(
                        chat_id=chat_id,
                        from_chat_id=channel_to_use,
                        message_id=exam["msg_id"],
                        reply_markup=get_main_keyboard(lang)
                    )
                except Exception as e:
                    bot.send_message(chat_id, f"Error: {e}", reply_markup=get_main_keyboard(lang))
        else:
            error_msg = f"⚠️ ይቅርታ፣ የጠየቁት ፋይል ({file_key}) አልተገኘም (File not found)." if lang == "am" else f"⚠️ Sorry, the requested file ({file_key}) was not found."
            bot.send_message(chat_id, error_msg, reply_markup=get_main_keyboard(lang))
            
        return

    bot.reply_to(
        message,
        f"Hello {message.from_user.first_name}! 👋\n\n"
        "Welcome to Bahirab Study Hub.\n"
        "Please choose your language to start:",
        reply_markup=get_lang_selection_keyboard()
    )

# --- ❓ በስህተት የተላኩ ጽሑፎችን መከታተያ (በተማሪው ቋንቋ ምላሽ የሚሰጥ) ---
@bot.message_handler(func=lambda msg: True, content_types=['text', 'photo', 'video', 'voice', 'document', 'audio'])
def handle_unexpected_messages(message):
    user = message.from_user
    user_id = str(user.id)

    track_user_db(user)
    record_bot_interaction(user_id)

    if user_id == str(ADMIN_ID):
        return

    lang = get_user_lang(user_id)
    msg_content = message.text or f"[{message.content_type}]"

    def alert_unknown():
        try:
            admin_alert = (
                f"❓ <b>ያልታወቀ/የተሳሳተ መልዕክት ደረሰ!</b>\n\n"
                f"👤 <b>ተማሪ፦</b> {user.first_name} (@{user.username or 'No Username'})\n"
                f"🆔 <b>ID፦</b> <code>{user_id}</code>\n"
                f"🌐 <b>ቋንቋ፦</b> {lang.upper()}\n"
                f"💬 <b>የላከው፦</b>\n{msg_content}"
            )
            reply_kb = InlineKeyboardMarkup()
            reply_kb.add(InlineKeyboardButton(text="↩️ መልስ ስጥ (Reply)", callback_data=f"admin_reply_{user_id}"))
            bot.send_message(int(ADMIN_ID), admin_alert, parse_mode="HTML", reply_markup=reply_kb)
        except Exception as e:
            print(f"Unknown msg alert error: {e}")

    threading.Thread(target=alert_unknown).start()

    if lang == "en":
        response_text = (
            "⚠️ Sorry, unrecognized message or command.\n\n"
            "📚 Please tap the <b>'Open App'</b> button below to access study materials, or click <b>'Feedback'</b>."
        )
    else:
        response_text = (
            "⚠️ ይቅርታ፣ ያልታወቀ መልዕክት ወይም ትዕዛዝ ነው።\n\n"
            "📚 ጥያቄዎችን፣ ፈተናዎችን እና ኖቶችን ለማግኘት ከታች ያለውን <b>'Open App'</b> በተን ይጫኑ ወይም አስተያየት ለመስጠት <b>'አስተያየት'</b> የሚለውን ይምረጡ።"
        )
    bot.reply_to(message, response_text, parse_mode="HTML", reply_markup=get_main_keyboard(lang))

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("✅ Web Server started...")

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"Webhook reset note: {e}")

    print("✅ Bahirab Quiz Hub Bot ዝግጁ ነው...")
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True, 
                timeout=20, 
                long_polling_timeout=20,
                allowed_updates=['message', 'callback_query', 'my_chat_member', 'chat_member', 'message_reaction']
            )
        except Exception as e:
            print(f"Polling conflict handled, retrying in 5s: {e}")
            time.sleep(5)
