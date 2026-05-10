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
from db_improved import (
    get_db, execute_query, fetch_one, fetch_all, execute_transaction,
    clear_user_all_data, verify_user_exists, get_user_data_safe, init_connection, get_db_context
)

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


def daily_task_keyboard(lang: str, task: dict, completed: bool, date_text: str = None) -> InlineKeyboardMarkup:
    date_text = date_text or datetime.now().strftime("%Y-%m-%d")
    if completed:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=pick_lang(lang, "✅ Виконано", "✅ Completed"),
                callback_data=f"daily_done_{date_text}"
            )
        ]])

    unit = pick_lang(lang, task["uk_unit"], task["en_unit"])
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"+{task['step']} {unit}",
            callback_data=f"daily_add_{date_text}"
        )
    ]])


def shop_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Показує тільки категорії (шаг 1 після /shop)."""
    categories = sorted(
        {item.get("category", "Інше") for item in SHOP_ITEMS.values()}
    )

    rows: list[list[InlineKeyboardButton]] = []
    for category in categories:
        rows.append([
            InlineKeyboardButton(
                text=f"━━ {category} ━━",
                callback_data=f"shop_cat_{category}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_category_keyboard(lang: str, category: str) -> InlineKeyboardMarkup:
    """Показує товари в конкретній категорії (шаг 2)."""
    rows: list[list[InlineKeyboardButton]] = []

    category_items = [
        (item_id, item)
        for item_id, item in SHOP_ITEMS.items()
        if item.get("category", "Інше") == category
    ]
    category_items.sort(key=lambda x: x[1].get("cost", 0))

    for item_id, item in category_items:
        icon = item.get("icon", "🛍️")
        item_name = pick_lang(lang, item["uk_name"], item["en_name"])
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {item['cost']}🪙 · {item_name}",
                callback_data=f"shop_buy_{item_id}"
            )
        ])

    # Кнопка назад в список категорий
    rows.append([
        InlineKeyboardButton(
            text=pick_lang(lang, "⬅️ Назад", "⬅️ Back"),
            callback_data="shop_back_to_categories"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


PROFILE_FIELDS = (
    ("height", "Зріст", "Height"),
    ("gender", "Стать", "Gender"),
    ("age", "Вік", "Age"),
    ("weight", "Вага", "Weight"),
    ("goal", "Мета", "Goal"),
)

# Константи для обмежень
MAX_POWER_PLANS = 3  # Макс преміум тренувань
MAX_MOTIVATION_PACKS = 2
MAX_COIN_BOOSTERS = 1
MAX_RESTORE_TOKENS = 2

SHOP_ITEMS = {
    # === ТРЕНУВАЛЬНІ ПРОГРАМИ ===
    "power_plan": {
        "cost": 60,
        "category": "Тренування",
        "type": "functional",
        "uk_name": "Преміум тренування",
        "en_name": "Premium workout",
        "uk_desc": "Посилене тренування з вулу.",
        "en_desc": "Get a random stronger workout.",
        "icon": "⚡",
    },
    "monthly_program": {
        "cost": 150,
        "category": "Тренування",
        "type": "functional",
        "uk_name": "Програма на місяць",
        "en_name": "Monthly program",
        "uk_desc": "30 днів прогресивного навчання. Доступний навіки.",
        "en_desc": "30 days of progressive training. Lifetime access.",
        "icon": "📅",
    },
    "home_gym": {
        "cost": 120,
        "category": "Тренування",
        "type": "functional",
        "uk_name": "Домашний спортзал",
        "en_name": "Home gym guide",
        "uk_desc": "Тренування без обладнання. 40+ вправ.",
        "en_desc": "Bodyweight exercises guide. 40+ exercises.",
        "icon": "🏠",
    },
    "hiit_protocol": {
        "cost": 100,
        "category": "Тренування",
        "type": "functional",
        "uk_name": "HIIT протокол",
        "en_name": "HIIT protocol",
        "uk_desc": "Інтенсивні інтервальні тренування для жиросплавки.",
        "en_desc": "High-intensity interval training for fat loss.",
        "icon": "🔥",
    },
    
    # === ПІДДЕРЖКА І ЕНЕРГІЯ ===
    "motivation_pack": {
        "cost": 35,
        "category": "Піддержка",
        "type": "functional",
        "uk_name": "Пак мотивації",
        "en_name": "Motivation pack",
        "uk_desc": "3 мотиваційні цитати.",
        "en_desc": "3 motivational quotes.",
        "icon": "💪",
    },
    "energy_drink": {
        "cost": 45,
        "category": "Піддержка",
        "type": "consumable",
        "uk_name": "Енергетичний напиток",
        "en_name": "Energy drink",
        "uk_desc": "Дай собі бодрості перед тренуванням.",
        "en_desc": "Boost before workout.",
        "icon": "🥤",
    },
    "sleep_guide": {
        "cost": 50,
        "category": "Піддержка",
        "type": "functional",
        "uk_name": "Гід здорового сну",
        "en_name": "Sleep guide",
        "uk_desc": "Оптимізуй відновлення: 8 годин якісного сну.",
        "en_desc": "Optimize recovery with quality sleep tips.",
        "icon": "😴",
    },
    
    # === АКСЕССУАРИ ===
    "gym_towel": {
        "cost": 25,
        "category": "Аксесуари",
        "type": "collectible",
        "uk_name": "Рушник для спортзалу",
        "en_name": "Gym towel",
        "uk_desc": "Якісний мікрофібровий рушник.",
        "en_desc": "Premium microfiber gym towel.",
        "icon": "🧣",
    },
    "water_bottle": {
        "cost": 40,
        "category": "Аксесуари",
        "type": "collectible",
        "uk_name": "Спортивна пляшка",
        "en_name": "Sports bottle",
        "uk_desc": "Залишайся гідратованим. 1.5 л.",
        "en_desc": "Stay hydrated. 1.5L capacity.",
        "icon": "🍾",
    },
    "training_gloves": {
        "cost": 55,
        "category": "Аксесуари",
        "type": "collectible",
        "uk_name": "Тренувальні рукавиці",
        "en_name": "Training gloves",
        "uk_desc": "Захист при силових вправах.",
        "en_desc": "Protection for heavy lifts.",
        "icon": "🧤",
    },
    "yoga_mat": {
        "cost": 60,
        "category": "Аксесуари",
        "type": "collectible",
        "uk_name": "Килимок для йоги",
        "en_name": "Yoga mat",
        "uk_desc": "Комфортна поверхня для вправ.",
        "en_desc": "Comfort mat for exercises.",
        "icon": "🧘",
    },
    "headphones": {
        "cost": 70,
        "category": "Аксесуари",
        "type": "collectible",
        "uk_name": "Спортивні навушники",
        "en_name": "Sports headphones",
        "uk_desc": "Водостійкі, з гарною музикою.",
        "en_desc": "Waterproof with great sound.",
        "icon": "🎧",
    },
    
    # === ХАРЧУВАННЯ ===
    "protein_powder": {
        "cost": 80,
        "category": "Харчування",
        "type": "consumable",
        "uk_name": "Протеїновий порошок",
        "en_name": "Protein powder",
        "uk_desc": "Якісний сироватковий білок. 500г.",
        "en_desc": "Quality whey protein. 500g.",
        "icon": "🥛",
    },
    "creatine": {
        "cost": 65,
        "category": "Харчування",
        "type": "consumable",
        "uk_name": "Креатин моногідрат",
        "en_name": "Creatine monohydrate",
        "uk_desc": "Для більшої сили і мышечної маси.",
        "en_desc": "Boost strength and muscle growth.",
        "icon": "💊",
    },
    "bcaa": {
        "cost": 75,
        "category": "Харчування",
        "type": "consumable",
        "uk_name": "BCAA амінокислоти",
        "en_name": "BCAA amino acids",
        "uk_desc": "Для відновлення м'язів. 200 порцій.",
        "en_desc": "Muscle recovery. 200 servings.",
        "icon": "⚗️",
    },
    "multivitamin": {
        "cost": 70,
        "category": "Харчування",
        "type": "consumable",
        "uk_name": "Мультивітамін",
        "en_name": "Multivitamin",
        "uk_desc": "Повні вітаміни і мінерали. Не хворій!",
        "en_desc": "Full spectrum vitamins & minerals.",
        "icon": "🔬",
    },
    "weight_gainer": {
        "cost": 90,
        "category": "Харчування",
        "type": "consumable",
        "uk_name": "Вейт-гейнер",
        "en_name": "Weight gainer",
        "uk_desc": "Для набору маси. 1 кг, 10 порцій.",
        "en_desc": "Mass gainer. 1kg, 10 servings.",
        "icon": "🍫",
    },
    
    # === БЕЙДЖИ (КОЛЕКЦІЙНІ) ===
    "rest_badge": {
        "cost": 80,
        "category": "Бейджи",
        "type": "collectible",
        "uk_name": "Бейдж Відновлення 🏆",
        "en_name": "Recovery badge 🏆",
        "uk_desc": "Рідкісний бейдж за баланс у тренуванні.",
        "en_desc": "Rare badge for training balance.",
        "icon": "🎖️",
    },
    "champion_badge": {
        "cost": 100,
        "category": "Бейджи",
        "type": "collectible",
        "uk_name": "Чемпіон 👑",
        "en_name": "Champion 👑",
        "uk_desc": "Престижний бейдж для переможців.",
        "en_desc": "Prestige badge for champions.",
        "icon": "👑",
    },
    "endurance_badge": {
        "cost": 85,
        "category": "Бейджи",
        "type": "collectible",
        "uk_name": "Витривалість 💯",
        "en_name": "Endurance 💯",
        "uk_desc": "За 100 днів безперервних тренувань.",
        "en_desc": "For 100 consecutive training days.",
        "icon": "💯",
    },
    "strength_badge": {
        "cost": 90,
        "category": "Бейджи",
        "type": "collectible",
        "uk_name": "Сила 💪",
        "en_name": "Strength 💪",
        "uk_desc": "За подолання власних меж.",
        "en_desc": "For pushing your limits.",
        "icon": "💪",
    },
    "speed_badge": {
        "cost": 85,
        "category": "Бейджи",
        "type": "collectible",
        "uk_name": "Швидкість ⚡",
        "en_name": "Speed ⚡",
        "uk_desc": "За швидкі інтенсивні тренування.",
        "en_desc": "For high-intensity cardio.",
        "icon": "⚡",
    },
    
    # === БУСТИ (ОБМЕЖЕНО) ===
    "coin_booster_x2": {
        "cost": 150,
        "category": "Бусти",
        "type": "booster",
        "uk_name": "Бустер монет ×2 (1 неділя)",
        "en_name": "Coin booster ×2 (1 week)",
        "uk_desc": "Отримуй в 2 рази більше монет за тренування.",
        "en_desc": "Earn 2x coins for 7 days.",
        "icon": "🪙",
        "max_count": MAX_COIN_BOOSTERS,
    },
    "restore_stamina": {
        "cost": 120,
        "category": "Бусти",
        "type": "booster",
        "uk_name": "Відновити енергію",
        "en_name": "Restore stamina",
        "uk_desc": "Перезагрузи свою енергію для нового челенджу.",
        "en_desc": "Reset your energy for new challenges.",
        "icon": "⚡",
        "max_count": MAX_RESTORE_TOKENS,
    },
    "skip_daily_task": {
        "cost": 90,
        "category": "Бусти",
        "type": "booster",
        "uk_name": "Пропустити завдання",
        "en_name": "Skip daily task",
        "uk_desc": "Пропусти щоденне завдання без штрафу.",
        "en_desc": "Skip daily task without penalty.",
        "icon": "⏭️",
    },
    
    # === ЕКСКЛЮЗИВНІ/ОБМЕЖЕНІ ===
    "legendary_pack": {
        "cost": 200,
        "category": "Ексклюзив",
        "type": "collectible",
        "uk_name": "Легендарний набір 🌟",
        "en_name": "Legendary pack 🌟",
        "uk_desc": "Всі програми + бейджи + бусти. Обмежено!",
        "en_desc": "All programs + badges + boosters. Limited!",
        "icon": "🌟",
    },
    "vip_membership": {
        "cost": 250,
        "category": "Ексклюзив",
        "type": "collectible",
        "uk_name": "VIP членство (1 місяць)",
        "en_name": "VIP membership (1 month)",
        "uk_desc": "Ексклюзивні тренування + 50% знижка на всіх товарах.",
        "en_desc": "Exclusive workouts + 50% discount on all items.",
        "icon": "👑",
    },
}

DAILY_TASKS = {
    "squats_100": {
        "target": 100,
        "step": 25,
        "reward": 45,
        "uk_name": "100 присідань",
        "en_name": "100 squats",
        "uk_unit": "присідань",
        "en_unit": "squats",
        "uk_hint": "Розбий на 4 підходи по 25. Темп спокійний, коліна не заводь всередину.",
        "en_hint": "Split it into 4 sets of 25. Keep a steady pace and knees tracking well.",
    },
    "pushups_60": {
        "target": 60,
        "step": 15,
        "reward": 45,
        "uk_name": "60 відтискувань",
        "en_name": "60 push ups",
        "uk_unit": "відтискувань",
        "en_unit": "push ups",
        "uk_hint": "Можна робити з колін або частинами протягом дня.",
        "en_hint": "Knee push ups count too, and you can split them through the day.",
    },
    "plank_180": {
        "target": 180,
        "step": 30,
        "reward": 50,
        "uk_name": "Планка 180 секунд",
        "en_name": "180 sec plank",
        "uk_unit": "сек",
        "en_unit": "sec",
        "uk_hint": "Наприклад 6 підходів по 30 секунд або 3 по 60.",
        "en_hint": "For example, 6 sets of 30 seconds or 3 sets of 60.",
    },
    "walk_45": {
        "target": 45,
        "step": 15,
        "reward": 45,
        "uk_name": "45 хвилин швидкої ходьби",
        "en_name": "45 min brisk walk",
        "uk_unit": "хв",
        "en_unit": "min",
        "uk_hint": "Підійде активна прогулянка, де дихання стає трохи частішим.",
        "en_hint": "A brisk walk counts when your breathing gets a little faster.",
    },
    "lunges_80": {
        "target": 80,
        "step": 20,
        "reward": 45,
        "uk_name": "80 випадів",
        "en_name": "80 lunges",
        "uk_unit": "випадів",
        "en_unit": "lunges",
        "uk_hint": "Рахуй обидві ноги разом. Тримай корпус рівно.",
        "en_hint": "Count both legs together. Keep your torso steady.",
    },
    "core_120": {
        "target": 120,
        "step": 30,
        "reward": 45,
        "uk_name": "120 скручувань на прес",
        "en_name": "120 sit ups",
        "uk_unit": "разів",
        "en_unit": "reps",
        "uk_hint": "Роби короткими підходами, без ривків шиєю.",
        "en_hint": "Use short sets and avoid pulling your neck.",
    },
}

WORKOUT_COIN_REWARD = 10
SUGGESTED_WORKOUT_REWARD = 25
CHALLENGE_COIN_REWARD = 35


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
    ("Маленькі кроки щодня = великі результати через місяць.", "Small steps every day = big results in a month."),
    ("Ти не завжди маєш бути мотивованим. Будь дисциплінованим.", "You don't always have to be motivated. Be disciplined."),
    ("Кожне тренування - це інвестиція у майбутнього себе.", "Every workout is an investment in your future self."),
    ("Не зупиняйся, коли втомився. Зупиняйся, коли завершив.", "Don't stop when you're tired. Stop when you're done."),
    ("Прогрес важливіший за ідеальність.", "Progress is more important than perfection.")
]

HEALTH_TIPS = [
    ("Після тренування випий склянку води протягом 15 хвилин.", "After training, drink a glass of water within 15 minutes."),
    ("Роби 5 хвилин розминки перед будь-яким навантаженням.", "Do 5 minutes of warm-up before any load."),
    ("Сон 7-8 годин пришвидшує відновлення м'язів.", "7-8 hours of sleep speeds up muscle recovery."),
    ("Додай білок до кожного основного прийому їжі.", "Add protein to every main meal."),
    ("Краще 20 хвилин руху щодня, ніж 2 години раз на тиждень.", "20 minutes of movement every day is better than 2 hours once a week.")
]

FITNESS_CHALLENGES = [
    ("30 присідань + 20 відтискувань + планка 40 сек", "30 squats + 20 push ups + 40 sec plank"),
    ("Швидка прогулянка 25 хв + розтяжка 5 хв", "25 min brisk walk + 5 min stretch"),
    ("3 кола: 15 випадів, 20 скручувань, планка 30 сек", "3 rounds: 15 lunges, 20 sit ups, 30 sec plank"),
    ("Біг або швидкий крок 20 хв без зупинок", "20 min run or fast walk without breaks"),
    ("100 стрибків на місці + 20 присідань + 20 випадів", "100 jumps in place + 20 squats + 20 lunges")
]


def get_localized_choice(lang: str, items):
    return random.choice(items)[1 if lang == "en" else 0]


def get_motivation_quote(lang: str) -> str:
    return get_localized_choice(lang, MOTIVATION_QUOTES)


def get_health_tip(lang: str) -> str:
    return get_localized_choice(lang, HEALTH_TIPS)


def get_fitness_challenge(lang: str) -> str:
    return get_localized_choice(lang, FITNESS_CHALLENGES)


def pick_lang(lang: str, uk: str, en: str) -> str:
    return en if lang == "en" else uk


def gender_display(lang: str, gender_value: str) -> str:
    v = (gender_value or "").strip().lower()

    # Что сейчас реально хранится в БД: "чоловік👨" / "жінка👩"
    if v in {"чоловік👨", "чоловік", "ч", "m", "male", "man 👨", "man"}:
        return pick_lang(lang, "чоловік👨", "man 👨")
    if v in {"жінка👩", "жінка", "ж", "f", "female", "woman 👩", "woman"}:
        return pick_lang(lang, "жінка👩", "woman 👩")

    # fallback: если вдруг уже "male"/"female"
    if v == "male":
        return pick_lang(lang, "чоловік👨", "man 👨")
    if v == "female":
        return pick_lang(lang, "жінка👩", "woman 👩")

    # совсем неожиданный формат — просто показываем как есть
    return str(gender_value)


def toggle_user_language(user_id: int) -> str:
    current = get_user_language(user_id)
    next_lang = "en" if current == "uk" else "uk"
    set_user_language(user_id, next_lang)
    return next_lang


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
        "/daily — щоденне завдання\n"
        "/wallet — баланс монет\n"
        "/shop — магазин\n"
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
        "/daily — daily task\n"
        "/wallet — coin balance\n"
        "/shop — shop\n"
        "/motivate — motivation\n"
        "/tip — health tip\n"
        "/challenge — challenge of the day"
    )
    return style_block(
        "SportBot",
        menu_body,
        icon="🏁"
    )


def generate_workout(goal: str, lang: str) -> str:
    goal_lower = goal.lower()

    if lang == "en":
        if any(keyword in goal_lower for keyword in ("gain", "mass", "muscle")):
            return random.choice([
                "💪 Muscle gain workout:\n"
                "• Push ups 4x15–20\n"
                "• Squats 4x25\n"
                "• Lunges 3x12\n"
                "• Plank 3x40 sec",
                "💪 Muscle gain workout:\n"
                "• Narrow push ups 4x12\n"
                "• Pause squats 4x20\n"
                "• Glute bridge 3x20\n"
                "• Plank 3x45 sec"
            ])
        elif any(keyword in goal_lower for keyword in ("lose", "fat", "diet", "slim")):
            return random.choice([
                "🔥 Fat burning workout:\n"
                "• Running 20–30 min\n"
                "• Burpees 3x12\n"
                "• Jumps 3x40 sec\n"
                "• Plank 3x30 sec",
                "🔥 Fat burning workout:\n"
                "• Jumping Jacks 4x40 sec\n"
                "• Mountain climbers 3x30 sec\n"
                "• Squats 3x25\n"
                "• Plank 3x35 sec"
            ])
        else:
            return random.choice([
                "🏋️ General workout:\n"
                "• Push ups 3x15\n"
                "• Squats 3x20\n"
                "• Plank 3x30 sec",
                "🏋️ General workout:\n"
                "• Push ups 3x12\n"
                "• Lunges 3x12\n"
                "• Bicycle 3x30 sec\n"
                "• Plank 3x40 sec"
            ])
    else:
        if "наб" in goal_lower:
            return random.choice([
                "💪 Тренування на набір маси:\n"
                "• Відтискування 4x15–20\n"
                "• Присідання 4x25\n"
                "• Випади 3x12\n"
                "• Планка 3x40 сек",
                "💪 Тренування на набір маси:\n"
                "• Відтискування вузькі 4x12\n"
                "• Присідання з паузою 4x20\n"
                "• Ягодичний міст 3x20\n"
                "• Планка 3x45 сек"
            ])
        elif "схуд" in goal_lower or "дієт" in goal_lower:
            return random.choice([
                "🔥 Тренування на спалювання жиру:\n"
                "• Біг 20–30 хвилин\n"
                "• Бьорпі 3x12\n"
                "• Стрибки 3x40 сек\n"
                "• Планка 3x30 сек",
                "🔥 Тренування на спалювання жиру:\n"
                "• Jumping Jack 4x40 сек\n"
                "• Альпініст 3x30 сек\n"
                "• Присідання 3x25\n"
                "• Планка 3x35 сек"
            ])
        else:
            return random.choice([
                "🏋️ Універсальне тренування:\n"
                "• Відтискування 3x15\n"
                "• Присідання 3x20\n"
                "• Планка 3x30 сек",
                "🏋️ Універсальне тренування:\n"
                "• Відтискування 3x12\n"
                "• Випади 3x12\n"
                "• Велосипед 3x30 сек\n"
                "• Планка 3x40 сек"
            ])





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
# get_db() теперь импортируется из db_improved и использует глобальное соединение
# Оставляем здесь для совместимости с остальным кодом


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
    if 'coin_balance' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN coin_balance INTEGER DEFAULT 0")
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

    cur.execute("""
                CREATE TABLE IF NOT EXISTS user_items
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    user_id
                    INTEGER,
                    item_id
                    TEXT,
                    purchased_at
                    TEXT
                )
                """)

    cur.execute("""
                CREATE TABLE IF NOT EXISTS daily_tasks
                (
                    user_id
                    INTEGER,
                    date
                    TEXT,
                    task_id
                    TEXT,
                    progress
                    INTEGER
                    DEFAULT
                    0,
                    completed
                    INTEGER
                    DEFAULT
                    0,
                    PRIMARY KEY
                    (user_id, date)
                )
                """)

    cur.execute("""
                CREATE TABLE IF NOT EXISTS coin_rewards
                (
                    user_id
                    INTEGER,
                    date
                    TEXT,
                    source
                    TEXT,
                    amount
                    INTEGER,
                    created_at
                    TEXT,
                    PRIMARY KEY
                    (user_id, date, source)
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


def get_user_profile(user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT height, gender, age, goal, current_weight,
               show_height, show_gender, show_age, show_weight, show_goal
        FROM users
        WHERE user_id=?
        """,
        (user_id,)
    )
    row = cur.fetchone()
    db.close()

    if not row:
        return None

    return {
        "height": row[0],
        "gender": row[1],
        "age": row[2],
        "goal": row[3],
        "current_weight": row[4],
        "show_height": bool(row[5]) if row[5] is not None else True,
        "show_gender": bool(row[6]) if row[6] is not None else True,
        "show_age": bool(row[7]) if row[7] is not None else True,
        "show_weight": bool(row[8]) if row[8] is not None else True,
        "show_goal": bool(row[9]) if row[9] is not None else True,
    }


def is_profile_complete(profile) -> bool:
    if not profile:
        return False
    return bool(
        profile.get("height") and
        profile.get("gender") and
        profile.get("goal")
    )


def ensure_user(user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO users (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
        (user_id,)
    )
    db.commit()
    db.close()


def get_coin_balance(user_id: int) -> int:
    ensure_user(user_id)
    row = fetch_one("SELECT coin_balance FROM users WHERE user_id=?", (user_id,))
    return int(row[0] or 0) if row else 0


def add_coins(user_id: int, amount: int) -> int:
    ensure_user(user_id)
    execute_query(
        "UPDATE users SET coin_balance = COALESCE(coin_balance, 0) + ? WHERE user_id=?",
        (amount, user_id)
    )
    row = fetch_one("SELECT coin_balance FROM users WHERE user_id=?", (user_id,))
    return int(row[0] or 0) if row else 0


def claim_daily_coin_reward(user_id: int, source: str, amount: int):
    ensure_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            """
            INSERT INTO coin_rewards (user_id, date, source, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date, source) DO UPDATE SET
                amount = coin_rewards.amount + excluded.amount,
                created_at = excluded.created_at
            """,
            (user_id, today, source, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        # coin_balance нужно увеличить всегда, когда мы добавляем amount (в т.ч. в конфликт)
        cur.execute(
            "UPDATE users SET coin_balance = COALESCE(coin_balance, 0) + ? WHERE user_id=?",
            (amount, user_id)
        )
        awarded = True
        cur.execute("SELECT coin_balance FROM users WHERE user_id=?", (user_id,))
        balance = int((cur.fetchone() or [0])[0] or 0)
        db.commit()
        return awarded, balance
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def spend_coins(user_id: int, amount: int):
    ensure_user(user_id)
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            """
            UPDATE users
            SET coin_balance = COALESCE(coin_balance, 0) - ?
            WHERE user_id=? AND COALESCE(coin_balance, 0) >= ?
            """,
            (amount, user_id, amount)
        )
        paid = cur.rowcount == 1
        cur.execute("SELECT coin_balance FROM users WHERE user_id=?", (user_id,))
        balance = int((cur.fetchone() or [0])[0] or 0)
        db.commit()
        return paid, balance
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def buy_shop_item(user_id: int, item_id: str, cost: int):
    """
    Безопасная функция покупки товара с использованием транзакции
    Возвращает (success: bool, balance: int, status: str)
    """
    ensure_user(user_id)
    
    try:
        # Проверяем максимальное количество
        item = SHOP_ITEMS.get(item_id, {})
        max_count = item.get('max_count')
        
        if max_count:
            row = fetch_one(
                "SELECT COUNT(*) FROM user_items WHERE user_id=? AND item_id=?",
                (user_id, item_id)
            )
            current_count = row[0] if row else 0
            if current_count >= max_count:
                balance_row = fetch_one(
                    "SELECT COALESCE(coin_balance, 0) FROM users WHERE user_id=?", 
                    (user_id,)
                )
                balance = int(balance_row[0] or 0) if balance_row else 0
                return False, balance, "limit_exceeded"
        
        # Используем транзакцию для атомарности операции
        operations = [
            # Сначала проверяем текущий баланс
            "SELECT COALESCE(coin_balance, 0) FROM users WHERE user_id=?",
        ]
        
        # Получаем текущий баланс
        balance_row = fetch_one(
            "SELECT COALESCE(coin_balance, 0) FROM users WHERE user_id=?",
            (user_id,)
        )
        current_balance = int(balance_row[0]) if balance_row else 0
        
        # Проверяем достаточность средств
        if current_balance < cost:
            return False, current_balance, "insufficient_coins"
        
        # Выполняем транзакцию
        try:
            ops = [
                (
                    "UPDATE users SET coin_balance = COALESCE(coin_balance, 0) - ? WHERE user_id=?",
                    (cost, user_id)
                ),
                (
                    "INSERT INTO user_items (user_id, item_id, purchased_at) VALUES (?, ?, ?)",
                    (user_id, item_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                ),
            ]
            execute_transaction(ops)
            
            # Получаем новый баланс
            balance_row = fetch_one(
                "SELECT COALESCE(coin_balance, 0) FROM users WHERE user_id=?",
                (user_id,)
            )
            new_balance = int(balance_row[0]) if balance_row else 0
            
            return True, new_balance, "success"
        except Exception as e:
            print(f"Error in transaction: {e}")
            # Откатываем изменения (они будут откачены автоматически в execute_transaction)
            return False, current_balance, "transaction_failed"
            
    except Exception as e:
        print(f"Error in buy_shop_item: {e}")
        # Получаем текущий баланс для возврата
        balance_row = fetch_one(
            "SELECT COALESCE(coin_balance, 0) FROM users WHERE user_id=?",
            (user_id,)
        )
        balance = int(balance_row[0]) if balance_row else 0
        return False, balance, "error"


def add_user_item(user_id: int, item_id: str):
    execute_query(
        "INSERT INTO user_items (user_id, item_id, purchased_at) VALUES (?, ?, ?)",
        (user_id, item_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )


def get_user_items(user_id: int) -> dict:
    rows = fetch_all(
        "SELECT item_id, COUNT(*) FROM user_items WHERE user_id=? GROUP BY item_id",
        (user_id,)
    )
    return {item_id: count for item_id, count in rows} if rows else {}


def format_coin_reward(lang: str, amount: int, balance: int) -> str:
    return pick_lang(
        lang,
        f"\n\n🪙 +{amount} монет\nБаланс: {balance}",
        f"\n\n🪙 +{amount} coins\nBalance: {balance}"
    )


def get_premium_workout(lang: str) -> str:
    workouts = [
        (
            "⚡ Преміум тренування:\n"
            "• Розминка 5 хв\n"
            "• Присідання 4x20\n"
            "• Відтискування 4x12\n"
            "• Альпініст 3x40 сек\n"
            "• Планка 3x45 сек",
            "⚡ Premium workout:\n"
            "• Warm-up 5 min\n"
            "• Squats 4x20\n"
            "• Push ups 4x12\n"
            "• Mountain climbers 3x40 sec\n"
            "• Plank 3x45 sec",
        ),
        (
            "⚡ Преміум тренування:\n"
            "• Швидкий крок 10 хв\n"
            "• Випади 4x12\n"
            "• Скручування 3x20\n"
            "• Бьорпі 3x10\n"
            "• Розтяжка 5 хв",
            "⚡ Premium workout:\n"
            "• Fast walk 10 min\n"
            "• Lunges 4x12\n"
            "• Sit ups 3x20\n"
            "• Burpees 3x10\n"
            "• Stretch 5 min",
        ),
    ]
    return get_localized_choice(lang, workouts)


def choose_daily_task_id(user_id: int, date_text: str) -> str:
    task_ids = list(DAILY_TASKS.keys())
    rng = random.Random(f"{user_id}:{date_text}")
    return rng.choice(task_ids)


def get_or_create_daily_task(user_id: int):
    ensure_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT task_id, progress, completed FROM daily_tasks WHERE user_id=? AND date=?",
        (user_id, today)
    )
    row = cur.fetchone()

    if not row:
        task_id = choose_daily_task_id(user_id, today)
        cur.execute(
            "INSERT INTO daily_tasks (user_id, date, task_id, progress, completed) VALUES (?, ?, ?, 0, 0)",
            (user_id, today, task_id)
        )
        db.commit()
        row = (task_id, 0, 0)

    db.close()
    task_id, progress, completed = row
    task = DAILY_TASKS.get(task_id, DAILY_TASKS["squats_100"])
    return today, task_id, task, int(progress or 0), bool(completed)


def build_progress_bar(progress: int, target: int) -> tuple[str, int]:
    percent = min(int(progress / target * 100), 100) if target else 0
    filled = min(percent // 10, 10)
    return "█" * filled + "░" * (10 - filled), percent


def build_daily_task_text(lang: str, task: dict, progress: int, completed: bool) -> str:
    target = task["target"]
    progress = min(progress, target)
    bar, percent = build_progress_bar(progress, target)
    unit = pick_lang(lang, task["uk_unit"], task["en_unit"])
    status = pick_lang(lang, "✅ Завершено", "✅ Completed") if completed else pick_lang(lang, "⏳ В процесі", "⏳ In progress")

    return pick_lang(
        lang,
        f"🎯 Завдання: {task['uk_name']}\n"
        f"📈 Прогрес: {progress}/{target} {unit}\n"
        f"{bar} {percent}%\n"
        f"🪙 Нагорода: {task['reward']} монет\n"
        f"📌 {task['uk_hint']}\n\n"
        f"{status}",
        f"🎯 Task: {task['en_name']}\n"
        f"📈 Progress: {progress}/{target} {unit}\n"
        f"{bar} {percent}%\n"
        f"🪙 Reward: {task['reward']} coins\n"
        f"📌 {task['en_hint']}\n\n"
        f"{status}"
    )


def update_daily_progress(user_id: int):
    today, task_id, task, progress, completed = get_or_create_daily_task(user_id)

    if completed:
        return task, progress, True, False, get_coin_balance(user_id)

    new_progress = min(progress + task["step"], task["target"])
    completed_now = new_progress >= task["target"]

    balance = get_coin_balance(user_id)
    rewarded = False
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            """
            UPDATE daily_tasks
            SET progress=?, completed=?
            WHERE user_id=? AND date=? AND completed=0
            """,
            (new_progress, 1 if completed_now else 0, user_id, today)
        )
        changed = cur.rowcount
        if changed and completed_now:
            cur.execute(
                """
                INSERT OR IGNORE INTO coin_rewards (user_id, date, source, amount, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, today, "daily", task["reward"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            rewarded = cur.rowcount == 1
        if rewarded:
            cur.execute(
                "UPDATE users SET coin_balance = COALESCE(coin_balance, 0) + ? WHERE user_id=?",
                (task["reward"], user_id)
            )
            cur.execute("SELECT coin_balance FROM users WHERE user_id=?", (user_id,))
            balance = int((cur.fetchone() or [0])[0] or 0)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if not changed:
        return task, progress, True, False, get_coin_balance(user_id)

    return task, new_progress, completed_now, rewarded, balance


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
    lang = get_user_language(uid)
    
    # Используем новую безопасную функцию
    success = clear_user_all_data(uid)
    
    if success:
        await callback.message.edit_text(
            pick_lang(lang, "✅ Профіль повністю видалено. Дані очищені.", 
                     "✅ Profile completely deleted. All data cleared.")
        )
    else:
        await callback.message.edit_text(
            pick_lang(lang, "❌ Помилка при видаленні. Спробуйте пізніше.", 
                     "❌ Error during deletion. Try again later.")
        )


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
    uid = message.from_user.id

    # Требование: любой вызов /set_language должен переключать UA <-> EN
    lang = toggle_user_language(uid)

    await message.answer(
        build_start_text(lang),
        parse_mode="HTML",
        reply_markup=language_kb
    )


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
    
    # Проверяем, существует ли пользователь
    if not verify_user_exists(uid):
        set_user_state(uid, "profile")
        await message.answer(
            pick_lang(
                lang,
                "Введи профіль:\nЗріст, стать, вік, мета\nПриклад: 165, ч, 25, набрати масу",
                "Enter your profile:\nHeight, gender, age, goal\nExample: 165, m, 25, gain muscle"
            )
        )
        return
    
    # Получаем данные безопасно
    profile_row = get_user_data_safe(uid)
    
    if not profile_row:
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
        gd = gender_display(lang, g)
        profile_lines.append(pick_lang(lang, f"🧍 Стать: {gd}", f"🧍 Gender: {gd}"))
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


@dp.message(Command("daily"))
async def daily(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)
    date_text, _, task, progress, completed = get_or_create_daily_task(uid)

    await message.answer(
        style_block(
            pick_lang(lang, "Щоденне завдання", "Daily task"),
            build_daily_task_text(lang, task, progress, completed),
            icon="🎮"
        ),
        parse_mode="HTML",
        reply_markup=daily_task_keyboard(lang, task, completed, date_text)
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("daily_"))
async def daily_progress(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    callback_date = None

    if callback.data.startswith("daily_add_"):
        callback_date = callback.data.replace("daily_add_", "", 1)
    elif callback.data.startswith("daily_done_"):
        callback_date = callback.data.replace("daily_done_", "", 1)
    elif callback.data.startswith("daily_finish_"):
        callback_date = callback.data.replace("daily_finish_", "", 1)

    if callback_date and callback_date != today:
        await callback.answer(
            pick_lang(lang, "Це старе завдання. Відкрий /daily", "This is an old task. Open /daily"),
            show_alert=True
        )
        return

    if callback.data.startswith("daily_done"):
        await callback.answer(pick_lang(lang, "Завдання вже виконано", "Task already completed"))
        return

    date_text, _, _, _, _ = get_or_create_daily_task(uid)
    task, progress, completed, rewarded, balance = update_daily_progress(uid)

    text = build_daily_task_text(lang, task, progress, completed)
    if rewarded:
        text += pick_lang(
            lang,
            f"\n\n🪙 +{task['reward']} монет\nБаланс: {balance}",
            f"\n\n🪙 +{task['reward']} coins\nBalance: {balance}"
        )

    await callback.message.edit_text(
        style_block(
            pick_lang(lang, "Щоденне завдання", "Daily task"),
            text,
            icon="🎮"
        ),
        parse_mode="HTML",
        reply_markup=daily_task_keyboard(lang, task, completed, date_text)
    )

    if rewarded:
        await callback.answer(pick_lang(lang, f"+{task['reward']} монет", f"+{task['reward']} coins"))
    else:
        await callback.answer(pick_lang(lang, "Прогрес оновлено", "Progress updated"))


@dp.message(Command("wallet"))
async def wallet(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)
    balance = get_coin_balance(uid)
    items = get_user_items(uid)

    if items:
        item_lines = []
        for item_id, count in items.items():
            item = SHOP_ITEMS.get(item_id)
            if item:
                item_lines.append(f"• {pick_lang(lang, item['uk_name'], item['en_name'])}: {count}")
        inventory = "\n".join(item_lines)
    else:
        inventory = pick_lang(lang, "Покупок ще немає.", "No purchases yet.")

    await message.answer(
        style_block(
            pick_lang(lang, "Гаманець", "Wallet"),
            pick_lang(
                lang,
                f"🪙 Баланс: {balance}\n\n🎒 Покупки:\n{inventory}\n\nМагазин: /shop",
                f"🪙 Balance: {balance}\n\n🎒 Purchases:\n{inventory}\n\nShop: /shop"
            ),
            icon="💰"
        ),
        parse_mode="HTML"
    )


@dp.message(Command("shop"))
async def shop(message: Message):
    uid = message.from_user.id
    lang = get_user_language(uid)
    
    # Обеспечиваем существование пользователя
    ensure_user(uid)
    
    # Безопасно получаем баланс
    balance = get_coin_balance(uid)
    
    # Формируем текст со структурированной информацией
    header = pick_lang(
        lang,
        f"🛒 Магазин Спортсмена\n\n🪙 Баланс: {balance} монет\n\nОберіть категорію товара:",
        f"🛒 Sports Shop\n\n🪙 Balance: {balance} coins\n\nChoose a category:"
    )
    
    try:
        # Отправляем сообщение с клавиатурой категорий
        await message.answer(
            header,
            parse_mode=None,
            reply_markup=shop_keyboard(lang)
        )
    except Exception as e:
        print(f"Error in shop command: {e}")
        # Fallback ответ
        await message.answer(
            pick_lang(
                lang,
                f"🛒 Магазин\n\n🪙 Баланс: {balance} монет\n\nИспользуйте кнопки для навигации.",
                f"🛒 Shop\n\n🪙 Balance: {balance} coins\n\nUse buttons to navigate."
            )
        )


@dp.callback_query(lambda c: c.data == "shop_noop")
async def shop_noop(callback: CallbackQuery):
    """Обработчик для кликов на заголовки категорий - ничего не делает"""
    await callback.answer()



@dp.callback_query(F.data.startswith("shop_cat_"))
async def shop_cat(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid)
    await callback.answer()

    category = callback.data.replace("shop_cat_", "", 1)
    text = pick_lang(lang, "📦 Магазин: оберіть товар", "📦 Shop: pick an item")

    try:
        await callback.message.edit_text(
            text,
            reply_markup=shop_category_keyboard(lang, category),
            parse_mode=None,
        )
    except Exception:
        # fallback если edit_text не удалось (не модифицировано / нельзя редактировать / т.п.)
        await callback.message.answer(
            text,
            reply_markup=shop_category_keyboard(lang, category),
        )


@dp.callback_query(F.data == "shop_back_to_categories")
async def shop_back_to_categories(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid)
    await callback.answer()

    text = pick_lang(lang, "📦 Магазин: категорії", "📦 Shop: categories")

    try:
        await callback.message.edit_text(
            text,
            reply_markup=shop_keyboard(lang),
            parse_mode=None,
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=shop_keyboard(lang),
        )


@dp.callback_query(F.data.startswith("shop_buy_"))
async def shop_buy(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid)
    item_id = callback.data.replace("shop_buy_", "", 1)
    item = SHOP_ITEMS.get(item_id)

    if not item:
        await callback.answer(pick_lang(lang, "Товар не знайдено", "Item not found"), show_alert=True)
        return

    paid, balance, status = buy_shop_item(uid, item_id, item["cost"])
    
    if status == "limit_exceeded":
        max_count = item.get('max_count', 1)
        await callback.answer(
            pick_lang(
                lang,
                f"Макс куплено: {max_count} шт. Вижраних: /wallet",
                f"Maximum purchased: {max_count}. View: /wallet"
            ),
            show_alert=True
        )
        return
    
    if status == "insufficient_coins":
        await callback.answer(
            pick_lang(
                lang,
                f"Не вистачає монет. Баланс: {balance}",
                f"Not enough coins. Balance: {balance}"
            ),
            show_alert=True
        )
        return

    # При успешной покупке генерируем разные отговеты в зависимости от типа
    item_name = pick_lang(lang, item['uk_name'], item['en_name'])
    item_desc = pick_lang(lang, item['uk_desc'], item['en_desc'])
    item_type = item.get('type', 'unknown')

    # Основное сообщение
    base_msg = pick_lang(
        lang,
        f"✅ {item_name}\n🪙 Баланс: {balance}",
        f"✅ {item_name}\n🪙 Balance: {balance}"
    )

    # Генерируем содержимое в зависимости от типа
    if item_type == "functional":
        if item_id == "power_plan":
            body = f"{base_msg}\n\n{get_premium_workout(lang)}"
        elif item_id == "monthly_program":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n📅 30 днів модуля:\n• Тиждень 1: Основа\n• Тиждень 2-3: Настроювання\n• Тиждень 4: Пік\n\nВицавлено наовна в /магазині",
                f"{base_msg}\n\n📅 30-day progression:\n• Week 1: Foundation\n• Week 2-3: Building\n• Week 4: Peak\n\nStart now: /profile"
            )
        elif item_id == "home_gym":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n🏠 40+ вправ без обладнання!\nУсо в /wallet",
                f"{base_msg}\n\n🏠 40+ bodyweight exercises!\nOpen: /wallet"
            )
        elif item_id == "hiit_protocol":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n🔥 HIIT - 20 мін для максимального ефекту калорій",
                f"{base_msg}\n\n🔥 20-min intervals for max calorie burn"
            )
        elif item_id == "sleep_guide":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n😴 Таємниці сну атлета: Оптимальна температура, час сну",
                f"{base_msg}\n\n😴 Athlete's sleep formula: temp, timing, duration"
            )
        else:
            body = f"{base_msg}\n\n{item_desc}"

    elif item_type == "consumable":
        if item_id == "motivation_pack":
            quotes = "\n".join(f"• {get_motivation_quote(lang)}" for _ in range(3))
            body = f"{base_msg}\n\n{quotes}"
        elif item_id == "energy_drink":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n🥤 Зарядився! 🤸\nТепер рязва пітти води і тренуватися!",
                f"{base_msg}\n\n🥤 Powered up! 🤸\nTime to crush it!"
            )
        else:
            body = f"{base_msg}\n\n✨ {item_desc}"

    elif item_type == "booster":
        if item_id == "coin_booster_x2":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n🪙 × 2 МОНЕТ на 7 днів!\nВсі тренування = 2x рівардс",
                f"{base_msg}\n\n🪙 × 2 COINS for 7 days!\nAll workouts = 2x rewards"
            )
        elif item_id == "restore_stamina":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n⚡ Відновлено!\nКільканка чотири години активності.",
                f"{base_msg}\n\n⚡ Restored!\n4 hours of active energy."
            )
        elif item_id == "skip_daily_task":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n⏭️ Топ (день) випало!",
                f"{base_msg}\n\n⏭️ Daily task skipped penalty-free!"
            )
        else:
            body = f"{base_msg}\n\n⚡ {item_desc}"

    else:  # collectible + exclusive
        if item_id == "legendary_pack":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n🌟 ЛЕГЕНДА! 🌟\nОвдточено всі доступні бонуси!\nОбмежено кілька годин.",
                f"{base_msg}\n\n🌟 LEGENDARY! 🌟\nUnlocked all available bonuses!\nHurry - limited time offer."
            )
        elif item_id == "vip_membership":
            body = pick_lang(
                lang,
                f"{base_msg}\n\n👑 VIP доступ 👑\nНа місяць: +50% знижка, екскльузив\nОтримати графік 1 ра неділя.",
                f"{base_msg}\n\n👑 VIP ACCESS 👑\n1 Month: 50% discount + exclusive\ntraining schedule unlock."
            )
        else:
            body = f"{base_msg}\n\n🌟 {item_desc}"

    await callback.message.answer(
        style_block(pick_lang(lang, "📖 Умвовання в /wallet", "📖 Unlocked in /wallet"), body, icon="✅"),
        parse_mode="HTML"
    )
    await callback.answer(pick_lang(lang, "🌟 Отмено!", "🌟 Awesome!"))


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
    
    if not row or row[0] is None:
        # Новый пользователь или неизвестный статус — включаем напоминания по умолчанию
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

    text = generate_workout(row[0], lang)
    await message.answer(text, reply_markup=suggest_keyboard(lang))


