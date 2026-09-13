"""رویدادهای گروهی: ورود بات، خوشامد عضو جدید، خروج."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import ChatMemberUpdated, Message

from ..db import Database
from ..utils import is_group, mention, render

router = Router(name="group")


@router.my_chat_member()
async def on_bot_membership(event: ChatMemberUpdated, db: Database) -> None:
    """وقتی بات به گروه اضافه یا از آن حذف می‌شود."""
    if not is_group(event.chat):
        return
    new_status = event.new_chat_member.status
    if new_status in {"member", "administrator", "restricted"}:
        await db.ensure_chat(event.chat.id, event.chat.title or "")
        await db.set_chat_field(event.chat.id, "enabled", 1)
        await event.bot.send_message(
            event.chat.id,
            "🌱 <b>عاقبت</b> به گروه اضافه شد!\n\n"
            "منو ادمین کن تا رتبه‌ها و دسترسی‌ها کار کنن.\n"
            "اعضا با /daily عاقبت روزانه می‌گیرن. راهنما: /help",
        )
        return
    if new_status in {"left", "kicked"}:
        chat = await db.get_chat(event.chat.id)
        if chat is not None:
            await db.set_chat_field(event.chat.id, "enabled", 0)


@router.message(F.new_chat_members)
async def on_new_members(message: Message, db: Database) -> None:
    """خوشامد به اعضای تازه‌وارد (به‌جز خود بات)."""
    if not is_group(message.chat) or not message.new_chat_members:
        return
    bot_id = (await message.bot.me()).id
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    for user in message.new_chat_members:
        if user.is_bot or user.id == bot_id:
            continue
        await db.ensure_member(message.chat.id, user.id, user.full_name, user.username or "")
        text = await render(
            db,
            message.chat.id,
            "welcome",
            name=user.full_name,
            mention=mention(user),
            amount=0,
            balance=0,
            unit=chat["unit_name"],
            emoji=chat["unit_emoji"],
            rank="",
            streak=0,
        )
        if text:
            await message.reply(text)


@router.message(F.left_chat_member)
async def on_left_member(message: Message) -> None:
    """خروج عضو را بی‌صدا رد می‌کند تا میدل‌ور امتیاز ندهد."""
    return
