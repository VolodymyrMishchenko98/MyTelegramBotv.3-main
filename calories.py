from __future__ import annotations

import re
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import aiohttp

API_NINJAS_URL: Final[str] = "https://api.api-ninjas.com/v1/caloriesburned"
X_API_NINJAS_KEY_ENV: Final[str] = "API_NINJAS_KEY"

# Локальный кэш (в bot.py уже есть свой calories_cache, но при рефакторе
# лучше сделать один источник кеша. Пока оставляем модуль автономным.)
_calories_cache: dict[str, int] = {}

# Чтобы не делать запросы слишком часто, ограничим TTL (упрощённо — сброс вручную снаружи можно будет добавить).
CACHE_MAX_KEYS: Final[int] = 5000

# -------- parsing --------
def parse_activity_and_duration(text: str) -> tuple[str, int]:
    raw = text.lower()
    m = re.search(r"(\d+)\s*(хв|хвилин|мин|min)", raw)
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
        "прес": "sit ups",
    }

    for key, api_activity in activity_map.items():
        if key in raw:
            return api_activity, duration

    return "workout", duration


def _fallback_calories(cache_key: str) -> int:
    m = re.search(r"(\d+)\s*(хв|хвилин|мин|min)", cache_key)
    if m:
        return int(m.group(1)) * 8

    if "x" in cache_key or "х" in cache_key:
        return 30

    return 0


def calc_calories_fallback_only(text: str) -> int:
    cache_key = text.strip().lower()
    if cache_key in _calories_cache:
        return _calories_cache[cache_key]

    value = _fallback_calories(cache_key)
    _calories_cache[cache_key] = value

    if len(_calories_cache) > CACHE_MAX_KEYS:
        _calories_cache.clear()

    return value


async def calc_calories_async(text: str, api_key: str) -> int:
    cache_key = text.strip().lower()
    if cache_key in _calories_cache:
        return _calories_cache[cache_key]

    activity, duration = parse_activity_and_duration(text)

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                API_NINJAS_URL,
                params={"activity": activity, "duration": duration},
                headers={"X-Api-Key": api_key},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list) and data:
                        total = data[0].get("total_calories")
                        if total is not None:
                            value = int(round(float(total)))
                            _calories_cache[cache_key] = value
                            if len(_calories_cache) > CACHE_MAX_KEYS:
                                _calories_cache.clear()
                            return value
    except Exception:
        # fallback ниже
        pass

    value = _fallback_calories(cache_key)
    _calories_cache[cache_key] = value
    if len(_calories_cache) > CACHE_MAX_KEYS:
        _calories_cache.clear()
    return value
