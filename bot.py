import asyncio
import requests
from aiogram import F
import sqlite3
import re
import html
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import random
from aiogram import Bot, Dispatcher
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand
)
from aiogram.filters import Command
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("BOT_TOKEN")
API_NINJAS_KEY = os.getenv("API_NINJAS_KEY")

if not token:
    raise RuntimeError("BOT_TOKEN is not set. Add it to environment variables.")
if not API_NINJAS_KEY:
    raise RuntimeError("API_NINJAS_KEY is not set. Add it to environment variables.")

bot = Bot(token=token, timeout=30)
dp = Dispatcher()

calories_cache = {}

# ---------- UI ----------
def reminders_on_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=pick_lang(lang, "❌ Вимкнути", "❌ Disable"),
            callback_data="reminders_off"
        )
    ]])


def reminders_off_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=pick_lang(lang, "✅ Увімкнути", "✅ Enable"),
            callback_data="reminders_on"
        )
    ]])


def reset_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=pick_lang(lang, "✅ Так", "✅ Yes"), callback_data="reset_yes"),
        InlineKeyboardButton(text=pick_lang(lang, "❌ Ні", "❌ No"), callback_data="reset_no")
    ]])


def suggest_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=pick_lang(lang, "✅ Виконав", "✅ Done"), callback_data="suggest_done"),
        InlineKeyboardButton(text=pick_lang(lang, "🔁 Інша", "🔁 Another"), callback_data="suggest_retry")
    ]])


def challenge_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=pick_lang(lang, "✅ Зробив", "✅ Done"), callback_data="challenge_done"),
        InlineKeyboardButton(text=pick_lang(lang, "🔁 Інший челендж", "🔁 Another challenge"), callback_data="challenge_next")
    ]])


PROFILE_FIELDS = (
    ("height", "Зріст", "Height"),
    ("gender", "Стать", "Gender"),
    ("age", "Вік", "Age"),
    ("weight", "Вага", "Weight"),
    ("goal", "Мета", "Goal"),
)


def profile_visibility_keyboard(lang: str, visibility: dict) -> InlineKeyboardMarkup:
    rows = []
    for field, uk_label, en_label in PROFILE_FIELDS:
        enabled = bool(visibility.get(field, True))
        icon = "✅" if enabled else "🚫"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {pick_lang(lang, uk_label, en_label)}",
                callback_data=f"profile_toggle_{field}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


language_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="English", callback_data="set_lang_en"),
        InlineKeyboardButton(text="Українська", callback_data="set_lang_uk")
    ]
])

MOTIVATION_QUOTES = [
    "Маленькі кроки щодня = великі результати через місяць.",
    "Ти не завжди маєш бути мотивованим. Будь дисциплінованим.",
    "Кожне тренування - це інвестиція у майбутнього себе.",
    "Не зупиняйся, коли втомився. Зупиняйся, коли завершив.",
    "Прогрес важливіший за ідеальність."
]

HEALTH_TIPS = [
    "Після тренування випий склянку води протягом 15 хвилин.",
    "Роби 5 хвилин розминки перед будь-яким навантаженням.",
    "Сон 7-8 годин пришвидшує відновлення м'язів.",
    "Додай білок до кожного основного прийому їжі.",
    "Краще 20 хвилин руху щодня, ніж 2 години раз на тиждень."
]

FITNESS_CHALLENGES = [
    "30 присідань + 20 відтискувань + планка 40 сек",
    "Швидка прогулянка 25 хв + розтяжка 5 хв",
    "3 кола: 15 випадів, 20 скручувань, планка 30 сек",
    "Біг або швидкий крок 20 хв без зупинок",
    "100 стрибків на місці + 20 присідань + 20 випадів"
]


def pick_lang(lang: str, uk: str, en: str) -> str:
    return en if lang == "en" else uk


def style_block(title: str, body: str, icon: str = "✨") -> str:
    safe_title = html.escape(title)
    safe_body = html.escape(body.strip())
    return (
        f"{icon} <b>{safe_title}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{safe_body}"
    )


def build_start_text(lang: str) -> str:
    menu_body = pick_lang(
        lang,
        "/profile — профіль\n"
        "/edit_profile — змінити профіль\n"
        "/profile_visibility — що показувати в профілі\n"
        "/workout — записати тренування\n"
        "/today — сьогодні\n"
        "/stats — статистика\n"
        "/weight — вага\n"
        "/reset — видалити все\n"
        "/weight_stats — статистика ваги\n"
        "/suggest — запропонувати тренування\n"
        "/set_goal — встановити мету на тиждень\n"
        "/set_language — змінити мову\n"
        "/reminders — нагадування\n"
        "/goal — показати мету на тиждень\n"
        "/motivate — мотивація\n"
        "/tip — корисна порада\n"
        "/challenge — челендж дня",
        "/profile — profile\n"
        "/edit_profile — edit profile\n"
        "/profile_visibility — profile fields visibility\n"
        "/workout — log workout\n"
        "/today — today\n"
        "/stats — statistics\n"
        "/weight — weight\n"
        "/reset — delete all data\n"
        "/weight_stats — weight statistics\n"
        "/suggest — suggest workout\n"
        "/set_goal — set weekly goal\n"
        "/set_language — change language\n"
        "/reminders — reminders\n"
        "/goal — show weekly goal\n"
        "/motivate — motivation\n"
        "/tip — health tip\n"
        "/challenge — challenge of the day"
    )
    return style_block(
        "SportBot",
        menu_body,
        icon="🏁"
    )


