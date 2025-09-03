import sqlite3
import datetime
from contextlib import contextmanager

@contextmanager
def get_db_connection():
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # ایجاد جدول کاربران
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                coin_balance INTEGER DEFAULT 0
            )
        ''')
        
        # ایجاد جدول آگهی‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ads (
                ad_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ad_type TEXT,
                ad_text TEXT,
                ad_contact TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_published BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # ایجاد جدول تراکنش‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # ایجاد جدول تنظیمات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # درج مقادیر پیش‌فرض
        cursor.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES ('sponsor_channels', '@channel1\\n@channel2\\n@channel3\\n@channel4')")
        cursor.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES ('ad_price', '20000')")
        cursor.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES ('price_last_increased', '2023-01-01')")
        
        conn.commit()

def get_config_value(key, default=None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM bot_config WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result['value'] if result else default

def set_config_value(key, value):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

def get_user(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

def create_user(user_id, username, first_name, last_name):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                      (user_id, username, first_name, last_name))
        conn.commit()

def update_user_balance(user_id, coin_change):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET coin_balance = coin_balance + ? WHERE user_id = ?",
                      (coin_change, user_id))
        conn.commit()

def create_ad(user_id, ad_type, ad_text, ad_contact):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ads (user_id, ad_type, ad_text, ad_contact) VALUES (?, ?, ?, ?)",
                      (user_id, ad_type, ad_text, ad_contact))
        conn.commit()
        return cursor.lastrowid

def mark_ad_published(ad_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE ads SET is_published = TRUE WHERE ad_id = ?", (ad_id,))
        conn.commit()

def create_transaction(transaction_id, user_id, amount):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO transactions (transaction_id, user_id, amount) VALUES (?, ?, ?)",
                      (transaction_id, user_id, amount))
        conn.commit()

def update_transaction_status(transaction_id, status):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET status = ? WHERE transaction_id = ?", (status, transaction_id))
        conn.commit()