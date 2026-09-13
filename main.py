"""نقطه ورود بات تلگرام عاقبت."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from aghebat.config import Config
from aghebat.db import Database
from aghebat.handlers import build_router
from aghebat.middlewares.activity import ActivityMiddleware
from aghebat.middlewares.deps import DepsMiddleware

logger = logging.getLogger(__name__)


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    config = Config.from_env()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(DepsMiddleware(db, config))
    dp.message.middleware(ActivityMiddleware())
    dp.include_router(build_router())

    me = await bot.get_me()
    logger.info("بات %s (@%s) آماده است.", config.bot_name, me.username)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("بات متوقف شد.")


if __name__ == "__main__":
    main()
