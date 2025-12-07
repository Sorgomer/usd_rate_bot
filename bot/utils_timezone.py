import aiohttp
import logging

"""
Автоматическое определение часового пояса по названию города.

Используем:
1) Nominatim (OpenStreetMap) для геокодинга города → lat/lon
2) Open-Meteo Timezone API для получения смещения UTC
"""

logger = logging.getLogger(__name__)

import time

# In-memory TTL cache for city timezone data
CITY_CACHE_RAM = {}  # { city_lower: {"lat": float, "lon": float, "offset": int, "updated_at": int} }
CACHE_TTL = 86400  # 24 hours


async def geocode_city(query: str) -> tuple[float, float, str]:
    """
    Определяет координаты города по текстовому запросу.
    Сначала пробуем Nominatim (OSM),
    затем — fallback Open-Meteo Geocoding API.
    """
    logger.info("Geocoding city (primary: Nominatim): %s", query)

    # --- Primary: Nominatim ---
    url_osm = "https://nominatim.openstreetmap.org/search"
    params_osm = {
        "q": query,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url_osm,
                params=params_osm,
                timeout=10,
                headers={"User-Agent": "TelegramBot"}
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        if data:
            item = data[0]
            lat = float(item["lat"])
            lon = float(item["lon"])
            display_name = item.get("display_name", query)
            logger.info("City geocoded via Nominatim: %s → lat=%s lon=%s",
                        display_name, lat, lon)
            return lat, lon, display_name

    except Exception as e:
        logger.warning("Nominatim geocoding failed: %s", e)

    # --- Fallback: Open-Meteo Geocoding ---
    logger.info("Trying fallback geocoder (Open-Meteo) for: %s", query)

    url_om = "https://geocoding-api.open-meteo.com/v1/search"
    params_om = {"name": query, "count": 1, "language": "en"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_om, params=params_om, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()

        results = data.get("results")
        if results:
            item = results[0]
            lat = float(item["latitude"])
            lon = float(item["longitude"])
            display_name = f"{item.get('name')}, {item.get('country', '')}"
            logger.info("City geocoded via Open-Meteo: %s → lat=%s lon=%s",
                        display_name, lat, lon)
            return lat, lon, display_name

    except Exception as e:
        logger.error("Open-Meteo fallback geocoding failed: %s", e)

    raise ValueError("Город не найден — оба геокодера не вернули результат")


async def get_timezone_offset_minutes(lat: float, lon: float) -> int:
    """
    Определяет смещение UTC в минутах через Open-Meteo (новый API).
    """
    logger.info("Fetching timezone for lat=%s lon=%s", lat, lon)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "auto",
        "current": "temperature_2m"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()

        if "utc_offset_seconds" not in data:
            raise ValueError(f"No utc offset in response: {data}")

        offset_seconds = data["utc_offset_seconds"]
        offset_minutes = offset_seconds // 60

        logger.info("Timezone resolved: offset_minutes=%s", offset_minutes)
        return offset_minutes

    except Exception as e:
        logger.error("Timezone fetch failed: %s", e)
        raise


async def get_city_timezone(city: str, db):
    """
    Унифицированный метод:
    1) Проверяет RAM-кэш
    2) Проверяет SQLite-кэш
    3) Делает API-запросы (геокодер + timezone)
    4) Сохраняет результат в оба кэша
    """
    city_key = city.lower()
    now = time.time()

    # 1) RAM cache
    if city_key in CITY_CACHE_RAM:
        c = CITY_CACHE_RAM[city_key]
        if now - c["updated_at"] < CACHE_TTL:
            logger.info(f"[CACHE RAM] Hit for: {city}")
            return c["lat"], c["lon"], c["offset"]

    # 2) SQLite cache
    row = await db.get_cached_city(city_key)
    if row:
        lat, lon, offset, ts = row
        if now - ts < CACHE_TTL:
            logger.info(f"[CACHE SQLite] Hit for: {city}")

            CITY_CACHE_RAM[city_key] = {
                "lat": lat,
                "lon": lon,
                "offset": offset,
                "updated_at": ts,
            }
            return lat, lon, offset

    # 3) Full API lookup
    lat, lon, _ = await geocode_city(city)
    offset = await get_timezone_offset_minutes(lat, lon)

    # Save into caches
    CITY_CACHE_RAM[city_key] = {
        "lat": lat,
        "lon": lon,
        "offset": offset,
        "updated_at": int(now),
    }
    await db.cache_city(city_key, lat, lon, offset)

    logger.info(f"[CACHE WRITE] Stored cache for {city}")
    return lat, lon, offset