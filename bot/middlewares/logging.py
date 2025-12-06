import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        user_id = getattr(from_user, "id", None)
        logger.info("Incoming update. user_id=%s, type=%s", user_id, type(event).__name__)
        try:
            result = await handler(event, data)
            return result
        except Exception:
            logger.exception("Error while handling update for user_id=%s", user_id)
            raise