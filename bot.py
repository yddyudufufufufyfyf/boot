import os
import psycopg
from psycopg.rows import dict_row
import telebot
from telebot import types
from threading import Thread
from flask import Flask

# --- إعداد سيرفر الويب لمنع توقف رندر ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7 with Smart Referral & Subs Verification!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- بيانات البوت وقاعدة البيانات ---
TOKEN = "8635700320:AAHj21exFO4kj0hKu476B7Gx0rVyOwerHZs"
ADMIN_ID = 837914662
ADMIN_USERNAME = "@GD_GQ"

bot = telebot.TeleBot(TOKEN)
DATABASE_URL = "postgresql://postgres.kenzoztnvvxqhbebgwgj:amgd%40%40%40%40####5@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres"

def get_db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT UNIQUE,
            username TEXT,
            balance REAL DEFAULT 0.0,
            is_authorized INTEGER DEFAULT 0,
            user_type TEXT DEFAULT 'normal',
            invited_by BIGINT DEFAULT NULL
        )
    ''')

    # جدول لتسجيل من دعا من، لمنع تكرار احتساب الرصيد لنفس الشخص
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            inviter_id BIGINT,
            invited_id BIGINT UNIQUE,
            reward_given REAL DEFAULT 0.0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT INTO settings (key, value) VALUES ('welcome_msg', ' أهلاً بك في البوت الرسمي.\nاختر نوع استخدامك للبدء:') ON CONFLICT (key) DO NOTHING")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('ref_reward', '0.5') ON CONFLICT (key) DO NOTHING")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS forced_channels (
            id SERIAL PRIMARY KEY,
            channel_username TEXT UNIQUE,
            reward REAL DEFAULT 0.0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            parent_id INTEGER DEFAULT NULL,
            name TEXT NOT NULL,
            price REAL DEFAULT NULL,
            target_type TEXT DEFAULT 'normal'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS codes (
            id SERIAL PRIMARY KEY,
            category_id INTEGER,
            code_text TEXT,
            is_used INTEGER DEFAULT 0,
            used_by BIGINT DEFAULT NULL
        )
    ''')

    # إضافة الآدمن كمدير وموزع معتمد تلقائياً
    cursor.execute("INSERT INTO users (user_id, balance, is_authorized, user_type) VALUES (%s, 999999.0, 1, 'reseller') ON CONFLICT (user_id) DO UPDATE SET is_authorized = 1, user_type='reseller'", (ADMIN_ID,))

    conn.commit()
    cursor.close()
    conn.close()

init_db()

def get_setting(key, default=""):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row['value'] if row else default

def update_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, str(value)))
    conn.commit()
    cursor.close()
    conn.close()

