import asyncio
import logging
import os

from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application,
)

from bot.config import load_config
from bot.db import Database
from bot.scheduler import NotificationScheduler
from bot.middlewares import LoggingMiddleware
from bot.handlers import start as start_handlers
from bot.handlers import settings as settings_handlers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, dispatcher: Dispatcher):
    """
    Вызывается aiogram при старте (через setup_application).
    """
    config = dispatcher["config"]
    db: Database = dispatcher["db"]
    scheduler: NotificationScheduler = dispatcher["scheduler"]

    await db.init_db()
    await scheduler.start()

    webhook_url = f"{config.webhook_base_url}/webhook"
    await bot.set_webhook(webhook_url)

    logger.info("Webhook set to %s", webhook_url)


async def on_shutdown(bot: Bot, dispatcher: Dispatcher):
    scheduler: NotificationScheduler = dispatcher["scheduler"]
    db: Database = dispatcher["db"]

    await scheduler.shutdown()
    await db.close()
    logger.info("Shutdown complete")


def create_app() -> web.Application:
    config = load_config()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # --- Global error handler (logs ALL exceptions) ---
    @dp.errors()
    async def global_error_handler(event):
        logging.error(
            "Unhandled error in update:\n"
            f"Update: {event.update}\n"
            f"Exception: {event.exception}",
            exc_info=True,
        )

    dp["config"] = config

    db = Database(config.database_path)
    scheduler = NotificationScheduler(db=db, bot=bot)

    dp["db"] = db
    dp["scheduler"] = scheduler

    # Роутеры
    dp.include_router(start_handlers.router)
    dp.include_router(settings_handlers.router)

    # Middleware логирования
    dp.update.middleware(LoggingMiddleware())

    # Хуки старта/остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()

    async def health(request):
        return web.Response(text="OK")
    
    app.router.add_get("/", health)

    # Надёжный webhook эндпоинт без токена (Render reverse proxy-safe)
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path="/webhook")

    # Настроить жизненный цикл приложения (startup/shutdown)
    setup_application(app, dp, bot=bot)

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", "8080"))
    web.run_app(app, host="0.0.0.0", port=port)