import sqlite3
import telebot
from telebot import types
import os
from threading import Thread
from flask import Flask

# --- إعداد سيرفر الوهمي للبورت (حتى لا يفصل رندر) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- التوكن والآيدي الخاص بك ---
TOKEN = "8635700320:AAHj21exFO4kj0hKu476B7Gx0rVyOwerHZs"
ADMIN_ID = 837914662
ADMIN_USERNAME = "@GD_GQ"  # يوزر الآدمن / الوكيل المسؤول

bot = telebot.TeleBot(TOKEN)

# --- إعداد قاعدة البيانات ---
def get_db():
    conn = sqlite3.connect('bot_database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER UNIQUE,
            username TEXT,
            balance REAL DEFAULT 0.0,
            is_authorized INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_msg', 'أهلاً بك في بوت الموزعين! اختر القسم المطلوب:')")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER DEFAULT NULL,
            name TEXT NOT NULL,
            price REAL DEFAULT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            code_text TEXT,
            is_used INTEGER DEFAULT 0,
            used_by INTEGER DEFAULT NULL
        )
    ''')

    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance, is_authorized) VALUES (?, 999999.0, 1)", (ADMIN_ID,))
    cursor.execute("UPDATE users SET is_authorized = 1 WHERE user_id = ?", (ADMIN_ID,))

    conn.commit()
    conn.close()

init_db()

def is_authorized(user_id, username=None):
    if user_id == ADMIN_ID:
        return True
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_authorized FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row['is_authorized'] == 1:
        conn.close()
        return True
        
    if username:
        clean_username = username.lstrip('@').lower()
        cursor.execute("SELECT rowid, is_authorized FROM users WHERE LOWER(username) = ?", (clean_username,))
        row_u = cursor.fetchone()
        if row_u and row_u['is_authorized'] == 1:
            cursor.execute("UPDATE users SET user_id = ?, is_authorized = 1 WHERE LOWER(username) = ?", (user_id, clean_username))
            conn.commit()
            conn.close()
            return True

    conn.close()
    return False

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🛒 الأقسام والمنتجات", "👤 حسابي ورصيدي")
    markup.row("💳 شحن رصيد")
    if user_id == ADMIN_ID:
        markup.row("⚙️ لوحة التحكم (للآدمن)")
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username

    conn = get_db()
    cursor = conn.cursor()
    if username:
        cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, 0.0) ON CONFLICT(user_id) DO UPDATE SET username=EXCLUDED.username", (user_id, username.lower()))
    else:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
    
    cursor.execute("SELECT value FROM settings WHERE key='welcome_msg'")
    welcome_msg = cursor.fetchone()['value']
    conn.commit()
    conn.close()
    
    if not is_authorized(user_id, username):
        safe_username = f"@{username}".replace("_", "\\_") if username else "غير محدد"
        safe_admin = ADMIN_USERNAME.replace("_", "\\_")
        
        bot.reply_to(
            message,
            f"❌ **عفواً، هذا البوت خاص بالموزعين المعتمدين فقط.**\n\n"
            f"🆔 **الآيدي (ID):** `{user_id}`\n"
            f"👤 **يوزرك:** {safe_username}\n\n"
            f"📌 يرجى إرسال الآيدي أو اليوزر للمسؤول لتفعيل حسابك:\n"
            f"👨‍💻 **المسؤول:** {safe_admin}",
            parse_mode="Markdown"
        )
        return

    bot.send_message(user_id, welcome_msg, reply_markup=main_menu(user_id))

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    username = message.from_user.username
    text = message.text

    if not is_authorized(user_id, username):
        return

    if text == "👤 حسابي ورصيدي":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        balance = row['balance'] if row else 0.0
        conn.close()
        bot.send_message(user_id, f"🆔 معرفك: `{user_id}`\n💰 رصيدك الحالي: **${balance:.2f}**", parse_mode="Markdown")

    elif text == "💳 شحن رصيد":
        safe_admin = ADMIN_USERNAME.replace("_", "\\_")
        bot.send_message(
            user_id,
            f"💳 **لشحن رصيدك في البوت:**\n\n"
            f"يرجى التواصل مع الوكيل لشراء وتعبئة الرصيد:\n"
            f"👨‍💻 **الوكيل:** {safe_admin}",
            parse_mode="Markdown"
        )

    elif text == "🛒 الأقسام والمنتجات":
        show_user_categories(user_id, message.chat.id, parent_id=None)

    elif text == "⚙️ لوحة التحكم (للآدمن)" and user_id == ADMIN_ID:
        show_admin_panel(user_id, message.chat.id)

def show_user_categories(user_id, chat_id, parent_id=None, message_id=None):
    conn = get_db()
    cursor = conn.cursor()

    if parent_id is None:
        cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL")
        title = "📁 **الأقسام الرئيسية:**"
    else:
        cursor.execute("SELECT * FROM categories WHERE id=?", (parent_id,))
        current_cat = cursor.fetchone()
        
        if current_cat and current_cat['price'] is not None:
            cursor.execute("SELECT COUNT(*) as count FROM codes WHERE category_id=? AND is_used=0", (parent_id,))
            stock = cursor.fetchone()['count']
            
            text = f"🛒 **السلعة:** {current_cat['name']}\n💵 **السعر:** ${current_cat['price']:.2f}\n📦 **المتوفر:** {stock} كود\n"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 شراء الآن", callback_data=f"buy_prod_{parent_id}"))
            
            back_id = current_cat['parent_id']
            back_cb = f"usr_cat_{back_id}" if back_id else "usr_cat_root"
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=back_cb))
            
            conn.close()
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
            else:
                bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
            return

        cursor.execute("SELECT * FROM categories WHERE parent_id=?", (parent_id,))
        title = f"📂 **قسم: {current_cat['name']}**"

    cats = cursor.fetchall()
    markup = types.InlineKeyboardMarkup()

    for c in cats:
        prefix = "🛒" if c['price'] is not None else "📁"
        price_str = f" (${c['price']:.2f})" if c['price'] is not None else ""
        markup.add(types.InlineKeyboardButton(f"{prefix} {c['name']}{price_str}", callback_data=f"usr_cat_{c['id']}"))

    if parent_id is not None:
        cursor.execute("SELECT parent_id FROM categories WHERE id=?", (parent_id,))
        p = cursor.fetchone()
        back_cb = f"usr_cat_{p['parent_id']}" if p and p['parent_id'] else "usr_cat_root"
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=back_cb))

    conn.close()

    if not cats and parent_id is None:
        bot.send_message(chat_id, "❌ لا توجد أقسام متوفرة حالياً.")
        return

    if message_id:
        try:
            bot.edit_message_text(title, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, title, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, title, parse_mode="Markdown", reply_markup=markup)

def show_admin_panel(user_id, chat_id, message_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ إضافة موزع معتمد", callback_data="adm_add_reseller"),
        types.InlineKeyboardButton("👥 الموزعين الحاليين", callback_data="adm_list_resellers"),
        types.InlineKeyboardButton("📂 إدارة الأقسام والسلع (الشجرة)", callback_data="adm_tree_0"),
        types.InlineKeyboardButton("💰 شحن رصيد مستخدم", callback_data="adm_add_balance"),
        types.InlineKeyboardButton("📝 تعديل رسالة الترحيب", callback_data="adm_edit_welcome"),
        types.InlineKeyboardButton("📊 الإحصائيات العامة", callback_data="adm_stats")
    )
    text = "⚙️ **لوحة التحكم الرئيسية (الآدمن):**"
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def show_admin_tree(chat_id, parent_id=0, message_id=None):
    conn = get_db()
    cursor = conn.cursor()

    real_parent_id = None if parent_id == 0 else parent_id

    if real_parent_id is None:
        cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL")
        title = "📂 **شجرة الأقسام (المستوى الرئيسي):**"
    else:
        cursor.execute("SELECT * FROM categories WHERE id=?", (real_parent_id,))
        current = cursor.fetchone()
        
        if current and current['price'] is not None:
            cursor.execute("SELECT COUNT(*) as count FROM codes WHERE category_id=? AND is_used=0", (real_parent_id,))
            stock = cursor.fetchone()['count']
            text = f"🛒 **إدارة السلعة:** {current['name']}\n💵 **السعر:** ${current['price']:.2f}\n🔑 **الأكواد المتوفرة:** {stock}"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔑 رفع أكواد جديدة لهذه السلعة", callback_data=f"adm_up_codes_{real_parent_id}"))
            markup.add(types.InlineKeyboardButton("🗑️ حذف هذه السلعة", callback_data=f"adm_del_{real_parent_id}"))
            
            back_id = current['parent_id'] if current['parent_id'] else 0
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=f"adm_tree_{back_id}"))
            
            conn.close()
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
            else:
                bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
            return

        cursor.execute("SELECT * FROM categories WHERE parent_id=?", (real_parent_id,))
        title = f"📂 **إدارة قسم:** {current['name']}"

    children = cursor.fetchall()
    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton("➕ إضافة قسم فرعي هنا", callback_data=f"adm_newcat_{parent_id}"),
        types.InlineKeyboardButton("➕ إضافة سلعة (بسعر) هنا", callback_data=f"adm_newprd_{parent_id}")
    )

    for c in children:
        prefix = "🛒 [سلعة]" if c['price'] is not None else "📁 [قسم]"
        price_str = f" (${c['price']:.2f})" if c['price'] is not None else ""
        markup.add(types.InlineKeyboardButton(f"{prefix} {c['name']}{price_str}", callback_data=f"adm_tree_{c['id']}"))

    if real_parent_id is not None:
        markup.add(types.InlineKeyboardButton("🗑️ حذف هذا القسم بالكامل", callback_data=f"adm_del_{real_parent_id}"))
        cursor.execute("SELECT parent_id FROM categories WHERE id=?", (real_parent_id,))
        p = cursor.fetchone()
        back_id = p['parent_id'] if p and p['parent_id'] else 0
        markup.add(types.InlineKeyboardButton("🔙 رجوع للأعلى", callback_data=f"adm_tree_{back_id}"))
    else:
        markup.add(types.InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="adm_main_menu"))

    conn.close()
    if message_id:
        try:
            bot.edit_message_text(title, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, title, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, title, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    username = call.from_user.username
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    if not is_authorized(user_id, username):
        bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية لاستخدام البوت.", show_alert=True)
        return

    if data == "usr_cat_root":
        show_user_categories(user_id, chat_id, parent_id=None, message_id=message_id)

    elif data.startswith("usr_cat_"):
        cat_id = int(data.split("_")[2])
        show_user_categories(user_id, chat_id, parent_id=cat_id, message_id=message_id)

    elif data.startswith("buy_prod_"):
        cat_id = int(data.split("_")[2])
        process_buy_code(user_id, chat_id, cat_id, call.id)

    elif user_id == ADMIN_ID:
        if data == "adm_main_menu":
            show_admin_panel(user_id, chat_id, message_id)

        elif data == "adm_add_reseller":
            msg = bot.send_message(chat_id, "👤 **أرسل الآن الآيدي (ID) أو اليوزر الخاص بالموزع:**\n\nمثال للآيدي: `123456789`\nمثال لاليوزر: `@username` أو `username`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_add_reseller)

        elif data == "adm_list_resellers":
            show_resellers_list(chat_id, message_id)

        elif data.startswith("adm_resinfo_"):
            target_uid = int(data.split("_")[2])
            show_single_reseller_info(chat_id, target_uid, message_id)

        elif data.startswith("adm_delres_"):
            target_uid = int(data.split("_")[2])
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id=? AND user_id!=?", (target_uid, ADMIN_ID))
            conn.commit()
            conn.close()
            bot.answer_callback_query(call.id, "✅ تم حذف الموزع بنجاح!")
            show_resellers_list(chat_id, message_id)

        elif data.startswith("adm_addbalto_"):
            target_uid = int(data.split("_")[2])
            msg = bot.send_message(chat_id, f"💰 أرسل المبلغ المراد إضافته لهذا الموزع (مثال: `10` أو `5.5`):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: process_direct_add_balance(m, target_uid))

        elif data.startswith("adm_tree_"):
            p_id = int(data.split("_")[2])
            show_admin_tree(chat_id, parent_id=p_id, message_id=message_id)

        elif data.startswith("adm_newcat_"):
            p_id = int(data.split("_")[2])
            msg = bot.send_message(chat_id, "📝 أرسل اسم **القسم الفرعي الجديد**:")
            bot.register_next_step_handler(msg, lambda m: save_new_category(m, p_id))

        elif data.startswith("adm_newprd_"):
            p_id = int(data.split("_")[2])
            msg = bot.send_message(chat_id, "📝 أرسل **اسم السلعة والسعر** بينهما شَخطَة `-`\nمثال: `يومي - 2.5`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: save_new_product(m, p_id))

        elif data.startswith("adm_up_codes_"):
            cat_id = int(data.split("_")[3])
            msg = bot.send_message(chat_id, "🔑 أرسل الأكواد الآن (ضع كل كود في سطر جديد):")
            bot.register_next_step_handler(msg, lambda m: save_uploaded_codes(m, cat_id))

        elif data.startswith("adm_del_"):
            cat_id = int(data.split("_")[2])
            delete_category_recursive(cat_id)
            bot.answer_callback_query(call.id, "✅ تم الحذف بنجاح!")
            show_admin_tree(chat_id, parent_id=0, message_id=message_id)

        elif data == "adm_add_balance":
            msg = bot.send_message(chat_id, "👤 أرسل آيدي المستخدم والمبلغ بمسافة بينهما\nمثال: `837914662 10`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_add_balance)

        elif data == "adm_edit_welcome":
            msg = bot.send_message(chat_id, "📝 أرسل رسالة الترحيب الجديدة للبوت:")
            bot.register_next_step_handler(msg, process_edit_welcome)

        elif data == "adm_stats":
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as u FROM users WHERE is_authorized=1")
            u_cnt = cursor.fetchone()['u']
            cursor.execute("SELECT COUNT(*) as c FROM codes WHERE is_used=0")
            c_cnt = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) as s FROM codes WHERE is_used=1")
            s_cnt = cursor.fetchone()['s']

            cursor.execute('''
                SELECT c.name, COUNT(cd.id) as sold_count
                FROM categories c
                LEFT JOIN codes cd ON c.id = cd.category_id AND cd.is_used = 1
                WHERE c.price IS NOT NULL
                GROUP BY c.id, c.name
            ''')
            products_sales = cursor.fetchall()
            conn.close()

            sales_details = ""
            for prod in products_sales:
                sales_details += f"▫️ **{prod['name']}:** {prod['sold_count']} كود\n"

            if not sales_details:
                sales_details = "لا توجد مبيعات حالياً.\n"

            text = (
                f"📊 **الإحصائيات العامة:**\n\n"
                f"👥 الموزعين المعتمدين: **{u_cnt}**\n"
                f"🔑 الأكواد المتاحة للشراء: **{c_cnt}**\n"
                f"✅ إجمالي الأكواد المباعة: **{s_cnt}**\n\n"
                f"📦 **عدد الأكواد المسحوبة حسب السلعة:**\n"
                f"{sales_details}"
            )

            bot.send_message(chat_id, text, parse_mode="Markdown")

def show_resellers_list(chat_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE is_authorized=1")
    resellers = cursor.fetchall()
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)
    for r in resellers:
        uname = f"@{r['username']}" if r['username'] else f"ID: {r['user_id']}"
        markup.add(types.InlineKeyboardButton(f"👤 {uname} (رصيد: ${r['balance']:.2f})", callback_data=f"adm_resinfo_{r['user_id']}"))

    markup.add(types.InlineKeyboardButton("🔙 رجوع للوحة التحكم", callback_data="adm_main_menu"))
    
    text = "👥 **قائمة الموزعين المعتمدين الحاليين:**\nاختر الموزع لعرض معلوماته وإدارته:"
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def show_single_reseller_info(chat_id, target_uid, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id=?", (target_uid,))
    res = cursor.fetchone()

    if not res:
        conn.close()
        bot.send_message(chat_id, "❌ لم يتم العثور على هذا المستخدم.")
        return

    cursor.execute("SELECT COUNT(*) as pulled FROM codes WHERE used_by=?", (target_uid,))
    pulled_count = cursor.fetchone()['pulled']
    conn.close()

    uname = f"@{res['username']}" if res['username'] else "بدون يوزر"
    text = (
        f"👤 **معلومات الموزع:**\n\n"
        f"🆔 الآيدي: `{res['user_id']}`\n"
        f"🔗 اليوزر: {uname}\n"
        f"💰 الرصيد الحالي: **${res['balance']:.2f}**\n"
        f"📦 عدد الأكواد المسحوبة: **{pulled_count}** كود"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ إضافة رصيد", callback_data=f"adm_addbalto_{target_uid}"),
        types.InlineKeyboardButton("🗑️ حذف الموزع", callback_data=f"adm_delres_{target_uid}")
    )
    markup.add(types.InlineKeyboardButton("🔙 رجوع لقائمة الموزعين", callback_data="adm_list_resellers"))

    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def process_direct_add_balance(message, target_uid):
    try:
        amount = float(message.text.strip())
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, target_uid))
        conn.commit()
        
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (target_uid,))
        new_bal = cursor.fetchone()['balance']
        conn.close()

        bot.send_message(message.chat.id, f"✅ تم إضافة **${amount}** بنجاح!\n💰 الرصيد الجديد للموزع: **${new_bal:.2f}**", parse_mode="Markdown")
        try:
            bot.send_message(target_uid, f"🎉 تم شحن حسابك بمبلغ **${amount}** من قبل الآدمن!\n💰 رصيدك الحالي: **${new_bal:.2f}**", parse_mode="Markdown")
        except Exception:
            pass
        
        show_single_reseller_info(message.chat.id, target_uid)
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ في القيمة المدخلة. يرجى إرسال رقم صحيح (مثال: `10`)")

def process_add_reseller(message):
    text = message.text.strip()
    conn = get_db()
    cursor = conn.cursor()

    if text.isdigit():
        target_id = int(text)
        cursor.execute("INSERT OR REPLACE INTO users (user_id, balance, is_authorized) VALUES (?, COALESCE((SELECT balance FROM users WHERE user_id=?), 0.0), 1)", (target_id, target_id))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ تم تفعيل الموزع بالآيدي `{target_id}` بنجاح!", parse_mode="Markdown")
        try:
            bot.send_message(target_id, "🎉 **تم تفعيل حسابك كموزع معتمد في البوت! اضغط /start لبدء الاستخدام.**", parse_mode="Markdown")
        except Exception:
            pass
    else:
        clean_username = text.lstrip('@').strip().lower()
        safe_username_display = clean_username.replace("_", "\\_")
        cursor.execute("SELECT user_id FROM users WHERE LOWER(username) = ?", (clean_username,))
        row = cursor.fetchone()
        
        if row and row['user_id']:
            cursor.execute("UPDATE users SET is_authorized = 1 WHERE LOWER(username) = ?", (clean_username,))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ تم تفعيل الموزع صاحب الحساب `@{safe_username_display}` بنجاح!", parse_mode="Markdown")
            try:
                bot.send_message(row['user_id'], "🎉 **تم تفعيل حسابك كموزع معتمد في البوت! اضغط /start لبدء الاستخدام.**", parse_mode="Markdown")
            except Exception:
                pass
        else:
            cursor.execute("INSERT OR IGNORE INTO users (username, is_authorized) VALUES (?, 1)", (clean_username,))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ تم إضافة اليوزر `@{safe_username_display}` لقائمة الموزعين المعتمدين.\nسيتم تفعيل حسابه تلقائياً بمجرد دخوله للبوت وضغطه على /start!", parse_mode="Markdown")

def process_buy_code(user_id, chat_id, cat_id, callback_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM categories WHERE id=?", (cat_id,))
    cat = cursor.fetchone()

    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    user_row = cursor.fetchone()
    user_balance = user_row['balance'] if user_row else 0.0

    if not cat or cat['price'] is None:
        bot.answer_callback_query(callback_id, "❌ حدث خطأ في المنتج.")
        conn.close()
        return

    if user_balance < cat['price']:
        bot.answer_callback_query(callback_id, "❌ رصيدك غير كافٍ للشراء!", show_alert=True)
        conn.close()
        return

    cursor.execute("SELECT id, code_text FROM codes WHERE category_id=? AND is_used=0 LIMIT 1", (cat_id,))
    code_row = cursor.fetchone()

    if not code_row:
        bot.answer_callback_query(callback_id, "❌ لا توجد أكواد متوفرة حالياً لهذه السلعة.", show_alert=True)
        conn.close()
        return

    new_balance = user_balance - cat['price']
    cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))
    cursor.execute("UPDATE codes SET is_used=1, used_by=? WHERE id=?", (user_id, code_row['id']))
    conn.commit()
    conn.close()

    bot.send_message(chat_id, f"🎉 **تم الشراء بنجاح!**\n\n📌 **السلعة:** {cat['name']}\n🔑 **الكود الخاص بك:**\n`{code_row['code_text']}`\n\n💰 **الرصيد المتبقي:** ${new_balance:.2f}", parse_mode="Markdown")
    bot.answer_callback_query(callback_id, "تم التسليم بنجاح!")

def save_new_category(message, parent_id):
    name = message.text.strip()
    p_id = None if parent_id == 0 else parent_id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (parent_id, name) VALUES (?, ?)", (p_id, name))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ تم إنشاء القسم **{name}** بنجاح!", parse_mode="Markdown")
    show_admin_tree(message.chat.id, parent_id=parent_id)

def save_new_product(message, parent_id):
    try:
        parts = message.text.split("-")
        name = parts[0].strip()
        price = float(parts[1].strip())
        p_id = None if parent_id == 0 else parent_id

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categories (parent_id, name, price) VALUES (?, ?, ?)", (p_id, name, price))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ تم إضافة السلعة **{name}** بسعر **${price:.2f}** بنجاح!", parse_mode="Markdown")
        show_admin_tree(message.chat.id, parent_id=parent_id)
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ بالصيغة! تأكد من وضع الشَخطَة بين الاسم والسعر (مثال: يومي - 2.5).")

def save_uploaded_codes(message, cat_id):
    codes = [c.strip() for c in message.text.split('\n') if c.strip()]
    if not codes:
        bot.send_message(message.chat.id, "❌ لم يتم إرسال أي أكواد.")
        return

    conn = get_db()
    cursor = conn.cursor()
    for code in codes:
        cursor.execute("INSERT INTO codes (category_id, code_text) VALUES (?, ?)", (cat_id, code))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ تم رفع **{len(codes)}** كود بنجاح!", parse_mode="Markdown")
    show_admin_tree(message.chat.id, parent_id=cat_id)

def delete_category_recursive(cat_id):
    conn = get_db()
    cursor = conn.cursor()
    
    def _delete(c_id):
        cursor.execute("SELECT id FROM categories WHERE parent_id=?", (c_id,))
        children = cursor.fetchall()
        for child in children:
            _delete(child['id'])
        cursor.execute("DELETE FROM codes WHERE category_id=?", (c_id,))
        cursor.execute("DELETE FROM categories WHERE id=?", (c_id,))

    _delete(cat_id)
    conn.commit()
    conn.close()

def process_add_balance(message):
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        amount = float(parts[1])

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, balance, is_authorized) VALUES (?, 0.0, 1)", (target_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, target_id))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"✅ تم شحن **${amount}** للمستخدم `{target_id}`", parse_mode="Markdown")
        try:
            bot.send_message(target_id, f"🎉 تم شحن حسابك بمبلغ **${amount}** بنجاح!", parse_mode="Markdown")
        except Exception:
            pass
    except Exception:
        bot.send_message(message.chat.id, "❌ صيغة خاطئة. أرسل الآيدي والمبلغ بمسافة بينهما.")

def process_edit_welcome(message):
    new_msg = message.text
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value=? WHERE key='welcome_msg'", (new_msg,))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "✅ تم تحديث رسالة الترحيب بنجاح!")

# --- تشغيل السيرفر الوهمي والبوت معاً ---
if __name__ == '__main__':
    print("تشغيل خادم الويب الوهمي للحفاظ على اتصال Render...")
    keep_alive()
    print("البوت الشجري المتكامل يعمل الآن...")
    bot.infinity_polling()
