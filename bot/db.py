from __future__ import annotations

import aiosqlite
from typing import Optional, Dict, Any, List

import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path: str):
        self._path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        logger.info("DB connect requested")
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._path)
            logger.info(f"Connected to SQLite DB at {self._path}")
            await self._conn.execute("PRAGMA foreign_keys = ON")
            await self._conn.execute("PRAGMA journal_mode = WAL")
            await self._conn.execute("PRAGMA synchronous = NORMAL")
            await self._conn.commit()

    async def init_db(self):
        await self.connect()
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users_settings (
                user_id INTEGER PRIMARY KEY,
                timezone_utc_offset_minutes INTEGER,
                currency TEXT,
                local_hour INTEGER,
                local_minute INTEGER,
                utc_hour INTEGER,
                utc_minute INTEGER,
                notification_enabled INTEGER DEFAULT 0
            )
            """
        )
        await self._conn.commit()

    async def _ensure_user_row(self, user_id: int):
        logger.debug(f"Ensuring user row exists: user_id={user_id}")
        await self.connect()
        cursor = await self._conn.execute(
            "SELECT 1 FROM users_settings WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            await self._conn.execute(
                "INSERT INTO users_settings (user_id, notification_enabled) VALUES (?, 0)",
                (user_id,),
            )
            await self._conn.commit()

    async def set_timezone(self, user_id: int, offset_minutes: int):
        logger.info(f"Setting timezone for user_id={user_id} offset={offset_minutes}")
        await self._ensure_user_row(user_id)
        await self._conn.execute(
            "UPDATE users_settings SET timezone_utc_offset_minutes = ? WHERE user_id = ?",
            (offset_minutes, user_id),
        )
        await self._conn.commit()

    async def set_currency(self, user_id: int, currency: str):
        logger.info(f"Setting currency for user_id={user_id} currency={currency}")
        await self._ensure_user_row(user_id)
        await self._conn.execute(
            "UPDATE users_settings SET currency = ? WHERE user_id = ?",
            (currency, user_id),
        )
        await self._conn.commit()

    async def set_notification_time(
        self,
        user_id: int,
        local_hour: int,
        local_minute: int,
        utc_hour: int,
        utc_minute: int,
        enabled: bool = True,
    ):
        logger.info(
            f"Setting notification time for user_id={user_id} "
            f"local={local_hour}:{local_minute} utc={utc_hour}:{utc_minute}"
        )
        await self._ensure_user_row(user_id)
        await self._conn.execute(
            """
            UPDATE users_settings
            SET local_hour = ?, local_minute = ?, utc_hour = ?, utc_minute = ?, notification_enabled = ?
            WHERE user_id = ?
            """,
            (local_hour, local_minute, utc_hour, utc_minute, int(enabled), user_id),
        )
        await self._conn.commit()

    async def set_notifications_enabled(self, user_id: int, enabled: bool):
        logger.info(f"Setting notifications_enabled={enabled} for user_id={user_id}")
        await self._ensure_user_row(user_id)
        await self._conn.execute(
            "UPDATE users_settings SET notification_enabled = ? WHERE user_id = ?",
            (int(enabled), user_id),
        )
        await self._conn.commit()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        logger.debug(f"Fetching user_id={user_id}")
        await self.connect()
        cursor = await self._conn.execute(
            """
            SELECT user_id, timezone_utc_offset_minutes, currency,
                   local_hour, local_minute, utc_hour, utc_minute,
                   notification_enabled
            FROM users_settings
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()

        if row is None:
            return None

        (
            user_id,
            offset,
            currency,
            local_hour,
            local_minute,
            utc_hour,
            utc_minute,
            enabled,
        ) = row

        return {
            "user_id": user_id,
            "timezone_utc_offset_minutes": offset,
            "currency": currency,
            "local_hour": local_hour,
            "local_minute": local_minute,
            "utc_hour": utc_hour,
            "utc_minute": utc_minute,
            "notification_enabled": bool(enabled),
        }

    async def get_all_with_notifications(self) -> List[Dict[str, Any]]:
        logger.debug("Fetching all users with enabled notifications")
        await self.connect()
        cursor = await self._conn.execute(
            """
            SELECT user_id, timezone_utc_offset_minutes, currency,
                   local_hour, local_minute, utc_hour, utc_minute,
                   notification_enabled
            FROM users_settings
            WHERE notification_enabled = 1
              AND utc_hour IS NOT NULL
              AND utc_minute IS NOT NULL
              AND currency IS NOT NULL
            """
        )
        rows = await cursor.fetchall()
        await cursor.close()

        users = []
        for row in rows:
            (
                user_id,
                offset,
                currency,
                local_hour,
                local_minute,
                utc_hour,
                utc_minute,
                enabled,
            ) = row
            users.append(
                {
                    "user_id": user_id,
                    "timezone_utc_offset_minutes": offset,
                    "currency": currency,
                    "local_hour": local_hour,
                    "local_minute": local_minute,
                    "utc_hour": utc_hour,
                    "utc_minute": utc_minute,
                    "notification_enabled": bool(enabled),
                }
            )
        return users

    async def close(self):
        if self._conn is not None:
            await self._conn.close()
            self._conn = None