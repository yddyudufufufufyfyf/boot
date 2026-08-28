import os
import psycopg
from psycopg.rows import dict_row
import telebot
from telebot import types
from threading import Thread
from flask import Flask

# --- إعداد سيرفر الويب الوهمي لمنع توقف رندر ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7 with Supabase & Inline Menus!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- البيانات الأساسية ---
TOKEN = "8635700320:AAHj21exFO4kj0hKu476B7Gx0rVyOwerHZs"
ADMIN_ID = 837914662
ADMIN_USERNAME = "@GD_GQ"

bot = telebot.TeleBot(TOKEN)

# --- رابط قاعدة البيانات السحابية (Supabase) مع كلمة المرور ---
DATABASE_URL = "postgresql://postgres:amgd@@@@####5@db.kenzoztnvvxqhbebgwgj.supabase.co:5432/postgres"

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
            user_type TEXT DEFAULT NULL,
            invited_by BIGINT DEFAULT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT INTO settings (key, value) VALUES ('welcome_msg', 'أهلاً بك في البوت! اختر من القائمة:') ON CONFLICT (key) DO NOTHING")
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
            price REAL DEFAULT NULL
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
        markup.add(types.InlineKeyboardButton(f"اشترك في قنواتنا 📢", url=f"https://t.me/{ch['channel_username'].lstrip('@')}"))
    markup.add(types.InlineKeyboardButton("تحقق من الاشتراك ✅", callback_data="check_sub"))

    bot.send_message(
        chat_id,
        "⚠️ عذراً، يجب عليك الاشتراكات في القنوات الإجبارية لتتمكن من استخدام البوت.\n"
        "يرجى الاشتراك في القنوات أدناه ثم اضغط 'تحقق من الاشتراك':",
        reply_markup=markup
    )

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.text.split()

    conn = get_db()
    cursor = conn.cursor()

    invited_by = None
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            invited_by = ref_id

    if username:
        cursor.execute("""
            INSERT INTO users (user_id, username, balance, invited_by) VALUES (%s, %s, 0.0, %s) 
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
        """, (user_id, username.lower(), invited_by))
    else:
        cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (%s, 0.0, %s) ON CONFLICT (user_id) DO NOTHING", (user_id, invited_by))
    
    conn.commit()
    cursor.close()
    conn.close()

    if not check_forced_subs(user_id):
        send_forced_channels_message(message.chat.id)
        return

    show_start_options(message.chat.id)

