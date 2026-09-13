"""دستورات مالک بات: مدیریت تسک‌های تبلیغاتی و آمار کلی."""
from __future__ import annotations

import asyncio

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database
from ..utils import parse_int, safe

router = Router(name="owner")


def _is_owner(message: Message, config: Config) -> bool:
    return message.from_user is not None and config.is_owner(message.from_user.id)


@router.message(Command("addtask"))
async def cmd_addtask(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """افزودن تسک تبلیغاتی (عضویت اجباری در کانال)."""
    if not _is_owner(message, config):
        return
    parts = (command.args or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.reply(
            "فرمت درست:\n<code>/addtask @channel 50 عنوان تسک</code>\n\n"
            "نکته: بات باید در کانال ادمین باشد تا بتواند عضویت را بررسی کند."
        )
        return
    target, raw_reward, title = parts
    reward = parse_int(raw_reward)
    if reward is None:
        await message.reply("❌ مقدار جایزه باید عدد باشد!")
        return
    scope = message.chat.id if message.chat.type in {"group", "supergroup"} else 0
    task_id = await db.add_task(title=title, target=target, reward=reward, chat_id=scope)
    scope_label = "این گروه" if scope else "همه گروه‌ها"
    await message.reply(
        f"✅ تسک <b>#{task_id}</b> ساخته شد.\n"
        f"🎯 هدف: <code>{safe(target)}</code>\n"
        f"🎁 جایزه: <b>{reward:,}</b>\n"
        f"📍 دامنه: {scope_label}"
    )


@router.message(Command("tasklist"))
async def cmd_tasklist(message: Message, db: Database, config: Config) -> None:
    """لیست همه تسک‌ها برای مالک."""
    if not _is_owner(message, config):
        return
    rows = await db.tasks(message.chat.id, only_active=False)
    if not rows:
        await message.reply("📭 هیچ تسکی ثبت نشده.")
        return
    lines = ["🗂 <b>همه تسک‌ها</b>", ""]
    for row in rows:
        state = "✅" if row["active"] else "⛔️"
        scope = "همه گروه‌ها" if not int(row["chat_id"]) else str(row["chat_id"])
        lines.append(
            f"{state} <b>#{row['id']}</b> {safe(row['title'])}\n"
            f"   └ {safe(row['target'])} | 🎁 {int(row['reward']):,} | 📍 {scope}"
        )
    lines += ["", "<code>/deltask 3</code> حذف | <code>/toggletask 3</code> فعال/غیرفعال"]
    await message.reply("\n".join(lines))


@router.message(Command("deltask"))
async def cmd_deltask(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """حذف یک تسک."""
    if not _is_owner(message, config):
        return
    task_id = parse_int(command.args or "")
    if task_id is None:
        await message.reply("فرمت درست:\n<code>/deltask 3</code>")
        return
    await db.delete_task(task_id)
    await message.reply(f"🗑 تسک #{task_id} حذف شد.")


@router.message(Command("toggletask"))
async def cmd_toggletask(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """فعال یا غیرفعال کردن تسک."""
    if not _is_owner(message, config):
        return
    task_id = parse_int(command.args or "")
    if task_id is None:
        await message.reply("فرمت درست:\n<code>/toggletask 3</code>")
        return
    task = await db.get_task(task_id)
    if task is None:
        await message.reply("❌ چنین تسکی وجود ندارد.")
        return
    new_state = not bool(task["active"])
    await db.set_task_active(task_id, new_state)
    await message.reply(f"تسک #{task_id} {'فعال شد ✅' if new_state else 'غیرفعال شد ⛔️'}")


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, config: Config) -> None:
    """آمار کلی بات."""
    if not _is_owner(message, config):
        return
    stats = await db.global_stats()
    await message.reply(
        "📊 <b>آمار کلی عاقبت</b>\n\n"
        f"👥 گروه‌ها: <b>{stats['chats']:,}</b>\n"
        f"🙋 اعضای ثبت‌شده: <b>{stats['members']:,}</b>\n"
        f"💬 مجموع پیام‌ها: <b>{stats['messages']:,}</b>\n"
        f"🎯 تسک‌های فعال: <b>{stats['tasks']:,}</b>"
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """ارسال پیام همگانی به همه گروه‌های فعال."""
    if not _is_owner(message, config):
        return
    text = command.args
    if not text:
        await message.reply("فرمت درست:\n<code>/broadcast متن پیام</code>")
        return
    chats = await db.all_chats()
    sent = failed = 0
    for chat in chats:
        try:
            await bot.send_message(int(chat["chat_id"]), text)
            sent += 1
        except Exception:  # noqa: BLE001 - گروه‌های حذف‌شده را رد می‌کنیم
            failed += 1
        await asyncio.sleep(0.05)
    await message.reply(f"📣 ارسال شد: <b>{sent}</b> | ناموفق: <b>{failed}</b>")
