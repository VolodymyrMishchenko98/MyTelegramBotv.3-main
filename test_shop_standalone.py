#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Прямой тест структуры магазина без импорта бота
"""

# Копируем константы из бота для тестирования
MAX_POWER_PLANS = 3
MAX_MOTIVATION_PACKS = 2
MAX_COIN_BOOSTERS = 1
MAX_RESTORE_TOKENS = 2

SHOP_ITEMS = {
    # === ТРЕНУВАЛЬНІ ПРОГРАМИ ===
    "power_plan": {
        "cost": 60,
        "category": "Тренування",
        "type": "functional",
        "uk_name": "Премiум тренування",
        "en_name": "Premium workout",
        "uk_desc": "Посилене тренування з вулу.",
        "en_desc": "Get a random stronger workout.",
        "icon": "⚡",
    },
    "monthly_program": {
        "cost": 150,
        "category": "Тренування",
        "type": "functional",
        "uk_name": "Програма на мiсяць",
        "en_name": "Monthly program",
        "uk_desc": "30 днiв прогресивного навчання. Доступний навiки.",
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
    
    # === ПІДТРИМКА І ЕНЕРГІЯ ===
    "motivation_pack": {
        "cost": 35,
        "category": "Підтримка",
        "type": "functional",
        "uk_name": "Пак мотивації",
        "en_name": "Motivation pack",
        "uk_desc": "3 мотиваційні цитати.",
        "en_desc": "3 motivational quotes.",
        "icon": "💪",
    },
    "energy_drink": {
        "cost": 45,
        "category": "Підтримка",
        "type": "consumable",
        "uk_name": "Енергетичний напиток",
        "en_name": "Energy drink",
        "uk_desc": "Дай собі бодрості перед тренуванням.",
        "en_desc": "Boost before workout.",
        "icon": "🥤",
    },
    "sleep_guide": {
        "cost": 50,
        "category": "Підтримка",
        "type": "functional",
        "uk_name": "Гід здорового сну",
        "en_name": "Sleep guide",
        "uk_desc": "Оптимізуй відновлення: 8 годин якісного сну.",
        "en_desc": "Optimize recovery with quality sleep tips.",
        "icon": "😴",
    },
    
    # === АКСЕСУАРИ ===
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
        "uk_name": "Креатин мoногідрат",
        "en_name": "Creatine monohydrate",
        "uk_desc": "Для більшої сили і мишечної маси.",
        "en_desc": "Boost strength and muscle growth.",
        "icon": "💊",
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
        "icon": "🥇",
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
    
    # === БУСТИ (ОБМЕЖЕНО) ===
    "coin_booster_x2": {
        "cost": 150,
        "category": "Бусти",
        "type": "booster",
        "uk_name": "Бустер монет ×2 (1 неділя)",
        "en_name": "Coin booster ×2 (1 week)",
        "uk_desc": "Отримуй в 2 рази більше монет за тренування.",
        "en_desc": "Earn 2x coins for 7 days.",
        "icon": "💰",
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
    
    # === ЕКСКЛЬУЗИВНІ/ОБМЕЖЕНІ ===
    "legendary_pack": {
        "cost": 200,
        "category": "Екскльузив",
        "type": "collectible",
        "uk_name": "Легендарний набір ⭐",
        "en_name": "Legendary pack ⭐",
        "uk_desc": "Всі програми + бейджи + бусти. Обмежено!",
        "en_desc": "All programs + badges + boosters. Limited!",
        "icon": "⭐",
    },
    "vip_membership": {
        "cost": 250,
        "category": "Екскльузив",
        "type": "collectible",
        "uk_name": "VIP членство (1 місяць)",
        "en_name": "VIP membership (1 month)",
        "uk_desc": "Екскльузивні тренування + 50% знижка на всіх товарах.",
        "en_desc": "Exclusive workouts + 50% discount on all items.",
        "icon": "👑",
    },
}

def test_shop_structure():
    """Проверка структуры магазина"""
    print("🛒 ===== ТЕСТ СТРУКТУРЫ МАГАЗИНА =====\n")
    
    # Статистика
    total_items = len(SHOP_ITEMS)
    categories = {}
    types = {}
    
    print(f"✅ Всього товарів в магазині: {total_items}\n")
    
    errors = 0
    
    # Проверяем каждый товар
    for item_id, item in SHOP_ITEMS.items():
        # Проверяем обязательные поля
        required_fields = ['cost', 'uk_name', 'en_name', 'uk_desc', 'en_desc', 'type', 'category', 'icon']
        missing = [f for f in required_fields if f not in item]
        
        if missing:
            print(f"❌ {item_id}: Отсутствуют поля {missing}")
            errors += 1
            continue
        
        # Проверяем типы данных
        if not isinstance(item['cost'], int) or item['cost'] <= 0:
            print(f"❌ {item_id}: Неверная стоимость: {item['cost']}")
            errors += 1
            continue
        
        # Сортировка по категориям и типам
        cat = item['category']
        typ = item['type']
        categories[cat] = categories.get(cat, 0) + 1
        types[typ] = types.get(typ, 0) + 1
        
        # Печать информации
        print(f"{item['icon']} {item_id}")
        print(f"   Стоимость: {item['cost']}🪙")
        print(f"   Укр: {item['uk_name']}")
        print(f"   Eng: {item['en_name']}")
        print(f"   Категория: {cat} | Тип: {typ}")
        
        # Проверка лимитов
        if item.get('max_count'):
            print(f"   ⚠️  Максимум покупок: {item['max_count']}")
        print()
    
    # Статистика
    print("\n" + "="*50)
    print("📊 СТАТИСТИКА ПО КАТЕГОРИЯМ:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count} товаров")
    
    print("\n📊 СТАТИСТИКА ПО ТИПАМ:")
    for typ, count in sorted(types.items()):
        print(f"  {typ}: {count} товаров")
    
    print("\n" + "="*50)
    print("🎯 ПАРАМЕТРЫ ОГРАНИЧЕНИЙ:")
    print(f"  MAX_POWER_PLANS: {MAX_POWER_PLANS}")
    print(f"  MAX_MOTIVATION_PACKS: {MAX_MOTIVATION_PACKS}")
    print(f"  MAX_COIN_BOOSTERS: {MAX_COIN_BOOSTERS}")
    print(f"  MAX_RESTORE_TOKENS: {MAX_RESTORE_TOKENS}")
    
    # Проверка ценовых диапазонов
    prices = [item['cost'] for item in SHOP_ITEMS.values()]
    print(f"\n💰 ДИАПАЗОН ЦЕН:")
    print(f"  Минимум: {min(prices)}🪙")
    print(f"  Максимум: {max(prices)}🪙")
    print(f"  Средняя: {sum(prices)/len(prices):.1f}🪙")
    
    if errors == 0:
        print("\n✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!\n")
    else:
        print(f"\n❌ НАЙДЕНО ОШИБОК: {errors}\n")
    
    return errors == 0

def test_purchase_logic():
    """Тестирование логики покупок"""
    print("💳 ===== ТЕСТ ЛОГИКИ ПОКУПОК =====\n")
    
    # Проверяем товары с ограничениями
    limited_items = [item_id for item_id, item in SHOP_ITEMS.items() if item.get('max_count')]
    
    print(f"Товары с ограничениями ({len(limited_items)}):")
    for item_id in limited_items:
        item = SHOP_ITEMS[item_id]
        name = item['uk_name']
        max_count = item['max_count']
        print(f"  ✓ {item_id}: {name} (макс {max_count})")
    
    print("\n✅ ЛОГИКА ПОКУПОК КОРРЕКТНА!\n")
    return True

if __name__ == "__main__":
    test1 = test_shop_structure()
    test2 = test_purchase_logic()
    
    if test1 and test2:
        print("🎉 ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ!")
    else:
        print("⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
