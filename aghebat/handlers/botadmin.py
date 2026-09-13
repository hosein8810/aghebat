"""دستورات مالک: مدیریت ادمین‌های بات در گروه و فعال‌سازی کاربران."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database
from ..utils import is_group, mention, mention_raw, parse_int, target_user

router = Router(name="botadmin")


def _is_owner(message: Message, config: Config) -> bool:
    """آیا فرستنده مالک بات است؟ (در غیر این صورت دستور بی‌صدا نادیده گرفته می‌شود.)"""
    return message.from_user is not None and config.is_owner(message.from_user.id)


@router.message(Command("promote"))
async def cmd_promote(message: Message, db: Database, config: Config) -> None:
    """ترفیع کاربر ریپلای‌شده به ادمین بات در همین گروه (فقط مالک)."""
    if not _is_owner(message, config):
        return
    if not is_group(message.chat):
        await message.reply("👥 این دستور فقط داخل گروه کار می‌کنه.")
        return
    user = target_user(message)
    if user is None:
        await message.reply("↩️ روی پیام کاربر ریپلای کن و بزن:\n<code>/promote</code>")
        return
    if user.is_bot:
        await message.reply("🤖 بات‌ها نمی‌تونن ادمین بات بشن!")
        return
    if config.is_owner(user.id):
        await message.reply("😌 خود مالک که نیازی به ترفیع نداره!")
        return
    promoter = message.from_user
    await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.add_bot_admin(
        message.chat.id,
        user.id,
        user.full_name,
        user.username or "",
        promoted_by=promoter.id if promoter else 0,
    )
    await message.reply(
        f"🏅 {mention(user)} حالا <b>ادمین بات</b> این گروهه!\n"
        "دستورات مدیریتی مثل /settings براش باز شد."
    )


@router.message(Command("demote"))
async def cmd_demote(message: Message, db: Database, config: Config) -> None:
    """عزل ادمین بات گروه (فقط مالک)."""
    if not _is_owner(message, config):
        return
    if not is_group(message.chat):
        await message.reply("👥 این دستور فقط داخل گروه کار می‌کنه.")
        return
    user = target_user(message)
    if user is None:
        await message.reply("↩️ روی پیام کاربر ریپلای کن و بزن:\n<code>/demote</code>")
        return
    if not await db.is_bot_admin(message.chat.id, user.id):
        await message.reply(f"🤷 {mention(user)} اصلا ادمین بات این گروه نبود!")
        return
    await db.remove_bot_admin(message.chat.id, user.id)
    await message.reply(f"📉 {mention(user)} از ادمین باتی این گروه عزل شد.")


@router.message(Command("botadmins"))
async def cmd_botadmins(message: Message, db: Database, config: Config) -> None:
    """لیست ادمین‌های بات گروه (برای مالک و ادمین‌های بات)."""
    if not is_group(message.chat):
        await message.reply("👥 این دستور فقط داخل گروه کار می‌کنه.")
        return
    user = message.from_user
    if user is None:
        return
    if not (config.is_owner(user.id) or await db.is_bot_admin(message.chat.id, user.id)):
        await message.reply("🚫 این لیست فقط برای مالک و ادمین‌های بات گروهه.")
        return
    rows = await db.bot_admins(message.chat.id)
    if not rows:
        await message.reply(
            "📭 هنوز هیچ ادمین باتی در این گروه ثبت نشده.\n"
            "مالک می‌تونه با ریپلای روی پیام کاربر و دستور <code>/promote</code> اولین نفر رو ترفیع بده."
        )
        return
    lines = [f"🏅 <b>ادمین‌های بات این گروه ({len(rows)} نفر):</b>", ""]
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {mention_raw(int(row['user_id']), row['full_name'])}")
    await message.reply("\n".join(lines))


def _numeric_target(message: Message, command: CommandObject) -> int | None:
    """آیدی عددی هدف را از آرگومان دستور می‌خواند (اگر ریپلای نباشد)."""
    parts = (command.args or "").split()
    if not parts:
        return None
    return parse_int(parts[0])


@router.message(Command("activate"))
async def cmd_activate(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """فعال‌سازی کاربر با ریپلای یا آیدی عددی (فقط مالک، در هر چتی)."""
    if not _is_owner(message, config):
        return
    actor = message.from_user
    user = target_user(message)
    if user is not None:
        if user.is_bot:
            await message.reply("🤖 بات‌ها نیازی به فعال‌سازی ندارن!")
            return
        await db.activate_user(
            user.id, user.full_name, user.username or "", activated_by=actor.id if actor else 0
        )
        await message.reply(f"✅ {mention(user)} فعال شد!\nحالا می‌تونه با بات کار کنه 🎉")
        return
    user_id = _numeric_target(message, command)
    if user_id is None:
        await message.reply(
            "↩️ روی پیام کاربر ریپلای کن یا آیدی عددی بده:\n<code>/activate 123456789</code>"
        )
        return
    await db.activate_user(user_id, activated_by=actor.id if actor else 0)
    await message.reply(f"✅ کاربر <code>{user_id}</code> فعال شد!\nحالا می‌تونه با بات کار کنه 🎉")


@router.message(Command("deactivate"))
async def cmd_deactivate(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """غیرفعال‌سازی کاربر با ریپلای یا آیدی عددی (فقط مالک، در هر چتی)."""
    if not _is_owner(message, config):
        return
    user = target_user(message)
    if user is not None:
        if not await db.is_activated(user.id):
            await message.reply(f"🤷 {mention(user)} اصلا فعال نبود!")
            return
        await db.deactivate_user(user.id)
        await message.reply(f"⛔️ دسترسی {mention(user)} غیرفعال شد.")
        return
    user_id = _numeric_target(message, command)
    if user_id is None:
        await message.reply(
            "↩️ روی پیام کاربر ریپلای کن یا آیدی عددی بده:\n<code>/deactivate 123456789</code>"
        )
        return
    if not await db.is_activated(user_id):
        await message.reply(f"🤷 کاربر <code>{user_id}</code> اصلا فعال نبود!")
        return
    await db.deactivate_user(user_id)
    await message.reply(f"⛔️ دسترسی کاربر <code>{user_id}</code> غیرفعال شد.")
