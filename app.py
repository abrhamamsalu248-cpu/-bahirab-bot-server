import os
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# --- Render Web Service Port Fix ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bahirab Quiz Hub Bot is Running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- TELEGRAM BOT CONFIGURATION ---
BOT_TOKEN = "8908510416:AAHFV0V2wydcDc4ZKoNGgh5VsP7ceavHBwo"
bot = telebot.TeleBot(BOT_TOKEN)

CHANNEL_ID = "@BahirabAcademy"
CHANNEL_USERNAME = "BahirabAcademy"
WEB_APP_URL = "https://abrhamamsalu248-cpu.github.io/Bahirab-Quiz/"

USERS_FILE = "users_detailed.txt"
total_downloads = 0
user_languages = {}

def track_user_info(user):
    """ተጠቃሚው ቦቱን ሲጀምር ይመዘግባል (ቀደም ሲል ከሌለ)"""
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
                    if len(parts) >= 4:
                        if parts[0] == user_id:
                            user_exists = True
                        users_data.append(line.strip())
                    elif len(parts) >= 3:
                        # የድሮውን ፎርማት ወደ አዲሱ (ውርዶች ብዛት ጨምሮ) ማስተካከል
                        if parts[0] == user_id:
                            user_exists = True
                            users_data.append(f"{parts[0]} | {parts[1]} | {parts[2]} | 0")
                        else:
                            users_data.append(f"{parts[0]} | {parts[1]} | {parts[2]} | 0")
                            
        if not user_exists:
            users_data.append(f"{user_id} | {name} | {username} | 0")
            
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            for item in users_data:
                f.write(item + "\n")
    except Exception as e:
        print(f"Tracking error: {e}")

def increment_user_download(user_id):
    """አንድ ተጠቃሚ ፋይል ሲያወርድ የውርዶች ብዛቱን በአንድ ይጨምራል"""
    try:
        user_id = str(user_id)
        users_data = []
        
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(" | ")
                    if len(parts) >= 4:
                        u_id, u_name, u_user, u_downloads = parts[0], parts[1], parts[2], int(parts[3])
                        if u_id == user_id:
                            u_downloads += 1
                        users_data.append(f"{u_id} | {u_name} | {u_user} | {u_downloads}")
                    else:
                        users_data.append(line.strip())
                        
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                for item in users_data:
                    f.write(item + "\n")
    except Exception as e:
        print(f"Increment download error: {e}")

def get_users_list():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

