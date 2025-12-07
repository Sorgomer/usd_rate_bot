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