def generate_workout(goal: str) -> str:
    if "наб" in goal:
        return (random.choice(
            ["💪 Тренування на набір маси:\n"
             "• Відтискування 4x15–20\n"
             "• Присідання 4x25\n"
             "• Випади 3x12\n"
             "• Планка 3x40 сек",
             "💪 Тренування на набір маси:\n"
             "• Відтискування вузькі 4x12\n"
             "• Присідання з паузою 4x20\n"
             "• Ягодичний міст 3x20\n"
             "• Планка 3x45 сек"])

        )
    elif "схуд" in goal or "дієт" in goal:
        return (random.choice([
            "🔥 Тренування на спалювання жиру:\n"
            "• Біг 20–30 хвилин\n"
            "• Бьорпі 3x12\n"
            "• Стрибки 3x40 сек\n"
            "• Планка 3x30 сек",
            "🔥 Тренування на спалювання жиру:\n"
            "• Jumping Jack 4x40 сек\n"
            "• Альпініст 3x30 сек\n"
            "• Присідання 3x25\n"
            "• Планка 3x35 сек"])
        )
    else:
        return (random.choice([
            "🏋️ Універсальне тренування:\n"
            "• Відтискування 3x15\n"
            "• Присідання 3x20\n"
            "• Планка 3x30 сек",
            "🏋️ Універсальне тренування:\n"
            "• Відтискування 3x12\n"
            "• Випади 3x12\n"
            "• Велосипед 3x30 сек\n"
            "• Планка 3x40 сек"])
        )





async def check_missed_days():
    db = get_db()
    cur = db.cursor()

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Вибираємо користувачів з включеними нагадуваннями, які мають тренування за останні 7 днів
    cur.execute("""
                SELECT DISTINCT u.user_id
                FROM users u
                WHERE u.reminders_enabled = 1
                  AND u.user_id IN (
                    SELECT DISTINCT user_id FROM workouts 
                    WHERE date >= ?
                  )
                """, ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),))

    users = [row[0] for row in cur.fetchall()]

    for uid in users:
        # Використовуємо окремий курсор для уникнення конфліктів
        check_cur = db.cursor()
        check_cur.execute("SELECT 1 FROM workouts WHERE user_id=? AND date=?", (uid, yesterday))
        if not check_cur.fetchone():
            lang = get_user_language(uid)
            messages = get_missed_day_messages(lang)
            await bot.send_message(uid, random.choice(messages))
        check_cur.close()

    db.close()
    print("✅Перевірка пропущених днів виконана.")


def get_missed_day_messages(lang: str):
    return [
        pick_lang(
            lang,
            "💪 Вчора пропустив тренування?\nСьогодні новий день! 🔥 /suggest",
            "💪 Missed a workout yesterday?\nToday is a new day! 🔥 /suggest"
        ),
        pick_lang(
            lang,
            "😴 Відпочив вчора? Повертайся до строю! /today",
            "😴 Rested yesterday? Back to action! /today"
        ),
        pick_lang(
            lang,
            "⚡ Швидкий тест: /suggest → ✅ Виконав!",
            "⚡ Quick test: /suggest → ✅ Done!"
        )
    ]


# ---------- DB ----------
def get_db():
    return sqlite3.connect("sportbot.db")


