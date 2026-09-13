"""سد فعال‌سازی: چت خصوصی فقط برای مالک و کاربران فعال‌شده باز است."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

from ..config import Config
from ..db import Database
from ..texts import render_start_promo
from ..utils import owner_contact_url


class AccessMiddleware(BaseMiddleware):
    """پیام‌های خصوصی کاربران فعال‌نشده (به‌جز /start) را با پیام تبلیغاتی می‌بندد.

    پیام‌های گروهی و کوئری‌های شیشه‌ای بدون بررسی رد می‌شوند؛ برای هر پیام خصوصی
    حداکثر یک کوئری به دیتابیس می‌زنیم.
    """

    def __init__(self, db: Database, config: Config) -> None:
        self.db = db
        self.config = config
        self._startgroup_url: str | None = None

    async def _promo_markup(self, bot: Bot) -> InlineKeyboardMarkup:
        """کیبورد پیام تبلیغاتی؛ لینک افزودن به گروه فقط یک‌بار گرفته می‌شود."""
        if self._startgroup_url is None:
            me = await bot.me()
            self._startgroup_url = f"https://t.me/{me.username}?startgroup=true"
        rows: list[list[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text="➕ افزودن به گروه", url=self._startgroup_url)]
        ]
        if self.config.owner_contact:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📞 تماس با مالک",
                        url=owner_contact_url(self.config.owner_contact),
                    )
                ]
            )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.chat.type == "private":
            user = event.from_user
            if (
                user is not None
                and not user.is_bot
                and not (event.text or "").startswith("/start")
                and not self.config.is_owner(user.id)
                and not await self.db.is_activated(user.id)
            ):
                await event.answer(
                    render_start_promo(self.config.owner_contact),
                    reply_markup=await self._promo_markup(event.bot),
                )
                return  # انتشار متوقف می‌شود؛ هیچ هندلری اجرا نمی‌شود.
        return await handler(event, data)
