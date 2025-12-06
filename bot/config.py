import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    webhook_base_url: str   # https://your-service.onrender.com
    database_path: str = "bot.db"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "")
    base_url = os.getenv("WEBHOOK_BASE_URL", "")
    if not token:
        raise RuntimeError("BOT_TOKEN env var is required")
    if not base_url:
        raise RuntimeError("WEBHOOK_BASE_URL env var is required")

    return Config(
        bot_token=token,
        webhook_base_url=base_url.rstrip("/"),
        database_path=os.getenv("DATABASE_PATH", "bot.db"),
    )