"""همگام‌سازی منوی دستورهای بات (setMyCommands) برای هر دامنه چت.

سه لیست ساخته می‌شود: چت خصوصی (حداقلی)، همه گروه‌ها (لیست کامل عمومی؛
اجرای دستورهای مدیریتی برای غیرادمین‌ها با پیام محترمانه رد می‌شود) و چت
خصوصی هر مالک (همه دستورها).
"""
from __future__ import annotations

import logging
import re

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

from ..config import Config

logger = logging.getLogger(__name__)

COMMAND_PATTERN = re.compile(r"^[a-z0-9_]{1,32}$")

# دستورهای عمومی داخل گروه — لیست کامل منو؛ سدهای مالک/ادمین بات در خود
# دستورها اعمال می‌شوند، نه در منو.
PUBLIC_GROUP_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="شروع کار با بات 🌱"),
    BotCommand(command="daily", description="گرفتن عاقبت روزانه 🎲"),
    BotCommand(command="me", description="کارنامه و موجودی من 📊"),
    BotCommand(command="top", description="برترین‌های گروه 🏆"),
    BotCommand(command="active", description="فعال‌ترین اعضا 💬"),
    BotCommand(command="ranks", description="نردبان رتبه‌ها 🪜"),
    BotCommand(command="tasks", description="تسک‌های جایزه‌دار 🎯"),
    BotCommand(command="history", description="تاریخچه امتیازهای من 🧾"),
    BotCommand(command="dice", description="شرط‌بندی شانسی 🎰"),
    BotCommand(command="fal", description="فال روزانه 🔮"),
    BotCommand(command="gift", description="هدیه دادن امتیاز به دوستان 🎁"),
    BotCommand(command="ttt", description="بازی دوز ❌⭕️"),
    BotCommand(command="rates", description="نرخ ارز و طلا 💱"),
    BotCommand(command="help", description="راهنمای بات 📚"),
    BotCommand(command="settings", description="پنل تنظیمات گروه ⚙️"),
]

# دستورهای چت خصوصی؛ بات خصوصی فقط برای فعال‌سازی و راهنماست.
PRIVATE_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="شروع کار با بات 🌱"),
    BotCommand(command="rates", description="نرخ ارز و طلا 💱"),
    BotCommand(command="help", description="راهنمای بات 📚"),
]

# دستورهای ویژه مالک که به لیست عمومی اضافه می‌شوند.
_OWNER_EXTRA_COMMANDS: list[BotCommand] = [
    BotCommand(command="promote", description="ترفیع کاربر به ادمین بات 🏅"),
    BotCommand(command="demote", description="عزل ادمین بات 📉"),
    BotCommand(command="botadmins", description="لیست ادمین‌های بات 📋"),
    BotCommand(command="activate", description="فعال‌سازی کاربر 🔑"),
    BotCommand(command="deactivate", description="غیرفعال‌سازی کاربر ⛔️"),
    BotCommand(command="addad", description="افزودن تبلیغ جدید 📣"),
    BotCommand(command="ads", description="لیست همه تبلیغ‌ها 🗂"),
    BotCommand(command="delad", description="حذف یک تبلیغ 🗑"),
    BotCommand(command="adtoggle", description="فعال/غیرفعال کردن تبلیغ 🔄"),
    BotCommand(command="adinterval", description="فاصله ارسال خودکار تبلیغ ⏱"),
    BotCommand(command="adnow", description="ارسال فوری تبلیغ 🚀"),
    BotCommand(command="addtask", description="افزودن تسک جایزه‌دار ➕"),
    BotCommand(command="tasklist", description="لیست همه تسک‌ها 🗂"),
    BotCommand(command="deltask", description="حذف یک تسک 🗑"),
    BotCommand(command="toggletask", description="فعال/غیرفعال کردن تسک 🔄"),
    BotCommand(command="stats", description="آمار کلی بات 📊"),
    BotCommand(command="broadcast", description="پیام همگانی به گروه‌ها 📢"),
    BotCommand(command="export", description="خروجی تنظیمات گروه 📤"),
    BotCommand(command="import", description="بارگذاری تنظیمات 📥"),
]

# چت خصوصی مالک: همه دستورها (عمومی + ویژه مالک).
OWNER_COMMANDS: list[BotCommand] = PUBLIC_GROUP_COMMANDS + _OWNER_EXTRA_COMMANDS


async def sync_bot_commands(bot: Bot, config: Config) -> None:
    """منوی دستورها را برای چت خصوصی، گروه‌ها و چت هر مالک ثبت می‌کند.

    هر فراخوانی جداگانه در try/except است؛ خطا فقط هشدار لاگ می‌شود و
    هیچ‌وقت بالا پرتاب نمی‌شود تا اجرای بات مختل نشود.
    """
    plans: list[tuple[object, list[BotCommand]]] = [
        (BotCommandScopeAllPrivateChats(), PRIVATE_COMMANDS),
        (BotCommandScopeAllGroupChats(), PUBLIC_GROUP_COMMANDS),
    ]
    plans.extend(
        (BotCommandScopeChat(chat_id=owner_id), OWNER_COMMANDS) for owner_id in config.owners
    )
    for scope, commands in plans:
        try:
            await bot.set_my_commands(commands, scope=scope)
        except Exception:  # noqa: BLE001 - منوی ناقص نباید بات را از کار بیندازد
            logger.warning(
                "ثبت منوی دستورها برای دامنه %s ناموفق بود.", scope.type, exc_info=True
            )
