"""پروفایل کاربر، لیدربورد و نمایش رتبه‌ها."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from ..db import Database
from ..services.ranks import load_ranks, next_rank, resolve_rank
from ..texts import progress_bar
from ..utils import is_group, mention_raw, safe, signed, target_user

router = Router(name="profile")

MEDALS = ["🥇", "🥈", "🥉"]


@router.message(Command("me", "profile"))
@router.message(F.text.in_({"پروفایل", "کارنامه"}))
async def cmd_profile(message: Message, db: Database) -> None:
    """کارنامه کامل کاربر را نمایش می‌دهد."""
    if not is_group(message.chat):
        await message.answer("📊 کارنامه فقط داخل گروه معنی داره!")
        return
    user = target_user(message) or message.from_user
    if user is None:
        return

    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    member = await db.ensure_member(message.chat.id, user.id, user.full_name, user.username or "")
    balance = int(member["balance"])
    unit = chat["unit_name"]

    ranks = await load_ranks(db, message.chat.id)
    current = resolve_rank(ranks, balance)
    upcoming = next_rank(ranks, balance)
    position = await db.rank_of(message.chat.id, user.id)
    total = await db.member_count(message.chat.id)

    lines = [
        f"{chat['unit_emoji']} <b>کارنامه {safe(user.full_name)}</b>",
        "",
        f"💰 موجودی: <b>{balance:,}</b> {unit}",
        f"🏅 رتبه: <b>{current.label if current else 'ندارد'}</b>",
        f"📈 جایگاه: <b>{position}</b> از {total}",
        f"⭐️ امتیاز فعالیت: <b>{int(member['points']):,}</b>",
        f"💬 تعداد پیام: <b>{int(member['messages']):,}</b>",
        f"🔥 استریک: <b>{int(member['streak'])}</b> روز (رکورد: {int(member['best_streak'])})",
    ]

    if upcoming is not None:
        span = upcoming.min_balance - (current.min_balance if current else 0)
        done = balance - (current.min_balance if current else 0)
        bar = progress_bar(done, span if span > 0 else 1)
        remain = upcoming.min_balance - balance
        lines += [
            "",
            f"🎯 رتبه بعدی: <b>{upcoming.label}</b>",
            f"{bar}  (<b>{remain:,}</b> {unit} مانده)",
        ]
    else:
        lines += ["", "👑 به بالاترین رتبه رسیدی! افسانه‌ای شدی."]

    if current is not None:
        perms = current.allowed_labels()
        if perms:
            lines += ["", "🔓 <b>دسترسی‌ها:</b> " + "، ".join(perms)]

    await message.reply("\n".join(lines))


@router.message(Command("top", "leaderboard"))
@router.message(F.text.in_({"لیدربورد", "برترین‌ها", "تاپ"}))
async def cmd_top(message: Message, db: Database) -> None:
    """ده نفر برتر گروه بر اساس موجودی عاقبت."""
    if not is_group(message.chat):
        return
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    rows = await db.leaderboard(message.chat.id, "balance", 10)
    if not rows:
        await message.reply("😴 هنوز هیچ‌کس عاقبتی نساخته! اولین نفر باش: /daily")
        return

    ranks = await load_ranks(db, message.chat.id)
    lines = [f"🏆 <b>جدول عاقبت {safe(chat['title'])}</b>", ""]
    for index, row in enumerate(rows):
        badge = MEDALS[index] if index < len(MEDALS) else f"<b>{index + 1}.</b>"
        rank = resolve_rank(ranks, int(row["balance"]))
        emoji = rank.emoji if rank else "▫️"
        name = mention_raw(int(row["user_id"]), row["full_name"])
        lines.append(f"{badge} {emoji} {name} — <b>{int(row['balance']):,}</b> {chat['unit_name']}")

    await message.reply("\n".join(lines))


@router.message(Command("topchat", "active"))
@router.message(F.text == "فعال‌ترین‌ها")
async def cmd_top_active(message: Message, db: Database) -> None:
    """فعال‌ترین اعضا بر اساس تعداد پیام."""
    if not is_group(message.chat):
        return
    await db.ensure_chat(message.chat.id, message.chat.title or "")
    rows = await db.leaderboard(message.chat.id, "messages", 10)
    if not rows:
        await message.reply("😴 هنوز آماری ثبت نشده!")
        return
    lines = ["💬 <b>فعال‌ترین اعضای گروه</b>", ""]
    for index, row in enumerate(rows):
        badge = MEDALS[index] if index < len(MEDALS) else f"<b>{index + 1}.</b>"
        name = mention_raw(int(row["user_id"]), row["full_name"])
        lines.append(f"{badge} {name} — <b>{int(row['messages']):,}</b> پیام")
    await message.reply("\n".join(lines))


@router.message(Command("ranks"))
@router.message(F.text.in_({"رتبه‌ها", "رتبه ها"}))
async def cmd_ranks(message: Message, db: Database) -> None:
    """لیست رتبه‌ها و دسترسی‌های هر کدام."""
    if not is_group(message.chat):
        return
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    ranks = await load_ranks(db, message.chat.id)
    lines = [f"🪜 <b>نردبان رتبه‌های {safe(chat['title'])}</b>", ""]
    for rank in ranks:
        threshold = "از ابتدا" if rank.min_balance <= -(10**8) else f"{rank.min_balance:,}+"
        lines.append(f"{rank.emoji} <b>{safe(rank.title)}</b> — {threshold} {chat['unit_name']}")
        perms = rank.allowed_labels()
        lines.append("   └ " + ("، ".join(perms) if perms else "بدون دسترسی"))
    lines += ["", "برای بالا رفتن هر روز /daily بزن و توی گروه فعال باش! 🚀"]
    await message.reply("\n".join(lines))


@router.message(Command("history"))
async def cmd_history(message: Message, db: Database) -> None:
    """آخرین تغییرات موجودی کاربر."""
    if not is_group(message.chat):
        return
    user = target_user(message) or message.from_user
    if user is None:
        return
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    rows = await db.history(message.chat.id, user.id, 10)
    if not rows:
        await message.reply("📭 هنوز تراکنشی ثبت نشده!")
        return
    reasons = {
        "daily": "عاقبت روزانه",
        "task": "تسک",
        "admin": "دستور ادمین",
        "gift": "هدیه",
    }
    lines = [f"🧾 <b>آخرین تغییرات {safe(user.full_name)}</b>", ""]
    for row in rows:
        label = reasons.get(row["reason"], row["reason"] or "نامشخص")
        lines.append(f"• {signed(int(row['amount']))} {chat['unit_name']} — {safe(label)}")
    await message.reply("\n".join(lines))