@dp.message(Command("motivate"))
async def motivate(message: Message):
    lang = get_user_language(message.from_user.id)
    quote = get_motivation_quote(lang)
    title = pick_lang(lang, "Мотивація", "Motivation")
    await message.answer(
        style_block(title, f"💬 {quote}", icon="🚀"),
        parse_mode="HTML"
    )


@dp.message(Command("tip"))
async def tip(message: Message):
    lang = get_user_language(message.from_user.id)
    tip_text = get_health_tip(lang)
    title = pick_lang(lang, "Порада дня", "Tip of the day")
    await message.answer(
        style_block(title, f"💡 {tip_text}", icon="🧠"),
        parse_mode="HTML"
    )


@dp.message(Command("challenge"))
async def challenge(message: Message):
    lang = get_user_language(message.from_user.id)
    challenge_text = get_fitness_challenge(lang)
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

    text = generate_workout(row[0], lang)
    await callback.message.answer(text, reply_markup=suggest_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "suggest_done")
async def suggest_done(callback: CallbackQuery):
    lang = get_user_language(callback.from_user.id)
    uid = callback.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    workout_text = callback.message.text or ""

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

    saved_count = 0
    for line in workout_text.split("\n"):
        if line.startswith("•"):
            cur.execute(
                "INSERT INTO workouts (user_id, text, date) VALUES (?, ?, ?)",
                (uid, line[2:], today)
            )
            saved_count += 1

    db.commit()
    db.close()

    reward = SUGGESTED_WORKOUT_REWARD if saved_count else 0
    rewarded, balance = claim_daily_coin_reward(uid, "suggest", reward) if reward else (False, get_coin_balance(uid))

    await callback.message.edit_text(
        callback.message.text
        + pick_lang(lang, "\n\n✅ Тренування збережено", "\n\n✅ Workout saved")
        + (format_coin_reward(lang, reward, balance) if rewarded else "")
    )
    await callback.answer(pick_lang(lang, f"+{reward} монет", f"+{reward} coins") if rewarded else pick_lang(lang, "ОК", "OK"))