EXAMS = {
    "global_trend_2015": {"name": "Global Trend Final Exam 2015", "msg_id": 3, "type": "file"},
    "history_2015": {"name": "History Mid Exam 2015", "msg_id": 4, "type": "file"},
    "geography_final": {"name": "Geography Final Exam", "msg_id": 5, "type": "file"},
    "emerging_tech_mid": {"name": "Emerging Technology Mid Exam", "msg_id": 6, "type": "file"},
    "civics_mid": {"name": "Civics Mid Exam", "msg_id": 7, "type": "file"},
    "logic_final": {"name": "Logic Final Exam", "msg_id": 8, "type": "file"},
    "freshman_app": {"name": "Freshman Modules and Exams Application", "msg_id": 9, "type": "file"},
    "inclusiveness_2014": {"name": "Inclusiveness Mid Exam 2014", "msg_id": 12, "type": "file"},
    "psychology_mid": {"name": "General Psychology Mid Exam", "msg_id": 13, "type": "file"},
    "chemistry_mid": {"name": "General Chemistry Mid Exam", "msg_id": 14, "type": "file"},
    "geography_2014": {"name": "Geography Mid Exam 2014", "msg_id": 15, "type": "file"},
    "physics_mid": {"name": "General Physics Mid Exam", "msg_id": 17, "type": "file"},
    "logic_mid": {"name": "Logic Mid Exam", "msg_id": 18, "type": "file"},
    "applied_math_mid": {"name": "Applied Mathematics Mid Exam", "msg_id": 21, "type": "file"},
    "cpp_mid": {"name": "C++ BDU Mid Exam", "msg_id": 22, "type": "file"},
    "history_mid_2016": {"name": "History Mid Exam 2016", "msg_id": 23, "type": "file"},
    "emerging_tech_2016": {"name": "Emerging Technology Mid Exam 2016", "msg_id": 24, "type": "file"},
    "global_trend_2016": {"name": "Global Trend Mid Exam 2016", "msg_id": 26, "type": "file"},
    "anthro_mid_2016": {"name": "Anthropology Mid Exam 2016", "msg_id": 28, "type": "file"},
    "econ_mid_2016": {"name": "Economic Mid Exam 2016", "msg_id": 29, "type": "file"},
    "history_final_2016": {"name": "History Final Exam 2016", "msg_id": 30, "type": "file"},
    "econ_final_2016": {"name": "Economics Final Exam 2016", "msg_id": 31, "type": "file"},
    "anthro_final_2016": {"name": "Anthropology Final Exam 2016", "msg_id": 32, "type": "file"},
    "emerging_tech_final": {"name": "Emerging Technology Final Exam", "msg_id": 34, "type": "file"},
    "math_social_mid": {"name": "Mathematics For Social Mid Exam", "msg_id": 35, "type": "file"},
    "math_social_mid_2016": {"name": "Mathematics For Social Mid Exam 2016", "msg_id": 37, "type": "file"},
    "geography_mid_2016": {"name": "Geography Mid Exam 2016", "msg_id": 38, "type": "file"},
    "applied_math_one_final": {"name": "Applied Mathematics One Final Exam", "msg_id": 46, "type": "file"},
    "moral_civic_mid_2016": {"name": "Moral and Civic Education Mid Exam 2016", "msg_id": 149, "type": "file"},
    "geography_mid_2016_b": {"name": "Geography Mid Exam 2016", "msg_id": 150, "type": "file"},
    "geography_mid_other": {"name": "Geography Mid Exam 2016 Other Semester", "msg_id": 151, "type": "file"},
    "logic_mid_2016": {"name": "Logic Mid Exam 2016", "msg_id": 152, "type": "file"},
    "history_mid_b": {"name": "History Mid Exam", "msg_id": 153, "type": "file"},
    "entrepreneurship_mid_2016": {"name": "Entrepreneurship Mid Exam 2016", "msg_id": 155, "type": "file"},
    "history_final_2015_b": {"name": "History Final Exam 2015", "msg_id": 163, "type": "file"},
    "math_natural_final": {"name": "Mathematics For Natural Final Exam", "msg_id": 165, "type": "file"},
    "math_final_2016": {"name": "Mathematics Final Exam 2016", "msg_id": 167, "type": "link"},
    "history_final_academy": {"name": "History Final Exam", "msg_id": 168, "type": "file"},
    "applied_math_one_final_b": {"name": "Applied Mathematics One Final Exam", "msg_id": 169, "type": "file"},
    "history_final_2016_2": {"name": "History 2016 Final Exam", "msg_id": 170, "type": "file"},
    "math_social_final": {"name": "Mathematics For Social Final Exam", "msg_id": 171, "type": "file"},
    "comm_skills_final": {"name": "Communication Skills One English Final Exam", "msg_id": 174, "type": "file"},
    "psychology_final": {"name": "General Psychology Final Exam", "msg_id": 175, "type": "file"},
    "global_final_176": {"name": "Global Final Exam", "msg_id": 176, "type": "file"},
    "global_trend_2015_b": {"name": "Global Trend Final Exam 2015", "msg_id": 177, "type": "file"},
    "global_final_179": {"name": "Global Final Exam", "msg_id": 179, "type": "link"},
    "civics_final_2016": {"name": "Civics Final Exam 2016", "msg_id": 180, "type": "file"},
    "civics_final_2023": {"name": "Civics Final Exam 2023", "msg_id": 182, "type": "file"},
    "civics_final_187": {"name": "Civics Final Exam", "msg_id": 187, "type": "link"},
    "civics_final_192": {"name": "Civics Final Exam", "msg_id": 192, "type": "link"},
    "moral_civic_final_193": {"name": "Moral & Civic Education Final Exam", "msg_id": 193, "type": "file"},
    "econ_final_2016_b": {"name": "Economics Final Exam 2016", "msg_id": 196, "type": "file"},
    "econ_final_2013": {"name": "Economics Final Exam 2013", "msg_id": 197, "type": "file"},
    "econ_final_2015": {"name": "Economics Final Exam 2015", "msg_id": 198, "type": "file"},
    "emerging_tech_2014": {"name": "Emerging Technology Final Exam 2014", "msg_id": 201, "type": "link"},
    "emerging_tech_2015": {"name": "Emerging Technology Final Exam 2015", "msg_id": 202, "type": "file"},
    "emerging_tech_203": {"name": "Emerging Technology Final Exam", "msg_id": 203, "type": "file"},
    "geography_final_204": {"name": "Geography Final Exam", "msg_id": 204, "type": "file"},
    "geography_final_2016": {"name": "Geography Final Exam 2016", "msg_id": 210, "type": "link"},
    "geography_final_213": {"name": "Geography Final Exam", "msg_id": 213, "type": "link"},
    "entrepreneurship_final_2016": {"name": "Entrepreneurship Final Exam 2016", "msg_id": 215, "type": "file"},
    "entrepreneurship_final_2015": {"name": "Entrepreneurship Final Exam 2015", "msg_id": 216, "type": "file"},
    "logic_final_219": {"name": "Logic Final Exam", "msg_id": 219, "type": "link"},
    "logic_final_2014": {"name": "Logic Final Exam 2014", "msg_id": 220, "type": "file"},
    "logic_final_2021": {"name": "Logic Final Exam 2021", "msg_id": 221, "type": "file"},
    "anthro_final_2015": {"name": "Anthropology Final Exam 2015", "msg_id": 222, "type": "file"},
    "anthro_final_2016_b": {"name": "Anthropology Final Exam 2016", "msg_id": 223, "type": "file"},
    "physics_final_224": {"name": "General Physics Final Exam", "msg_id": 224, "type": "file"},
    "logic_final_2017": {"name": "Logic Final Exam 2017", "msg_id": 226, "type": "file"},
    "geography_final_2017": {"name": "Geography Final Exam 2017", "msg_id": 227, "type": "file"},
    "anthro_mid_2017": {"name": "Anthropology Mid Exam 2017", "msg_id": 318, "type": "file"},
    "critical_thinking_mid_2017": {"name": "Critical Thinking Mid Exam 2017", "msg_id": 319, "type": "file"},
    "global_trend_mid_2017": {"name": "Global Trend Mid Exam 2017", "msg_id": 320, "type": "file"},
    "geography_mid_2017": {"name": "Geography Mid Exam 2017", "msg_id": 321, "type": "file"},
    "econ_mid_2017": {"name": "Economics Mid Exam 2017", "msg_id": 322, "type": "file"},
    "moral_civic_mid_323": {"name": "Moral and Civic Education Mid Exam 2016", "msg_id": 323, "type": "file"},
    "math_social_mid_325": {"name": "Mathematics Mid Exam For Social", "msg_id": 325, "type": "file"},
    "comm_english_two_2016": {"name": "Communication English Skills Two Mid Exam 2016", "msg_id": 326, "type": "file"},
    "comm_english_two_b": {"name": "Communication English Skills Two Mid Exam", "msg_id": 327, "type": "file"},
    "comm_english_two_2017": {"name": "Communication English Skills Two Mid Exam 2016/17", "msg_id": 328, "type": "file"},
    "history_mid_2017": {"name": "History Mid Exam 2017", "msg_id": 329, "type": "file"},
    "psychology_330": {"name": "General Psychology Material / Exam", "msg_id": 330, "type": "file"},
    "comm_english_two_final_406": {"name": "Communication English Skills Two Final Exam 2017", "msg_id": 406, "type": "file"},
    "global_trend_final_790": {"name": "Global Trend Final Exam 2017", "msg_id": 790, "type": "file"},
    "entrepreneurship_final_785": {"name": "Entrepreneurship Final Exam 2017", "msg_id": 785, "type": "file"},
    "psychology_final_793": {"name": "General Psychology Final Exam 2017", "msg_id": 793, "type": "file"},
    "psychology_final_794": {"name": "General Psychology Final Exam 2017 Other Semester", "msg_id": 794, "type": "file"},
    "logic_final_802": {"name": "Logic Final Exam", "msg_id": 802, "type": "link"},
    "logic_final_808": {"name": "Logic Final Exam 2017", "msg_id": 808, "type": "file"},
    "logic_final_809": {"name": "Logic Final Exam 2017 Other Semester", "msg_id": 809, "type": "file"},
    "econ_final_814": {"name": "Economics Final Exam 2017", "msg_id": 814, "type": "file"},
    "logic_final_818": {"name": "Logic Final Exam 2017", "msg_id": 818, "type": "link"},
    "comm_skills_one_822": {"name": "Communication Skills One English Final Exam", "msg_id": 822, "type": "file"},
    "comm_skills_one_823": {"name": "Communication Skills One English Final Exam 2017", "msg_id": 823, "type": "link"},
    "comm_skills_one_827": {"name": "Communication Skills One English Final Exam 2017", "msg_id": 827, "type": "file"},

    # አዲስ የተጨመሩ (ለአፑ እንዲሰሩ የተደረጉ)
    "psychology_final_2016": {"name": "General Psychology Final Exam", "msg_id": 175, "type": "file"},
    "english_final_2016": {"name": "Communication Skills English Final Exam", "msg_id": 174, "type": "file"},
    "english_mid_2016": {"name": "Communication English Skills Two Mid Exam", "msg_id": 326, "type": "file"},
    "civics_final_2015": {"name": "Civics Final Exam 2016", "msg_id": 180, "type": "file"},
    "civics_mid_2016": {"name": "Civics Mid Exam 2016", "msg_id": 149, "type": "file"},
    "global_final_2016": {"name": "Global Final Exam", "msg_id": 176, "type": "file"},
    "global_mid_2016": {"name": "Global Trend Mid Exam 2016", "msg_id": 26, "type": "file"},
    "emerging_final_2016": {"name": "Emerging Technology Final Exam", "msg_id": 34, "type": "file"},
    "emerging_mid_2016": {"name": "Emerging Technology Mid Exam 2016", "msg_id": 24, "type": "file"}
}

