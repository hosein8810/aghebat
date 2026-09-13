"""دستور دریافت عاقبت روزانه."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import Config
from ..db import Database
from ..services.economy import claim_daily
from ..services.ranks import sync_member_rank
from ..texts import get_flavor
from ..utils import is_group, mention, render, signed

router = Router(name="daily")


@router.message(Command("daily", "aghebat"))
@router.message(F.text.in_({"عاقبت", "عاقبتم", "شانس"}))
async def cmd_daily(message: Message, bot: Bot, db: Database, config: Config) -> None:
    """عاقبت روزانه کاربر را قرعه‌کشی و اعلام می‌کند."""
    if not is_group(message.chat):
        await message.answer("🌱 این دستور فقط داخل گروه کار می‌کنه!")
        return
    user = message.from_user
    if user is None:
        return

    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.ensure_member(message.chat.id, user.id, user.full_name, user.username or "")
    unit = chat["unit_name"]
    emoji = chat["unit_emoji"]

    result = await claim_daily(db, message.chat.id, user.id)
    if not result.claimed:
        text = await render(
            db,
            message.chat.id,
            "already_claimed",
            name=user.full_name,
            mention=mention(user),
            balance=f"{result.balance:,}",
            unit=unit,
            emoji=emoji,
        )
        await message.reply(text)
        return

    previous, new_rank = await sync_member_rank(
        bot, db, message.chat.id, user.id, result.balance, enforce=bool(chat["enforce_ranks"])
    )
    rank_label = (new_rank or previous).label if (new_rank or previous) else "بدون رتبه"

    if result.total > 0:
        key = "daily_gain"
    elif result.total < 0:
        key = "daily_loss"
    else:
        key = "daily_zero"

    text = await render(
        db,
        message.chat.id,
        key,
        name=user.full_name,
        mention=mention(user),
        amount=signed(result.total),
        balance=f"{result.balance:,}",
        unit=unit,
        emoji=emoji,
        rank=rank_label,
        streak=result.streak,
    )
    lines = [text, "", f"<i>{get_flavor(result.total)}</i>"]
    if result.bonus:
        lines.append(f"🎁 پاداش استریک: <b>{signed(result.bonus)}</b> {unit}")
    await message.reply("\n".join(lines))

    if new_rank is not None:
        key = "rank_up" if (previous is None or new_rank.min_balance > previous.min_balance) else "rank_down"
        announce = await render(
            db,
            message.chat.id,
            key,
            name=user.full_name,
            mention=mention(user),
            rank=new_rank.label,
            balance=f"{result.balance:,}",
            unit=unit,
            emoji=emoji,
            streak=result.streak,
        )
        perms = new_rank.allowed_labels()
        if perms:
            announce += "\n\n🔓 دسترسی‌ها: " + "، ".join(perms)
        await message.answer(announce)
