from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from carousell_alert_bot.bot.handlers import build_router, register_bot_commands
from carousell_alert_bot.config import Settings
from carousell_alert_bot.db.session import create_session_factory


async def async_main() -> None:
    settings = Settings()
    logging.basicConfig(level=logging.INFO)
    session_factory = create_session_factory(settings)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router(settings=settings, session_factory=session_factory))
    await register_bot_commands(bot)
    await dispatcher.start_polling(bot, polling_timeout=settings.bot_polling_timeout)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

