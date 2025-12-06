from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from aiogram.fsm.context import FSMContext

from bot.db import Database
from bot.states import SettingsStates
from bot.utils_timezone import TimezoneParseError, parse_timezone_offset_minutes
from bot.keyboards.currencies import get_currencies_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! 👋\n\n"
        "Я буду присылать курсы валют ЦБ РФ.\n"
        "Для начала укажи свой часовой пояс в формате, например:\n"
        "`UTC+3` или `GMT-5`.",
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_timezone)


@router.message(SettingsStates.waiting_timezone)
async def process_timezone(
    message: Message, state: FSMContext, db: Database
):
    try:
        offset_minutes = parse_timezone_offset_minutes(message.text)
    except TimezoneParseError:
        await message.answer(
            "Не получилось распознать часовой пояс 🤔\n"
            "Пример: `UTC+3`, `GMT-5`, `UTC+4:30`.",
            parse_mode="Markdown",
        )
        return

    await db.set_timezone(message.from_user.id, offset_minutes)

    await message.answer(
        "Часовой пояс сохранён ✅\n\n"
        "Теперь выбери валюту, по которой хочешь получать курс:",
        reply_markup=get_currencies_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_currency)