from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup


class TimePickerCallback(CallbackData, prefix="tp"):
    action: str  # inc_h, dec_h, inc_m, dec_m, confirm, noop
    hour: int
    minute: int


ALLOWED_MINUTES = [0, 15, 30, 45]


def normalize_time(hour: int, minute: int) -> tuple[int, int]:
    hour = hour % 24
    if minute not in ALLOWED_MINUTES:
        # привести к ближайшему из 0/15/30/45
        closest = min(ALLOWED_MINUTES, key=lambda m: abs(m - minute))
        minute = closest
    return hour, minute


def build_time_picker(hour: int, minute: int) -> InlineKeyboardMarkup:
    hour, minute = normalize_time(hour, minute)

    b = InlineKeyboardBuilder()

    # Первая строка: стрелки ▲ ▲ (часы / минуты)
    b.button(
        text="▲",
        callback_data=TimePickerCallback(
            action="inc_h", hour=hour, minute=minute
        ).pack(),
    )
    b.button(
        text="▲",
        callback_data=TimePickerCallback(
            action="inc_m", hour=hour, minute=minute
        ).pack(),
    )

    # Вторая строка: текущее значение часов и минут (кнопки-«плейсхолдеры»)
    b.button(
        text=f"{hour:02d}",
        callback_data=TimePickerCallback(
            action="noop", hour=hour, minute=minute
        ).pack(),
    )
    b.button(
        text=f"{minute:02d}",
        callback_data=TimePickerCallback(
            action="noop", hour=hour, minute=minute
        ).pack(),
    )

    # Третья строка: стрелки ▼ ▼
    b.button(
        text="▼",
        callback_data=TimePickerCallback(
            action="dec_h", hour=hour, minute=minute
        ).pack(),
    )
    b.button(
        text="▼",
        callback_data=TimePickerCallback(
            action="dec_m", hour=hour, minute=minute
        ).pack(),
    )

    # Четвёртая строка: Подтвердить
    b.button(
        text="Подтвердить",
        callback_data=TimePickerCallback(
            action="confirm", hour=hour, minute=minute
        ).pack(),
    )

    b.adjust(2, 2, 2, 1)
    return b.as_markup()