from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from aiogram.fsm.context import FSMContext

from bot.db import Database
from bot.states import SettingsStates
from bot.keyboards.currencies import (
    get_currencies_keyboard,
    CurrencyCallback,
)
from bot.keyboards.time_picker import (
    build_time_picker,
    TimePickerCallback,
    ALLOWED_MINUTES,
)
from bot.scheduler import NotificationScheduler

router = Router()


# ---------- /settings и /unsubscribe ----------


@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database):
    user = await db.get_user(message.from_user.id)
    tz = user["timezone_utc_offset_minutes"] if user else None
    currency = user["currency"] if user else None
    enabled = user["notification_enabled"] if user else False
    local_time = None
    if user and user["local_hour"] is not None and user["local_minute"] is not None:
        local_time = f"{user['local_hour']:02d}:{user['local_minute']:02d}"

    text_lines = ["⚙️ Настройки:"]
    text_lines.append(f"• Уведомления: {'включены ✅' if enabled else 'выключены ❌'}")
    if tz is not None:
        sign = "+" if tz >= 0 else "-"
        abs_min = abs(tz)
        h, m = divmod(abs_min, 60)
        tz_str = f"UTC{sign}{h}"
        if m:
            tz_str += f":{m:02d}"
        text_lines.append(f"• Часовой пояс: {tz_str}")
    if currency:
        text_lines.append(f"• Валюта: {currency}")
    if local_time:
        text_lines.append(f"• Время уведомлений (локальное): {local_time}")

    text_lines.append("\nКоманды:")
    text_lines.append("/start – пройти настройку заново")
    text_lines.append("/unsubscribe – выключить уведомления")
    text_lines.append("Чтобы изменить валюту – просто выбери её ещё раз.")

    await message.answer("\n".join(text_lines))


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(
    message: Message,
    db: Database,
    scheduler: NotificationScheduler,
):
    await db.set_notifications_enabled(message.from_user.id, False)
    await scheduler.reschedule_for_user(message.from_user.id)
    await message.answer("Ежедневная рассылка отключена. ❌")


# ---------- Выбор валюты ----------


@router.callback_query(CurrencyCallback.filter())
async def on_currency_chosen(
    callback: CallbackQuery,
    callback_data: CurrencyCallback,
    state: FSMContext,
    db: Database,
):
    user_id = callback.from_user.id
    await db.set_currency(user_id, callback_data.code)

    await callback.message.edit_text(
        f"Валюта **{callback_data.code}** сохранена ✅\n\n"
        "Теперь выбери время ежедневного уведомления:",
        parse_mode="Markdown",
        reply_markup=build_time_picker(12, 0),
    )
    await state.set_state(SettingsStates.waiting_time)
    await callback.answer()


# ---------- Колесо времени ----------


@router.callback_query(
    TimePickerCallback.filter(F.action.in_({"inc_h", "dec_h", "inc_m", "dec_m", "noop"}))
)
async def on_time_adjust(
    callback: CallbackQuery,
    callback_data: TimePickerCallback,
):
    hour = callback_data.hour
    minute = callback_data.minute

    if callback_data.action == "inc_h":
        hour = (hour + 1) % 24
    elif callback_data.action == "dec_h":
        hour = (hour - 1) % 24
    elif callback_data.action == "inc_m":
        idx = ALLOWED_MINUTES.index(minute)
        minute = ALLOWED_MINUTES[(idx + 1) % len(ALLOWED_MINUTES)]
    elif callback_data.action == "dec_m":
        idx = ALLOWED_MINUTES.index(minute)
        minute = ALLOWED_MINUTES[(idx - 1) % len(ALLOWED_MINUTES)]
    elif callback_data.action == "noop":
        await callback.answer()
        return

    await callback.message.edit_reply_markup(
        reply_markup=build_time_picker(hour, minute)
    )
    await callback.answer()


@router.callback_query(TimePickerCallback.filter(F.action == "confirm"))
async def on_time_confirm(
    callback: CallbackQuery,
    callback_data: TimePickerCallback,
    db: Database,
    scheduler: NotificationScheduler,
    state: FSMContext,
):
    user_id = callback.from_user.id
    hour = callback_data.hour
    minute = callback_data.minute

    user = await db.get_user(user_id)
    if not user or user["timezone_utc_offset_minutes"] is None:
        await callback.answer("Сначала укажи часовой пояс через /start", show_alert=True)
        return

    offset = user["timezone_utc_offset_minutes"]

    local_total = hour * 60 + minute
    utc_total = (local_total - offset) % (24 * 60)
    utc_hour, utc_minute = divmod(utc_total, 60)

    await db.set_notification_time(
        user_id=user_id,
        local_hour=hour,
        local_minute=minute,
        utc_hour=utc_hour,
        utc_minute=utc_minute,
        enabled=True,
    )

    await scheduler.reschedule_for_user(user_id)

    await state.clear()

    await callback.message.edit_text(
        f"Готово! ✅\n\n"
        f"Курсы будут приходить ежедневно в {hour:02d}:{minute:02d} "
        f"(ваше локальное время)."
    )
    await callback.answer("Время сохранено")