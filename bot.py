import sqlite3


def add_column_if_missing(cursor, table_name, column_name, definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


conn = sqlite3.connect("sportbot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    height INTEGER,
    gender TEXT,
    age INTEGER,
    goal TEXT,
    weekly_goal INTEGER,
    current_weight REAL DEFAULT 0,
    reminders_enabled INTEGER DEFAULT 1,
    language TEXT DEFAULT 'uk',
    coin_balance INTEGER DEFAULT 0,
    show_height INTEGER DEFAULT 1,
    show_gender INTEGER DEFAULT 1,
    show_age INTEGER DEFAULT 1,
    show_weight INTEGER DEFAULT 1,
    show_goal INTEGER DEFAULT 1
)
""")

for name, definition in (
    ("height", "INTEGER"),
    ("gender", "TEXT"),
    ("age", "INTEGER"),
    ("goal", "TEXT"),
    ("weekly_goal", "INTEGER"),
    ("current_weight", "REAL DEFAULT 0"),
    ("reminders_enabled", "INTEGER DEFAULT 1"),
    ("language", "TEXT DEFAULT 'uk'"),
    ("coin_balance", "INTEGER DEFAULT 0"),
    ("show_height", "INTEGER DEFAULT 1"),
    ("show_gender", "INTEGER DEFAULT 1"),
    ("show_age", "INTEGER DEFAULT 1"),
    ("show_weight", "INTEGER DEFAULT 1"),
    ("show_goal", "INTEGER DEFAULT 1"),
):
    add_column_if_missing(cursor, "users", name, definition)

cursor.execute("""
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    date TEXT,
    is_challenge INTEGER DEFAULT 0
)
""")
add_column_if_missing(cursor, "workouts", "is_challenge", "INTEGER DEFAULT 0")

cursor.execute("""
CREATE TABLE IF NOT EXISTS weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    weight REAL,
    date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_states (
    user_id INTEGER PRIMARY KEY,
    state TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    item_id TEXT,
    purchased_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_tasks (
    user_id INTEGER,
    date TEXT,
    task_id TEXT,
    progress INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, date)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS coin_rewards (
    user_id INTEGER,
    date TEXT,
    source TEXT,
    amount INTEGER,
    created_at TEXT,
    PRIMARY KEY (user_id, date, source)
)
""")

conn.commit()
conn.close()
