"""بخش سرگرمی: شرط‌بندی، فال، هدیه و واکنش‌های فان."""
from __future__ import annotations

import random

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..db import Database
from ..services.ranks import sync_member_rank
from ..utils import is_group, mention, parse_int, safe, signed, target_user

router = Router(name="fun")

FORTUNES: list[str] = [
    "🔮 امروز یه خبر خوب در راهه، گوشیت رو شارژ نگه دار!",
    "🔮 یکی داره پشت سرت تعریفت رو می‌کنه.",
    "🔮 امروز روز خوبی برای سکوت کردنه... مخصوصاً توی این گروه.",
    "🔮 یه فرصت طلایی جلوی پاته، فقط چشمات رو باز کن.",
    "🔮 پول در راهه، ولی از جیب خودت می‌ره!",
    "🔮 امروز با هرکی بحث کنی می‌بازی. بی‌خیال شو.",
    "🔮 ستاره‌ها می‌گن امروز بخواب، فردا بجنگ.",
    "🔮 یه دوست قدیمی بهت پیام می‌ده.",
    "🔮 صبرت جواب می‌ده، فقط یه‌کم دیگه.",
    "🔮 امروز بهترین روز برای شروع کاریه که مدت‌ها عقب انداختی.",
]

DICE_EMOJI = "🎲"


@router.message(Command("fal", "fortune"))
@router.message(F.text.in_({"فال", "فالم"}))
async def cmd_fal(message: Message) -> None:
    """یک فال تصادفی می‌دهد."""
    user = message.from_user
    name = safe(user.full_name) if user else "دوست عزیز"
    await message.reply(f"<b>فال {name}</b>\n\n{random.choice(FORTUNES)}")


@router.message(Command("dice", "bet"))
@router.message(F.text.startswith("شرط"))
async def cmd_dice(
    message: Message, bot: Bot, db: Database, command: CommandObject | None = None
) -> None:
    """شرط‌بندی با تاس: برد دو برابر، باخت نصف."""
    if not is_group(message.chat):
        await message.answer("🎰 شرط‌بندی فقط داخل گروه!")
        return
    user = message.from_user
    if user is None:
        return

    raw = command.args if command and command.args else (message.text or "").replace("شرط", "", 1)
    stake = parse_int(raw or "")
    if stake is None or stake <= 0:
        await message.reply("فرمت درست:\n<code>/dice 20</code>\nیا: <code>شرط 20</code>")
        return

    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    member = await db.ensure_member(message.chat.id, user.id, user.full_name, user.username or "")
    balance = int(member["balance"])
    unit = chat["unit_name"]

    if balance < stake:
        await message.reply(
            f"💸 موجودیت کافی نیست!\nموجودی: <b>{balance:,}</b> {unit}"
        )
        return

    dice = await message.answer_dice(emoji=DICE_EMOJI)
    value = dice.dice.value if dice.dice else random.randint(1, 6)
    delta = stake if value >= 4 else -stake
    new_balance = await db.add_balance(message.chat.id, user.id, delta, reason="gift")
    _, new_rank = await sync_member_rank(
        bot, db, message.chat.id, user.id, new_balance, enforce=bool(chat["enforce_ranks"])
    )

    if delta > 0:
        text = (
            f"🎉 تاس <b>{value}</b> اومد! بردی {mention(user)}\n"
            f"<b>{signed(delta)}</b> {unit} | موجودی: <b>{new_balance:,}</b>"
        )
    else:
        text = (
            f"💀 تاس <b>{value}</b> اومد! باختی {mention(user)}\n"
            f"<b>{signed(delta)}</b> {unit} | موجودی: <b>{new_balance:,}</b>"
        )
    if new_rank is not None:
        text += f"\n🏅 رتبه جدید: <b>{new_rank.label}</b>"
    await message.reply(text)


@router.message(Command("gift"))
async def cmd_gift(
    message: Message, bot: Bot, db: Database, command: CommandObject
) -> None:
    """انتقال بخشی از موجودی به کاربر دیگر."""
    if not is_group(message.chat):
        return
    sender = message.from_user
    receiver = target_user(message)
    if sender is None:
        return
    if receiver is None or receiver.id == sender.id:
        await message.reply("↩️ روی پیام کسی که می‌خوای بهش هدیه بدی ریپلای کن.")
        return

    amount = parse_int(command.args or "")
    if amount is None or amount <= 0:
        await message.reply("فرمت درست:\n<code>/gift 50</code> (با ریپلای)")
        return

    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    sender_row = await db.ensure_member(
        message.chat.id, sender.id, sender.full_name, sender.username or ""
    )
    if int(sender_row["balance"]) < amount:
        await message.reply("💸 موجودیت کافی نیست!")
        return

    await db.ensure_member(
        message.chat.id, receiver.id, receiver.full_name, receiver.username or ""
    )
    sender_balance = await db.add_balance(message.chat.id, sender.id, -amount, reason="gift")
    receiver_balance = await db.add_balance(message.chat.id, receiver.id, amount, reason="gift")

    enforce = bool(chat["enforce_ranks"])
    await sync_member_rank(bot, db, message.chat.id, sender.id, sender_balance, enforce)
    _, new_rank = await sync_member_rank(
        bot, db, message.chat.id, receiver.id, receiver_balance, enforce
    )

    text = (
        f"🎁 {mention(sender)} مقدار <b>{amount:,}</b> {chat['unit_name']} "
        f"به {mention(receiver)} هدیه داد!\n\nچه آدم خوبی 🥹"
    )
    if new_rank is not None:
        text += f"\n🏅 رتبه جدید گیرنده: <b>{new_rank.label}</b>"
    await message.reply(text)