def show_start_options(chat_id, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👔 أريد أن أكون موزعاً", callback_data="type_reseller"),
        types.InlineKeyboardButton("👤 مستخدم عادي (مجاني)", callback_data="type_normal")
    )
    text = "👋 أهلاً بك في البوت!\n\nاختر نوع استخدامك للبوت:"
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def show_main_inline_menu(chat_id, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🛍️ المتجر", callback_data="menu_store"),
        types.InlineKeyboardButton("💰 رصيدي", callback_data="menu_balance"),
        types.InlineKeyboardButton("📋 طلباتي", callback_data="menu_orders"),
        types.InlineKeyboardButton("👥 تجميع رصيد (دعوة أصدقاء)", callback_data="menu_ref"),
        types.InlineKeyboardButton("📢 قنوات ربح الرصيد", callback_data="menu_earn_channels")
    )
    text = "👋 أهلاً بك في القائمة الرئيسية!\n\nاختر من القائمة:"
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    username = call.from_user.username
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    if data == "check_sub":
        if check_forced_subs(user_id):
            bot.answer_callback_query(call.id, "شكراً لاشتراكك!")
            show_start_options(chat_id, message_id)
        else:
            bot.answer_callback_query(call.id, "لم تقم بالاشتراك في كافة القنوات بعد!", show_alert=True)
        return

    if not check_forced_subs(user_id):
        send_forced_channels_message(chat_id)
        return

    if data == "type_reseller":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET user_type='reseller' WHERE user_id=%s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        bot.edit_message_text(
            f"عفواً، يتطلب حساب الموزع موافقة الإدارة.\n\n"
            f"الآيدي الخاص بك: `{user_id}`\n"
            f"يرجى مراسلة المسؤول لتفعيل حسابك كموزع:\n"
            f"المسؤول: {ADMIN_USERNAME}",
            chat_id, message_id, parse_mode="Markdown"
        )

    elif data == "type_normal":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET user_type='normal' WHERE user_id=%s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        show_main_inline_menu(chat_id, message_id)

    elif data == "menu_store":
        show_user_categories(user_id, chat_id, parent_id=None, message_id=message_id)

    elif data == "menu_balance":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id=%s", (user_id,))
        row = cursor.fetchone()
        bal = row['balance'] if row else 0.0
        cursor.close()
        conn.close()
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع للقائمة الرئيسية", callback_data="back_to_main"))
        bot.edit_message_text(f"👤 معرفك: `{user_id}`\n💰 رصيدك الحالي: ${bal:.2f}\n\nيمكنك شحن رصيدك عبر التواصل مع المدير: {ADMIN_USERNAME}", chat_id, message_id, reply_markup=markup, parse_mode="Markdown")

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

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع للقائمة الرئيسية", callback_data="back_to_main"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "menu_ref":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        reward = get_setting('ref_reward', '0.5')
        
        text = (
            f"👥 **نظام دعوة الأصدقاء**\n\n"
            f"شارك رابط الدعوة الخاص بك مع أصدقائك، واكسب ${reward} عن كل شخص يدخل ويشترك بالقنوات الإجبارية!\n\n"
            f"🔗 رابطك:\n`{ref_link}`"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع للقائمة الرئيسية", callback_data="back_to_main"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "menu_earn_channels":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM forced_channels")
        channels = cursor.fetchall()
        cursor.close()
        conn.close()

        markup = types.InlineKeyboardMarkup()
        for ch in channels:
            markup.add(types.InlineKeyboardButton(f"قناة: {ch['channel_username']} (ربح ${ch['reward']})", url=f"https://t.me/{ch['channel_username'].lstrip('@')}"))
        markup.add(types.InlineKeyboardButton("رجوع للقائمة الرئيسية", callback_data="back_to_main"))
        
        bot.edit_message_text("📢 القنوات المتاحة للاشتراك وجمع الرصيد:", chat_id, message_id, reply_markup=markup)

    elif data == "back_to_main":
        show_main_inline_menu(chat_id, message_id)

    elif data == "usr_cat_root":
        show_user_categories(user_id, chat_id, parent_id=None, message_id=message_id)

    elif data.startswith("usr_cat_"):
        cat_id = int(data.split("_")[2])
        show_user_categories(user_id, chat_id, parent_id=cat_id, message_id=message_id)

    elif data.startswith("buy_prod_"):
        cat_id = int(data.split("_")[2])
        process_buy_code(user_id, chat_id, cat_id, call.id)

    elif user_id == ADMIN_ID:
        if data == "adm_main_menu":
            show_admin_panel(chat_id, message_id)
        elif data == "adm_channels":
            show_admin_channels(chat_id, message_id)
        elif data == "adm_add_channel":
            msg = bot.send_message(chat_id, "أرسل معرف القناة ورصيد المكافأة بالشكل التالي (مثال: @MyChannel 0.5):")
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
        elif data == "adm_tree_0":
            show_admin_tree(chat_id, parent_id=0, message_id=message_id)
        elif data.startswith("adm_tree_"):
            p_id = int(data.split("_")[2])
            show_admin_tree(chat_id, parent_id=p_id, message_id=message_id)
        elif data.startswith("adm_newcat_"):
            p_id = int(data.split("_")[2])
            msg = bot.send_message(chat_id, "أرسل اسم القسم الفرعي الجديد:")
            bot.register_next_step_handler(msg, lambda m: save_new_category(m, p_id))
        elif data.startswith("adm_newprd_"):
            p_id = int(data.split("_")[2])
            msg = bot.send_message(chat_id, "أرسل اسم السلعة والسعر وبينهما شخطه (مثال: شدات ببجي - 2.5):")
            bot.register_next_step_handler(msg, lambda m: save_new_product(m, p_id))
        elif data.startswith("adm_up_codes_"):
            cat_id = int(data.split("_")[3])
            msg = bot.send_message(chat_id, "أرسل الأكواد الآن (كل كود في سطر):")
            bot.register_next_step_handler(msg, lambda m: save_uploaded_codes(m, cat_id))
        elif data.startswith("adm_del_"):
            cat_id = int(data.split("_")[2])
            delete_category_recursive(cat_id)
            bot.answer_callback_query(call.id, "تم الحذف بنجاح!")
            show_admin_tree(chat_id, parent_id=0, message_id=message_id)

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if message.from_user.id == ADMIN_ID:
        show_admin_panel(message.chat.id)

