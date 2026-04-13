import sqlite3
import json
import os
from contextlib import contextmanager

# Путь к базе данных (можно переопределить через переменную окружения)
DB_FILE = os.getenv("DB_PATH", "vanguard.db")

@contextmanager
def get_db():
    """Контекстный менеджер для работы с БД"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_database():
    """Инициализация базы данных"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Таблица доступов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS access (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                level TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        
        # Таблица вайтлиста
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        
        # Таблица черного списка
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        
        # Таблица защищенных
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS protected (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        
        # Таблица стабильных ролей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stable_roles (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        
        # Таблица временных банов (pusy)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS temp_bans (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                expire_date TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        
        # Таблица жестких банов (apusy)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hard_bans (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                expire_date TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        
        # Таблица каналов логов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS log_channels (
                guild_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL
            )
        """)
        
        # Таблица настроек автороли
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auto_roles (
                guild_id TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                role_id TEXT
            )
        """)
        
        conn.commit()
        print("✅ База данных инициализирована")

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ДОСТУПАМИ
# ==========================================

def get_access(guild_id):
    """Получить все доступы для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, level FROM access WHERE guild_id = ?", (str(guild_id),))
        return {row['user_id']: row['level'] for row in cursor.fetchall()}

def add_access(guild_id, user_id, level):
    """Добавить доступ"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO access (guild_id, user_id, level)
            VALUES (?, ?, ?)
        """, (str(guild_id), str(user_id), level))

def remove_access(guild_id, user_id):
    """Удалить доступ"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM access WHERE guild_id = ? AND user_id = ?", 
                      (str(guild_id), str(user_id)))

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ВАЙТЛИСТОМ
# ==========================================

def get_whitelist(guild_id):
    """Получить вайтлист для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM whitelist WHERE guild_id = ?", (str(guild_id),))
        return [int(row['user_id']) for row in cursor.fetchall()]

def add_to_whitelist(guild_id, user_id):
    """Добавить в вайтлист"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO whitelist (guild_id, user_id)
            VALUES (?, ?)
        """, (str(guild_id), str(user_id)))

def remove_from_whitelist(guild_id, user_id):
    """Удалить из вайтлиста"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM whitelist WHERE guild_id = ? AND user_id = ?",
                      (str(guild_id), str(user_id)))

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ЧЕРНЫМ СПИСКОМ
# ==========================================

def get_blacklist(guild_id):
    """Получить черный список для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM blacklist WHERE guild_id = ?", (str(guild_id),))
        return [int(row['user_id']) for row in cursor.fetchall()]

def add_to_blacklist(guild_id, user_id):
    """Добавить в черный список"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO blacklist (guild_id, user_id)
            VALUES (?, ?)
        """, (str(guild_id), str(user_id)))

def remove_from_blacklist(guild_id, user_id):
    """Удалить из черного списка"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blacklist WHERE guild_id = ? AND user_id = ?",
                      (str(guild_id), str(user_id)))

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАЩИЩЕННЫМИ
# ==========================================

def get_protected(guild_id):
    """Получить защищенных для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM protected WHERE guild_id = ?", (str(guild_id),))
        return [int(row['user_id']) for row in cursor.fetchall()]

def add_to_protected(guild_id, user_id):
    """Добавить в защищенные"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO protected (guild_id, user_id)
            VALUES (?, ?)
        """, (str(guild_id), str(user_id)))

def remove_from_protected(guild_id, user_id):
    """Удалить из защищенных"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM protected WHERE guild_id = ? AND user_id = ?",
                      (str(guild_id), str(user_id)))

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С БАНАМИ
# ==========================================

def get_temp_bans(guild_id):
    """Получить временные баны для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, expire_date FROM temp_bans WHERE guild_id = ?", 
                      (str(guild_id),))
        return {row['user_id']: row['expire_date'] for row in cursor.fetchall()}

def add_temp_ban(guild_id, user_id, expire_date):
    """Добавить временный бан"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO temp_bans (guild_id, user_id, expire_date)
            VALUES (?, ?, ?)
        """, (str(guild_id), str(user_id), expire_date))

def remove_temp_ban(guild_id, user_id):
    """Удалить временный бан"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?",
                      (str(guild_id), str(user_id)))

def get_hard_bans(guild_id):
    """Получить жесткие баны для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, expire_date FROM hard_bans WHERE guild_id = ?",
                      (str(guild_id),))
        return {row['user_id']: row['expire_date'] for row in cursor.fetchall()}

def add_hard_ban(guild_id, user_id, expire_date):
    """Добавить жесткий бан"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO hard_bans (guild_id, user_id, expire_date)
            VALUES (?, ?, ?)
        """, (str(guild_id), str(user_id), expire_date))

def remove_hard_ban(guild_id, user_id):
    """Удалить жесткий бан"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM hard_bans WHERE guild_id = ? AND user_id = ?",
                      (str(guild_id), str(user_id)))

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С СТАБИЛЬНЫМИ РОЛЯМИ
# ==========================================

def get_stable_roles(guild_id):
    """Получить стабильные роли для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, role_id FROM stable_roles WHERE guild_id = ?",
                      (str(guild_id),))
        return {row['user_id']: int(row['role_id']) for row in cursor.fetchall()}

def set_stable_role(guild_id, user_id, role_id):
    """Установить стабильную роль"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO stable_roles (guild_id, user_id, role_id)
            VALUES (?, ?, ?)
        """, (str(guild_id), str(user_id), str(role_id)))

def remove_stable_role(guild_id, user_id):
    """Удалить стабильную роль"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stable_roles WHERE guild_id = ? AND user_id = ?",
                      (str(guild_id), str(user_id)))

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ЛОГАМИ
# ==========================================

def get_log_channel(guild_id):
    """Получить канал логов для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id FROM log_channels WHERE guild_id = ?",
                      (str(guild_id),))
        row = cursor.fetchone()
        return int(row['channel_id']) if row else None

def set_log_channel(guild_id, channel_id):
    """Установить канал логов"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO log_channels (guild_id, channel_id)
            VALUES (?, ?)
        """, (str(guild_id), str(channel_id)))

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С АВТОРОЛЬЮ
# ==========================================

def get_auto_role(guild_id):
    """Получить настройки автороли для сервера"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT enabled, role_id FROM auto_roles WHERE guild_id = ?",
                      (str(guild_id),))
        row = cursor.fetchone()
        if row:
            return {'enabled': bool(row['enabled']), 'role_id': row['role_id']}
        return {'enabled': False, 'role_id': None}

def set_auto_role(guild_id, enabled, role_id=None):
    """Установить настройки автороли"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO auto_roles (guild_id, enabled, role_id)
            VALUES (?, ?, ?)
        """, (str(guild_id), 1 if enabled else 0, str(role_id) if role_id else None))
