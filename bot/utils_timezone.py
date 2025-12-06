import re


class TimezoneParseError(ValueError):
    pass


TZ_REGEX = re.compile(
    r"^(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::(\d{1,2}))?$",
    re.IGNORECASE,
)


def parse_timezone_offset_minutes(text: str) -> int:
    """
    Парсит строки вида: UTC+3, UTC-5, GMT+4:30 и т.п.
    Возвращает смещение в минутах относительно UTC.
    """
    text = (text or "").strip()
    m = TZ_REGEX.match(text)
    if not m:
        raise TimezoneParseError("Неверный формат часового пояса")

    sign, hours_str, minutes_str = m.groups()
    hours = int(hours_str)
    minutes = int(minutes_str) if minutes_str is not None else 0

    if hours > 14:
        raise TimezoneParseError("Слишком большое смещение по часам (макс. 14)")
    if minutes < 0 or minutes >= 60:
        raise TimezoneParseError("Минуты должны быть от 0 до 59")

    total = hours * 60 + minutes
    if sign == "-":
        total = -total
    return total