@dp.callback_query(F.data == "challenge_next")
async def challenge_next(callback: CallbackQuery):
    lang = get_user_language(callback.from_user.id)
    challenge_text = get_fitness_challenge(lang)
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
    message_text = callback.message.text or ""
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
    if cur.fetchone():
        db.close()
        await callback.answer(pick_lang(lang, "Сьогодні вже зараховано", "Already counted today"))
        return

    cur.execute(
        "INSERT INTO workouts (user_id, text, date, is_challenge) VALUES (?, ?, ?, 1)",
        (uid, challenge_text, today)
    )
    db.commit()
    db.close()

    rewarded, balance = claim_daily_coin_reward(uid, "challenge", CHALLENGE_COIN_REWARD)

    await callback.message.edit_text(
        callback.message.text
        + pick_lang(lang, "\n\n✅ Челендж зараховано!", "\n\n✅ Challenge counted!")
        + (format_coin_reward(lang, CHALLENGE_COIN_REWARD, balance) if rewarded else ""),
        parse_mode="HTML"
    )
    await callback.answer(
        pick_lang(lang, f"+{CHALLENGE_COIN_REWARD} монет", f"+{CHALLENGE_COIN_REWARD} coins")
        if rewarded else pick_lang(lang, "Зараховано", "Counted")
    )


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
            if goal < 1:
                raise ValueError("invalid goal")

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
        return

    # WORKOUT
    if state == "workout":
        exercises = [x.strip() for x in message.text.split(",") if x.strip()]
        if not exercises:
            await message.answer(
                pick_lang(
                    lang,
                    "Введи хоча б одну вправу.",
                    "Enter at least one exercise."
                )
            )
            return

        db = get_db()
        cur = db.cursor()

        for ex in exercises:
            cur.execute(
                "INSERT INTO workouts (user_id, text, date) VALUES (?, ?, ?)",
                (uid, ex, datetime.now().strftime("%Y-%m-%d"))
            )

        db.commit()
        db.close()

        reward = min(len(exercises) * WORKOUT_COIN_REWARD, 50)
        rewarded, balance = claim_daily_coin_reward(uid, "workout", reward) if reward else (False, get_coin_balance(uid))
        reward_text = (
            pick_lang(lang, f"\n🪙 +{reward} монет\nБаланс: {balance}", f"\n🪙 +{reward} coins\nBalance: {balance}")
            if rewarded else
            pick_lang(lang, f"\n🪙 Нагорода за /workout сьогодні вже отримана\nБаланс: {balance}", f"\n🪙 Today's /workout reward is already claimed\nBalance: {balance}")
        )

        await message.answer(
            pick_lang(
                lang,
                f"Збережено: {len(exercises)}{reward_text}",
                f"Saved: {len(exercises)}{reward_text}"
            )
        )
        clear_user_state(uid)
        return


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
        BotCommand(command="daily", description="Щоденне завдання"),
        BotCommand(command="wallet", description="Баланс монет"),
        BotCommand(command="shop", description="Магазин"),
        BotCommand(command="reminders", description="Нагадування"),
        BotCommand(command="motivate", description="Мотивація"),
        BotCommand(command="tip", description="Корисна порада"),
        BotCommand(command="challenge", description="Челендж дня")
    ])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
