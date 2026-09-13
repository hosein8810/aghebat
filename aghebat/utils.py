"""توابع کمکی مشترک بات عاقبت."""
from __future__ import annotations

import html

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Chat, Message, User

from .db import Database
from .texts import DEFAULT_TEXTS

ADMIN_STATUSES = {"administrator", "creator", "owner"}


def mention(user: User) -> str:
    """منشن HTML امن برای کاربر."""
    return f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'


def mention_raw(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{html.escape(name or str(user_id))}</a>'


def safe(text: str | None) -> str:
    return html.escape(text or "")


def is_group(chat: Chat) -> bool:
    return chat.type in {"group", "supergroup"}


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """آیا کاربر در گروه ادمین است؟"""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramAPIError:
        return False
    return member.status in ADMIN_STATUSES


async def render(
    db: Database,
    chat_id: int,
    key: str,
    **kwargs: object,
) -> str:
    """متن قالب را از دیتابیس (یا پیش‌فرض) گرفته و مقادیر را جایگزین می‌کند."""
    template = await db.get_text(chat_id, key) or DEFAULT_TEXTS.get(key, "")
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def parse_int(value: str, default: int | None = None) -> int | None:
    """تبدیل امن رشته به عدد صحیح (با پشتیبانی از ارقام فارسی)."""
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = value.strip().translate(table)
    try:
        return int(cleaned)
    except ValueError:
        return default


def target_user(message: Message) -> User | None:
    """کاربر هدف دستور را از ریپلای برمی‌گرداند."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None


def format_number(value: int) -> str:
    """عدد را با جداکننده هزارگان و علامت مناسب نمایش می‌دهد."""
    return f"{value:,}"


def signed(value: int) -> str:
    return f"+{value:,}" if value > 0 else f"{value:,}"


def owner_contact_url(contact: str) -> str:
    """مقدار OWNER_CONTACT را به لینک قابل کلیک t.me تبدیل می‌کند."""
    value = contact.strip()
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("t.me/"):
        return f"https://{value}"
    return f"https://t.me/{value.lstrip('@')}"