def show_admin_panel(chat_id, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 إدارة قنوات الاشتراك الإجباري والربح", callback_data="adm_channels"),
        types.InlineKeyboardButton("📂 إدارة الأقسام والسلع والألعاب", callback_data="adm_tree_0")
    )
    text = "⚙️ لوحة تحكم الآدمن:"
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def show_admin_channels(chat_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forced_channels")
    channels = cursor.fetchall()
    cursor.close()
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("➕ إضافة قناة جديدة", callback_data="adm_add_channel"))
    for ch in channels:
        markup.add(types.InlineKeyboardButton(f"🗑️ حذف {ch['channel_username']} (${ch['reward']})", callback_data=f"adm_delchan_{ch['id']}"))
    markup.add(types.InlineKeyboardButton("رجوع للوحة التحكم", callback_data="adm_main_menu"))

    text = "📢 إدارة القنوات:"
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def save_forced_channel(message):
    try:
        parts = message.text.split()
        ch_name = parts[0]
        reward = float(parts[1])
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO forced_channels (channel_username, reward) VALUES (%s, %s) ON CONFLICT (channel_username) DO UPDATE SET reward = EXCLUDED.reward", (ch_name, reward))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(message.chat.id, "تمت إضافة القناة بنجاح!")
        show_admin_channels(message.chat.id)
    except Exception:
        bot.send_message(message.chat.id, "خطأ بالصيغة! استخدم المثال: @ChannelName 0.5")

def show_user_categories(user_id, chat_id, parent_id=None, message_id=None):
    conn = get_db()
    cursor = conn.cursor()

    if parent_id is None:
        cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL")
        title = "🛒 أقسام المتجر (ببجي، بليارد، أوكسيد وغيرها):"
    else:
        cursor.execute("SELECT * FROM categories WHERE id=%s", (parent_id,))
        current_cat = cursor.fetchone()
        
        if current_cat and current_cat['price'] is not None:
            cursor.execute("SELECT COUNT(*) as count FROM codes WHERE category_id=%s AND is_used=0", (parent_id,))
            stock = cursor.fetchone()['count']
            
            text = f"السلعة: {current_cat['name']}\nالسعر: ${current_cat['price']:.2f}\nالمتوفر: {stock} كود"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("شراء الآن", callback_data=f"buy_prod_{parent_id}"))
            
            back_id = current_cat['parent_id']
            back_cb = f"usr_cat_{back_id}" if back_id is not None else "usr_cat_root"
            markup.add(types.InlineKeyboardButton("رجوع", callback_data=back_cb))
            
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
        markup.add(types.InlineKeyboardButton(f"{prefix} {c['name']}{price_str}", callback_data=f"usr_cat_{c['id']}"))

    if parent_id is not None:
        cursor.execute("SELECT parent_id FROM categories WHERE id=%s", (parent_id,))
        p = cursor.fetchone()
        back_cb = f"usr_cat_{p['parent_id']}" if p and p['parent_id'] is not None else "usr_cat_root"
        markup.add(types.InlineKeyboardButton("رجوع", callback_data=back_cb))
    else:
        markup.add(types.InlineKeyboardButton("رجوع للقائمة الرئيسية", callback_data="back_to_main"))

    cursor.close()
    conn.close()

    if message_id:
        try:
            bot.edit_message_text(title, chat_id, message_id, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, title, reply_markup=markup)
    else:
        bot.send_message(chat_id, title, reply_markup=markup)

def show_admin_tree(chat_id, parent_id=0, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    real_parent_id = None if parent_id == 0 else parent_id

    if real_parent_id is None:
        cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL")
        title = "شجرة الأقسام الرئيسية:"
    else:
        cursor.execute("SELECT * FROM categories WHERE id=%s", (real_parent_id,))
        current = cursor.fetchone()
        
        if current and current['price'] is not None:
            cursor.execute("SELECT COUNT(*) as count FROM codes WHERE category_id=%s AND is_used=0", (real_parent_id,))
            stock = cursor.fetchone()['count']
            text = f"إدارة السلعة: {current['name']}\nالسعر: ${current['price']:.2f}\nالأكواد المتوفرة: {stock}"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("رفع أكواد جديدة", callback_data=f"adm_up_codes_{real_parent_id}"))
            markup.add(types.InlineKeyboardButton("حذف هذه السلعة", callback_data=f"adm_del_{real_parent_id}"))
            back_id = current['parent_id'] if current['parent_id'] is not None else 0
            markup.add(types.InlineKeyboardButton("رجوع", callback_data=f"adm_tree_{back_id}"))
            
            cursor.close()
            conn.close()
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            else:
                bot.send_message(chat_id, text, reply_markup=markup)
            return

        cursor.execute("SELECT * FROM categories WHERE parent_id=%s", (real_parent_id,))
        title = f"إدارة قسم: {current['name']}"

    children = cursor.fetchall()
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("➕ إضافة قسم فرعي", callback_data=f"adm_newcat_{parent_id}"),
        types.InlineKeyboardButton("➕ إضافة سلعة/لعبة بسعر", callback_data=f"adm_newprd_{parent_id}")
    )

    for c in children:
        prefix = "🛒" if c['price'] is not None else "📁"
        price_str = f" (${c['price']:.2f})" if c['price'] is not None else ""
        markup.add(types.InlineKeyboardButton(f"{prefix} {c['name']}{price_str}", callback_data=f"adm_tree_{c['id']}"))

    if real_parent_id is not None:
        markup.add(types.InlineKeyboardButton("🗑️ حذف هذا القسم", callback_data=f"adm_del_{real_parent_id}"))
        cursor.execute("SELECT parent_id FROM categories WHERE id=%s", (real_parent_id,))
        p = cursor.fetchone()
        back_id = p['parent_id'] if p and p['parent_id'] is not None else 0
        markup.add(types.InlineKeyboardButton("رجوع للأعلى", callback_data=f"adm_tree_{back_id}"))
    else:
        markup.add(types.InlineKeyboardButton("العودة للوحة التحكم", callback_data="adm_main_menu"))

    cursor.close()
    conn.close()
    if message_id:
        bot.edit_message_text(title, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, title, reply_markup=markup)

