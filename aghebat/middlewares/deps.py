"""تزریق وابستگی‌ها (دیتابیس و تنظیمات) به هندلرها."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..config import Config
from ..db import Database


class DepsMiddleware(BaseMiddleware):
    """db و config را در اختیار همه هندلرها می‌گذارد."""

    def __init__(self, db: Database, config: Config) -> None:
        self.db = db
        self.config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["config"] = self.config
        return await handler(event, data)
