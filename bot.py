# -*- coding: utf-8 -*-
import os
import sys
import re
import json
import time
import random
import secrets
import hashlib
import threading
import subprocess
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

_RAILWAY_RUNTIME = bool(os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RAILWAY_PROJECT_ID'))
BASE_PATH = os.environ.get('BASE_PATH') or ('/data' if _RAILWAY_RUNTIME else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'panel_data'))
os.makedirs(BASE_PATH, exist_ok=True)
USERS_FOLDER = os.path.join(BASE_PATH, 'users_data')
USERS_FILE = os.path.join(BASE_PATH, 'users.json')
IPS_FILE = os.path.join(BASE_PATH, 'ips_pool.json')
OWNER_CONFIG_FILE = os.path.join(BASE_PATH, 'owner_config.json')
os.makedirs(USERS_FOLDER, exist_ok=True)
USER_WRITE_LOCK = threading.Lock()

def load_json_file(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def save_json_file(path, data):
    try:
        temp = path + '.tmp'
        with open(temp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(temp, path)
        return True
    except Exception as e:
        print(f'[BOT] Could not save {os.path.basename(path)}: {e}', flush=True)
        return False

def load_users():
    data = load_json_file(USERS_FILE, {})
    return data if isinstance(data, dict) else {}

def save_users(data):
    return save_json_file(USERS_FILE, data)

def hash_user_password(password):
    return generate_password_hash(password)

def load_owner_config():
    return load_json_file(OWNER_CONFIG_FILE, {})

def escape_md2(text):
    return re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', str(text))

def load_ips():
    return load_json_file(IPS_FILE, {'available': [], 'assigned': {}})

def save_ips(data):
    return save_json_file(IPS_FILE, data)

def assign_ip(username):
    data = load_ips()
    if username in data.get('assigned', {}):
        return data['assigned'][username]
    available = data.get('available', [])
    if available:
        ip = available.pop(0)
    else:
        ip = f"{random.randint(45,185)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(2,254)}"
    data.setdefault('assigned', {})[username] = ip
    save_ips(data)
    return ip

try:
    try:
        import telebot
        from telebot import types
    except ImportError:
        print(" * [BOT] pyTelegramBotAPI is missing; installing it...", flush=True)
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', '--quiet',
            '--break-system-packages', 'pyTelegramBotAPI'
        ])
        import telebot
        from telebot import types
    import hashlib
    from datetime import datetime, timedelta

    cfg = load_owner_config()
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    if not TOKEN:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is missing')
    try:
        ADMIN_ID = int(str(os.environ.get('TELEGRAM_ADMIN_ID', '0') or '0').strip())
    except (TypeError, ValueError):
        ADMIN_ID = 0
        print(" * Telegram Bot: owner ID is empty/invalid; admin-only actions are disabled.", flush=True)
    bot = telebot.TeleBot(TOKEN)

    # إعدادات البوت (تُحفظ في ملف منفصل)
    BOT_SETTINGS_FILE = os.path.join(BASE_PATH, 'bot_settings.json')
    def load_bot_settings():
        return load_json_file(BOT_SETTINGS_FILE, {
            'force_channel': '@V_P1_V1',
            'force_channel2': '@VSA_A',
            'points_per_server': 10,
            'points_per_invite': 2,
            'dev_channel': 'https://t.me/S7_MX3',
            'dev_user': 'https://t.me/V2P_1',
            'admin_list': [],
            'codes': {},
            'panel_url': ''
        })

    def save_bot_settings(s):
        save_json_file(BOT_SETTINGS_FILE, s)

    def check_force_subscribe(user_id):
        settings = load_bot_settings()
        channels = [
            settings.get('force_channel', '').strip(),
            settings.get('force_channel2', '').strip(),
        ]
        channels = [c for c in channels if c]
        if not channels: return True
        for channel in channels:
            try:
                member = bot.get_chat_member(channel, user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    return False
            except Exception:
                return False
        return True

    def enforce_subscription(message):
        """فحص الاشتراك الإجباري في قناتين وإرسال رسالة التنبيه. يرجع True إذا مسموح."""
        settings = load_bot_settings()
        channels = [
            settings.get('force_channel', '').strip(),
            settings.get('force_channel2', '').strip(),
        ]
        channels = [c for c in channels if c]
        if not channels:
            return True
        unsubscribed = []
        for channel in channels:
            try:
                member = bot.get_chat_member(channel, message.from_user.id)
                if member.status not in ['member', 'administrator', 'creator']:
                    unsubscribed.append(channel)
            except Exception:
                unsubscribed.append(channel)
        if not unsubscribed:
            return True
        sep = "\u200B\n"
        prompt = (
            ">⛔ عـذراً\\!\n" + sep +
            ">لا يمكنك استخدام البوت قبل الاشتراك في القنوات\n" + sep +
            ">اشترك في القنوات ثم اضغط زر **تحققت من الاشتراك** 👇"
        )
        mk = types.InlineKeyboardMarkup(row_width=1)
        for channel in unsubscribed:
            chan_link = channel if channel.startswith('http') else f"https://t.me/{channel.lstrip('@')}"
            chan_name = channel.lstrip('@').replace('https://t.me/', '')
            mk.add(types.InlineKeyboardButton(f"🔔 اشترك في {chan_name}", url=chan_link))
        mk.add(types.InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_sub_verify"))
        bot.send_message(message.chat.id, prompt, parse_mode="MarkdownV2", reply_markup=mk)
        return False

    def is_admin(user_id):
        if user_id == ADMIN_ID: return True
        settings = load_bot_settings()
        return user_id in settings.get('admin_list', [])

    # الكيبوردات
    def main_keyboard(user_id):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.row("ملفي الشخصي")
        markup.row("إنشاء سيرفر", "شراء نقاط")
        markup.row("استخدام كود")
        markup.row("مساعدة", "إحالة")
        markup.row("المطور", "قناة المطور")
        if is_admin(user_id):
            markup.row("لوحة الأدمن")
        return markup

    def admin_keyboard():
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("إحصائيات", callback_data="admin_stats"),
            types.InlineKeyboardButton("فحص مستخدم", callback_data="admin_check_user"),
            types.InlineKeyboardButton("حظر مستخدم", callback_data="admin_ban"),
            types.InlineKeyboardButton("فك حظر", callback_data="admin_unban"),
            types.InlineKeyboardButton("إضافة أدمن", callback_data="admin_add_admin"),
            types.InlineKeyboardButton("حذف أدمن", callback_data="admin_del_admin"),
            types.InlineKeyboardButton("إضافة قناة إجبارية", callback_data="admin_add_channel"),
            types.InlineKeyboardButton("حذف قناة إجبارية", callback_data="admin_del_channel"),
            types.InlineKeyboardButton("إضافة كود", callback_data="admin_add_code"),
            types.InlineKeyboardButton("قائمة الأكواد", callback_data="admin_list_codes"),
            types.InlineKeyboardButton("قائمة السيرفرات", callback_data="admin_list_servers"),
            types.InlineKeyboardButton("إضافة نقاط", callback_data="admin_add_points"),
            types.InlineKeyboardButton("خصم نقاط", callback_data="admin_del_points"),
            types.InlineKeyboardButton("تكلفة السيرفر (نقاط)", callback_data="admin_set_server_cost"),
            types.InlineKeyboardButton("تعيين لينك اللوحة", callback_data="admin_set_panel_url")
        )
        return markup

    @bot.message_handler(commands=['start'])
    def start(message):
        if not enforce_subscription(message):
            return

        # منطق النقاط عند الدخول عبر رابط دعوة
        args = message.text.split()
        if len(args) > 1:
            inviter_id = int(args[1])
            if inviter_id != message.from_user.id:
                users = load_users()
                for u, data in users.items():
                    if data.get('telegram_id') == inviter_id:
                        settings = load_bot_settings()
                        data['points'] = data.get('points', 0) + settings.get('points_per_invite', 2)
                        save_users(users)
                        try:
                            bot.send_message(inviter_id, f"💰 لقد حصلت على {settings.get('points_per_invite', 2)} نقاط لأن صديقك اشترك عبر رابطك!")
                        except: pass
                        break

        first_name = message.from_user.first_name or "مستخدم"
        sep = "\u200B\n"
        welcome_caption = (
            ">أهـلاً بـك 𝗠𝗦 \\| إم إس فـي بـوت MS  VPS\n" + sep +
            ">هنـا تجـد سيـرفرات VPS بلـغـه بـايثـون\n" + sep +
            ">مميـزاتـنا  :\n" + sep +
            ">عـزل آمـن بيـن السـيرفـرات\n" + sep +
            ">حـمايـه قـويه ضـد الهجـمات\n" + sep +
            ">سـهـوله التحـكم فـي ملفـاتك\n" + sep +
            ">اسـتقـرار النـظام الـدائــم\n" + sep +
            ">مـراقـبه الشبـكه و حـمايه المـلفات من أي هجـمات\n" + sep +
            ">عـمل دائـم بـدون تـوقف أبـداً\n" + sep +
            ">*قـم بـالبــدء الآن نحـو القـمه*"
        )
        bot.send_photo(
            message.chat.id,
            photo="https://g.top4top.io/p_3832nmswi0.jpg",
            caption=welcome_caption,
            parse_mode="MarkdownV2",
            reply_markup=main_keyboard(message.from_user.id)
        )

    @bot.message_handler(func=lambda m: m.text == "ملفي الشخصي")
    def my_info(message):
        if not enforce_subscription(message): return
        users = load_users()
        ips_data = load_ips()
        assigned_ips = ips_data.get('assigned', {})

        # جمع كل السيرفرات (الحسابات) المرتبطة بهذا المستخدم
        my_servers = []
        for u, data in users.items():
            if data.get('telegram_id') == message.from_user.id:
                my_servers.append((u, data))

        if not my_servers:
            bot.send_message(message.chat.id, "❌ لم يتم العثور على حساب مرتبط بهذا التليجرام.\nقم بإنشاء حساب أولاً.")
            return

        settings = load_bot_settings()
        panel_url = settings.get('panel_url', '').strip()

        # أول حساب = البيانات الأساسية للمستخدم
        first_uname, first_data = my_servers[0]
        msg = f"👤 **ملفك الشخصي:**\n\n"
        msg += f"💰 النقاط: `{first_data.get('points', 0)}` نقطة\n"
        msg += f"🖥️ السيرفرات المتاحة: `{first_data.get('max_servers', 2)}`\n"
        msg += f"📅 تاريخ الإنشاء: `{first_data.get('created', '-')[:10]}`\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        msg += f"🖥️ **سيرفراتك ({len(my_servers)}):**\n\n"

        for idx, (uname, data) in enumerate(my_servers, 1):
            ip = assigned_ips.get(uname, 'غير متاح')
            password = '🔒 محفوظة بشكل مشفر'
            msg += f"**السيرفر {idx}:**\n"
            msg += f"  👤 المستخدم: `{uname}`\n"
            msg += f"  🔑 كلمة السر: `{password}`\n"
            msg += f"  🌐 الـ IP: `{ip}`\n\n"

        mk = types.InlineKeyboardMarkup()
        if panel_url:
            mk.add(types.InlineKeyboardButton("🌐 لوحة التحكم", url=panel_url))
        bot.send_message(message.chat.id, msg, parse_mode="Markdown",
                         reply_markup=mk if panel_url else None)

    @bot.message_handler(func=lambda m: m.text == "إنشاء سيرفر")
    def create_account_start(message):
        if not enforce_subscription(message): return
        users = load_users()
        user_data = None
        uname = None
        for u, data in users.items():
            if data.get('telegram_id') == message.from_user.id:
                user_data = data
                uname = u
                break
        if user_data:
            settings = load_bot_settings()
            cost = settings.get('points_per_server', 5)
            pts = user_data.get('points', 0)
            max_srv = user_data.get('max_servers', 1)
            mk = types.InlineKeyboardMarkup(row_width=1)
            mk.add(types.InlineKeyboardButton(
                f"🖥️ شراء سيرفر إضافي ({cost} نقطة) — رصيدك: {pts} نقطة",
                callback_data="buy_server_slot"
            ))
            bot.send_message(message.chat.id,
                f"✅ لديك حساب بالفعل!\n\n"
                f"👤 المستخدم: `{uname}`\n"
                f"🖥️ سيرفراتك المتاحة: `{max_srv}`\n"
                f"💰 رصيدك: `{pts}` نقطة\n\n"
                f"يمكنك زيادة عدد سيرفراتك بشراء سيرفر إضافي مقابل {cost} نقطة:",
                parse_mode="Markdown", reply_markup=mk)
            return
        msg = bot.send_message(message.chat.id, "🚀 أرسل اسم المستخدم الذي تريده (باللغة الإنجليزية):")
        bot.register_next_step_handler(msg, process_username)

    def process_username(message):
        if not enforce_subscription(message): return
        username = message.text.strip()
        if not username or not username.isalnum():
            bot.send_message(message.chat.id, "❌ اسم مستخدم غير صالح! استخدم أحرف وأرقام فقط.")
            return

        users = load_users()
        if username in users:
            bot.send_message(message.chat.id, "❌ اسم المستخدم هذا مأخوذ بالفعل.")
            return

        msg = bot.send_message(message.chat.id, "ارسل كلمة المرور التي تريدها:")
        bot.register_next_step_handler(msg, lambda m: process_password(m, username))

    def process_password(message, username):
        if not enforce_subscription(message): return
        password = message.text.strip()
        if len(password) < 6:
            bot.send_message(message.chat.id, "❌ كلمة المرور يجب أن تكون 6 أحرف على الأقل.")
            return

        users = load_users()
        users[username] = {
            'password': hash_user_password(password),
            'max_sessions': 999,
            'max_servers': 2,
            'points': 0,
            'main_file': 'main.py',
            'runtime': 'python',
            'runtime_version': '3.11',
            'access_token': secrets.token_urlsafe(32),
            'created': datetime.now().isoformat(),
            'expiry': None,
            'telegram_id': message.from_user.id,
            'banned': False
        }
        save_users(users)
        os.makedirs(os.path.join(USERS_FOLDER, username), exist_ok=True)
        assigned_ip = assign_ip(username)
        settings = load_bot_settings()
        panel_url = settings.get('panel_url', '').strip()
        first_name = message.from_user.first_name or username
        ip_str = escape_md2(assigned_ip or 'غير متاح')
        uname_str = escape_md2(username)
        pass_str = escape_md2(password)
        caption = (
            f">تـم إنشـاء السـيـرفر بـنجـاح  💫\n"
            f">\n"
            f">🌐 الـ IP  :  `{ip_str}`\n"
            f">إسم المسـتخدم  :  `{uname_str}`\n"
            f">كلـمـة المـرور  :  `{pass_str}`"
        )
        markup_photo = types.InlineKeyboardMarkup()
        if panel_url:
            markup_photo.add(types.InlineKeyboardButton("🌐 لوحة التحكم", url=panel_url))
        bot.send_photo(
            message.chat.id,
            photo="https://g.top4top.io/p_3832nmswi0.jpg",
            caption=caption,
            parse_mode="MarkdownV2",
            reply_markup=markup_photo if panel_url else None
        )

    @bot.message_handler(func=lambda m: m.text == "قناة المطور")
    def dev_channel_btn(message):
        if not enforce_subscription(message): return
        bot.send_message(message.chat.id, "📢 قناة المطور الرسمية :",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("📢 قناة الأدمن", url="https://t.me/S7_MX3")
            ))

    @bot.message_handler(func=lambda m: m.text == "المطور")
    def dev_user_btn(message):
        if not enforce_subscription(message): return
        bot.send_message(message.chat.id, "👨‍💻 مطور البوت:",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("💬 تواصل مع الأدمن", url="https://t.me/V2P_1")
            ))

    @bot.callback_query_handler(func=lambda call: call.data == "check_sub_verify")
    def check_sub_verify(call):
        bot.answer_callback_query(call.id)
        settings = load_bot_settings()
        channels = [
            settings.get('force_channel', '').strip(),
            settings.get('force_channel2', '').strip(),
        ]
        channels = [c for c in channels if c]
        unsubscribed = []
        for channel in channels:
            try:
                member = bot.get_chat_member(channel, call.from_user.id)
                if member.status not in ['member', 'administrator', 'creator']:
                    unsubscribed.append(channel)
            except:
                pass

        if not unsubscribed:
            pass  # تم التحقق - يكمل الكود بعدها
        else:
            sep = "\u200B\n"
            prompt = (
                ">❌ لم يتم التحقق من اشتراكك بعد\\!\n" + sep +
                ">تأكد أنك اشتركت في جميع القنوات ثم اضغط التحقق مجدداً 👇"
            )
            mk = types.InlineKeyboardMarkup(row_width=1)
            for channel in unsubscribed:
                chan_link = channel if channel.startswith('http') else f"https://t.me/{channel.lstrip('@')}"
                chan_name = channel.lstrip('@').replace('https://t.me/', '')
                mk.add(types.InlineKeyboardButton(f"🔔 اشترك في {chan_name}", url=chan_link))
            mk.add(types.InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_sub_verify"))
            try:
                bot.edit_message_text(prompt, call.message.chat.id, call.message.message_id,
                                      parse_mode="MarkdownV2", reply_markup=mk)
            except:
                bot.send_message(call.message.chat.id, prompt, parse_mode="MarkdownV2", reply_markup=mk)
            return

        # مشترك ✅ — احذف رسالة الاشتراك وابعت رسالة الترحيب
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        sep = "\u200B\n"
        welcome_caption = (
            ">أهـلاً بـك 𝗠𝗦 \\| إم إس فـي بـوت MS  VPS\n" + sep +
            ">هنـا تجـد سيـرفرات VPS بلـغـه بـايثـون\n" + sep +
            ">مميـزاتـنا  :\n" + sep +
            ">عـزل آمـن بيـن السـيرفـرات\n" + sep +
            ">حـمايـه قـويه ضـد الهجـمات\n" + sep +
            ">سـهـوله التحـكم فـي ملفـاتك\n" + sep +
            ">اسـتقـرار النـظام الـدائــم\n" + sep +
            ">مـراقـبه الشبـكه و حـمايه المـلفات من أي هجـمات\n" + sep +
            ">عـمل دائـم بـدون تـوقف أبـداً\n" + sep +
            ">*قـم بـالبــدء الآن نحـو القـمه*"
        )
        bot.send_photo(
            call.message.chat.id,
            photo="https://g.top4top.io/p_3832nmswi0.jpg",
            caption=welcome_caption,
            parse_mode="MarkdownV2",
            reply_markup=main_keyboard(call.from_user.id)
        )

    @bot.callback_query_handler(func=lambda call: call.data == "buy_server_slot")
    def buy_server_slot(call):
        bot.answer_callback_query(call.id)
        users = load_users()
        settings = load_bot_settings()
        cost = settings.get('points_per_server', 10)
        for uname, data in users.items():
            if data.get('telegram_id') == call.from_user.id:
                pts = data.get('points', 0)
                if pts < cost:
                    bot.send_message(call.message.chat.id,
                        f"❌ رصيدك غير كافٍ!\n\n"
                        f"💰 رصيدك: `{pts}` نقطة\n"
                        f"💸 المطلوب: `{cost}` نقطة\n\n"
                        f"استخدم رابط الإحالة 🔗 أو الأكواد 🎟️ للحصول على نقاط.",
                        parse_mode="Markdown")
                    return
                # خصم النقاط مؤقتاً وابدأ تسجيل سيرفر جديد
                data['points'] = pts - cost
                save_users(users)
                bot.send_message(call.message.chat.id,
                    f"✅ تم خصم `{cost}` نقطة.\n\n🖥️ الآن أنشئ سيرفرك الجديد:\nأرسل اسم المستخدم الجديد (باللغة الإنجليزية):",
                    parse_mode="Markdown")
                msg = bot.send_message(call.message.chat.id, "اكتب اسم المستخدم:")
                bot.register_next_step_handler(msg, process_paid_username)
                return
        bot.send_message(call.message.chat.id, "❌ لم يتم العثور على حسابك.")

    def process_paid_username(message):
        if not enforce_subscription(message): return
        username = message.text.strip()
        if not username or not username.isalnum():
            bot.send_message(message.chat.id, "❌ اسم مستخدم غير صالح! استخدم أحرف وأرقام فقط.")
            return
        users = load_users()
        if username in users:
            bot.send_message(message.chat.id, "❌ اسم المستخدم هذا مأخوذ. اختر اسماً آخر:")
            msg = bot.send_message(message.chat.id, "اكتب اسم المستخدم:")
            bot.register_next_step_handler(msg, process_paid_username)
            return
        msg = bot.send_message(message.chat.id, f"👤 اسم المستخدم: `{username}`\n\nأرسل كلمة المرور:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_paid_password(m, username))

    def process_paid_password(message, username):
        if not enforce_subscription(message): return
        password = message.text.strip()
        if len(password) < 6:
            bot.send_message(message.chat.id, "❌ كلمة المرور يجب أن تكون 6 أحرف على الأقل.")
            return
        users = load_users()
        users[username] = {
            'password': hash_user_password(password),
            'max_sessions': 999,
            'max_servers': 2,
            'points': 0,
            'main_file': 'main.py',
            'runtime': 'python',
            'runtime_version': '3.11',
            'access_token': secrets.token_urlsafe(32),
            'created': datetime.now().isoformat(),
            'expiry': None,
            'telegram_id': message.from_user.id,
            'banned': False
        }
        save_users(users)
        os.makedirs(os.path.join(USERS_FOLDER, username), exist_ok=True)
        assigned_ip = assign_ip(username)
        settings = load_bot_settings()
        panel_url = settings.get('panel_url', '').strip()
        first_name = message.from_user.first_name or username
        ip_str = escape_md2(assigned_ip or 'غير متاح')
        uname_str = escape_md2(username)
        pass_str = escape_md2(password)
        caption = (
            f">تـم إنشـاء السـيـرفر بـنجـاح  💫\n"
            f">\n"
            f">🌐 الـ IP  :  `{ip_str}`\n"
            f">إسم المسـتخدم  :  `{uname_str}`\n"
            f">كلـمـة المـرور  :  `{pass_str}`"
        )
        markup_photo = types.InlineKeyboardMarkup()
        if panel_url:
            markup_photo.add(types.InlineKeyboardButton("🌐 لوحة التحكم", url=panel_url))
        bot.send_photo(
            message.chat.id,
            photo="https://g.top4top.io/p_3832nmswi0.jpg",
            caption=caption,
            parse_mode="MarkdownV2",
            reply_markup=markup_photo if panel_url else None
        )

    @bot.message_handler(func=lambda m: m.text == "إحالة")
    def invite_link(message):
        if not enforce_subscription(message): return
        link = f"https://t.me/{(bot.get_me().username)}?start={message.from_user.id}"
        settings = load_bot_settings()
        bot.send_message(message.chat.id, f"🔗 **رابط الإحالة الخاص بك:**\n\nشارك هذا الرابط مع أصدقائك:\n`{link}`\n\n💰 لكل شخص يشترك من خلالك ستحصل على *{settings.get('points_per_invite', 2)} نقاط*.\n\n🎁 يمكنك استبدال النقاط بزيادة عدد السيرفرات المتاحة لك.", parse_mode="Markdown")

    @bot.message_handler(func=lambda m: m.text == "شراء نقاط")
    def buy_points(message):
        if not enforce_subscription(message): return
        settings = load_bot_settings()
        bot.send_message(message.chat.id,
            f"💫 **شراء النقاط:**\n\n"
            f"🔹 {settings.get('points_per_server', 10)} نقطة = سيرفر إضافي\n"
            f"🔹 للحصول على نقاط مجانية استخدم زر الإحالة 🔗\n\n"
            f"📩 للشراء تواصل مع المطور:",
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("👨‍💻 تواصل مع الأدمن", url=settings.get('dev_user', 'https://t.me/V2P_1'))
            )
        )

    @bot.message_handler(func=lambda m: m.text == "مساعدة")
    def help_msg(message):
        if not enforce_subscription(message): return
        settings = load_bot_settings()
        bot.send_message(message.chat.id,
            "❓ **المساعدة:**\n\n"
            "🚀 *إنشاء سيرفر* — أنشئ حساباً للوحة التحكم\n"
            "👤 *ملفي الشخصي* — عرض بياناتك وكلمة مرورك\n"
            "🔗 *إحالة* — احصل على نقاط بدعوة أصدقائك\n"
            "💫 *شراء نقاط* — زيادة عدد سيرفراتك\n"
            "🎟️ *استخدام كود* — استخدم كود للحصول على نقاط\n\n"
            "🌐 رابط لوحة التحكم :",
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("📢 قناة الأدمن", url=settings.get('dev_channel', 'https://t.me/S7_MX3'))
            )
        )

    @bot.message_handler(func=lambda m: m.text == "استخدام كود")
    def use_code(message):
        if not enforce_subscription(message): return
        msg = bot.send_message(message.chat.id, "🎟️ أرسل الكود الذي تريد استخدامه:")
        bot.register_next_step_handler(msg, process_code)

    def process_code(message):
        if not enforce_subscription(message): return
        code_input = message.text.strip()
        settings = load_bot_settings()
        codes = settings.get('codes', {})
        if code_input not in codes:
            bot.send_message(message.chat.id, "❌ الكود غير صحيح أو منتهي الصلاحية.")
            return
        code_data = codes[code_input]
        if code_data.get('uses', 0) <= 0:
            bot.send_message(message.chat.id, "❌ هذا الكود نفدت استخداماته.")
            return
        # فحص إذا المستخدم استخدمه من قبل
        used_by = code_data.get('used_by', [])
        if message.from_user.id in used_by:
            bot.send_message(message.chat.id, "❌ لقد استخدمت هذا الكود من قبل.")
            return
        # تطبيق النقاط
        users = load_users()
        found = False
        for u, data in users.items():
            if data.get('telegram_id') == message.from_user.id:
                pts = code_data.get('points', 0)
                data['points'] = data.get('points', 0) + pts
                found = True
                save_users(users)
                # تحديث الكود
                codes[code_input]['uses'] -= 1
                codes[code_input].setdefault('used_by', []).append(message.from_user.id)
                settings['codes'] = codes
                save_bot_settings(settings)
                bot.send_message(message.chat.id, f"✅ تم استخدام الكود بنجاح!\n💰 حصلت على *{pts} نقطة*!\n🔹 رصيدك الآن: *{data['points']} نقطة*", parse_mode="Markdown")
                break
        if not found:
            bot.send_message(message.chat.id, "❌ لم يتم العثور على حسابك. قم بإنشاء حساب أولاً.")

    @bot.message_handler(func=lambda m: m.text == "📊 سيرفراتي")
    def my_servers(message):
        if not enforce_subscription(message): return
        procs = load_processes()
        users = load_users()
        uname = None
        for u, data in users.items():
            if data.get('telegram_id') == message.from_user.id:
                uname = u
                break

        if not uname:
            bot.send_message(message.chat.id, "❌ سجل أولاً.")
            return

        user_procs = [p for p in procs.values() if p.get('username') == uname]
        if not user_procs:
            bot.send_message(message.chat.id, "📭 ليس لديك سيرفرات شغالة حالياً.")
            return

        msg = "📊 **سيرفراتك الشغالة:**\n\n"
        for p in user_procs:
            msg += f"🔹 ملف: `{p.get('filename')}`\n"
            msg += f"🔹 PID: `{p.get('pid')}`\n"
            msg += f"🔹 الحالة: `Running`\n"
            msg += f"🔹 الوقت: `{p.get('start_time', '')[:19]}`\n\n"
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    # لوحة الأدمن
    @bot.message_handler(func=lambda m: m.text == "لوحة الأدمن" and is_admin(m.from_user.id))
    def admin_panel(message):
        bot.send_message(message.chat.id, "👑 مرحباً بك في لوحة تحكم الأدمن:", reply_markup=admin_keyboard())

    @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
    def admin_callbacks(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية!")
            return
        bot.answer_callback_query(call.id)

        if call.data == "admin_stats":
            users = load_users()
            procs = load_processes()
            settings = load_bot_settings()
            admins = settings.get('admin_list', [])
            channel = settings.get('force_channel', 'غير محددة')
            msg = (f"📊 **إحصائيات النظام:**\n\n"
                   f"👥 عدد المستخدمين: `{len(users)}`\n"
                   f"🖥️ السيرفرات النشطة: `{len(procs)}`\n"
                   f"👑 الأدمنز: `{len(admins) + 1}`\n"
                   f"📢 قناة الاشتراك: `{channel}`\n"
                   f"💰 نقاط/سيرفر: `{settings.get('points_per_server', 10)}`\n"
                   f"🔗 نقاط/إحالة: `{settings.get('points_per_invite', 2)}`")
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

        elif call.data == "admin_ban":
            msg = bot.send_message(call.message.chat.id, "🚫 أرسل اسم المستخدم لحظره من البوت:")
            bot.register_next_step_handler(msg, admin_ban_user)

        elif call.data == "admin_unban":
            msg = bot.send_message(call.message.chat.id, "✅ أرسل اسم المستخدم لفك حظره:")
            bot.register_next_step_handler(msg, admin_unban_user)

        elif call.data == "admin_add_admin":
            msg = bot.send_message(call.message.chat.id, "➕ أرسل معرف التليجرام (ID) للمستخدم الجديد الأدمن:")
            bot.register_next_step_handler(msg, admin_add_admin_step)

        elif call.data == "admin_del_admin":
            settings = load_bot_settings()
            admins = settings.get('admin_list', [])
            if not admins:
                bot.send_message(call.message.chat.id, "❌ لا يوجد أدمنز مضافون حالياً.")
            else:
                bot.send_message(call.message.chat.id, f"👑 قائمة الأدمنز:\n" + "\n".join([f"• `{a}`" for a in admins]) + "\n\n➖ أرسل ID الأدمن لحذفه:", parse_mode="Markdown")
                msg = bot.send_message(call.message.chat.id, "أرسل ID:")
                bot.register_next_step_handler(msg, admin_del_admin_step)

        elif call.data == "admin_add_channel":
            msg = bot.send_message(call.message.chat.id, "📢 أرسل معرف القناة (مثال: @channel_name) لإضافتها كاشتراك إجباري:")
            bot.register_next_step_handler(msg, admin_add_channel_step)

        elif call.data == "admin_del_channel":
            settings = load_bot_settings()
            current = settings.get('force_channel', '')
            if current:
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(
                    types.InlineKeyboardButton("🗑️ نعم، احذفها", callback_data="admin_confirm_del_channel"),
                    types.InlineKeyboardButton("❌ لا، إلغاء", callback_data="admin_cancel_del_channel")
                )
                bot.send_message(call.message.chat.id,
                    f"📢 القناة الحالية: `{current}`\n\nهل تريد حذف هذه القناة من الاشتراك الإجباري؟",
                    parse_mode="Markdown", reply_markup=mk)
            else:
                bot.send_message(call.message.chat.id, "❌ لا توجد قناة اشتراك إجباري مضافة.")

        elif call.data == "admin_confirm_del_channel":
            settings = load_bot_settings()
            current = settings.get('force_channel', '')
            if current:
                settings['force_channel'] = ''
                save_bot_settings(settings)
                try:
                    bot.edit_message_text(f"✅ تم حذف قناة الاشتراك الإجباري: `{current}`",
                        call.message.chat.id, call.message.message_id, parse_mode="Markdown")
                except:
                    bot.send_message(call.message.chat.id, f"✅ تم حذف قناة الاشتراك الإجباري: `{current}`", parse_mode="Markdown")
            else:
                bot.send_message(call.message.chat.id, "❌ لا توجد قناة مضافة.")

        elif call.data == "admin_cancel_del_channel":
            try:
                bot.edit_message_text("🚫 تم إلغاء الحذف.",
                    call.message.chat.id, call.message.message_id)
            except:
                bot.send_message(call.message.chat.id, "🚫 تم إلغاء الحذف.")

        elif call.data == "admin_add_code":
            msg = bot.send_message(call.message.chat.id, "🎟️ أرسل اسم الكود:")
            bot.register_next_step_handler(msg, admin_code_name_step)

        elif call.data == "admin_list_codes":
            settings = load_bot_settings()
            codes = settings.get('codes', {})
            if not codes:
                bot.send_message(call.message.chat.id, "❌ لا توجد أكواد مضافة.")
            else:
                msg = "📋 **قائمة الأكواد:**\n\n"
                for code, data in codes.items():
                    msg += f"🎟️ `{code}` — {data.get('uses', 0)} استخدام متبقي — {data.get('points', 0)} نقطة\n"
                bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

        elif call.data == "admin_list_servers":
            users = load_users()
            if not users:
                bot.send_message(call.message.chat.id, "❌ لا يوجد مستخدمون.")
            else:
                msg = "🖥️ **قائمة السيرفرات والمستخدمين:**\n\n"
                for uname, data in users.items():
                    status = "🔴 محظور" if data.get('banned') else "🟢 نشط"
                    password = '🔒 محفوظة بشكل مشفر'
                    msg += (f"👤 `{uname}` {status}\n"
                            f"   🔑 كلمة المرور: `{password}`\n"
                            f"   💰 النقاط: `{data.get('points', 0)}`\n"
                            f"   🖥️ السيرفرات: `{data.get('max_servers', 1)}`\n\n")
                for chunk in [msg[i:i+3500] for i in range(0, len(msg), 3500)]:
                    bot.send_message(call.message.chat.id, chunk, parse_mode="Markdown")

        elif call.data == "admin_add_points":
            msg = bot.send_message(call.message.chat.id, "💰 أرسل اسم المستخدم الذي تريد إضافة نقاط له:")
            bot.register_next_step_handler(msg, admin_add_points_user_step)

        elif call.data == "admin_del_points":
            msg = bot.send_message(call.message.chat.id, "➖ أرسل اسم المستخدم الذي تريد خصم نقاط منه:")
            bot.register_next_step_handler(msg, admin_del_points_user_step)

        elif call.data == "admin_check_user":
            msg = bot.send_message(call.message.chat.id, "🔍 أرسل اسم المستخدم لفحصه:")
            bot.register_next_step_handler(msg, admin_check_user_step)

        elif call.data == "admin_set_server_cost":
            settings = load_bot_settings()
            current_cost = settings.get('points_per_server', 10)
            msg = bot.send_message(call.message.chat.id,
                f"⚙️ **تكلفة السيرفر الإضافي الحالية:** `{current_cost}` نقطة\n\nأرسل العدد الجديد من النقاط لكل سيرفر إضافي:",
                parse_mode="Markdown")
            bot.register_next_step_handler(msg, admin_set_server_cost_step)

        elif call.data == "admin_set_panel_url":
            settings = load_bot_settings()
            current_url = settings.get('panel_url', 'غير محدد')
            msg = bot.send_message(call.message.chat.id,
                f"🔗 **لينك اللوحة الحالي:** `{current_url}`\n\nأرسل لينك لوحة التحكم الجديد (مثال: https://mysite.replit.app):",
                parse_mode="Markdown")
            bot.register_next_step_handler(msg, admin_set_panel_url_step)

    # --- خطوات الأدمن ---
    def admin_ban_user(message):
        uname = message.text.strip()
        users = load_users()
        if uname in users:
            users[uname]['banned'] = True
            save_users(users)
            bot.send_message(message.chat.id, f"✅ تم حظر `{uname}` من البوت بنجاح.", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")

    def admin_unban_user(message):
        uname = message.text.strip()
        users = load_users()
        if uname in users:
            users[uname]['banned'] = False
            save_users(users)
            bot.send_message(message.chat.id, f"✅ تم فك حظر `{uname}` بنجاح.", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")

    def admin_add_admin_step(message):
        try:
            new_id = int(message.text.strip())
            settings = load_bot_settings()
            admins = settings.get('admin_list', [])
            if new_id not in admins:
                admins.append(new_id)
                settings['admin_list'] = admins
                save_bot_settings(settings)
                bot.send_message(message.chat.id, f"✅ تم إضافة `{new_id}` كأدمن بنجاح.", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "❌ هذا المستخدم أدمن بالفعل.")
        except ValueError:
            bot.send_message(message.chat.id, "❌ أرسل ID رقمي صحيح.")

    def admin_del_admin_step(message):
        try:
            del_id = int(message.text.strip())
            settings = load_bot_settings()
            admins = settings.get('admin_list', [])
            if del_id in admins:
                admins.remove(del_id)
                settings['admin_list'] = admins
                save_bot_settings(settings)
                bot.send_message(message.chat.id, f"✅ تم حذف `{del_id}` من الأدمنز.", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "❌ هذا المستخدم ليس أدمن.")
        except ValueError:
            bot.send_message(message.chat.id, "❌ أرسل ID رقمي صحيح.")

    def admin_add_channel_step(message):
        channel = message.text.strip()
        if not channel.startswith('@'):
            channel = '@' + channel
        settings = load_bot_settings()
        settings['force_channel'] = channel
        save_bot_settings(settings)
        bot.send_message(message.chat.id, f"✅ تم إضافة قناة الاشتراك الإجباري: `{channel}`", parse_mode="Markdown")

    def admin_code_name_step(message):
        code_name = message.text.strip()
        msg = bot.send_message(message.chat.id, f"🎟️ الكود: `{code_name}`\n\nأرسل عدد الاستخدامات المسموحة:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: admin_code_uses_step(m, code_name))

    def admin_code_uses_step(message, code_name):
        try:
            uses = int(message.text.strip())
            msg = bot.send_message(message.chat.id, f"💰 أرسل عدد النقاط التي يحصل عليها المستخدم عند استخدام الكود:")
            bot.register_next_step_handler(msg, lambda m: admin_code_points_step(m, code_name, uses))
        except ValueError:
            bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

    def admin_code_points_step(message, code_name, uses):
        try:
            points = int(message.text.strip())
            settings = load_bot_settings()
            settings.setdefault('codes', {})[code_name] = {'uses': uses, 'points': points, 'used_by': []}
            save_bot_settings(settings)
            bot.send_message(message.chat.id,
                f"✅ **تم إضافة الكود بنجاح!**\n\n"
                f"🎟️ الكود: `{code_name}`\n"
                f"🔢 الاستخدامات: `{uses}`\n"
                f"💰 النقاط: `{points}`",
                parse_mode="Markdown")
        except ValueError:
            bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

    def admin_del_points_user_step(message):
        uname = message.text.strip()
        users = load_users()
        if uname not in users:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")
            return
        current_pts = users[uname].get('points', 0)
        msg = bot.send_message(message.chat.id,
            f"➖ رصيد `{uname}` الحالي: *{current_pts}* نقطة\n\nكم نقطة تريد خصمها؟",
            parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: admin_del_points_amount_step(m, uname))

    def admin_del_points_amount_step(message, uname):
        try:
            pts = int(message.text.strip())
            if pts <= 0:
                bot.send_message(message.chat.id, "❌ أرسل رقماً أكبر من صفر.")
                return
            users = load_users()
            old_pts = users[uname].get('points', 0)
            new_pts = max(0, old_pts - pts)
            users[uname]['points'] = new_pts
            save_users(users)
            bot.send_message(message.chat.id,
                f"✅ تم خصم `{pts}` نقطة من `{uname}`.\n💰 كان رصيده: *{old_pts}* نقطة\n💰 رصيده الآن: *{new_pts}* نقطة",
                parse_mode="Markdown")
            try:
                tid = users[uname].get('telegram_id')
                if tid:
                    bot.send_message(tid,
                        f"⚠️ تم خصم `{pts}` نقطة من حسابك من قِبل الأدمن.\n💰 رصيدك الحالي: *{new_pts}* نقطة",
                        parse_mode="Markdown")
            except: pass
        except ValueError:
            bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

    def admin_add_points_user_step(message):
        uname = message.text.strip()
        users = load_users()
        if uname not in users:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")
            return
        msg = bot.send_message(message.chat.id, f"💰 كم نقطة تريد إضافتها لـ `{uname}`؟", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: admin_add_points_amount_step(m, uname))

    def admin_add_points_amount_step(message, uname):
        try:
            pts = int(message.text.strip())
            users = load_users()
            users[uname]['points'] = users[uname].get('points', 0) + pts
            save_users(users)
            bot.send_message(message.chat.id, f"✅ تم إضافة `{pts}` نقطة لـ `{uname}`.\nرصيده الآن: `{users[uname]['points']}` نقطة.", parse_mode="Markdown")
            try:
                tid = users[uname].get('telegram_id')
                if tid:
                    bot.send_message(tid, f"🎉 تم إضافة `{pts}` نقطة لحسابك من الأدمن!\nرصيدك الآن: `{users[uname]['points']}` نقطة.", parse_mode="Markdown")
            except: pass
        except ValueError:
            bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

    def admin_check_user_step(message):
        uname = message.text.strip()
        users = load_users()
        if uname not in users:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")
            return
        data = users[uname]
        status = "🔴 محظور" if data.get('banned') else "🟢 نشط"
        password = '🔒 محفوظة بشكل مشفر'
        msg = (f"🔍 **معلومات المستخدم:**\n\n"
               f"👤 الاسم: `{uname}`\n"
               f"🔑 كلمة المرور: `{password}`\n"
               f"📊 الحالة: {status}\n"
               f"💰 النقاط: `{data.get('points', 0)}`\n"
               f"🖥️ السيرفرات المسموحة: `{data.get('max_servers', 1)}`\n"
               f"📅 تاريخ الإنشاء: `{str(data.get('created', '-'))[:10]}`\n"
               f"📱 Telegram ID: `{data.get('telegram_id', '-')}`")
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    def admin_set_server_cost_step(message):
        try:
            cost = int(message.text.strip())
            if cost < 0:
                bot.send_message(message.chat.id, "❌ يجب أن يكون الرقم أكبر من أو يساوي صفر.")
                return
            settings = load_bot_settings()
            settings['points_per_server'] = cost
            save_bot_settings(settings)
            bot.send_message(message.chat.id,
                f"✅ تم تحديث تكلفة السيرفر الإضافي إلى `{cost}` نقطة بنجاح!",
                parse_mode="Markdown")
        except ValueError:
            bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

    def admin_set_panel_url_step(message):
        url = message.text.strip()
        if not url.startswith('http'):
            bot.send_message(message.chat.id, "❌ اللينك يجب أن يبدأ بـ http أو https.")
            return
        settings = load_bot_settings()
        settings['panel_url'] = url
        save_bot_settings(settings)
        bot.send_message(message.chat.id,
            f"✅ تم تعيين لينك اللوحة بنجاح!\n\n🔗 `{url}`\n\nسيتم إرسال هذا اللينك للمستخدمين بعد إنشاء حساباتهم.",
            parse_mode="Markdown")

    print(" * Starting Advanced Telegram Bot...", flush=True)
    if not TOKEN:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is missing')
    if ADMIN_ID <= 0:
        print('[BOT] WARNING: set TELEGRAM_ADMIN_ID to your numeric Telegram user ID for admin commands.', flush=True)
    bot.remove_webhook()
    bot.polling(none_stop=True)
except Exception as e:
    print(f" * Telegram Bot Error: {e}")
