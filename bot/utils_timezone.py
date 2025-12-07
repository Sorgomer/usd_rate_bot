import aiohttp
import logging

"""
Автоматическое определение часового пояса по названию города.

Используем:
1) Nominatim (OpenStreetMap) для геокодинга города → lat/lon
2) Open-Meteo Timezone API для получения смещения UTC
"""

logger = logging.getLogger(__name__)


async def geocode_city(query: str) -> tuple[float, float, str]:
    """
    Определяет координаты города по текстовому запросу.
    Возвращает: (lat, lon, display_name)

    Используется Nominatim (OSM) — бесплатный и без API-ключа.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
    }

    logger.info("Geocoding city: %s", query)

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=10, headers={"User-Agent": "TelegramBot"}) as resp:
            resp.raise_for_status()
            data = await resp.json()

    if not data:
        raise ValueError("Город не найден")

    item = data[0]
    lat = float(item["lat"])
    lon = float(item["lon"])
    display_name = item.get("display_name", query)

    logger.info("City geocoded: %s → lat=%s lon=%s", display_name, lat, lon)
    return lat, lon, display_name


async def get_timezone_offset_minutes(lat: float, lon: float) -> int:
    """
    Возвращает смещение UTC в минутах для координат lat/lon.

    Использует Open-Meteo Timezone API.
    """
    url = "https://api.open-meteo.com/v1/timezone"
    params = {
        "latitude": lat,
        "longitude": lon,
    }

    logger.info("Fetching timezone for lat=%s lon=%s", lat, lon)

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=10) as resp:
            resp.raise_for_status()
            data = await resp.json()

    if "utc_offset_seconds" not in data:
        raise ValueError("Не удалось получить timezone offset")

    offset_seconds = data["utc_offset_seconds"]
    offset_minutes = int(offset_seconds // 60)

    logger.info("Timezone offset fetched: %s minutes", offset_minutes)
    return offset_minutes