def init_db():
    db = get_db()
    cur = db.cursor()

    # Создаем users БЕЗ reminders_enabled сначала
    cur.execute("""
                CREATE TABLE IF NOT EXISTS users
                (
                    user_id
                    INTEGER
                    PRIMARY
                    KEY,
                    height
                    INTEGER,
                    gender
                    TEXT,
                    age
                    INTEGER,
                    goal
                    TEXT,
                    weekly_goal
                    INTEGER,
                    current_weight
                    REAL
                    DEFAULT
                    0
                )
                """)

    # ПРОВЕРЯЕМ и добавляем колонку ТОЛЬКО если её нет
    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]

    if 'reminders_enabled' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN reminders_enabled INTEGER DEFAULT 1")
    if 'language' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'uk'")
    if 'age' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN age INTEGER")
    for column_name in (
        'show_height',
        'show_gender',
        'show_age',
        'show_weight',
        'show_goal'
    ):
        if column_name not in columns:
            cur.execute(f"ALTER TABLE users ADD COLUMN {column_name} INTEGER DEFAULT 1")

    cur.execute("""
                CREATE TABLE IF NOT EXISTS weights
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    user_id
                    INTEGER,
                    weight
                    REAL,
                    date
                    TEXT
                )
                """)

    cur.execute("""
                CREATE TABLE IF NOT EXISTS workouts
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    user_id
                    INTEGER,
                    text
                    TEXT,
                    date
                    TEXT,
                    is_challenge
                    INTEGER
                    DEFAULT
                    0
                )
                """)

    # Add is_challenge column if it doesn't exist
    cur.execute("PRAGMA table_info(workouts)")
    columns = [row[1] for row in cur.fetchall()]
    if 'is_challenge' not in columns:
        cur.execute("ALTER TABLE workouts ADD COLUMN is_challenge INTEGER DEFAULT 0")

    cur.execute("""
                CREATE TABLE IF NOT EXISTS user_states
                (
                    user_id
                    INTEGER
                    PRIMARY
                    KEY,
                    state
                    TEXT
                )
                """)

    db.commit()
    db.close()


# ---------- UTILS ----------
def set_user_state(user_id: int, state: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO user_states (user_id, state)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET state=excluded.state
        """,
        (user_id, state)
    )
    db.commit()
    db.close()


def get_user_state(user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT state FROM user_states WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    db.close()
    return row[0] if row else None


def clear_user_state(user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM user_states WHERE user_id=?", (user_id,))
    db.commit()
    db.close()


def get_user_language(user_id: int) -> str:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    db.close()
    if row and row[0] in ("uk", "en"):
        return row[0]
    return "uk"


def set_user_language(user_id: int, lang: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO users (user_id, language)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET language=excluded.language
        """,
        (user_id, lang)
    )
    db.commit()
    db.close()


