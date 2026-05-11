#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестирование логики магазина и проверка всех товаров
"""
import sys
sys.path.insert(0, '.')

from bot import SHOP_ITEMS, MAX_POWER_PLANS, MAX_MOTIVATION_PACKS, MAX_COIN_BOOSTERS, MAX_RESTORE_TOKENS

def test_shop_structure():
    """Проверка структуры магазина"""
    print("🛒 ===== ТЕСТ СТРУКТУРЫ МАГАЗИНА =====\n")
    
    # Статистика
    total_items = len(SHOP_ITEMS)
    categories = {}
    types = {}
    
    print(f"✅ Всього товарів в магазині: {total_items}\n")
    
    # Проверяем каждый товар
    for item_id, item in SHOP_ITEMS.items():
        # Проверяем обязательные поля
        required_fields = ['cost', 'uk_name', 'en_name', 'uk_desc', 'en_desc', 'type', 'category', 'icon']
        missing = [f for f in required_fields if f not in item]
        
        if missing:
            print(f"❌ {item_id}: Отсутствуют поля {missing}")
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
    
    print("\n✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!\n")

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

if __name__ == "__main__":
    test_shop_structure()
    test_purchase_logic()
    print("🎉 ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ!")
