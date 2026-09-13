"""ثبت فعالیت کاربران و امتیازدهی به ازای پیام در گروه."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from ..db import Database
from ..services.economy import reward_message
from ..utils import is_group


class ActivityMiddleware(BaseMiddleware):
    """هر پیام گروهی را شمارش می‌کند و امتیاز فعالیت می‌دهد."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if (
            isinstance(event, Message)
            and event.from_user
            and not event.from_user.is_bot
            and is_group(event.chat)
        ):
            db: Database = data["db"]
            await db.ensure_chat(event.chat.id, event.chat.title or "")
            await db.ensure_member(
                event.chat.id,
                event.from_user.id,
                event.from_user.full_name,
                event.from_user.username or "",
            )
            await reward_message(db, event.chat.id, event.from_user.id, int(time.time()))
        return await handler(event, data)