def get_profile_visibility(user_id: int) -> dict:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT show_height, show_gender, show_age, show_weight, show_goal
        FROM users
        WHERE user_id=?
        """,
        (user_id,)
    )
    row = cur.fetchone()
    db.close()

    if not row:
        return {field: True for field, _, _ in PROFILE_FIELDS}

    return {
        "height": row[0] != 0,
        "gender": row[1] != 0,
        "age": row[2] != 0,
        "weight": row[3] != 0,
        "goal": row[4] != 0,
    }


def ensure_user(user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO users (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
        (user_id,)
    )
    db.commit()
    db.close()


def parse_activity_and_duration(text: str):
    raw = text.lower()
    m = re.search(r'(\d+)\s*(хв|хвилин|мин|min)', raw)
    duration = int(m.group(1)) if m else 30

    activity_map = {
        "біг": "running",
        "run": "running",
        "ходьб": "walking",
        "прогулянк": "walking",
        "вело": "bicycling",
        "велосипед": "bicycling",
        "плав": "swimming",
        "відтиск": "push ups",
        "push": "push ups",
        "присідан": "squats",
        "squat": "squats",
        "планк": "plank",
        "випад": "lunges",
        "lunge": "lunges",
        "бурпі": "burpees",
        "бьорпі": "burpees",
        "burpee": "burpees",
        "jumping jack": "jumping jacks",
        "стрибк": "jumping jacks",
        "альпініст": "mountain climbers",
        "mountain": "mountain climbers",
        "скручуван": "sit ups",
        "прес": "sit ups"
    }

    for key, api_activity in activity_map.items():
        if key in raw:
            return api_activity, duration

    return "workout", duration


def calc_calories(text: str) -> int:
    cache_key = text.strip().lower()
    if cache_key in calories_cache:
        return calories_cache[cache_key]

    activity, duration = parse_activity_and_duration(text)

    try:
        response = requests.get(
            "https://api.api-ninjas.com/v1/caloriesburned",
            params={"activity": activity, "duration": duration},
            headers={"X-Api-Key": API_NINJAS_KEY},
            timeout=8
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and data:
                total = data[0].get("total_calories")
                if total is not None:
                    value = int(round(float(total)))
                    calories_cache[cache_key] = value
                    return value
    except Exception:
        pass

    # Fallback estimate when API is unavailable or activity wasn't matched
    text = cache_key
    m = re.search(r'(\d+)\s*(хв|хвилин|мин|min)', text)
    if m:
        value = int(m.group(1)) * 8  # rough estimate
        calories_cache[cache_key] = value
        return value

    if 'x' in text or 'х' in text:
        calories_cache[cache_key] = 30
        return 30

    calories_cache[cache_key] = 0
    return 0


def calculate_streak(dates):
    used = set(dates)
    streak = 0
    today = datetime.now().date()

    while True:
        day = today - timedelta(days=streak)
        if day.strftime("%Y-%m-%d") in used:
            streak += 1
        else:
            break
    return streak


# ---------- RESET ----------
@dp.message(Command("reset"))
async def reset_profile(message: Message):
    lang = get_user_language(message.from_user.id)
    await message.answer(
        pick_lang(lang, "Видалити профіль і всі дані?", "Delete profile and all data?"),
        reply_markup=reset_keyboard(lang)
    )


@dp.callback_query(lambda c: c.data == "reset_yes")
async def reset_yes(callback: CallbackQuery):
    uid = callback.from_user.id
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM workouts WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM weights WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM users WHERE user_id=?", (uid,))

    db.commit()
    db.close()

    lang = get_user_language(uid)
    await callback.message.edit_text(pick_lang(lang, "Профіль повністю видалено.", "Profile and all data were deleted."))


@dp.callback_query(lambda c: c.data == "reset_no")
async def reset_no(callback: CallbackQuery):
    lang = get_user_language(callback.from_user.id)
    await callback.message.edit_text(pick_lang(lang, "Скасування.", "Canceled."))


# ---------- COMMANDS ----------
@dp.message(Command("start"))
async def start(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT language FROM users WHERE user_id=?", (uid,))
    has_lang = cur.fetchone()
    db.close()

    if not has_lang or not has_lang[0]:
        await message.answer("Оберіть мову", reply_markup=language_kb)
        return

    await message.answer(build_start_text(lang), parse_mode="HTML")


@dp.message(Command("set_language"))
async def set_language_command(message: Message):
    await message.answer("Choose language / Оберіть мову", reply_markup=language_kb)


@dp.callback_query(lambda c: c.data in ("set_lang_en", "set_lang_uk"))
async def set_language(callback: CallbackQuery):
    lang = "en" if callback.data == "set_lang_en" else "uk"
    set_user_language(callback.from_user.id, lang)
    await callback.answer("Saved" if lang == "en" else "Збережено")
    await callback.message.edit_text(build_start_text(lang), parse_mode="HTML")


@dp.message(Command("profile"))
async def profile(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)
    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        SELECT height, gender, age, goal, current_weight,
               show_height, show_gender, show_age, show_weight, show_goal
        FROM users
        WHERE user_id=?
        """,
        (uid,)
    )
    profile_row = cur.fetchone()
    db.close()

    if not profile_row or not profile_row[0]:
        set_user_state(uid, "profile")
        await message.answer(
            pick_lang(
                lang,
                "Введи профіль:\nЗріст, стать, вік, мета\nПриклад: 165, ч, 25, набрати масу",
                "Enter your profile:\nHeight, gender, age, goal\nExample: 165, m, 25, gain muscle"
            )
        )
        return

    h, g, age, goal, current_weight, show_height, show_gender, show_age, show_weight, show_goal = profile_row
    weight_text = f"{current_weight:.1f} кг" if current_weight and current_weight > 0 else pick_lang(lang, "не вказана", "not set")
    age_text = str(age) if age else pick_lang(lang, "не вказаний", "not set")

    profile_lines = []
    if show_height:
        profile_lines.append(pick_lang(lang, f"📏 Зріст: {h} см", f"📏 Height: {h} cm"))
    if show_gender:
        profile_lines.append(pick_lang(lang, f"🧍 Стать: {g}", f"🧍 Gender: {g}"))
    if show_age:
        profile_lines.append(pick_lang(lang, f"🎂 Вік: {age_text}", f"🎂 Age: {age_text}"))
    if show_weight:
        profile_lines.append(pick_lang(lang, f"⚖️ Вага: {weight_text}", f"⚖️ Weight: {weight_text}"))
    if show_goal:
        profile_lines.append(pick_lang(lang, f"🎯 Мета: {goal}", f"🎯 Goal: {goal}"))

    if not profile_lines:
        profile_lines.append(
            pick_lang(
                lang,
                "Усі поля приховані. Налаштувати: /profile_visibility",
                "All fields are hidden. Configure: /profile_visibility"
            )
        )

    await message.answer(
        style_block(
            pick_lang(lang, "Профіль", "Profile"),
            "\n".join(profile_lines),
            icon="👤"
        ),
        parse_mode="HTML"
    )


@dp.message(Command("edit_profile"))
async def edit_profile(message: Message):
    lang = get_user_language(message.from_user.id)
    set_user_state(message.from_user.id, "profile")
    await message.answer(
        pick_lang(
            lang,
            "Зріст, стать, вік, мета\nПриклад: 170, ж, 25, схуднути\n\nСтарий формат теж працює: 170, ж, схуднути",
            "Height, gender, age, goal\nExample: 170, f, 25, lose weight\n\nOld format also works: 170, f, lose weight"
        )
    )


@dp.message(Command("profile_visibility"))
async def profile_visibility(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)
    ensure_user(uid)
    visibility = get_profile_visibility(uid)
    await message.answer(
        pick_lang(
            lang,
            "Обери, які поля показувати в /profile:",
            "Choose which fields to show in /profile:"
        ),
        reply_markup=profile_visibility_keyboard(lang, visibility)
    )


