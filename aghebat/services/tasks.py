"""بررسی و تایید تسک‌های تبلیغاتی (عضویت اجباری در کانال‌ها)."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

JOINED_STATUSES = {"member", "administrator", "creator", "owner"}


def normalize_target(target: str) -> str | int:
    """شناسه کانال را به فرمت قابل قبول تلگرام تبدیل می‌کند."""
    value = target.strip()
    if value.startswith("https://t.me/"):
        value = value.rsplit("/", 1)[-1]
    if value.lstrip("-").isdigit():
        return int(value)
    if not value.startswith("@"):
        value = "@" + value
    return value


def task_url(target: str, url: str = "") -> str:
    """لینک قابل کلیک برای تسک می‌سازد."""
    if url:
        return url
    value = target.strip().lstrip("@")
    if value.lstrip("-").isdigit():
        return ""
    return f"https://t.me/{value}"


async def is_member(bot: Bot, target: str, user_id: int) -> bool:
    """بررسی می‌کند کاربر عضو کانال هدف هست یا نه."""
    try:
        member = await bot.get_chat_member(chat_id=normalize_target(target), user_id=user_id)
    except TelegramAPIError as exc:
        logger.warning("بررسی عضویت ناموفق (target=%s user=%s): %s", target, user_id, exc)
        return False
    return member.status in JOINED_STATUSES