def get_main_keyboard(lang="am"):
    btn_text = "🔍 ተጨማሪ ጥያቄዎች ያግኙ (Open App)" if lang == "am" else "🔍 Get More Questions & Exams"
    lang_btn_text = "🌐 ቋንቋ ቀይሩ (Change Language)" if lang == "am" else "🌐 Change Language"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text=btn_text, web_app=WebAppInfo(url=WEB_APP_URL)))
    keyboard.add(InlineKeyboardButton(text=lang_btn_text, callback_data="change_lang"))
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
        
        recent_users = users[-20:]
        lines = []
        for u in recent_users:
            parts = u.split(" | ")
            if len(parts) >= 4:
                u_id, u_name, u_user, u_downloads = parts[0], parts[1], parts[2], parts[3]
                lines.append(f"• ID: {u_id} | 👤 {u_name} ({u_user}) - 📥 {u_downloads} ውርዶች")
            elif len(parts) >= 3:
                u_id, u_name, u_user = parts[0], parts[1], parts[2]
                lines.append(f"• ID: {u_id} | 👤 {u_name} ({u_user}) - 📥 0 ውርዶች")
            else:
                lines.append(f"• {u}")
                
        user_list_str = "\n".join(lines) if lines else "ምንም ተጠቃሚ የለም"
        
        stats_msg = (
            "📊 Bahirab Bot Analytics\n\n"
            f"👥 ጠቅላላ ተጠቃሚዎች: {total_u}\n"
            f"📥 አጠቃላይ የተወረዱ ፈተናዎች: {total_downloads} ጊዜ\n\n"
            f"📝 የቅርብ ተጠቃሚዎች ዝርዝር (ከነ ውርዳቸው ብዛት)፦\n{user_list_str}"
        )
        bot.send_message(message.chat.id, stats_msg)
    except Exception as e:
        bot.send_message(message.chat.id, f"Stats Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_") or call.data == "change_lang")
