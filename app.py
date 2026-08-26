import os
import threading
import time
import hmac
import hashlib
import json
import sqlite3
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

# --- SQLite Database Setup for Coins ---
def init_db():
    conn = sqlite3.connect('database.sqlite')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_coins (
        telegram_id TEXT PRIMARY KEY,
        first_name TEXT,
        coins INTEGER DEFAULT 300,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

# --- TELEGRAM BOT CONFIGURATION ---
BOT_TOKEN = "8908510416:AAHFV0V2wydcDc4ZKoNGgh5VsP7ceavHBwo"
bot = telebot.TeleBot(BOT_TOKEN)

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

@app.route('/')
def home():
    return "Bahirab Quiz Hub Bot is Running 24/7!"

# 1. የተጠቃሚውን ነጥብ ማመሳሰል (Get Balance / Register)
@app.route('/api/user/sync', methods=['POST'])
def sync_user():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user = verify_telegram_data(data.get('initData'))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = str(user.get('id'))
        first_name = user.get('first_name', 'Student')

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT coins FROM user_coins WHERE telegram_id = ?', (user_id,))
        row = c.fetchone()

        if row:
            coins = row[0]
        else:
            coins = 300
            c.execute('INSERT INTO user_coins (telegram_id, first_name, coins) VALUES (?, ?, ?)', (user_id, first_name, coins))
            conn.commit()

        conn.close()
        return jsonify({"coins": coins}), 200
    except Exception as e:
        print(f"Sync error: {e}")
        return jsonify({"error": "Server error"}), 500

# 2. ነጥብ መቀነስ/መጨመር (Update Coins - Quiz / Ads)
@app.route('/api/user/update-coins', methods=['POST'])
def update_user_coins():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user = verify_telegram_data(data.get('initData'))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = str(user.get('id'))
        amount = int(data.get('amount', 0))

        # የነጥብ መጠን ማረጋገጫ (አንድ ጊዜ ከ 150 በላይ እንዳይጨመር)
        if amount > 150 or amount < -100:
            return jsonify({"error": "Invalid amount"}), 400

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT coins FROM user_coins WHERE telegram_id = ?', (user_id,))
        row = c.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "User not found"}), 404

        new_coins = max(0, row[0] + amount)
        c.execute('UPDATE user_coins SET coins = ? WHERE telegram_id = ?', (new_coins, user_id))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "coins": new_coins}), 200
    except Exception as e:
        print(f"Update coins error: {e}")
        return jsonify({"error": "Server error"}), 500

# 3. ፈተና ወይም ሞጁል በ 100 Coins መክፈቻ API
@app.route('/api/user/unlock-material', methods=['POST'])
def unlock_material_api():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user = verify_telegram_data(data.get('initData'))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = str(user.get('id'))
        file_key = data.get('fileKey')

        conn = sqlite3.connect('database.sqlite')
        c = conn.cursor()
        c.execute('SELECT coins FROM user_coins WHERE telegram_id = ?', (user_id,))
        row = c.fetchone()

        if not row or row[0] < 100:
            conn.close()
            return jsonify({"success": False, "message": "በቂ Coins የለዎትም!"}), 400

        new_coins = row[0] - 100
        c.execute('UPDATE user_coins SET coins = ? WHERE telegram_id = ?', (new_coins, user_id))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "coins": new_coins, "fileKey": file_key}), 200
    except Exception as e:
        print(f"Unlock error: {e}")
        return jsonify({"error": "Server error"}), 500

# 📺 ተጠቃሚው አድ ሲያይ ከሚኒ አፑ መረጃ የሚቀበልበት API
@app.route('/api/track-ad', methods=['POST'])
def track_ad_view():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_id = data.get('user_id')
        if user_id:
            increment_user_ad(user_id)
            return jsonify({"status": "success", "user_id": user_id}), 200
    except Exception as e:
        print(f"Track ad error: {e}")
    return jsonify({"status": "error"}), 400

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# 2ቱ ዋና ዋና ቻናሎች
EXAMS_CHANNEL = "@BahirabAcademy"
MODULES_CHANNEL = "@bahirabquiz"

WEB_APP_URL = "https://abrhamamsalu248-cpu.github.io/Bahirab-Quiz/"
ADMIN_ID = "7105615214"

# ቋሚ የ Menu Button ማዘጋጃ (በቋሚነት ከታች የሚቀመጠው በተን)
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

USERS_FILE = "users_detailed.txt"
FEEDBACK_FILE = "feedback.txt"
user_languages = {}

