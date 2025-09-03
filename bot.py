import logging
import sqlite3
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackContext, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters,
    ConversationHandler,
    PreCheckoutQueryHandler
)

# ==================== تنظیمات ====================
BOT_TOKEN = "7342514951:AAG2CfvhSAD8iGd1Rf3hmA901r_fl_jiXkM"  # توکن ربات از @BotFather
PROVIDER_TOKEN = ""  # توکن پرداخت از @BotFather
CHANNEL_ID = "@Freelances99"  # یوزرنیم کانال برای انتشار آگهی‌ها
ADMIN_ID = 7738438127  # آیدی عددی شما (ادمین)

# حالت‌های گفتگو
(
    SELECTING_AD_TYPE,
    GETTING_AD_DESCRIPTION,
    GETTING_AD_BUDGET,
    GETTING_AD_CONTACT
) = range(4)

# ==================== مدیریت دیتابیس ====================
class AdvancedDatabase:
    def __init__(self, db_name='advanced_bot.db'):
        self.db_name = db_name
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_name, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # جدول کاربران
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    coin_balance INTEGER DEFAULT 0,
                    is_banned BOOLEAN DEFAULT FALSE,
                    total_ads_posted INTEGER DEFAULT 0
                )
            ''')
            
            # جدول آگهی‌ها
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ads (
                    ad_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    ad_type TEXT CHECK(ad_type IN ('freelancer', 'employer')),
                    ad_description TEXT,
                    ad_budget TEXT,
                    ad_contact TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_published BOOLEAN DEFAULT FALSE,
                    is_approved BOOLEAN DEFAULT FALSE,
                    published_at TIMESTAMP NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول تراکنش‌ها
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    provider_payload TEXT UNIQUE,
                    telegram_payment_charge_id TEXT UNIQUE,
                    status TEXT CHECK(status IN ('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED')) DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول تنظیمات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_config (
                    key TEXT PRIMARY KEY CHECK(key IN (
                        'sponsor_channels', 
                        'ad_price', 
                        'price_last_changed', 
                        'admin_password',
                        'channel_username'
                    )),
                    value TEXT NOT NULL
                )
            ''')
            
            # جدول کانال‌های اسپانسر
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sponsor_channels (
                    channel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_username TEXT NOT NULL UNIQUE,
                    is_active BOOLEAN DEFAULT TRUE,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # درج مقادیر پیش‌فرض
            cursor.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES ('ad_price', '20000')")
            cursor.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES ('price_last_changed', ?)", 
                          (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
            cursor.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES ('admin_password', 'change_this_password_123!')")
            cursor.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES ('channel_username', ?)", (CHANNEL_ID,))
            
            # درج کانال‌های اسپانسر پیش‌فرض
            default_sponsors = [
                '@channel1',
                '@channel2', 
                '@channel3',
                '@channel4',
                '@channel5'
            ]
            
            for sponsor in default_sponsors:
                cursor.execute("INSERT OR IGNORE INTO sponsor_channels (channel_username) VALUES (?)", (sponsor,))
            
            conn.commit()
    
    def get_config_value(self, key, default=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            return result['value'] if result else default
    
    def set_config_value(self, key, value):
        valid_keys = ['sponsor_channels', 'ad_price', 'price_last_changed', 'admin_password', 'channel_username']
        if key not in valid_keys:
            raise ValueError("Invalid config key")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
    
    def get_sponsor_channels(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT channel_username FROM sponsor_channels WHERE is_active = TRUE")
            return [row['channel_username'] for row in cursor.fetchall()]
    
    def add_sponsor_channel(self, channel_username):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO sponsor_channels (channel_username) VALUES (?)", (channel_username,))
            conn.commit()
    
    def remove_sponsor_channel(self, channel_username):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sponsor_channels WHERE channel_username = ?", (channel_username,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return cursor.fetchone()
    
    def create_user(self, user_id, username, first_name, last_name):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                          (user_id, username, first_name, last_name))
            conn.commit()
    
    def update_user_balance(self, user_id, coin_change):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET coin_balance = coin_balance + ? WHERE user_id = ? AND is_banned = FALSE",
                          (coin_change, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def increment_user_ads(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET total_ads_posted = total_ads_posted + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
    
    def create_ad(self, user_id, ad_type, ad_description, ad_budget, ad_contact):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ads (user_id, ad_type, ad_description, ad_budget, ad_contact) 
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, ad_type, ad_description, ad_budget, ad_contact))
            conn.commit()
            return cursor.lastrowid
    
    def mark_ad_published(self, ad_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE ads 
                SET is_published = TRUE, is_approved = TRUE, published_at = CURRENT_TIMESTAMP 
                WHERE ad_id = ?
            """, (ad_id,))
            conn.commit()
    
    def create_transaction(self, user_id, amount, provider_payload):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (user_id, amount, provider_payload) 
                VALUES (?, ?, ?)
            """, (user_id, amount, provider_payload))
            conn.commit()
            return cursor.lastrowid
    
    def update_transaction_status(self, transaction_id, status, telegram_payment_charge_id=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if telegram_payment_charge_id:
                cursor.execute("""
                    UPDATE transactions 
                    SET status = ?, telegram_payment_charge_id = ?, completed_at = CURRENT_TIMESTAMP 
                    WHERE transaction_id = ?
                """, (status, telegram_payment_charge_id, transaction_id))
            else:
                cursor.execute("""
                    UPDATE transactions 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP 
                    WHERE transaction_id = ?
                """, (status, transaction_id))
            conn.commit()
    
    def get_user_transactions(self, user_id, limit=10):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            return cursor.fetchall()
    
    def ban_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_banned = TRUE WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def unban_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_banned = FALSE WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0

# ایجاد نمونه دیتابیس
db = AdvancedDatabase()

# ==================== دستورات اصلی ربات ====================
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    db.create_user(user.id, user.username, user.first_name, user.last_name)
    
    user_data = db.get_user(user.id)
    if user_data and user_data['is_banned']:
        await update.message.reply_text("❌ حساب شما مسدود شده است. لطفاً با پشتیبانی تماس بگیرید.")
        return
    
    # چک کردن عضویت در کانال‌های اسپانسر
    sponsor_channels = db.get_sponsor_channels()
    not_joined = []
    
    for channel in sponsor_channels:
        if channel.strip():
            try:
                member = await context.bot.get_chat_member(channel.strip(), user.id)
                if member.status in ['left', 'kicked']:
                    not_joined.append(channel.strip())
            except Exception as e:
                logging.error(f"خطا در بررسی عضویت برای {channel}: {e}")
                not_joined.append(channel.strip())
    
    if not_joined:
        channels_text = "\n".join([f"🔹 {channel}" for channel in not_joined])
        keyboard = [[InlineKeyboardButton("✅ بررسی مجدد عضویت", callback_data='check_membership')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 سلام {user.first_name}!\n\n"
            f"⚠️ برای استفاده از ربات، لطفاً در کانال‌های اسپانسر زیر عضو شوید:\n{channels_text}\n\n"
            f"پس از عضویت، روی دکمه زیر کلیک کنید:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return
    
    await show_main_menu(update)

async def check_membership_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    sponsor_channels = db.get_sponsor_channels()
    not_joined = []
    
    for channel in sponsor_channels:
        if channel.strip():
            try:
                member = await context.bot.get_chat_member(channel.strip(), user.id)
                if member.status in ['left', 'kicked']:
                    not_joined.append(channel.strip())
            except Exception:
                not_joined.append(channel.strip())
    
    if not_joined:
        channels_text = "\n".join([f"🔹 {channel}" for channel in not_joined])
        await query.edit_message_text(
            f"❌ هنوز در کانال‌های زیر عضو نشدی:\n{channels_text}\n\nلطفاً عضو شو و دوباره بررسی کن:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ بررسی مجدد عضویت", callback_data='check_membership')]]),
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text("✅ عالی! حالا میتونی از منوی اصلی استفاده کنی.")
        await show_main_menu_from_callback(query)

async def show_main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("💰 خرید سکه", callback_data='buy_coin')],
        [InlineKeyboardButton("📢 ارسال آگهی", callback_data='post_ad')],
        [InlineKeyboardButton("📊 موجودی سکه", callback_data='check_balance')],
        [InlineKeyboardButton("📋 تاریخچه تراکنش‌ها", callback_data='transaction_history')],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    user = update.effective_user
    user_data = db.get_user(user.id)
    balance = user_data['coin_balance'] if user_data else 0
    
    await update.message.reply_text(
        f"🎯 <b>منوی اصلی</b>\n\n"
        f"👤 کاربر: {user.first_name}\n"
        f"💰 موجودی سکه: {balance}\n\n"
        f"لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def show_main_menu_from_callback(query):
    keyboard = [
        [InlineKeyboardButton("💰 خرید سکه", callback_data='buy_coin')],
        [InlineKeyboardButton("📢 ارسال آگهی", callback_data='post_ad')],
        [InlineKeyboardButton("📊 موجودی سکه", callback_data='check_balance')],
        [InlineKeyboardButton("📋 تاریخچه تراکنش‌ها", callback_data='transaction_history')],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    user = query.from_user
    user_data = db.get_user(user.id)
    balance = user_data['coin_balance'] if user_data else 0
    
    await query.message.reply_text(
        f"🎯 <b>منوی اصلی</b>\n\n"
        f"👤 کاربر: {user.first_name}\n"
        f"💰 موجودی سکه: {balance}\n\n"
        f"لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def buy_coin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    if user_data and user_data['is_banned']:
        await query.message.reply_text("❌ حساب شما مسدود شده است. لطفاً با پشتیبانی تماس بگیرید.")
        return
    
    current_price = int(db.get_config_value('ad_price', '20000'))
    
    # ایجاد invoice برای پرداخت
    title = "💰 خرید 1 سکه"
    description = "با خرید این سکه می‌توانید یک آگهی در کانال منتشر کنید"
    payload = f"coin_purchase_{user_id}_{datetime.now().timestamp()}"
    currency = "IRT"  # ریال ایران
    price = current_price * 10  # تبدیل به ریال (چون تلگرام از ریال استفاده می‌کند)
    
    prices = [LabeledPrice("1 سکه", price)]
    
    # ذخیره تراکنش در دیتابیس
    transaction_id = db.create_transaction(user_id, current_price, payload)
    
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter="coin-purchase",
        need_name=True,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False
    )

async def precheckout_callback(update: Update, context: CallbackContext):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    successful_payment = update.message.successful_payment
    
    # پیدا کردن تراکنش بر اساس payload
    transactions = db.get_user_transactions(user_id, 5)
    target_transaction = None
    
    for transaction in transactions:
        if transaction['provider_payload'] == successful_payment.invoice_payload:
            target_transaction = transaction
            break
    
    if target_transaction:
        db.update_transaction_status(
            target_transaction['transaction_id'], 
            'SUCCESS', 
            successful_payment.telegram_payment_charge_id
        )
        
        # افزودن سکه به حساب کاربر
        db.update_user_balance(user_id, 1)
        
        await update.message.reply_text(
            "✅ <b>پرداخت شما با موفقیت انجام شد!</b>\n\n"
            f"💎 1 سکه به حساب شما اضافه شد.\n"
            f"💰 مبلغ پرداختی: {successful_payment.total_amount // 10} تومان\n\n"
            f"📧 اکنون می‌توانید از منوی اصلی آگهی خود را ثبت کنید.",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "❌ خطایی در پردازش پرداخت رخ داد. لطفاً با پشتیبانی تماس بگیرید."
        )

async def post_ad(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    if user_data and user_data['is_banned']:
        await query.message.reply_text("❌ حساب شما مسدود شده است. لطفاً با پشتیبانی تماس بگیرید.")
        return
    
    if user_data and user_data['coin_balance'] > 0:
        keyboard = [
            [InlineKeyboardButton("👨‍💼 فریلنسر (انجام دهنده)", callback_data='ad_type_freelancer')],
            [InlineKeyboardButton("👔 کارفرما (درخواست کننده)", callback_data='ad_type_employer')],
            [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            "📝 <b>انتخاب نوع آگهی</b>\n\n"
            "لطفاً نوع آگهی خود را انتخاب کنید:\n\n"
            "👨‍💼 <b>فریلنسر</b>: اگر شما خدماتی ارائه می‌دهید\n"
            "👔 <b>کارفرما</b>: اگر شما به دنبال نیروی متخصص هستید",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await query.message.edit_text(
            "❌ موجودی سکه شما کافی نیست. لطفاً сначала سکه خریداری کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 خرید سکه", callback_data='buy_coin')]])
        )

async def ad_type_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    ad_type = query.data.split('_')[-1]
    context.user_data['ad_type'] = ad_type
    ad_type_persian = "فریلنسر" if ad_type == 'freelancer' else "کارفرما"
    
    await query.message.edit_text(
        f"📝 <b>توضیحات آگهی ({ad_type_persian})</b>\n\n"
        "لطفاً توضیحات کامل آگهی خود را وارد کنید:\n\n"
        "✅ شامل:\n"
        "- مهارت‌ها و تخصص‌های شما (برای فریلنسرها)\n"
        "- شرح کامل پروژه (برای کارفرماها)\n"
        "- زمینه کاری و جزئیات مورد نیاز\n\n"
        "✅ می‌توانید از اموجی‌ها برای جذاب‌تر شدن آگهی استفاده کنید\n"
        "✅ حداکثر 1000 کاراکتر مجاز است\n\n"
        "❌ از قرار دادن لینک‌های غیرمجاز خودداری کنید",
        parse_mode='HTML'
    )
    
    return GETTING_AD_DESCRIPTION

async def get_ad_description(update: Update, context: CallbackContext):
    description = update.message.text
    
    if len(description) > 5000:
        await update.message.reply_text(
            "❌ متن آگهی شما بیش از 5000 کاراکتر است. لطفاً متن کوتاه‌تری وارد کنید."
        )
        return GETTING_AD_DESCRIPTION
    
    context.user_data['ad_description'] = description
    
    ad_type = context.user_data['ad_type']
    ad_type_persian = "فریلنسر" if ad_type == 'freelancer' else "کارفرما"
    
    budget_example = "50,000 تومان" if ad_type == 'freelancer' else "تا 500,000,000 تومان"
    
    await update.message.reply_text(
        f"💰 <b>مبلغ پیشنهادی ({ad_type_persian})</b>\n\n"
        "لطفاً مبلغ پیشنهادی خود را وارد کنید:\n\n"
        f"📌 مثال: {budget_example}\n\n"
        "✅ می‌توانید به صورت زیر وارد کنید:\n"
        "- 200000 تومان\n"
        "- 300,000 تومان\n"
        "- تا 500 میلیون تومان\n"
        "- توافقی\n\n"
        "💰 برای آگهی‌های کارفرمایی می‌توانید بازه قیمتی مشخص کنید",
        parse_mode='HTML'
    )
    
    return GETTING_AD_BUDGET

async def get_ad_budget(update: Update, context: CallbackContext):
    budget = update.message.text
    context.user_data['ad_budget'] = budget
    
    await update.message.reply_text(
        "📞 <b>روش تماس</b>\n\n"
        "لطفاً روش تماس خود را وارد کنید:\n\n"
        "📌 مثال‌ها:\n"
        "• آیدی تلگرام: @username\n"
        "• شماره تماس: ۰۹۱۲۳۴۵۶۷۸۹\n"
        "• ایمیل: example@email.com\n"
        "• لینک LinkedIn: linkedin.com/in/username\n\n"
        "✅ این اطلاعات در آگهی نمایش داده خواهد شد\n"
        "❌ از قرار دادن اطلاعات شخصی غیرضروری خودداری کنید",
        parse_mode='HTML'
    )
    
    return GETTING_AD_CONTACT

async def get_ad_contact(update: Update, context: CallbackContext):
    contact = update.message.text
    user_id = update.effective_user.id
    
    # جمع‌آوری تمام اطلاعات آگهی
    ad_type = context.user_data['ad_type']
    ad_description = context.user_data['ad_description']
    ad_budget = context.user_data['ad_budget']
    
    # ایجاد آگهی در دیتابیس
    ad_id = db.create_ad(user_id, ad_type, ad_description, ad_budget, contact)
    
    # کسر یک سکه از حساب کاربر
    if db.update_user_balance(user_id, -1):
        # افزایش شمارش آگهی‌های کاربر
        db.increment_user_ads(user_id)
        
        # ارسال آگهی به کانال
        ad_type_persian = "فریلنسر" if ad_type == 'freelancer' else "کارفرما"
        ad_type_emoji = "👨‍💼" if ad_type == 'freelancer' else "👔"
        
        ad_message = (
            f"{ad_type_emoji} <b>آگهی جدید ({ad_type_persian})</b>\n\n"
            f"📋 <b>توضیحات:</b>\n{ad_description}\n\n"
            f"💰 <b>مبلغ پیشنهادی:</b> {ad_budget}\n\n"
            f"📞 <b>روش تماس:</b> {contact}\n\n"
            f"🔔 <b>برای ارسال آگهی:</b> @{context.bot.username}\n"
            f"🕒 <b>زمان ارسال:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        try:
            channel_username = db.get_config_value('channel_username', CHANNEL_ID)
            await context.bot.send_message(
                chat_id=channel_username,
                text=ad_message,
                parse_mode='HTML'
            )
            db.mark_ad_published(ad_id)
            
            await update.message.reply_text(
                "✅ <b>آگهی شما با موفقیت در کانال منتشر شد!</b>\n\n"
                f"📌 می‌توانید آگهی خود را در کانال مشاهده کنید: {channel_username}\n\n"
                "🔄 برای ارسال آگهی جدید، از منوی اصلی اقدام کنید.",
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"خطا در ارسال آگهی: {e}")
            # برگرداندن سکه به کاربر
            db.update_user_balance(user_id, 1)
            await update.message.reply_text(
                "❌ خطایی در ارسال آگهی به کانال رخ داد. سکه به حساب شما بازگردانده شد.\n"
                "لطفاً稍后再试 یا با پشتیبانی تماس بگیرید."
            )
    else:
        await update.message.reply_text(
            "❌ خطایی در کسر سکه رخ داد. لطفاً با پشتیبانی تماس بگیرید."
        )
    
    # پاک کردن داده‌های موقت
    context.user_data.clear()
    
    await show_main_menu(update)
    return ConversationHandler.END

async def check_balance(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    if user_data:
        current_price = int(db.get_config_value('ad_price', '20000'))
        await query.message.edit_text(
            f"💰 <b>موجودی حساب شما</b>\n\n"
            f"🪙 سکه: {user_data['coin_balance']}\n"
            f"📊 تعداد آگهی‌های ارسال شده: {user_data['total_ads_posted']}\n\n"
            f"💵 قیمت هر آگهی: {current_price} تومان\n\n"
            f"🔔 برای خرید سکه بیشتر، گزینه «خرید سکه» را انتخاب کنید.",
            parse_mode='HTML'
        )
    else:
        await query.message.edit_text("❌ خطایی در دریافت اطلاعات حساب شما رخ داد.")

async def transaction_history(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    transactions = db.get_user_transactions(user_id, 10)
    
    if not transactions:
        await query.message.edit_text("📝 شما هیچ تراکنشی ندارید.")
        return
    
    history_text = "📋 <b>تاریخچه تراکنش‌های شما</b>\n\n"
    
    for i, transaction in enumerate(transactions, 1):
        status_emoji = "✅" if transaction['status'] == 'SUCCESS' else "🔄" if transaction['status'] == 'PENDING' else "❌"
        status_text = {
            'SUCCESS': 'موفق',
            'PENDING': 'در انتظار',
            'FAILED': 'ناموفق',
            'REFUNDED': 'عودت شده'
        }.get(transaction['status'], transaction['status'])
        
        history_text += (
            f"{i}. مبلغ: <b>{transaction['amount']} تومان</b>\n"
            f"   وضعیت: {status_emoji} {status_text}\n"
            f"   تاریخ: {transaction['created_at']}\n\n"
        )
    
    await query.message.edit_text(history_text, parse_mode='HTML')

async def help_command(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    help_text = """
🤖 <b>راهنمای ربات فریلنسریاب</b>

💰 <b>خرید سکه:</b>
- با پرداخت مبلغ مشخص، سکه دریافت کنید
- هر سکه اجازه انتشار یک آگهی را می‌دهد

📢 <b>ارسال آگهی:</b>
- به عنوان فریلنسر (ارائه‌دهنده خدمت)
- یا به عنوان کارفرما (درخواست‌دهنده)

📋 <b>فرآیند ارسال آگهی:</b>
1. انتخاب نوع آگهی (فریلنسر/کارفرما)
2. وارد کردن توضیحات کامل
3. مشخص کردن مبلغ پیشنهادی
4. وارد کردن روش تماس

📞 <b>پشتیبانی:</b>
برای مشکلات فنی با آیدی @admin تماس بگیرید.

⚡ <b>نکات مهم:</b>
- آگهی‌ها پس از پرداخت بلافاصله منتشر می‌شوند
- از قرار دادن محتوای غیرمجاز خودداری کنید
- در صورت تخلف، حساب شما مسدود خواهد شد
"""
    
    await query.message.edit_text(help_text, parse_mode='HTML')

async def cancel(update: Update, context: CallbackContext):
    if 'ad_type' in context.user_data:
        context.user_data.clear()
    
    await update.message.reply_text("❌ عملیات کنسل شد.")
    await show_main_menu(update)
    return ConversationHandler.END

# ==================== دستورات ادمین ====================
async def admin_login(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی denied.")
        return
    
    if context.args:
        password = context.args[0]
        stored_password = db.get_config_value('admin_password')
        
        if password == stored_password:
            context.user_data['admin_authenticated'] = True
            await update.message.reply_text("✅ وارد شدید. دستورات ادمین در دسترس هستند.")
        else:
            await update.message.reply_text("❌ رمز عبور اشتباه است.")
    else:
        await update.message.reply_text("⚠️ لطفاً رمز عبور را وارد کنید:\n/admin <password>")

def admin_required(func):
    async def wrapper(update: Update, context: CallbackContext):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ دسترسی denied.")
            return
        
        if not context.user_data.get('admin_authenticated', False):
            await update.message.reply_text("❌ ابتدا باید وارد شوید:\n/admin <password>")
            return
        
        return await func(update, context)
    return wrapper

@admin_required
async def set_price(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً قیمت جدید را وارد کنید:\n/setprice <مبلغ به تومان>")
        return
    
    try:
        new_price = int(context.args[0])
        if new_price <= 0:
            await update.message.reply_text("❌ قیمت باید عدد مثبت باشد.")
            return
        
        db.set_config_value('ad_price', str(new_price))
        db.set_config_value('price_last_changed', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        await update.message.reply_text(f"✅ قیمت آگهی به {new_price} تومان تنظیم شد.")
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")

@admin_required
async def show_price(update: Update, context: CallbackContext):
    current_price = int(db.get_config_value('ad_price', '20000'))
    last_changed = db.get_config_value('price_last_changed', 'نامشخص')
    
    await update.message.reply_text(
        f"💰 قیمت فعلی هر آگهی: {current_price} تومان\n"
        f"📅 آخرین تغییر: {last_changed}"
    )

@admin_required
async def add_sponsor(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً یوزرنیم کانال را وارد کنید:\n/addsponsor @channel_username")
        return
    
    channel_username = context.args[0]
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    
    db.add_sponsor_channel(channel_username)
    await update.message.reply_text(f"✅ کانال {channel_username} به لیست اسپانسرها اضافه شد.")

@admin_required
async def remove_sponsor(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً یوزرنیم کانال را وارد کنید:\n/removesponsor @channel_username")
        return
    
    channel_username = context.args[0]
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    
    if db.remove_sponsor_channel(channel_username):
        await update.message.reply_text(f"✅ کانال {channel_username} از لیست اسپانسرها حذف شد.")
    else:
        await update.message.reply_text(f"❌ کانال {channel_username} یافت نشد.")

@admin_required
async def list_sponsors(update: Update, context: CallbackContext):
    sponsors = db.get_sponsor_channels()
    
    if not sponsors:
        await update.message.reply_text("❌ هیچ کانال اسپانسری ثبت نشده است.")
        return
    
    sponsors_text = "📋 <b>لیست کانال‌های اسپانسر</b>\n\n"
    for i, sponsor in enumerate(sponsors, 1):
        sponsors_text += f"{i}. {sponsor}\n"
    
    await update.message.reply_text(sponsonsors_text, parse_mode='HTML')

@admin_required
async def set_channel(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً یوزرنیم کانال را وارد کنید:\n/setchannel @channel_username")
        return
    
    channel_username = context.args[0]
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    
    db.set_config_value('channel_username', channel_username)
    await update.message.reply_text(f"✅ کانال مقصد به {channel_username} تنظیم شد.")

@admin_required
async def admin_stats(update: Update, context: CallbackContext):
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # تعداد کاربران
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        # تعداد کاربران فعال
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = FALSE")
        active_users = cursor.fetchone()[0]
        
        # تعداد کاربران مسدود شده
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = TRUE")
        banned_users = cursor.fetchone()[0]
        
        # تعداد آگهی‌ها
        cursor.execute("SELECT COUNT(*) FROM ads")
        ad_count = cursor.fetchone()[0]
        
        # تعداد آگهی‌های منتشر شده
        cursor.execute("SELECT COUNT(*) FROM ads WHERE is_published = TRUE")
        published_ads = cursor.fetchone()[0]
        
        # تعداد تراکنش‌های موفق
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'SUCCESS'")
        success_transactions = cursor.fetchone()[0]
        
        # درآمد کل
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE status = 'SUCCESS'")
        total_income = cursor.fetchone()[0] or 0
        
        # تعداد کانال‌های اسپانسر
        cursor.execute("SELECT COUNT(*) FROM sponsor_channels WHERE is_active = TRUE")
        sponsor_count = cursor.fetchone()[0]
    
    stats_text = f"""
📊 <b>آمار کامل ربات</b>

👥 <b>کاربران:</b>
- کل کاربران: {user_count}
- کاربران فعال: {active_users}
- کاربران مسدود: {banned_users}

📢 <b>آگهی‌ها:</b>
- کل آگهی‌ها: {ad_count}
- آگهی‌های منتشر شده: {published_ads}

💰 <b>مالی:</b>
- تراکنش‌های موفق: {success_transactions}
- درآمد کل: {total_income} تومان

📣 <b>کانال‌ها:</b>
- کانال اسپانسر: {sponsor_count}
- کانال مقصد: {db.get_config_value('channel_username')}

⚙️ <b>تنظیمات:</b>
- قیمت فعلی: {db.get_config_value('ad_price')} تومان
- آخرین تغییر قیمت: {db.get_config_value('price_last_changed')}
"""
    await update.message.reply_text(stats_text, parse_mode='HTML')

@admin_required
async def ban_user(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً آیدی کاربر را وارد کنید:\n/ban <user_id>")
        return
    
    try:
        user_id = int(context.args[0])
        if db.ban_user(user_id):
            await update.message.reply_text(f"✅ کاربر {user_id} مسدود شد.")
        else:
            await update.message.reply_text(f"❌ کاربر {user_id} یافت نشد.")
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک آیدی معتبر وارد کنید.")

@admin_required
async def unban_user(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً آیدی کاربر را وارد کنید:\n/unban <user_id>")
        return
    
    try:
        user_id = int(context.args[0])
        if db.unban_user(user_id):
            await update.message.reply_text(f"✅ کاربر {user_id} آزاد شد.")
        else:
            await update.message.reply_text(f"❌ کاربر {user_id} یافت نشد.")
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک آیدی معتبر وارد کنید.")

@admin_required
async def change_password(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً رمز عبور جدید را وارد کنید:\n/changepassword <رمز جدید>")
        return
    
    new_password = context.args[0]
    db.set_config_value('admin_password', new_password)
    
    await update.message.reply_text("✅ رمز عبور ادمین تغییر کرد.")

@admin_required
async def admin_help(update: Update, context: CallbackContext):
    help_text = """
🔧 <b>دورات ادمین</b>

/login <password> - ورود به پنل ادمین
/setprice <مبلغ> - تنظیم قیمت جدید آگهی
/showprice - نمایش قیمت فعلی
/setchannel @channel - تنظیم کانال مقصد
/addsponsor @channel - اضافه کردن کانال اسپانسر
/removesponsor @channel - حذف کانال اسپانسر
/listsponsors - نمایش لیست کانال‌های اسپانسر
/stats - نمایش آمار کامل ربات
/ban <user_id> - مسدود کردن کاربر
/unban <user_id> - آزاد کردن کاربر
/changepassword <رمز جدید> - تغییر رمز عبور ادمین

⚠️ توجه: تمام دستورات ادمین نیاز به احراز هویت دارند.
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

# ==================== راه‌اندازی ربات ====================
def main():
    # ایجاد application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # افزودن handlers اصلی
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_membership_callback, pattern='^check_membership$'))
    application.add_handler(CallbackQueryHandler(buy_coin, pattern='^buy_coin$'))
    application.add_handler(CallbackQueryHandler(post_ad, pattern='^post_ad$'))
    application.add_handler(CallbackQueryHandler(ad_type_selected, pattern='^ad_type_'))
    application.add_handler(CallbackQueryHandler(check_balance, pattern='^check_balance$'))
    application.add_handler(CallbackQueryHandler(transaction_history, pattern='^transaction_history$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^help$'))
    application.add_handler(CallbackQueryHandler(show_main_menu_from_callback, pattern='^main_menu$'))
    
    # handlers برای حالت گفتگو (ثبت آگهی)
    ad_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ad_type_selected, pattern='^ad_type_')],
        states={
            GETTING_AD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad_description)],
            GETTING_AD_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad_budget)],
            GETTING_AD_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad_contact)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(ad_conv_handler)
    
    # handlers برای پرداخت
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    
    # handlers برای ادمین
    application.add_handler(CommandHandler("admin", admin_login))
    application.add_handler(CommandHandler("setprice", set_price))
    application.add_handler(CommandHandler("showprice", show_price))
    application.add_handler(CommandHandler("setchannel", set_channel))
    application.add_handler(CommandHandler("addsponsor", add_sponsor))
    application.add_handler(CommandHandler("removesponsor", remove_sponsor))
    application.add_handler(CommandHandler("listsponsors", list_sponsors))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("changepassword", change_password))
    application.add_handler(CommandHandler("adminhelp", admin_help))
    
    # راه‌اندازی ربات
    application.run_polling()

if __name__ == '__main__':
    main()