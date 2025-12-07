from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message

import logging
logger = logging.getLogger(__name__)

from aiogram.fsm.context import FSMContext

from bot.db import Database
from bot.states import SettingsStates
from bot.utils_timezone import geocode_city, get_timezone_offset_minutes
from bot.keyboards.currencies import get_currencies_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    logger.info("User %s started /start", message.from_user.id)
    await state.clear()
    await message.answer(
        "Привет! 👋\n\n"
        "Я буду присылать курсы валют ЦБ РФ.\n"
        "Для начала введи свой город или город и страну.\n"
        "Например: `Москва`, `Berlin`, `New York`.",
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_city)


@router.message(SettingsStates.waiting_city)
async def process_timezone(
    message: Message, state: FSMContext, db: Database
):
    logger.info("User %s sent city input: %s", message.from_user.id, message.text)

    # Геокодирование города
    try:
        lat, lon, display_name = await geocode_city(message.text)
    except Exception as e:
        logger.warning("Failed to geocode city for user_id=%s input='%s' error=%s",
                       message.from_user.id, message.text, e)
        await message.answer(
            "Не получилось найти такой город 🤔\n"
            "Попробуй написать иначе. Например: `Москва`, `Berlin`, `New York`.",
            parse_mode="Markdown",
        )
        return

    # Получение смещения UTC
    try:
        offset_minutes = await get_timezone_offset_minutes(lat, lon)
    except Exception as e:
        logger.warning("Failed to fetch timezone for user_id=%s lat=%s lon=%s error=%s",
                       message.from_user.id, lat, lon, e)
        await message.answer(
            "Не удалось определить часовой пояс для этого города 😕\n"
            "Попробуй указать другой крупный город рядом.",
        )
        return

    logger.info(
        "City resolved for user_id=%s: %s (lat=%s lon=%s) offset_minutes=%s",
        message.from_user.id, display_name, lat, lon, offset_minutes
    )

    await db.set_timezone(message.from_user.id, offset_minutes)

    await message.answer(
        f"Город определён: *{display_name}* 🌍\n"
        f"Часовой пояс: UTC{offset_minutes/60:+.0f} сохранён ✅\n\n"
        "Теперь выбери валюту, по которой хочешь получать курс:",
        parse_mode="Markdown",
        reply_markup=get_currencies_keyboard(),
    )

    await state.set_state(SettingsStates.waiting_currency)