def check_forced_subs(user_id):
    if user_id == ADMIN_ID:
        return True
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forced_channels")
    channels = cursor.fetchall()
    cursor.close()
    conn.close()

    for ch in channels:
        ch_username = ch['channel_username']
        try:
            member = bot.get_chat_member(ch_username, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except Exception:
            return False
    return True

def send_forced_channels_message(chat_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forced_channels")
    channels = cursor.fetchall()
    cursor.close()
    conn.close()

    markup = types.InlineKeyboardMarkup()
    for ch in channels:
        markup.add(types.InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{ch['channel_username'].lstrip('@')}"))
    markup.add(types.InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub"))

    bot.send_message(
        chat_id,
        "⚠️ تنبيه مهم:\n"
        "للاستفادة من خدمات البوت واستلام الأرباح، يجب عليك الاشتراك في القنوات الإجبارية أولاً.\n\n"
        "يرجى الاشتراك ثم اضغط على زر التحقق:",
        reply_markup=markup
    )

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.text.split()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    existing_user = cursor.fetchone()

    invited_by = None
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        # التحقق: لا يدعو نفسه، ومستخدم جديد تماماً، ولم يتم تسجيل هذه الدعوة مسبقاً
        if ref_id != user_id and not existing_user:
            cursor.execute("SELECT * FROM referrals WHERE invited_id=%s", (user_id,))
            already_invited = cursor.fetchone()
            if not already_invited:
                invited_by = ref_id
                reward_val = float(get_setting('ref_reward', '0.5'))
                
                # إضافة الرصيد للمُدعي
                cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (reward_val, ref_id))
                # تسجيل الدعوة لمنع تكرارها نهائياً
                cursor.execute("INSERT INTO referrals (inviter_id, invited_id, reward_given) VALUES (%s, %s, %s)", (ref_id, user_id, reward_val))
                
                # إرسال إشعار لصاحب الرابط بأن شخصاً دخل عبر رابطه
                try:
                    bot.send_message(
                        ref_id,
                        f"🎉 دخل شخص جديد عبر رابط الدعوة الخاص بك!\n"
                        f"• تم إضافة رصيد بقيمة: `${reward_val}` إلى حسابك.\n"
                        f"• آيدي العضو الجديد: `{user_id}`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    if not existing_user:
        if username:
            cursor.execute("INSERT INTO users (user_id, username, balance, invited_by) VALUES (%s, %s, 0.0, %s)", (user_id, username.lower(), invited_by))
        else:
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (%s, 0.0, %s)", (user_id, invited_by))
    else:
        if username:
            cursor.execute("UPDATE users SET username=%s WHERE user_id=%s", (username.lower(), user_id))

    conn.commit()
    cursor.close()
    conn.close()

    if not check_forced_subs(user_id):
        send_forced_channels_message(message.chat.id)
        return

    show_start_options(message.chat.id)

# مراقبة مغادرة الأعضاء من القنوات الإجبارية لخصم الرصيد تلقائياً
@bot.chat_member_handler()
def handle_chat_member_update(update):
    try:
        # التحقق إذا كان الحدث يخص قناة إجبارية مسجلة
        chat_username = f"@{update.chat.username}" if update.chat.username else None
        if not chat_username:
            return

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM forced_channels WHERE channel_username = %s", (chat_username,))
        channel_row = cursor.fetchone()

        if channel_row:
            old_status = update.old_chat_member.status
            new_status = update.new_chat_member.status
            user_id = update.new_chat_member.user.id

            # إذا كان العضو غادر أو أزال الاشتراك (مثلاً كان عضو وغادر)
            if old_status in ['member', 'administrator', 'creator'] and new_status in ['left', 'kicked']:
                # التحقق هل هذا العضو جاء عن طريق دعوة شخص آخر وتم منحه رصيد
                cursor.execute("SELECT * FROM referrals WHERE invited_id = %s", (user_id,))
                ref_record = cursor.fetchone()

                if ref_record:
                    inviter_id = ref_record['inviter_id']
                    reward_val = ref_record['reward_given']

                    # خصم الرصيد من صاحب الرابط
                    cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (reward_val, inviter_id))
                    # حذف سجل الإحالة لكي لا يتكرر الخصم ويصبح نظيفاً
                    cursor.execute("DELETE FROM referrals WHERE invited_id = %s", (user_id,))
                    conn.commit()

                    # إشعار صاحب الرابط بأن الشخص غادر وتم خصم الرصيد
                    try:
                        bot.send_message(
                            inviter_id,
                            f"⚠️ تنبيه: قام الشخص الذي دعوته (آيدي: `{user_id}`) بمغادرة القناة الأساسية ({chat_username}).\n"
                            f"• تم خصم مبلغ الإحالة (`${reward_val}`) من رصيدك.",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error in chat_member handler: {e}")

def show_start_options(chat_id, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👔 لوحة الموزعين", callback_data="type_reseller"),
        types.InlineKeyboardButton("👤 المستخدم العادي", callback_data="type_normal")
    )
    if chat_id == ADMIN_ID:
        markup.add(types.InlineKeyboardButton("⚙️ لوحة تحكم الآدمن", callback_data="adm_main_menu"))

    welcome_text = get_setting('welcome_msg', 'أهلاً بك في البوت!')
    if message_id:
        try:
            bot.edit_message_text(welcome_text, chat_id, message_id, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, welcome_text, reply_markup=markup)
    else:
        bot.send_message(chat_id, welcome_text, reply_markup=markup)

def show_main_menu(chat_id, user_type, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🛍️ المتجر والسلع", callback_data=f"store_{user_type}"))
    markup.add(types.InlineKeyboardButton("💰 رصيدي", callback_data="menu_balance"))
    markup.add(types.InlineKeyboardButton("📋 طلباتي السابقة", callback_data="menu_orders"))
    markup.add(types.InlineKeyboardButton("👥 تجميع رصيد (دعوة أصدقاء)", callback_data="menu_ref"))
    markup.add(types.InlineKeyboardButton("📢 قنوات الربح والاشتراك", callback_data="menu_earn_channels"))
    markup.add(types.InlineKeyboardButton("🔙 تغيير نوع الاستخدام", callback_data="back_to_start"))
    
    if chat_id == ADMIN_ID:
        markup.add(types.InlineKeyboardButton("⚙️ لوحة تحكم الآدمن", callback_data="adm_main_menu"))

    title = f" القائمة الرئيسية ({'الموزعين' if user_type=='reseller' else 'المستخدم العادي'}):"
    if message_id:
        try:
            bot.edit_message_text(title, chat_id, message_id, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, title, reply_markup=markup)
    else:
        bot.send_message(chat_id, title, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    if data == "check_sub":
        if check_forced_subs(user_id):
            bot.answer_callback_query(call.id, "✅ تم التحقق من الاشتراك بنجاح!")
            show_start_options(chat_id, message_id)
        else:
            bot.answer_callback_query(call.id, "❌ لم تقم بالاشتراك في كافة القنوات الإجبارية بعد!", show_alert=True)
        return

    if not check_forced_subs(user_id):
        send_forced_channels_message(chat_id)
        return

    if data == "type_reseller":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT is_authorized, user_type FROM users WHERE user_id=%s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_id == ADMIN_ID or (row and row['is_authorized'] == 1):
            show_main_menu(chat_id, 'reseller', message_id)
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET user_type='reseller', is_authorized=0 WHERE user_id=%s", (user_id,))
            conn.commit()
            cursor.close()
            conn.close()
            
            bot.answer_callback_query(call.id, "تم إرسال طلبك للإدارة بانتظار الموافقة.", show_alert=True)
            bot.edit_message_text(
                f" حساب الموزع يتطلب موافقة الإدارة.\n\n"
                f"معرفك: `{user_id}`\n"
                f"تواصل مع المسؤول للتفعيل الفوري: {ADMIN_USERNAME}",
                chat_id, message_id, parse_mode="Markdown"
            )

    elif data == "type_normal":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET user_type='normal' WHERE user_id=%s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        show_main_menu(chat_id, 'normal', message_id)

    elif data == "back_to_start":
        show_start_options(chat_id, message_id)

    elif data.startswith("store_"):
        u_type = data.split("_")[1]
        show_store_categories(user_id, chat_id, u_type, parent_id=None, message_id=message_id)

    elif data.startswith("usr_cat_"):
        parts = data.split("_")
        u_type = parts[2]
        cat_id = int(parts[3])
        show_store_categories(user_id, chat_id, u_type, parent_id=cat_id, message_id=message_id)

    elif data.startswith("buy_prod_"):
        parts = data.split("_")
        u_type = parts[2]
        cat_id = int(parts[3])
        process_buy_code(user_id, chat_id, u_type, cat_id, call.id)

    elif data == "menu_balance":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT balance, user_type FROM users WHERE user_id=%s", (user_id,))
        row = cursor.fetchone()
        bal = row['balance'] if row else 0.0
        u_type = row['user_type'] if row else 'normal'
        cursor.close()
        conn.close()
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع للقائمة", callback_data=f"store_{u_type}"))
        bot.edit_message_text(f"👤 معرفك: `{user_id}`\n💰 رصيدك الحالي: `${bal:.2f}`\n\nتواصل مع المدير للشحن الفوري: {ADMIN_USERNAME}", chat_id, message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "menu_orders":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.name, cd.code_text FROM codes cd 
            JOIN categories c ON cd.category_id = c.id 
            WHERE cd.used_by = %s
        """, (user_id,))
        orders = cursor.fetchall()
        cursor.close()
        conn.close()

        text = "📋 مشترياتك السابقة:\n\n"
        if orders:
            for o in orders:
                text += f"▫️ {o['name']} ⟵ `{o['code_text']}`\n"
        else:
            text += "لا توجد طلبات سابقة."

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type FROM users WHERE user_id=%s", (user_id,))
        u_type = cursor.fetchone()['user_type']
        cursor.close()
        conn.close()

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع للقائمة", callback_data=f"store_{u_type}"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "menu_ref":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        reward = get_setting('ref_reward', '0.5')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type FROM users WHERE user_id=%s", (user_id,))
        u_type = cursor.fetchone()['user_type']
        cursor.close()
        conn.close()

        text = (
            f"👥 نظام دعوة الأصدقاء الآمن\n\n"
            f"• شارك رابطك واكسب **${reward}** فور دخول الشخص واشتراكه بالقناة.\n"
            f"• تنبيه: إذا قام الشخص بمغادرة القناة، سيتم خصم الرصيد تلقائياً.\n\n"
            f"رابطك الخاص:\n`{ref_link}`"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع للقائمة", callback_data=f"store_{u_type}"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "menu_earn_channels":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM forced_channels")
        channels = cursor.fetchall()
        cursor.close()
        conn.close()

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type FROM users WHERE user_id=%s", (user_id,))
        u_type = cursor.fetchone()['user_type']
        cursor.close()
        conn.close()

        markup = types.InlineKeyboardMarkup()
        for ch in channels:
            markup.add(types.InlineKeyboardButton(f"قناة: {ch['channel_username']}", url=f"https://t.me/{ch['channel_username'].lstrip('@')}"))
        markup.add(types.InlineKeyboardButton("رجوع للقائمة", callback_data=f"store_{u_type}"))
        
        bot.edit_message_text("📢 القنوات الإجبارية والربح المتاحة:", chat_id, message_id, reply_markup=markup)

    # --- لوحة تحكم الآدمن ---
    elif user_id == ADMIN_ID:
        if data == "adm_main_menu":
            show_admin_panel(chat_id, message_id)
        elif data == "adm_resellers_panel":
            show_admin_resellers_menu(chat_id, message_id)
        elif data == "adm_list_resellers":
            show_all_resellers_list(chat_id, message_id)
        elif data.startswith("adm_reseller_info_"):
            r_id = int(data.split("_")[3])
            show_single_reseller_details(chat_id, r_id, message_id)
        elif data.startswith("adm_addbal_prompt_"):
            r_id = int(data.split("_")[3])
            msg = bot.send_message(chat_id, f"للمستخدم `{r_id}`، أرسل المبلغ المراد إضافته (أو بالسالب للخصم مثل `-5`):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: process_admin_balance_change(m, r_id))
        elif data.startswith("adm_auth_reseller_"):
            r_id = int(data.split("_")[3])
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_authorized=1 WHERE user_id=%s", (r_id,))
            conn.commit()
            cursor.close()
            conn.close()
            bot.answer_callback_query(call.id, "تم تفعيل الموزع بنجاح!")
            show_single_reseller_details(chat_id, r_id, message_id)
        
        elif data == "adm_normal_users_panel":
            show_admin_normal_users_menu(chat_id, message_id)
        elif data == "adm_store_panel":
            show_admin_store_menu(chat_id, message_id)
        elif data.startswith("adm_store_target_"):
            target = data.split("_")[3]
            show_admin_tree(chat_id, target, parent_id=0, message_id=message_id)
        elif data.startswith("adm_tree_"):
            parts = data.split("_")
            target = parts[2]
            p_id = int(parts[3])
            show_admin_tree(chat_id, target, parent_id=p_id, message_id=message_id)
        elif data.startswith("adm_newcat_"):
            parts = data.split("_")
            target = parts[2]
            p_id = int(parts[3])
            msg = bot.send_message(chat_id, "أرسل اسم القسم الفرعي الجديد:")
            bot.register_next_step_handler(msg, lambda m: save_new_category(m, target, p_id))
        elif data.startswith("adm_newprd_"):
            parts = data.split("_")
            target = parts[2]
            p_id = int(parts[3])
            msg = bot.send_message(chat_id, "أرسل اسم السلعة والسعر وبينهما شخطة (مثال: حساب نتفليكس - 2.5):")
            bot.register_next_step_handler(msg, lambda m: save_new_product(m, target, p_id))
        elif data.startswith("adm_up_codes_"):
            parts = data.split("_")
            target = parts[3]
            cat_id = int(parts[4])
            msg = bot.send_message(chat_id, "أرسل الأكواد أو الحسابات (كل واحد في سطر):")
            bot.register_next_step_handler(msg, lambda m: save_uploaded_codes(m, target, cat_id))
        elif data.startswith("adm_del_cat_"):
            parts = data.split("_")
            target = parts[3]
            cat_id = int(parts[4])
            delete_category_recursive(cat_id)
            bot.answer_callback_query(call.id, "تم الحذف بنجاح!")
            show_admin_tree(chat_id, target, parent_id=0, message_id=message_id)

        elif data == "adm_channels_panel":
            show_admin_channels(chat_id, message_id)
        elif data == "adm_add_channel":
            msg = bot.send_message(chat_id, "أرسل معرف القناة الإجبارية ورصيد المكافأة (مثال: @ChannelName 0.5):")
            bot.register_next_step_handler(msg, save_forced_channel)
        elif data.startswith("adm_delchan_"):
            chan_id = int(data.split("_")[2])
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM forced_channels WHERE id=%s", (chan_id,))
            conn.commit()
            cursor.close()
            conn.close()
            bot.answer_callback_query(call.id, "تم حذف القناة!")
            show_admin_channels(chat_id, message_id)

        elif data == "adm_settings_panel":
            show_admin_settings(chat_id, message_id)
        elif data == "adm_set_welcome":
            msg = bot.send_message(chat_id, "أرسل رسالة الترحيب الجديدة:")
            bot.register_next_step_handler(msg, save_new_welcome)
        elif data == "adm_set_ref":
            msg = bot.send_message(chat_id, "أرسل مبلغ مكافأة الدعوة الجديد (مثال: 0.75):")
            bot.register_next_step_handler(msg, save_new_ref_reward)

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if message.from_user.id == ADMIN_ID:
        show_admin_panel(message.chat.id)

def show_admin_panel(chat_id, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👔 قسم الموزعين (القائمة والأرصدة)", callback_data="adm_resellers_panel"),
        types.InlineKeyboardButton("👤 قسم المستخدمين العاديين", callback_data="adm_normal_users_panel"),
        types.InlineKeyboardButton("📂 قسم إدارة المتجر (منفصل تماماً)", callback_data="adm_store_panel"),
        types.InlineKeyboardButton("📢 قنوات الاشتراك الإجباري والربح", callback_data="adm_channels_panel"),
        types.InlineKeyboardButton("⚙️ الإعدادات العامة", callback_data="adm_settings_panel"),
        types.InlineKeyboardButton("🔙 العودة للبوت", callback_data="back_to_start")
    )
    text = "⚙️ لوحة تحكم الآدمن الرئيسية:"
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def show_admin_resellers_menu(chat_id, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 قائمة الموزعين والطلبات الحالية", callback_data="adm_list_resellers"),
        types.InlineKeyboardButton("🔙 رجوع لوحة التحكم", callback_data="adm_main_menu")
    )
    text = "👔 إدارة الموزعين:"
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def show_all_resellers_list(chat_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_type='reseller'")
    resellers = cursor.fetchall()
    cursor.close()
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)
    for r in resellers:
        status = "✅" if r['is_authorized'] == 1 else "⏳"
        markup.add(types.InlineKeyboardButton(f"{status} ID: {r['user_id']} | رصيد: ${r['balance']:.2f}", callback_data=f"adm_reseller_info_{r['user_id']}"))
    
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_resellers_panel"))
    text = "📋 قائمة الموزعين (اضغط على أي موزع لعرض رصيده والأكواد المسحوبة وتعديل رصيده):"
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def show_single_reseller_details(chat_id, reseller_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (reseller_id,))
    r = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as cnt FROM codes WHERE used_by=%s", (reseller_id,))
    used_codes_count = cursor.fetchone()['cnt']
    cursor.close()
    conn.close()

    if not r:
        bot.send_message(chat_id, "المستخدم غير موجود.")
        return

    status_str = "مفعل ✅" if r['is_authorized'] == 1 else "بانتظار الموافقة ⏳"
    text = (
        f"👤 **تفاصيل الموزع:**\n\n"
        f"• الآيدي: `{r['user_id']}`\n"
        f"• المعرف: @{r['username'] or 'لا يوجد'}\n"
        f"• الرصيد الحالي: `${r['balance']:.2f}`\n"
        f"• الحالة: {status_str}\n"
        f"• إجمالي السلع/الأكواد المسحوبة: `{used_codes_count}`"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💵 إضافة أو خصم رصيد", callback_data=f"adm_addbal_prompt_{reseller_id}"))
    if r['is_authorized'] == 0:
        markup.add(types.InlineKeyboardButton("✅ تفعيل الموزع", callback_data=f"adm_auth_reseller_{reseller_id}"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع لقائمة الموزعين", callback_data="adm_list_resellers"))

    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def process_admin_balance_change(message, reseller_id):
    try:
        amount = float(message.text.strip())
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, reseller_id))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(message.chat.id, f"✅ تم تحديث رصيد الموزع بنجاح بمقدار ${amount:.2f}!")
        show_single_reseller_details(message.chat.id, reseller_id)
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ! أرسل رقماً صحيحاً (مثال: 10 أو -5).")

def show_admin_normal_users_menu(chat_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE user_type='normal'")
    normal_count = cursor.fetchone()['cnt']
    cursor.close()
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔙 رجوع لوحة التحكم", callback_data="adm_main_menu"))
    
    text = f"👤 إدارة المستخدمين العاديين:\n\n• إجمالي عددهم: `{normal_count}`"
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def show_admin_store_menu(chat_id, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👔 إدارة متجر الموزعين (خاص بهم)", callback_data="adm_store_target_reseller"),
        types.InlineKeyboardButton("👤 إدارة متجر المستخدمين العاديين", callback_data="adm_store_target_normal"),
        types.InlineKeyboardButton("🔙 رجوع لوحة التحكم", callback_data="adm_main_menu")
    )
    text = "📂 قسم إدارة المتجر والسلع (منفصل):"
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def show_admin_tree(chat_id, target_type, parent_id=0, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    real_parent_id = None if parent_id == 0 else parent_id

    if real_parent_id is None:
        cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL AND target_type=%s", (target_type,))
        title = f"إدارة أقسام متجر ({'الموزعين' if target_type=='reseller' else 'العاديين'}):"
    else:
        cursor.execute("SELECT * FROM categories WHERE id=%s", (real_parent_id,))
        current = cursor.fetchone()
        
        if current and current['price'] is not None:
            cursor.execute("SELECT COUNT(*) as count FROM codes WHERE category_id=%s AND is_used=0", (real_parent_id,))
            stock = cursor.fetchone()['count']
            text = f"السلعة: {current['name']}\nالسعر: ${current['price']:.2f}\nالأكواد المتوفرة: {stock}"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("➕ رفع أكواد جديدة", callback_data=f"adm_up_codes_{target_type}_{real_parent_id}"))
            markup.add(types.InlineKeyboardButton("🗑️ حذف هذه السلعة", callback_data=f"adm_del_cat_{target_type}_{real_parent_id}"))
            back_id = current['parent_id'] if current['parent_id'] is not None else 0
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=f"adm_tree_{target_type}_{back_id}"))
            
            cursor.close()
            conn.close()
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            else:
                bot.send_message(chat_id, text, reply_markup=markup)
            return

        cursor.execute("SELECT * FROM categories WHERE parent_id=%s", (real_parent_id,))
        title = f"قسم: {current['name']}"

    children = cursor.fetchall()
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("➕ إضافة قسم فرعي", callback_data=f"adm_newcat_{target_type}_{parent_id}"),
        types.InlineKeyboardButton("➕ إضافة سلعة بسعر", callback_data=f"adm_newprd_{target_type}_{parent_id}")
    )

    for c in children:
        prefix = "🛒" if c['price'] is not None else "📁"
        price_str = f" (${c['price']:.2f})" if c['price'] is not None else ""
        markup.add(types.InlineKeyboardButton(f"{prefix} {c['name']}{price_str}", callback_data=f"adm_tree_{target_type}_{c['id']}"))

    if real_parent_id is not None:
        markup.add(types.InlineKeyboardButton("🗑️ حذف هذا القسم", callback_data=f"adm_del_cat_{target_type}_{real_parent_id}"))
        cursor.execute("SELECT parent_id FROM categories WHERE id=%s", (real_parent_id,))
        p = cursor.fetchone()
        back_id = p['parent_id'] if p and p['parent_id'] is not None else 0
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=f"adm_tree_{target_type}_{back_id}"))
    else:
        markup.add(types.InlineKeyboardButton("🔙 رجوع لاختيار المتجر", callback_data="adm_store_panel"))

    cursor.close()
    conn.close()
    if message_id:
        bot.edit_message_text(title, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, title, reply_markup=markup)

def save_new_category(message, target_type, parent_id):
    name = message.text.strip()
    p_id = None if parent_id == 0 else parent_id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (parent_id, name, target_type) VALUES (%s, %s, %s)", (p_id, name, target_type))
    conn.commit()
    cursor.close()
    conn.close()
    bot.send_message(message.chat.id, f"✅ تم إنشاء القسم {name} بنجاح!")
    show_admin_tree(message.chat.id, target_type, parent_id=parent_id)

def save_new_product(message, target_type, parent_id):
    try:
        parts = message.text.split("-")
        name = parts[0].strip()
        price = float(parts[1].strip())
        p_id = None if parent_id == 0 else parent_id

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categories (parent_id, name, price, target_type) VALUES (%s, %s, %s, %s)", (p_id, name, price, target_type))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(message.chat.id, f"✅ تم إضافة السلعة {name} بسعر ${price:.2f} بنجاح!")
        show_admin_tree(message.chat.id, target_type, parent_id=parent_id)
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ! استخدم الشخطة (مثال: اسم السلعة - 2.5).")

def save_uploaded_codes(message, target_type, cat_id):
    codes = [c.strip() for c in message.text.split('\n') if c.strip()]
    if not codes:
        bot.send_message(message.chat.id, "❌ لم يتم إرسال أي أكواد.")
        return
    conn = get_db()
    cursor = conn.cursor()
    for code in codes:
        cursor.execute("INSERT INTO codes (category_id, code_text) VALUES (%s, %s)", (cat_id, code))
    conn.commit()
    cursor.close()
    conn.close()
    bot.send_message(message.chat.id, f"✅ تم رفع {len(codes)} كود بنجاح!")
    show_admin_tree(message.chat.id, target_type, parent_id=cat_id)

def delete_category_recursive(cat_id):
    conn = get_db()
    cursor = conn.cursor()
    def _delete(c_id):
        cursor.execute("SELECT id FROM categories WHERE parent_id=%s", (c_id,))
        for child in cursor.fetchall():
            _delete(child['id'])
        cursor.execute("DELETE FROM codes WHERE category_id=%s", (c_id,))
        cursor.execute("DELETE FROM categories WHERE id=%s", (c_id,))
    _delete(cat_id)
    conn.commit()
    cursor.close()
    conn.close()

def show_store_categories(user_id, chat_id, user_type, parent_id=None, message_id=None):
    conn = get_db()
    cursor = conn.cursor()

    if parent_id is None:
        cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL AND target_type=%s", (user_type,))
        title = f"🛍️ متجر ({'الموزعين' if user_type=='reseller' else 'المستخدم العادي'}):"
    else:
        cursor.execute("SELECT * FROM categories WHERE id=%s", (parent_id,))
        current_cat = cursor.fetchone()
        
        if current_cat and current_cat['price'] is not None:
            cursor.execute("SELECT COUNT(*) as count FROM codes WHERE category_id=%s AND is_used=0", (parent_id,))
            stock = cursor.fetchone()['count']
            
            text = f"السلعة: {current_cat['name']}\nالسعر: ${current_cat['price']:.2f}\nالمتوفر بالمخزن: {stock}"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🛒 شراء الآن", callback_data=f"buy_prod_{user_type}_{parent_id}"))
            
            back_id = current_cat['parent_id']
            back_cb = f"usr_cat_{user_type}_{back_id}" if back_id is not None else f"store_{user_type}"
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=back_cb))
            
            cursor.close()
            conn.close()
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            else:
                bot.send_message(chat_id, text, reply_markup=markup)
            return

        cursor.execute("SELECT * FROM categories WHERE parent_id=%s", (parent_id,))
        title = f"قسم: {current_cat['name']}"

    cats = cursor.fetchall()
    markup = types.InlineKeyboardMarkup()

    for c in cats:
        prefix = "🛒" if c['price'] is not None else "📁"
        price_str = f" (${c['price']:.2f})" if c['price'] is not None else ""
        markup.add(types.InlineKeyboardButton(f"{prefix} {c['name']}{price_str}", callback_data=f"usr_cat_{user_type}_{c['id']}"))

    if parent_id is not None:
        cursor.execute("SELECT parent_id FROM categories WHERE id=%s", (parent_id,))
        p = cursor.fetchone()
        back_cb = f"usr_cat_{user_type}_{p['parent_id']}" if p and p['parent_id'] is not None else f"store_{user_type}"
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=back_cb))
    else:
        markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data=f"back_to_main_menu_{user_type}"))

    cursor.close()
    conn.close()

    if message_id:
        try:
            bot.edit_message_text(title, chat_id, message_id, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, title, reply_markup=markup)
    else:
        bot.send_message(chat_id, title, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_main_menu_"))
def back_to_main_menu_handler(call):
    user_type = call.data.split("_")[4]
    show_main_menu(call.message.chat.id, user_type, call.message.message_id)

def process_buy_code(user_id, chat_id, user_type, cat_id, callback_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories WHERE id=%s", (cat_id,))
    cat = cursor.fetchone()
    cursor.execute("SELECT balance FROM users WHERE user_id=%s", (user_id,))
    user_row = cursor.fetchone()
    user_balance = user_row['balance'] if user_row else 0.0

    if not cat or cat['price'] is None:
        bot.answer_callback_query(callback_id, "خطأ في المنتج.")
        cursor.close()
        conn.close()
        return

    if user_balance < cat['price']:
        bot.answer_callback_query(callback_id, "❌ رصيدك غير كافٍ للشراء!", show_alert=True)
        cursor.close()
        conn.close()
        return

    cursor.execute("SELECT id, code_text FROM codes WHERE category_id=%s AND is_used=0 LIMIT 1", (cat_id,))
    code_row = cursor.fetchone()

    if not code_row:
        bot.answer_callback_query(callback_id, "❌ عذراً، نفدت الكمية من المخزن.", show_alert=True)
        cursor.close()
        conn.close()
        return

    new_balance = user_balance - cat['price']
    cursor.execute("UPDATE users SET balance=%s WHERE user_id=%s", (new_balance, user_id))
    cursor.execute("UPDATE codes SET is_used=1, used_by=%s WHERE id=%s", (user_id, code_row['id']))
    conn.commit()
    cursor.close()
    conn.close()

    bot.send_message(chat_id, f"✅ تم الشراء بنجاح!\n\nالسلعة: {cat['name']}\nالكود:\n`{code_row['code_text']}`\n\nرصيدك المتبقي: ${new_balance:.2f}", parse_mode="Markdown")
    bot.answer_callback_query(callback_id, "تم التسليم بنجاح!")

def show_admin_channels(chat_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forced_channels")
    channels = cursor.fetchall()
    cursor.close()
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("➕ إضافة قناة إجبارية جديدة", callback_data="adm_add_channel"))
    for ch in channels:
        markup.add(types.InlineKeyboardButton(f"🗑️ حذف {ch['channel_username']}", callback_data=f"adm_delchan_{ch['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_main_menu"))

    text = "📢 إدارة القنوات الإجبارية والاشتراك:"
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def save_forced_channel(message):
    try:
        parts = message.text.split()
        ch_name = parts[0]
        reward = float(parts[1]) if len(parts) > 1 else 0.0
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO forced_channels (channel_username, reward) VALUES (%s, %s) ON CONFLICT (channel_username) DO UPDATE SET reward = EXCLUDED.reward", (ch_name, reward))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(message.chat.id, "✅ تمت إضافة القناة وحفظها بنجاح!")
        show_admin_channels(message.chat.id)
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ! استخدم الصيغة: @ChannelName 0.5")

def show_admin_settings(chat_id, message_id=None):
    ref_rew = get_setting('ref_reward', '0.5')
    welcome = get_setting('welcome_msg', '')
    text = f"⚙️ الإعدادات العامة:\n\n💬 رسالة الترحيب:\n{welcome}\n\n💰 مكافأة الدعوة: ${ref_rew}"
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✏️ تعديل رسالة الترحيب", callback_data="adm_set_welcome"),
        types.InlineKeyboardButton("💵 تعديل مكافأة الدعوة", callback_data="adm_set_ref"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_main_menu")
    )
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def save_new_welcome(message):
    text = message.text.strip()
    update_setting('welcome_msg', text)
    bot.send_message(message.chat.id, "✅ تم تحديث رسالة الترحيب!")
    show_admin_settings(message.chat.id)

def save_new_ref_reward(message):
    try:
        val = float(message.text.strip())
        update_setting('ref_reward', str(val))
        bot.send_message(message.chat.id, f"✅ تم تحديث المكافأة إلى ${val:.2f}!")
        show_admin_settings(message.chat.id)
    except Exception:
        bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً (مثال: 0.5)")

if __name__ == '__main__':
    print("تشغيل الخادم مع نظام الإحالات والخصم الذكي والمغادرة...")
    keep_alive()
    bot.infinity_polling(allowed_updates=["message", "callback_query", "chat_member"])
