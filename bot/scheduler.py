from __future__ import annotations

import logging
from datetime import timezone
from typing import Dict, Any

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import Bot

from bot.db import Database

logger = logging.getLogger(__name__)

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"


async def fetch_cbr_rate(currency: str) -> tuple[float, str]:
    """
    Возвращает (курс, дата_YYYY-MM-DD) для указанной валюты.
    """
    logger.info("Fetching CBR rate for currency=%s", currency)
    async with aiohttp.ClientSession() as session:
        async with session.get(CBR_URL) as resp:
            logger.debug("CBR request sent, awaiting response...")
            resp.raise_for_status()
            data = await resp.json()
            logger.debug("CBR response received successfully")

    date_str_raw = data.get("Date")  # вида '2025-12-06T11:30:00+03:00'
    if date_str_raw and "T" in date_str_raw:
        date_str = date_str_raw.split("T", 1)[0]
    else:
        date_str = ""

    valute = data.get("Valute", {})
    info = valute.get(currency.upper())
    if not info:
        raise ValueError(f"Валюта {currency} не найдена в ответе ЦБР")

    value = float(info["Value"])
    nominal = int(info.get("Nominal", 1))
    rate = value / nominal if nominal else value

    return rate, date_str


async def send_daily_rate(bot: Bot, user_id: int, currency: str):
    logger.info("Sending daily rate to user_id=%s currency=%s", user_id, currency)
    try:
        rate, date_str = await fetch_cbr_rate(currency)
    except Exception:
        logger.exception("Failed to fetch CBR rate for user_id=%s", user_id)
        return

    text = f"{currency.upper()} → {rate:.2f} ₽\nДата: {date_str}"
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except Exception:
        logger.exception("Failed to send daily rate to user_id=%s currency=%s", user_id, currency)


class NotificationScheduler:
    def __init__(self, db: Database, bot: Bot):
        self.db = db
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)

    async def start(self):
        logger.info("Starting NotificationScheduler...")
        if not self.scheduler.running:
            self.scheduler.start()
        await self.reload_jobs()

    async def shutdown(self):
        logger.info("Shutting down NotificationScheduler...")
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def reload_jobs(self):
        logger.info("Reloading all scheduled jobs...")
        self.scheduler.remove_all_jobs()
        users = await self.db.get_all_with_notifications()
        logger.debug("Users with notifications enabled: %s", users)
        for user in users:
            self._add_job_for_user(user)

    async def reschedule_for_user(self, user_id: int):
        logger.info("Rescheduling job for user_id=%s", user_id)
        job_id = f"user_{user_id}"
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

        user = await self.db.get_user(user_id)
        if (
            not user
            or not user["notification_enabled"]
            or user["utc_hour"] is None
            or user["utc_minute"] is None
            or not user["currency"]
        ):
            return

        self._add_job_for_user(user)

    def _add_job_for_user(self, user: Dict[str, Any]):
        user_id = int(user["user_id"])
        utc_hour = int(user["utc_hour"])
        utc_minute = int(user["utc_minute"])
        currency = str(user["currency"]).upper()

        logger.debug(
            "Preparing to schedule job: user_id=%s utc_time=%02d:%02d currency=%s",
            user_id, utc_hour, utc_minute, currency
        )

        job_id = f"user_{user_id}"

        logger.info(
            "Scheduling job for user_id=%s at %02d:%02d UTC (%s)",
            user_id,
            utc_hour,
            utc_minute,
            currency,
        )

        self.scheduler.add_job(
            send_daily_rate,
            "cron",
            hour=utc_hour,
            minute=utc_minute,
            id=job_id,
            replace_existing=True,
            kwargs={"bot": self.bot, "user_id": user_id, "currency": currency},
        )