def handle_language_choice(call):
    chat_id = call.message.chat.id
    if call.data == "change_lang":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="🌐 እባክዎ ቋንቋ ይምረጡ / Please select your language:",
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
    global total_downloads
    chat_id = message.chat.id
    user = message.from_user
    
    # ተጠቃሚውን መዝግብ (አዲስ ከሆነ)
    track_user_info(user)
    
    text_parts = message.text.split()
    lang = user_languages.get(chat_id, "am")
    
    # ተጠቃሚው ከአፑ ውስጥ ማቴሪያል ከፍቶ ሲመጣ (በ Parameter)
    if len(text_parts) > 1:
        file_key = text_parts[1]
        
        # የተጠየቀው ፋይል ካለ
        if file_key in EXAMS:
            total_downloads += 1
            # የዚህን ተጠቃሚ የግል ውርዶች ብዛት በአንድ እንጨምራለን
            increment_user_download(user.id)
            
            exam = EXAMS[file_key]
            
            if exam["type"] == "link":
                post_url = f"https://t.me/{CHANNEL_USERNAME}/{exam['msg_id']}"
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
                    f"📥 {exam['name']}\n\n✨ ፈተናው ከታች ተልኮላችኋል 👇"
                    if lang == "am" else
                    f"📥 {exam['name']}\n\n✨ Your exam has been sent below 👇"
                )
                bot.send_message(chat_id, file_notice)
                try:
                    # ፋይሉን ከዋናው ቻናል በቀጥታ ወደ ተጠቃሚው ይልካል
                    bot.copy_message(
                        chat_id=chat_id,
                        from_chat_id=CHANNEL_ID,
                        message_id=exam["msg_id"],
                        reply_markup=get_main_keyboard(lang)
                    )
                except Exception as e:
                    bot.send_message(chat_id, f"Error: {e}", reply_markup=get_main_keyboard(lang))
        else:
            error_msg = f"⚠️ ይቅርታ፣ የጠየቁት ፋይል ({file_key}) አልተገኘም (File not found)." if lang == "am" else f"⚠️ Sorry, the requested file ({file_key}) was not found."
            bot.send_message(chat_id, error_msg, reply_markup=get_main_keyboard(lang))
            
        return

    # ምንም Parameter ሳይኖር ንጹህ /start ብቻ ሲመጣ (አዲስ ተጠቃሚ)
    bot.reply_to(
        message,
        f"ሰላም {message.from_user.first_name}!\n\n"
        "🌐 እባክዎ ቋንቋ ይምረጡ / Please choose your language:",
        reply_markup=get_lang_selection_keyboard()
    )

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    print("✅ Bahirab Quiz Hub Bot ዝግጁ ነው...")
    bot.infinity_polling(none_stop=True)