@dp.callback_query(F.data.startswith("profile_toggle_"))
async def profile_toggle(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid)
    field = callback.data.replace("profile_toggle_", "", 1)

    if field not in {name for name, _, _ in PROFILE_FIELDS}:
        await callback.answer()
        return

    column = f"show_{field}"
    ensure_user(uid)

    db = get_db()
    cur = db.cursor()
    cur.execute(f"SELECT {column} FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    new_value = 0 if row and row[0] else 1
    cur.execute(f"UPDATE users SET {column}=? WHERE user_id=?", (new_value, uid))
    db.commit()
    db.close()

    visibility = get_profile_visibility(uid)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=profile_visibility_keyboard(lang, visibility)
        )
    except Exception:
        pass
    await callback.answer(pick_lang(lang, "Оновлено", "Updated"))


@dp.message(Command("set_goal"))
async def set_goal(message: Message):
    lang = get_user_language(message.from_user.id)
    set_user_state(message.from_user.id, "weekly_goal")
    await message.answer(
        pick_lang(lang, "Введи мету на тиждень (кількість днів тренувань)\nПриклад: 4", "Enter weekly goal (number of workout days)\nExample: 4")
    )


@dp.message(Command("goal"))
async def goal(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)
    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT weekly_goal FROM users WHERE user_id=?",
        (uid,)
    )
    row = cur.fetchone()

    if not row or not row[0] or row[0] < 1:
        db.close()
        await message.answer(pick_lang(lang, "Мета не задана. Використовуй /set_goal", "Goal is not set. Use /set_goal"))
        return

    weekly_goal = int(row[0])

    week_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    cur.execute(
        "SELECT COUNT(DISTINCT date) FROM workouts WHERE user_id=? AND date>=?",
        (uid, week_ago)
    )
    done = cur.fetchone()[0] or 0
    db.close()

    progress = min(int(done / weekly_goal * 100), 100)

    blocks_total = 10
    blocks_done = int(progress / 10)
    bar = "█" * blocks_done + "░" * (blocks_total - blocks_done)

    status = pick_lang(lang, "🔥 Чудово", "🔥 Great") if done >= weekly_goal else pick_lang(lang, "⏳ Продовжуй", "⏳ Keep going")

    await message.answer(
        style_block(
            pick_lang(lang, "Мета на тиждень", "Weekly goal"),
            pick_lang(
                lang,
                f"🎯 Ціль: {weekly_goal}\n✅ Виконано: {done}\n📈 Прогрес: {progress}% {bar}\n{status}",
                f"🎯 Goal: {weekly_goal}\n✅ Done: {done}\n📈 Progress: {progress}% {bar}\n{status}"
            ),
            icon="🗓️"
        ),
        parse_mode="HTML"
    )


@dp.message(Command("reminders"))
async def reminders(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)
    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT reminders_enabled FROM users WHERE user_id=?",
        (uid,)
    )
    row = cur.fetchone()
    
    if not row:
        # Новый пользователь - создаём запись с включенными напоминаниями
        cur.execute(
            "INSERT INTO users (user_id, reminders_enabled) VALUES (?, 1)",
            (uid,)
        )
        db.commit()
        status = True
    else:
        status = bool(row[0])
    
    db.close()

    if status:
        await message.answer(
            pick_lang(lang, "🔔 Нагадування вже увімкнені.\n\nХочеш вимкнути?", "🔔 Reminders are already enabled.\n\nDo you want to disable them?"),
            reply_markup=reminders_on_keyboard(lang)
        )
    else:
        await message.answer(
            pick_lang(lang, "🔕 Нагадування вже вимкнені.\n\nХочеш увімкнути?", "🔕 Reminders are already disabled.\n\nDo you want to enable them?"),
            reply_markup=reminders_off_keyboard(lang)
        )


@dp.callback_query(lambda c: c.data == "reminders_on")
async def reminders_on(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid)
    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        INSERT INTO users (user_id, reminders_enabled)
        VALUES (?, 1)
        ON CONFLICT(user_id) DO NOTHING
        """,
        (uid,)
    )
    cur.execute(
        "UPDATE users SET reminders_enabled=1 WHERE user_id=?",
        (uid,)
    )
    db.commit()
    db.close()

    try:
        await callback.message.edit_text(
            pick_lang(
                lang,
                "🔔 Нагадування УВІМКНЕНІ!\n\nОтримувати мотивацію щодня при пропуску тренування? 💪",
                "🔔 Reminders are ENABLED!\n\nGet daily motivation if you skip a workout? 💪"
            ),
            reply_markup=None
        )
    except:
        pass
    await callback.answer(pick_lang(lang, "Увімкнено!", "Enabled!"))


@dp.callback_query(lambda c: c.data == "reminders_off")
async def reminders_off(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid)
    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        INSERT INTO users (user_id, reminders_enabled)
        VALUES (?, 1)
        ON CONFLICT(user_id) DO NOTHING
        """,
        (uid,)
    )
    cur.execute(
        "UPDATE users SET reminders_enabled=0 WHERE user_id=?",
        (uid,)
    )
    db.commit()
    db.close()

    try:
        await callback.message.edit_text(
            pick_lang(
                lang,
                "🔕 Нагадування ВИМКНЕНІ\n\nТи босс, тренуйся за настроєм! 😎",
                "🔕 Reminders are DISABLED\n\nYou're the boss, train by your mood! 😎"
            ),
            reply_markup=None
        )
    except:
        pass
    await callback.answer(pick_lang(lang, "Вимкнено!", "Disabled!"))


