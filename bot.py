import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

# Путь к БД
DB_PATH = "sportbot.db"

# Глобальная блокировка для потокобезопасности
_db_lock = threading.RLock()

# Кеш единого соединения
_connection = None


def _get_connection():
    """Получить глобальное соединение к БД с правильными параметрами"""
    global _connection
    
    if _connection is None:
        _connection = sqlite3.connect(
            DB_PATH,
            check_same_thread=False,  # Разрешить доступ из разных потоков (aiogram использует asyncio)
            timeout=10.0,  # Таймаут 10 секунд при блокировке
            isolation_level=None  # Автокоммит по умолчанию для лучшей производительности
        )
        # Включить foreign keys
        _connection.execute("PRAGMA foreign_keys = ON")
        # Установить WAL mode для лучшей параллельности
        _connection.execute("PRAGMA journal_mode = WAL")
        # Оптимизировать производительность
        _connection.execute("PRAGMA synchronous = NORMAL")
        _connection.execute("PRAGMA cache_size = 10000")
    
    return _connection


def get_db():
    """Получить соединение к БД (с автоматической обработкой блокировок)"""
    return _get_connection()


@contextmanager
def get_db_context():
    """Context manager для безопасной работы с БД (если нужен контекст)"""
    conn = _get_connection()
    with _db_lock:
        try:
            yield conn
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                # Если БД заблокирована, попробовать еще раз
                conn.execute("BEGIN IMMEDIATE")
                conn.commit()
                yield conn
            else:
                raise


def execute_query(query, params=None):
    """Выполнить запрос с автоматическим управлением соединением"""
    with _db_lock:
        conn = get_db()
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        conn.commit()
        return cursor


def fetch_one(query, params=None):
    """Получить одну строку"""
    with _db_lock:
        conn = get_db()
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchone()


def fetch_all(query, params=None):
    """Получить все строки"""
    with _db_lock:
        conn = get_db()
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall()


def execute_transaction(operations):
    """
    Выполнить несколько операций в одной транзакции
    operations - список кортежей (query, params) или просто query
    """
    with _db_lock:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            for operation in operations:
                if isinstance(operation, tuple):
                    query, params = operation
                    cursor.execute(query, params)
                else:
                    cursor.execute(operation)
            cursor.execute("COMMIT")
            conn.commit()
            return True
        except Exception as e:
            cursor.execute("ROLLBACK")
            conn.commit()
            raise


def clear_user_all_data(user_id: int):
    """
    Полностью очистить все данные пользователя
    Используется при reset
    """
    operations = [
        ("DELETE FROM workouts WHERE user_id=?", (user_id,)),
        ("DELETE FROM weights WHERE user_id=?", (user_id,)),
        ("DELETE FROM user_items WHERE user_id=?", (user_id,)),
        ("DELETE FROM daily_tasks WHERE user_id=?", (user_id,)),
        ("DELETE FROM coin_rewards WHERE user_id=?", (user_id,)),
        ("DELETE FROM user_states WHERE user_id=?", (user_id,)),
        ("DELETE FROM users WHERE user_id=?", (user_id,)),
    ]
    
    try:
        execute_transaction(operations)
        # Дополнительно убедиться, что данные удалены
        with _db_lock:
            conn = get_db()
            conn.execute("VACUUM")  # Очистить файл БД
            conn.commit()
        return True
    except Exception as e:
        print(f"Error clearing user data: {e}")
        return False


def verify_user_exists(user_id: int) -> bool:
    """Проверить, существует ли пользователь в БД"""
    result = fetch_one("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    return result is not None


def get_user_data_safe(user_id: int):
    """
    Безопасно получить данные пользователя
    Проверяет существование перед возвратом
    """
    result = fetch_one(
        """
        SELECT height, gender, age, goal, current_weight,
               show_height, show_gender, show_age, show_weight, show_goal
        FROM users
        WHERE user_id=?
        """,
        (user_id,)
    )
    return result


def init_connection():
    """Инициализировать соединение при старте приложения"""
    conn = _get_connection()
    print(f"✅ Соединение с БД инициализировано: {DB_PATH}")
    print(f"   Journal mode: {fetch_one('PRAGMA journal_mode')[0]}")
    print(f"   Synchronous: {fetch_one('PRAGMA synchronous')[0]}")
    return conn

