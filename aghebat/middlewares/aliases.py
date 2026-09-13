"""میدل‌ور ترجمه: عبارت‌های فارسی را به دستور اسلش‌دار معادل تبدیل می‌کند."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from ..aliases import resolve_alias, rewrite_message


class AliasMiddleware(BaseMiddleware):
    """پیام‌های متنی فارسی (مثل «تنظیم ادمین») را به دستور معادل ترجمه می‌کند.

    فقط روی پیام‌های متنی کاربران انسانی که با اسلش شروع نمی‌شوند کار
    می‌کند؛ در صورت یافتن معادل، پیام با کپی بازنویسی‌شده (متن دستور + یک
    موجودیت bot_command) به هندلرها پاس داده می‌شود. در غیر این صورت پیام
    دست‌نخورده می‌رود. این میدل‌ور فقط نحوه تایپ را عوض می‌کند و هیچ
    گاردی (مالک/ادمین بات) را کم یا زیاد نمی‌کند.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        user = event.from_user
        if user is None or user.is_bot or not event.text or event.text.startswith("/"):
            return await handler(event, data)
        resolved = resolve_alias(event.text)
        if resolved is None:
            return await handler(event, data)
        command, args = resolved
        return await handler(rewrite_message(event, command, args), data)