@dp.message(Command("suggest"))
async def suggest(message: Message):
    lang = get_user_language(message.from_user.id)
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT goal FROM users WHERE user_id=?", (message.from_user.id,))
    row = cur.fetchone()
    db.close()

    if not row or not row[0]:
        await message.answer(pick_lang(lang, "Спочатку задай мету в профілі (/profile).", "Set a goal in your profile first (/profile)."))
        return

    text = generate_workout(row[0])
    await message.answer(text, reply_markup=suggest_keyboard(lang))


@dp.message(Command("motivate"))
async def motivate(message: Message):
    lang = get_user_language(message.from_user.id)
    quote = random.choice(MOTIVATION_QUOTES)
    title = pick_lang(lang, "Мотивація", "Motivation")
    await message.answer(
        style_block(title, f"💬 {quote}", icon="🚀"),
        parse_mode="HTML"
    )


@dp.message(Command("tip"))
async def tip(message: Message):
    lang = get_user_language(message.from_user.id)
    tip_text = random.choice(HEALTH_TIPS)
    title = pick_lang(lang, "Порада дня", "Tip of the day")
    await message.answer(
        style_block(title, f"💡 {tip_text}", icon="🧠"),
        parse_mode="HTML"
    )


@dp.message(Command("challenge"))
async def challenge(message: Message):
    lang = get_user_language(message.from_user.id)
    challenge_text = random.choice(FITNESS_CHALLENGES)
    title = pick_lang(lang, "Челендж дня", "Challenge of the day")
    await message.answer(
        style_block(title, f"🔥 {challenge_text}", icon="🏆"),
        parse_mode="HTML",
        reply_markup=challenge_keyboard(lang)
    )


@dp.callback_query(F.data == "suggest_retry")
async def suggest_retry(callback: CallbackQuery):
    lang = get_user_language(callback.from_user.id)
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT goal FROM users WHERE user_id=?", (callback.from_user.id,))
    row = cur.fetchone()
    db.close()

    if not row or not row[0]:
        await callback.answer(pick_lang(lang, "Немає мети", "No goal set"), show_alert=True)
        return

    text = generate_workout(row[0])
    await callback.message.answer(text, reply_markup=suggest_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "suggest_done")
async def suggest_done(callback: CallbackQuery):
    lang = get_user_language(callback.from_user.id)
    await callback.answer("OK")
    uid = callback.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    workout_text = callback.message.text.split("\n", 1)[1]

    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT 1 FROM workouts WHERE user_id=? AND date=?",
        (uid, today)
    )
    if cur.fetchone():
        db.close()
        await callback.answer(pick_lang(lang, "Сьогодні вже зараховано", "Already counted today"))
        return

    for line in workout_text.split("\n"):
        if line.startswith("•"):
            cur.execute(
                "INSERT INTO workouts (user_id, text, date) VALUES (?, ?, ?)",
                (uid, line[2:], today)
            )

    db.commit()
    db.close()

    await callback.message.edit_text(
        callback.message.text + pick_lang(lang, "\n\n✅ Тренування збережено", "\n\n✅ Workout saved")
    )


@dp.callback_query(F.data == "challenge_next")
async def challenge_next(callback: CallbackQuery):
    lang = get_user_language(callback.from_user.id)
    challenge_text = random.choice(FITNESS_CHALLENGES)
    await callback.message.edit_text(
        style_block(pick_lang(lang, "Челендж дня", "Challenge of the day"), f"🔥 {challenge_text}", icon="🏆"),
        parse_mode="HTML",
        reply_markup=challenge_keyboard(lang)
    )
    await callback.answer(pick_lang(lang, "Новий челендж 💪", "New challenge 💪"))