def track_user_info(user):
    try:
        user_id = str(user.id)
        name = (user.first_name or "Student").replace("|", "-").replace("\n", " ")
        username = f"@{user.username}" if user.username else "No Username"
        
        users_data = []
        user_exists = False
        
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(" | ")
                    if len(parts) >= 5:
                        if parts[0] == user_id:
                            user_exists = True
                        users_data.append(line.strip())
                    elif len(parts) == 4:
                        if parts[0] == user_id:
                            user_exists = True
                        users_data.append(f"{parts[0]} | {parts[1]} | {parts[2]} | {parts[3]} | 0")
                    elif len(parts) >= 3:
                        if parts[0] == user_id:
                            user_exists = True
                        users_data.append(f"{parts[0]} | {parts[1]} | {parts[2]} | 0 | 0")
                            
        if not user_exists:
            users_data.append(f"{user_id} | {name} | {username} | 0 | 0")
            
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            for item in users_data:
                f.write(item + "\n")
    except Exception as e:
        print(f"Tracking error: {e}")

def increment_user_download(user_id):
    try:
        user_id = str(user_id)
        users_data = []
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(" | ")
                    if len(parts) >= 5:
                        u_id, u_name, u_user, u_dl, u_ads = parts[0], parts[1], parts[2], int(parts[3]), int(parts[4])
                        if u_id == user_id:
                            u_dl += 1
                        users_data.append(f"{u_id} | {u_name} | {u_user} | {u_dl} | {u_ads}")
                    elif len(parts) >= 4:
                        u_id, u_name, u_user, u_dl = parts[0], parts[1], parts[2], int(parts[3])
                        if u_id == user_id:
                            u_dl += 1
                        users_data.append(f"{u_id} | {u_name} | {u_user} | {u_dl} | 0")
                    else:
                        users_data.append(line.strip())
                        
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                for item in users_data:
                    f.write(item + "\n")
    except Exception as e:
        print(f"Increment download error: {e}")

def increment_user_ad(user_id):
    try:
        user_id = str(user_id)
        users_data = []
        user_found = False
        
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(" | ")
                    if len(parts) >= 5:
                        u_id, u_name, u_user, u_dl, u_ads = parts[0], parts[1], parts[2], int(parts[3]), int(parts[4])
                        if u_id == user_id:
                            u_ads += 1
                            user_found = True
                        users_data.append(f"{u_id} | {u_name} | {u_user} | {u_dl} | {u_ads}")
                    elif len(parts) == 4:
                        u_id, u_name, u_user, u_dl = parts[0], parts[1], parts[2], int(parts[3])
                        u_ads = 1 if u_id == user_id else 0
                        if u_id == user_id:
                            user_found = True
                        users_data.append(f"{u_id} | {u_name} | {u_user} | {u_dl} | {u_ads}")
                    else:
                        users_data.append(line.strip())
                        
        if not user_found:
            users_data.append(f"{user_id} | User | No Username | 0 | 1")
            
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            for item in users_data:
                f.write(item + "\n")
    except Exception as e:
        print(f"Increment ad error: {e}")

def get_users_list():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

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
    "mod_math_social": {"name": "Mathematics for Social Sciences Module", "msg_id": 19, "type": "file", "channel": MODULES_CHANNEL}
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

# --- STATS COMMAND ---
@bot.message_handler(commands=['stats', 'States', 'stat'])
def handle_stats(message):
    try:
        users = get_users_list()
        total_u = len(users)
        
        total_d = 0
        total_a = 0
        
        recent_users = users[-20:]
        lines = []
        for u in users:
            parts = u.split(" | ")
            if len(parts) >= 5:
                if parts[3].isdigit(): total_d += int(parts[3])
                if parts[4].isdigit(): total_a += int(parts[4])
            elif len(parts) >= 4:
                if parts[3].isdigit(): total_d += int(parts[3])
                
        for u in recent_users:
            parts = u.split(" | ")
            if len(parts) >= 5:
                u_id, u_name, u_user, u_dl, u_ads = parts[0], parts[1], parts[2], parts[3], parts[4]
                lines.append(f"• ID: {u_id} | 👤 {u_name} ({u_user})\n   ↳ 📥 {u_dl} ውርዶች | 📺 {u_ads} ማስታወቂያዎች")
            elif len(parts) >= 4:
                u_id, u_name, u_user, u_dl = parts[0], parts[1], parts[2], parts[3]
                lines.append(f"• ID: {u_id} | 👤 {u_name} ({u_user})\n   ↳ 📥 {u_dl} ውርዶች | 📺 0 ማስታወቂያዎች")
            else:
                lines.append(f"• {u}")
                
        user_list_str = "\n\n".join(lines) if lines else "ምንም ተጠቃሚ የለም"
        
        stats_msg = (
            "📊 Bahirab Bot Analytics\n\n"
            f"👥 ጠቅላላ ተጠቃሚዎች: {total_u}\n"
            f"📥 አጠቃላይ የተወረዱ ፈተናዎች: {total_d} ጊዜ\n"
            f"📺 የታዩ ማስታወቂያዎች: {total_a} ጊዜ\n\n"
            f"📝 የቅርብ ተጠቃሚዎች ዝርዝር፦\n\n{user_list_str}"
        )
        bot.send_message(message.chat.id, stats_msg)
    except Exception as e:
        bot.send_message(message.chat.id, f"Stats Error: {e}")

