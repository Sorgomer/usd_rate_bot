from __future__ import annotations

import logging
from datetime import timezone, datetime, date, timedelta
from typing import Dict, Any
import asyncio

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from bot.db import Database

logger = logging.getLogger(__name__)

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"


async def fetch_cbr_rate(currency: str, db: Database) -> dict:
    """
    Получить курс валюты из ЦБ РФ с агрессивным фоллбеком.

    Пытаемся получить курс из JSON сервиса за сегодня.
    Если неудачно, пытаемся получить из архива JSON за вчера.
    Если неудачно, пытаемся получить из XML за сегодня.
    Если неудачно, пытаемся получить из архива XML за вчера.
    Возвращаем словарь с ключами: rate, date, stale (bool), change_arrow (str).
    """
    import xml.etree.ElementTree as ET

    json_url_today = "https://www.cbr-xml-daily.ru/daily_json.js"
    xml_url_today = "https://www.cbr.ru/scripts/XML_daily.asp"

    # Helper to parse date string from XML format DD.MM.YYYY to YYYY-MM-DD
    def parse_xml_date(xml_date: str) -> str:
        try:
            d, m, y = xml_date.split(".")
            return f"{y}-{m}-{d}"
        except Exception:
            return xml_date

    async def _get_json_today() -> dict | None:
        backoff = 1
        for _ in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(json_url_today, timeout=10) as resp:
                        resp.raise_for_status()
                        data = await resp.json()
                return data
            except Exception as e:
                logger.warning("Failed JSON today attempt (backoff=%ss): %s", backoff, e)
                await asyncio.sleep(backoff)
                backoff *= 2
        return None

    async def _get_json_archive(date_obj: date) -> dict | None:
        date_str = date_obj.strftime("%Y/%m/%d")
        url = f"https://www.cbr-xml-daily.ru/archive/{date_str}/daily_json.js"
        backoff = 1
        for _ in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as resp:
                        resp.raise_for_status()
                        data = await resp.json()
                return data
            except Exception as e:
                logger.warning("Failed JSON archive %s (backoff=%ss): %s", date_str, backoff, e)
                await asyncio.sleep(backoff)
                backoff *= 2
        return None

    async def _get_xml_today() -> tuple[str | None, ET.Element | None]:
        backoff = 1
        for _ in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(xml_url_today, timeout=10) as resp:
                        resp.raise_for_status()
                        xml_text = await resp.text()
                root = ET.fromstring(xml_text)
                xml_date = root.attrib.get("Date", None)
                return xml_date, root
            except Exception as e:
                logger.warning("Failed XML today (backoff=%ss): %s", backoff, e)
                await asyncio.sleep(backoff)
                backoff *= 2
        return None, None

    async def _get_xml_archive(date_obj: date) -> tuple[str | None, ET.Element | None]:
        date_str = date_obj.strftime("%d/%m/%Y")
        url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={date_str}"
        backoff = 1
        for _ in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as resp:
                        resp.raise_for_status()
                        xml_text = await resp.text()
                root = ET.fromstring(xml_text)
                xml_date = root.attrib.get("Date", None)
                return xml_date, root
            except Exception as e:
                logger.warning("Failed XML archive %s (backoff=%ss): %s", date_str, backoff, e)
                await asyncio.sleep(backoff)
                backoff *= 2
        return None, None

    def _calculate_arrow(current_rate: float, previous_rate: float) -> str:
        if current_rate > previous_rate:
            return "↑"
        elif current_rate < previous_rate:
            return "↓"
        else:
            return "→"

    # 1) JSON today
    data = await _get_json_today()
    if data:
        valute = data.get("Valute", {})
        info = valute.get(currency.upper())
        if info:
            value = float(info["Value"])
            nominal = float(info.get("Nominal", 1))
            rate = value / nominal if nominal else value
            raw_date = data.get("Date", "")
            date_str = raw_date.split("T")[0] if "T" in raw_date else raw_date
            stale = False

            previous_rate = await db.get_previous_rate(currency.upper())
            if previous_rate is None:
                change_arrow = "→"
            else:
                change_arrow = _calculate_arrow(rate, previous_rate)

            await db.save_rate(currency.upper(), rate, date_str)

            return {
                "rate": rate,
                "date": date_str,
                "stale": stale,
                "change_arrow": change_arrow,
            }

    # 2) JSON archive (вчера)
    yesterday = date.today() - timedelta(days=1)
    data = await _get_json_archive(yesterday)
    if data:
        valute = data.get("Valute", {})
        info = valute.get(currency.upper())
        if info:
            value = float(info["Value"])
            nominal = float(info.get("Nominal", 1))
            rate = value / nominal if nominal else value
            raw_date = data.get("Date", "")
            date_str = raw_date.split("T")[0] if "T" in raw_date else raw_date
            stale = True

            previous_rate = await db.get_previous_rate(currency.upper())
            if previous_rate is None:
                change_arrow = "→"
            else:
                change_arrow = _calculate_arrow(rate, previous_rate)

            await db.save_rate(currency.upper(), rate, date_str)

            return {
                "rate": rate,
                "date": date_str,
                "stale": stale,
                "change_arrow": change_arrow,
            }

    # 3) XML today
    xml_date, root = await _get_xml_today()
    if root is not None:
        date_str = parse_xml_date(xml_date) if xml_date else ""
        for val in root.findall("Valute"):
            code = val.findtext("CharCode")
            if code == currency.upper():
                nominal = float((val.findtext("Nominal") or "1").replace(",", "."))
                value = float((val.findtext("Value") or "0").replace(",", "."))
                rate = value / nominal if nominal else value
                stale = False

                previous_rate = await db.get_previous_rate(currency.upper())
                if previous_rate is None:
                    change_arrow = "→"
                else:
                    change_arrow = _calculate_arrow(rate, previous_rate)

                await db.save_rate(currency.upper(), rate, date_str)

                return {
                    "rate": rate,
                    "date": date_str,
                    "stale": stale,
                    "change_arrow": change_arrow,
                }

    # 4) XML archive (вчера)
    xml_date, root = await _get_xml_archive(yesterday)
    if root is not None:
        date_str = parse_xml_date(xml_date) if xml_date else ""
        for val in root.findall("Valute"):
            code = val.findtext("CharCode")
            if code == currency.upper():
                nominal = float((val.findtext("Nominal") or "1").replace(",", "."))
                value = float((val.findtext("Value") or "0").replace(",", "."))
                rate = value / nominal if nominal else value
                stale = True

                previous_rate = await db.get_previous_rate(currency.upper())
                if previous_rate is None:
                    change_arrow = "→"
                else:
                    change_arrow = _calculate_arrow(rate, previous_rate)

                await db.save_rate(currency.upper(), rate, date_str)

                return {
                    "rate": rate,
                    "date": date_str,
                    "stale": stale,
                    "change_arrow": change_arrow,
                }

    # If all attempts failed, raise exception
    raise RuntimeError(
        f"Failed to fetch CBR rate for currency {currency} with all fallbacks."
    )


async def send_daily_rate(bot: Bot, user_id: int, currency: str, db: Database):
    logger.info("Sending daily rate to user_id=%s currency=%s", user_id, currency)
    try:
        result = await fetch_cbr_rate(currency, db)
    except Exception:
        logger.exception("Failed to fetch CBR rate for user_id=%s", user_id)
        return

    rate = result["rate"]
    date_str = result["date"]
    stale = result["stale"]
    arrow = result["change_arrow"]

    stale_text = " (данные могут быть устаревшими)" if stale else ""
    text = (
        f"{currency.upper()} → {rate:.2f} ₽ {arrow}\n"
        f"Дата: {date_str}{stale_text}"
    )

    try:
        await bot.send_message(chat_id=user_id, text=text)
    except Exception:
        logger.exception(
            "Failed to send daily rate to user_id=%s currency=%s",
            user_id,
            currency,
        )


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
            user_id,
            utc_hour,
            utc_minute,
            currency,
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
            kwargs={
                "bot": self.bot,
                "db": self.db,
                "user_id": user_id,
                "currency": currency,
            },
        )