@dp.callback_query(F.data == "challenge_done")
async def challenge_done(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Extract challenge text from the message (it's between 🔥 markers)
    message_text = callback.message.text
    # Find the challenge text that starts with 🔥
    lines = message_text.split("\n")
    challenge_text = None
    for line in lines:
        if line.startswith("🔥"):
            challenge_text = line[1:].strip()  # Remove 🔥 emoji
            break
    
    if not challenge_text:
        challenge_text = message_text

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM workouts WHERE user_id=? AND date=? AND is_challenge=1",
        (uid, today)
    )
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO workouts (user_id, text, date, is_challenge) VALUES (?, ?, ?, 1)",
            (uid, challenge_text, today)
        )
        db.commit()
    db.close()

    await callback.message.edit_text(
        callback.message.text + pick_lang(lang, "\n\n✅ Челендж зараховано!", "\n\n✅ Challenge counted!"),
        parse_mode="HTML"
    )
    await callback.answer(pick_lang(lang, "Круто! Так тримати 🔥", "Great! Keep it up 🔥"))


@dp.message(Command("workout"))
async def workout(message: Message):
    lang = get_user_language(message.from_user.id)
    set_user_state(message.from_user.id, "workout")
    await message.answer(
        pick_lang(
            lang,
            "Введи тренування.\nМожна через кому:\nБіг 30 хвилин, Відтискування 4x20",
            "Enter workout.\nYou can separate by commas:\nRunning 30 min, Push ups 4x20"
        )
    )


@dp.message(Command("weight"))
async def weight(message: Message):
    lang = get_user_language(message.from_user.id)
    set_user_state(message.from_user.id, "weight")
    await message.answer(pick_lang(lang, "Введи вагу (кг)", "Enter weight (kg)"))


@dp.message(Command("weight_stats"))
async def weight_stats(message: Message):
    lang = get_user_language(message.from_user.id)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT weight, date FROM weights WHERE user_id=? ORDER BY date DESC LIMIT 7",
        (message.from_user.id,)
    )
    rows = cur.fetchall()
    db.close()

    if not rows:
        await message.answer(pick_lang(lang, "Вага ще не записувалася.", "No weight entries yet."))
        return

    text = pick_lang(lang, "⚖️ Вага (останні записи):\n", "⚖️ Weight (latest entries):\n")
    for w, d in rows:
        text += f"{d}: {w} кг\n"

    await message.answer(text)


# ---------- TODAY ----------
@dp.message(Command("today"))
async def today(message: Message):
    lang = get_user_language(message.from_user.id)
    db = get_db()
    cur = db.cursor()

    today_date = datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        "SELECT text, is_challenge FROM workouts WHERE user_id=? AND date=? ORDER BY id",
        (message.from_user.id, today_date)
    )
    rows = cur.fetchall()
    db.close()

    if not rows:
        await message.answer(pick_lang(lang, "Сьогодні тренувань немає.", "No workouts today."))
        return

    # Separate challenges and regular workouts
    workouts_text_list = []
    total_cal = 0
    
    for text, is_challenge in rows:
        cal = calc_calories(text)
        total_cal += cal
        
        if is_challenge:
            # Display challenge with trophy icon
            workouts_text_list.append(f"🏆 {text}")
        else:
            # Display regular workout
            workouts_text_list.append(f"• {text}")
    
    text = "\n".join(workouts_text_list)

    await message.answer(
        style_block(
            pick_lang(lang, "Сьогоднішні тренування", "Today's workouts"),
            pick_lang(lang, f"{text}\n\n🔥 Витрачено: ~{total_cal} ккал", f"{text}\n\n🔥 Burned: ~{total_cal} kcal"),
            icon="🏋️"
        ),
        parse_mode="HTML"
    )


# ---------- STATS ----------
@dp.message(Command("stats"))
async def stats(message: Message):
    db = get_db()
    cur = db.cursor()
    uid = message.from_user.id
    lang = get_user_language(uid)

    cur.execute(
        "SELECT date, text FROM workouts WHERE user_id=? ORDER BY date DESC",
        (uid,)
    )
    rows = cur.fetchall()
    db.close()

    if not rows:
        await message.answer(pick_lang(lang, "Тренувань немає.", "No workouts yet."))
        return

    dates = [d for d, _ in rows]
    streak = calculate_streak(dates)

    week_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")

    total_cal = sum(calc_calories(t) for _, t in rows)
    week_cal = sum(calc_calories(t) for d, t in rows if d >= week_ago)

    text = (
        pick_lang(
            lang,
            f"📊 Статистика\nДнів тренування: {len(set(dates))}\nСерія: {streak}\n🔥 Калорій всього: ~{total_cal}\n🔥 За 7 днів: ~{week_cal}\n\nОстанні:\n",
            f"📊 Statistics\nWorkout days: {len(set(dates))}\nStreak: {streak}\n🔥 Calories total: ~{total_cal}\n🔥 Last 7 days: ~{week_cal}\n\nRecent:\n"
        )
    )

    for d, t in rows[:5]:
        text += f"{d}: {t}\n"

    await message.answer(
        style_block(
            pick_lang(lang, "Статистика", "Statistics"),
            text.replace(pick_lang(lang, "📊 Статистика\n", "📊 Statistics\n"), "").strip(),
            icon="📊"
        ),
        parse_mode="HTML"
    )