def process_buy_code(user_id, chat_id, cat_id, callback_id):
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
        bot.answer_callback_query(callback_id, "رصيدك غير كافٍ للشراء!", show_alert=True)
        cursor.close()
        conn.close()
        return

    cursor.execute("SELECT id, code_text FROM codes WHERE category_id=%s AND is_used=0 LIMIT 1", (cat_id,))
    code_row = cursor.fetchone()

    if not code_row:
        bot.answer_callback_query(callback_id, "لا توجد أكواد متوفرة حالياً.", show_alert=True)
        cursor.close()
        conn.close()
        return

    new_balance = user_balance - cat['price']
    cursor.execute("UPDATE users SET balance=%s WHERE user_id=%s", (new_balance, user_id))
    cursor.execute("UPDATE codes SET is_used=1, used_by=%s WHERE id=%s", (user_id, code_row['id']))
    conn.commit()
    cursor.close()
    conn.close()

    bot.send_message(chat_id, f"تم الشراء بنجاح!\n\nالسلعة: {cat['name']}\nالكود الخاص بك:\n`{code_row['code_text']}`\n\nالرصيد المتبقي: ${new_balance:.2f}", parse_mode="Markdown")
    bot.answer_callback_query(callback_id, "تم التسليم بنجاح!")

def save_new_category(message, parent_id):
    name = message.text.strip()
    p_id = None if parent_id == 0 else parent_id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (parent_id, name) VALUES (%s, %s)", (p_id, name))
    conn.commit()
    cursor.close()
    conn.close()
    bot.send_message(message.chat.id, f"تم إنشاء القسم {name} بنجاح!")
    show_admin_tree(message.chat.id, parent_id=parent_id)

def save_new_product(message, parent_id):
    try:
        parts = message.text.split("-")
        name = parts[0].strip()
        price = float(parts[1].strip())
        p_id = None if parent_id == 0 else parent_id

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categories (parent_id, name, price) VALUES (%s, %s, %s)", (p_id, name, price))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(message.chat.id, f"تم إضافة السلعة {name} بسعر ${price:.2f} بنجاح!")
        show_admin_tree(message.chat.id, parent_id=parent_id)
    except Exception:
        bot.send_message(message.chat.id, "خطأ بالصيغة! استخدم الشخطة (مثال: شدات ببجي - 2.5).")

def save_uploaded_codes(message, cat_id):
    codes = [c.strip() for c in message.text.split('\n') if c.strip()]
    if not codes:
        bot.send_message(message.chat.id, "لم يتم إرسال أي أكواد.")
        return
    conn = get_db()
    cursor = conn.cursor()
    for code in codes:
        cursor.execute("INSERT INTO codes (category_id, code_text) VALUES (%s, %s)", (cat_id, code))
    conn.commit()
    cursor.close()
    conn.close()
    bot.send_message(message.chat.id, f"تم رفع {len(codes)} كود بنجاح!")
    show_admin_tree(message.chat.id, parent_id=cat_id)

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

if __name__ == '__main__':
    print("تشغيل خادم الويب الوهمي للحفاظ على اتصال Render...")
    keep_alive()
    print("البوت يعمل الآن بنجاح...")
    bot.infinity_polling()
