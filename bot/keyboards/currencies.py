from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup


STANDARD_CURRENCIES = ["USD", "EUR", "CNY", "KZT", "TRY"]


class CurrencyCallback(CallbackData, prefix="cur"):
    code: str


def get_currencies_keyboard(
    currencies: list[str] | None = None,
) -> InlineKeyboardMarkup:
    if currencies is None:
        currencies = STANDARD_CURRENCIES

    builder = InlineKeyboardBuilder()
    for code in currencies:
        builder.button(
            text=code,
            callback_data=CurrencyCallback(code=code).pack(),
        )
    builder.adjust(3, 3)  # раскладка сеткой
    return builder.as_markup()