# ---------- INPUT ----------
@dp.message()
async def handle_input(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)

    if not message.text:
        await message.answer(pick_lang(lang, "Поки що працюю лише з текстом. Спробуй команду /start", "I currently work with text only. Try /start"))
        return

    if message.text.startswith("/"):
        return

    state = get_user_state(uid)

    if not state:
        await message.answer(pick_lang(lang, "Я на зв'язку 👋 Використай /start, щоб побачити команди.", "I'm here 👋 Use /start to see commands."))
        return

    if state == "weekly_goal":
        try:
            goal = int(message.text)

            db = get_db()
            cur = db.cursor()

            cur.execute(
                """
                INSERT INTO users (user_id, weekly_goal)
                VALUES (?, ?) ON CONFLICT(user_id)
                DO
                UPDATE SET weekly_goal=excluded.weekly_goal
                """,
                (uid, goal)
            )

            db.commit()
            db.close()

            await message.answer(pick_lang(lang, "Мета тижня збережена.", "Weekly goal saved."))
            clear_user_state(uid)
        except:
            await message.answer(pick_lang(lang, "Введи число.", "Enter a number."))
        return

    # WEIGHT
    if state == "weight":
        try:
            w = float(message.text)
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "INSERT INTO users (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
                (uid,)
            )
            cur.execute(
                "INSERT INTO weights (user_id, weight, date) VALUES (?, ?, ?)",
                (uid, w, datetime.now().strftime("%Y-%m-%d"))
            )

            cur.execute(
                "UPDATE users SET current_weight = ? WHERE user_id = ?",
                (w, uid)
            )
            db.commit()
            db.close()

            await message.answer(pick_lang(lang, "Вагу збережено.", "Weight saved."))
            clear_user_state(uid)
        except:
            await message.answer(pick_lang(lang, "Введи число.", "Enter a number."))
        return

    # PROFILE
    if state == "profile":
        try:
            parts = [part.strip() for part in message.text.split(",")]
            if len(parts) < 3:
                raise ValueError("not enough profile parts")

            h = int(parts[0])
            g = parts[1].lower()
            age = None

            if len(parts) >= 4:
                age = int(parts[2])
                goal = ",".join(parts[3:]).strip()
            else:
                goal = parts[2]

            if age is not None and not 1 <= age <= 120:
                raise ValueError("invalid age")
            if not goal:
                raise ValueError("empty goal")

            if g in ("ч", "m", "male"):
                g = "чоловік👨"
            elif g in ("ж", "f", "female"):
                g = "жінка👩"
            db = get_db()
            cur = db.cursor()
            cur.execute(
                """
                INSERT INTO users (user_id, height, gender, age, goal)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id) DO
                UPDATE SET
                    height=excluded.height,
                    gender=excluded.gender,
                    age=COALESCE(excluded.age, users.age),
                    goal=excluded.goal
                """,
                (uid, h, g, age, goal)
            )
            db.commit()
            db.close()

            await message.answer(pick_lang(lang, "Профіль збережено.", "Profile saved."))
            clear_user_state(uid)
        except:
            await message.answer(pick_lang(lang, "Формат: 165, ч, 25, мета", "Format: 165, m, 25, goal"))

    # WORKOUT
    if state == "workout":
        exercises = [x.strip() for x in message.text.split(",") if x.strip()]
        db = get_db()
        cur = db.cursor()

        for ex in exercises:
            cur.execute(
                "INSERT INTO workouts (user_id, text, date) VALUES (?, ?, ?)",
                (uid, ex, datetime.now().strftime("%Y-%m-%d"))
            )

        db.commit()
        db.close()

        await message.answer(pick_lang(lang, f"Збережено: {len(exercises)}", f"Saved: {len(exercises)}"))
        clear_user_state(uid)


# ---------- RUN ----------
async def main():
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_missed_days, 'cron', hour=9, minute=0)  # 9:00 кожноденно
    scheduler.start()
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="set_language", description="Змінити мову"),
        BotCommand(command="profile", description="Профіль"),
        BotCommand(command="edit_profile", description="Змінити профіль"),
        BotCommand(command="profile_visibility", description="Поля профілю"),
        BotCommand(command="workout", description="Тренування"),
        BotCommand(command="today", description="Сьогодні"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="weight", description="Вага"),
        BotCommand(command="reset", description="Видалити все"),
        BotCommand(command="weight_stats", description="Статистика ваги"),
        BotCommand(command="suggest", description="Запропонувати тренування"),
        BotCommand(command="set_goal", description="Встановити мету на тиждень"),
        BotCommand(command="goal", description="Показати мету на тиждень"),
        BotCommand(command="reminders", description="Нагадування"),
        BotCommand(command="motivate", description="Мотивація"),
        BotCommand(command="tip", description="Корисна порада"),
        BotCommand(command="challenge", description="Челендж дня")
    ])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
