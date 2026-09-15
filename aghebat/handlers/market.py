"""دستور نرخ بازار: ارز، طلا و سکه با نمایش تومانی (منبع: bonbast.com)."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..services.market import MarketError, format_market, get_market

logger = logging.getLogger(__name__)

router = Router(name="market")

UNAVAILABLE_TEXT = (
    "😕 الان نتونستم نرخ‌ها رو بگیرم.\n"
    "منبع نرخ‌ها موقتاً در دسترس نیست؛ لطفاً چند دقیقه دیگه دوباره امتحان کن."
)


@router.message(Command("rates", "prices"))
async def cmd_rates(message: Message) -> None:
    """نرخ لحظه‌ای ارز، طلا و سکه را به تومان می‌فرستد (خصوصی و گروه)."""
    try:
        snapshot = await get_market()
    except MarketError:
        logger.warning("گرفتن نرخ‌های بازار ناموفق بود.", exc_info=True)
        await message.reply(UNAVAILABLE_TEXT)
        return
    await message.reply(format_market(snapshot))