# --- FEEDBACK BUTTON & HANDLER ---
@bot.callback_query_handler(func=lambda call: call.data == "give_feedback")
def feedback_prompt(call):
    chat_id = call.message.chat.id
    lang = user_languages.get(chat_id, "am")
    prompt_text = (
        "✍️ እባክዎ ስለ ቦቱ፣ ፈተናዎች ወይም ማቴሪያሎች ያሎትን አስተያየት ወይም ጥያቄ ከዚህ በታች ይጻፉልን:"
        if lang == "am" else
        "✍️ Please type your feedback, suggestion, or question below:"
    )
    sent_msg = bot.send_message(chat_id, prompt_text)
    bot.register_next_step_handler(sent_msg, save_and_forward_feedback)

def save_and_forward_feedback(message):
    user = message.from_user
    feedback_text = message.text or ""
    chat_id = message.chat.id
    lang = user_languages.get(chat_id, "am")
    
    # አስተያየቱን ሰርቨሩ ላይ ባለው የጽሑፍ ፋይል ውስጥ መዝግቦ መያዝ
    try:
        with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(f"ID: {user.id} | Name: {user.first_name} | Username: @{user.username} | Text: {feedback_text}\n")
    except Exception as err:
        print(f"File log error: {err}")

    # ለአድሚን የሚላከው ማሳወቂያ እና የመልስ መስጫ በተን (Reply Button)
    admin_notification = (
        "📩 አዲስ አስተያየት መጣ! (New Feedback)\n\n"
        f"👤 ከ: {user.first_name} (@{user.username if user.username else 'No Username'})\n"
        f"🆔 ID: {user.id}\n\n"
        f"💬 አስተያየት፦\n{feedback_text}"
    )
    
    reply_kb = InlineKeyboardMarkup()
    reply_kb.add(InlineKeyboardButton(text="↩️ ለተጠቃሚው መልስ ስጥ (Reply)", callback_data=f"admin_reply_{user.id}"))
    
    try:
        bot.send_message(int(ADMIN_ID), admin_notification, reply_markup=reply_kb)
    except Exception as e:
        print(f"Admin forward warning: {e}")

    # ለተጠቃሚው የተላከበትን ማረጋገጫ መስጠት
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
        user_lang = user_languages.get(int(target_user_id), "am")
        header = "📩 ከአስተዳዳሪው የተላከ መልስ፦\n\n" if user_lang == "am" else "📩 Reply from Admin:\n\n"
        bot.send_message(int(target_user_id), header + reply_text, reply_markup=get_main_keyboard(user_lang))
        bot.reply_to(message, f"✅ መልስዎ ለተጠቃሚው (ID: {target_user_id}) በተሳካ ሁኔታ ተልኳል!")
    except Exception as e:
        bot.reply_to(message, f"❌ መልሱን መላክ አልተቻለም (ምናልባት ተጠቃሚው ቦቱን ዘግቶት ሊሆን ይችላል)፦ {e}")

# በትእዛዝ ለመመለስ: /reply <user_id> <message>
@bot.message_handler(commands=['reply'])
def handle_reply_command(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "⚠️ አጠቃቀም፦\n`/reply <USER_ID> <የመልስ_ጽሁፍ>`\n\nምሳሌ፦\n`/reply 12345678 ሰላም፣ ፈተናው ተስተካክሏል!`")
        return

    target_user_id = parts[1]
    reply_text = parts[2]

    try:
        user_lang = user_languages.get(int(target_user_id), "am")
        header = "📩 ከአስተዳዳሪው የተላከ መልስ፦\n\n" if user_lang == "am" else "📩 Reply from Admin:\n\n"
        bot.send_message(int(target_user_id), header + reply_text, reply_markup=get_main_keyboard(user_lang))
        bot.reply_to(message, f"✅ መልስዎ ለተጠቃሚው (ID: {target_user_id}) በተሳካ ሁኔታ ተልኳል!")
    except Exception as e:
        bot.reply_to(message, f"❌ መልሱን መላክ አልተቻለም፦ {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_") or call.data == "change_lang")
def handle_language_choice(call):
    chat_id = call.message.chat.id
    if call.data == "change_lang":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="🌐 Please choose your language / እባክዎ ቋንቋ ይምረጡ:",
            reply_markup=get_lang_selection_keyboard()
        )
        return

    if call.data == "lang_am":
        user_languages[chat_id] = "am"
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
    elif call.data == "lang_en":
        user_languages[chat_id] = "en"
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

@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    user = message.from_user
    
    track_user_info(user)
    
    text_parts = message.text.split()
    
    if len(text_parts) > 1:
        file_key = text_parts[1]
        lang = user_languages.get(chat_id, "am")
        
        if file_key in EXAMS:
            increment_user_download(user.id)
            
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
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"Polling conflict handled, retrying in 5s: {e}")
            time.sleep(5)
