"""دستورات ادمین گروه: تنظیمات، متن‌ها، رتبه‌ها و مدیریت موجودی."""
from __future__ import annotations

import json

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database
from ..services.ranks import PERM_FIELDS, PERM_LABELS, load_ranks, sync_member_rank
from ..texts import DEFAULT_TEXTS
from ..utils import is_chat_admin, is_group, mention, parse_int, safe, signed, target_user

router = Router(name="admin")

PERM_ALIASES: dict[str, str] = {
    "متن": "can_send_messages",
    "عکس": "can_send_photos",
    "ویدیو": "can_send_videos",
    "فایل": "can_send_documents",
    "آهنگ": "can_send_audios",
    "ویس": "can_send_voice_notes",
    "ویدیومسیج": "can_send_video_notes",
    "استیکر": "can_send_other_messages",
    "گیف": "can_send_other_messages",
    "نظرسنجی": "can_send_polls",
    "لینک": "can_add_web_page_previews",
    "دعوت": "can_invite_users",
    "پین": "can_pin_messages",
}


async def _guard(message: Message, bot: Bot, config: Config) -> bool:
    """اجازه اجرای دستور ادمینی را بررسی می‌کند."""
    if not is_group(message.chat):
        await message.reply("⚙️ این دستور فقط داخل گروه کار می‌کنه.")
        return False
    user = message.from_user
    if user is None:
        return False
    if config.is_owner(user.id) or await is_chat_admin(bot, message.chat.id, user.id):
        return True
    await message.reply("🚫 فقط ادمین‌های گروه می‌تونن این دستور رو اجرا کنن!")
    return False


@router.message(Command("settings", "panel"))
async def cmd_settings(message: Message, bot: Bot, db: Database, config: Config) -> None:
    """نمایش تنظیمات فعلی گروه."""
    if not await _guard(message, bot, config):
        return
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    ranks = await load_ranks(db, message.chat.id)
    members = await db.member_count(message.chat.id)
    lines = [
        f"⚙️ <b>تنظیمات عاقبت — {safe(chat['title'])}</b>",
        "",
        f"وضعیت: {'✅ فعال' if chat['enabled'] else '⛔️ خاموش'}",
        f"واحد: {chat['unit_emoji']} <b>{safe(chat['unit_name'])}</b>",
        f"بازه روزانه: <b>{int(chat['daily_min'])}</b> تا <b>{int(chat['daily_max'])}</b>",
        f"امتیاز هر پیام: <b>{int(chat['msg_points'])}</b> (کول‌داون {int(chat['msg_cooldown'])} ثانیه)",
        f"اعمال دسترسی‌ها: {'✅' if chat['enforce_ranks'] else '❌'}",
        f"حالت فان: {'✅' if chat['fun_mode'] else '❌'}",
        f"تعداد رتبه‌ها: <b>{len(ranks)}</b> | اعضای ثبت‌شده: <b>{members}</b>",
        "",
        "<b>دستورات:</b>",
        "<code>/setrange -5 20</code> — بازه عدد روزانه",
        "<code>/setunit سکه 🪙</code> — نام و ایموجی واحد",
        "<code>/setmsgpoints 1 30</code> — امتیاز پیام و کول‌داون",
        "<code>/toggle enforce</code> — روشن/خاموش کردن اعمال دسترسی",
        "<code>/toggle fun</code> — روشن/خاموش کردن حالت فان",
        "<code>/toggle bot</code> — فعال/غیرفعال کردن بات در گروه",
        "<code>/addrank</code> , <code>/delrank</code> , <code>/resetranks</code>",
        "<code>/settext</code> , <code>/texts</code> — شخصی‌سازی متن‌ها",
        "<code>/give</code> , <code>/take</code> , <code>/setbalance</code>",
        "<code>/syncall</code> — هماهنگ‌سازی دسترسی همه اعضا",
    ]
    await message.reply("\n".join(lines))


@router.message(Command("setrange"))
async def cmd_setrange(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """تنظیم بازه عدد تصادفی روزانه (می‌تواند منفی باشد)."""
    if not await _guard(message, bot, config):
        return
    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.reply("فرمت درست:\n<code>/setrange -5 20</code>")
        return
    low, high = parse_int(parts[0]), parse_int(parts[1])
    if low is None or high is None:
        await message.reply("❌ اعداد معتبر نیستند!")
        return
    if low > high:
        low, high = high, low
    await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.set_chat_field(message.chat.id, "daily_min", low)
    await db.set_chat_field(message.chat.id, "daily_max", high)
    await message.reply(f"✅ بازه روزانه روی <b>{low}</b> تا <b>{high}</b> تنظیم شد.")


@router.message(Command("setunit"))
async def cmd_setunit(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """تنظیم نام و ایموجی واحد امتیاز."""
    if not await _guard(message, bot, config):
        return
    parts = (command.args or "").split()
    if not parts:
        await message.reply("فرمت درست:\n<code>/setunit سکه 🪙</code>")
        return
    name = parts[0]
    emoji = parts[1] if len(parts) > 1 else "🌱"
    await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.set_chat_field(message.chat.id, "unit_name", name)
    await db.set_chat_field(message.chat.id, "unit_emoji", emoji)
    await message.reply(f"✅ واحد گروه حالا <b>{safe(name)}</b> {emoji} است.")


@router.message(Command("setmsgpoints"))
async def cmd_setmsgpoints(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """تنظیم امتیاز هر پیام و فاصله زمانی آن."""
    if not await _guard(message, bot, config):
        return
    parts = (command.args or "").split()
    if not parts:
        await message.reply("فرمت درست:\n<code>/setmsgpoints 1 30</code>")
        return
    points = parse_int(parts[0])
    cooldown = parse_int(parts[1]) if len(parts) > 1 else 30
    if points is None or cooldown is None or points < 0 or cooldown < 0:
        await message.reply("❌ مقادیر باید عدد مثبت باشند!")
        return
    await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.set_chat_field(message.chat.id, "msg_points", points)
    await db.set_chat_field(message.chat.id, "msg_cooldown", cooldown)
    await message.reply(
        f"✅ هر پیام <b>{points}</b> امتیاز (هر <b>{cooldown}</b> ثانیه یک‌بار)."
    )


@router.message(Command("toggle"))
async def cmd_toggle(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """روشن/خاموش کردن قابلیت‌های گروه."""
    if not await _guard(message, bot, config):
        return
    key = (command.args or "").strip().lower()
    mapping = {"enforce": "enforce_ranks", "fun": "fun_mode", "bot": "enabled"}
    if key not in mapping:
        await message.reply("گزینه‌ها: <code>enforce</code> | <code>fun</code> | <code>bot</code>")
        return
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    field = mapping[key]
    new_value = 0 if chat[field] else 1
    await db.set_chat_field(message.chat.id, field, new_value)
    await message.reply(f"✅ <code>{key}</code> {'روشن شد ✅' if new_value else 'خاموش شد ⛔️'}")


@router.message(Command("addrank"))
async def cmd_addrank(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """افزودن رتبه جدید با حداقل موجودی و دسترسی‌ها."""
    if not await _guard(message, bot, config):
        return
    parts = (command.args or "").split()
    if len(parts) < 3:
        await message.reply(
            "فرمت درست:\n<code>/addrank عنوان ایموجی حداقل_موجودی دسترسی‌ها</code>\n"
            "مثال:\n<code>/addrank شوالیه 🛡 250 متن عکس استیکر</code>\n\n"
            "دسترسی‌های مجاز: " + "، ".join(PERM_ALIASES)
        )
        return
    title, emoji = parts[0], parts[1]
    minimum = parse_int(parts[2])
    if minimum is None:
        await message.reply("❌ حداقل موجودی باید عدد باشد!")
        return
    perms = {"can_send_messages": True}
    for token in parts[3:]:
        field = PERM_ALIASES.get(token)
        if field:
            perms[field] = True
    await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.add_rank(message.chat.id, title, emoji, minimum, perms)
    labels = "، ".join(PERM_LABELS[f] for f in PERM_FIELDS if perms.get(f))
    await message.reply(
        f"✅ رتبه {emoji} <b>{safe(title)}</b> از <b>{minimum:,}</b> به بالا اضافه شد.\n🔓 {labels}"
    )


@router.message(Command("delrank"))
async def cmd_delrank(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """حذف یک رتبه با شناسه."""
    if not await _guard(message, bot, config):
        return
    rank_id = parse_int(command.args or "")
    if rank_id is None:
        ranks = await load_ranks(db, message.chat.id)
        listing = "\n".join(f"<code>{r.id}</code> — {r.label}" for r in ranks)
        await message.reply(f"شناسه رتبه را بده:\n<code>/delrank 3</code>\n\n{listing}")
        return
    await db.delete_rank(message.chat.id, rank_id)
    await message.reply("🗑 رتبه حذف شد.")


@router.message(Command("resetranks"))
async def cmd_resetranks(message: Message, bot: Bot, db: Database, config: Config) -> None:
    """بازگرداندن رتبه‌ها به حالت پیش‌فرض."""
    if not await _guard(message, bot, config):
        return
    await db.reset_ranks(message.chat.id)
    await message.reply("♻️ رتبه‌ها به حالت پیش‌فرض برگشتند.")


@router.message(Command("texts"))
async def cmd_texts(message: Message, bot: Bot, db: Database, config: Config) -> None:
    """کلیدهای متنی قابل تنظیم."""
    if not await _guard(message, bot, config):
        return
    custom = await db.all_texts(message.chat.id)
    lines = ["📝 <b>متن‌های قابل تنظیم</b>", ""]
    for key in DEFAULT_TEXTS:
        mark = "✏️" if key in custom else "▫️"
        lines.append(f"{mark} <code>{key}</code>")
    lines += [
        "",
        "تغییر متن:\n<code>/settext daily_gain متن جدید شما</code>",
        "بازگردانی:\n<code>/deltext daily_gain</code>",
        "",
        "متغیرها: <code>{mention}</code> <code>{name}</code> <code>{amount}</code> "
        "<code>{balance}</code> <code>{unit}</code> <code>{emoji}</code> "
        "<code>{rank}</code> <code>{streak}</code>",
    ]
    await message.reply("\n".join(lines))


@router.message(Command("settext"))
async def cmd_settext(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """تنظیم متن سفارشی برای یک کلید."""
    if not await _guard(message, bot, config):
        return
    args = (command.args or "").split(maxsplit=1)
    if len(args) < 2:
        await message.reply("فرمت درست:\n<code>/settext daily_gain متن جدید</code>")
        return
    key, value = args[0], args[1]
    if key not in DEFAULT_TEXTS:
        await message.reply(f"❌ کلید نامعتبر! لیست کلیدها: /texts")
        return
    await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.set_text(message.chat.id, key, value)
    await message.reply(f"✅ متن <code>{key}</code> ذخیره شد.")


@router.message(Command("deltext"))
async def cmd_deltext(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """بازگرداندن یک متن به حالت پیش‌فرض."""
    if not await _guard(message, bot, config):
        return
    key = (command.args or "").strip()
    if key not in DEFAULT_TEXTS:
        await message.reply("❌ کلید نامعتبر! لیست کلیدها: /texts")
        return
    await db.clear_text(message.chat.id, key)
    await message.reply(f"♻️ متن <code>{key}</code> به پیش‌فرض برگشت.")


async def _adjust(
    message: Message, bot: Bot, db: Database, config: Config, raw_amount: str, sign: int
) -> None:
    """کم/زیاد کردن موجودی کاربر هدف."""
    if not await _guard(message, bot, config):
        return
    user = target_user(message)
    if user is None:
        await message.reply("↩️ روی پیام کاربر ریپلای کن.")
        return
    amount = parse_int(raw_amount)
    if amount is None:
        await message.reply("❌ مقدار باید عدد باشد!")
        return
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.ensure_member(message.chat.id, user.id, user.full_name, user.username or "")
    balance = await db.add_balance(message.chat.id, user.id, sign * amount, reason="admin")
    previous, new_rank = await sync_member_rank(
        bot, db, message.chat.id, user.id, balance, enforce=bool(chat["enforce_ranks"])
    )
    text = (
        f"✅ <b>{signed(sign * amount)}</b> {chat['unit_name']} برای {mention(user)}\n"
        f"موجودی جدید: <b>{balance:,}</b> {chat['unit_name']}"
    )
    if new_rank is not None:
        text += f"\n🏅 رتبه جدید: <b>{new_rank.label}</b>"
    await message.reply(text)


@router.message(Command("give"))
async def cmd_give(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """اضافه کردن موجودی به کاربر."""
    await _adjust(message, bot, db, config, command.args or "", 1)


@router.message(Command("take"))
async def cmd_take(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """کم کردن موجودی کاربر."""
    await _adjust(message, bot, db, config, command.args or "", -1)


@router.message(Command("setbalance"))
async def cmd_setbalance(
    message: Message, bot: Bot, db: Database, config: Config, command: CommandObject
) -> None:
    """تنظیم مستقیم موجودی کاربر."""
    if not await _guard(message, bot, config):
        return
    user = target_user(message)
    amount = parse_int(command.args or "")
    if user is None or amount is None:
        await message.reply("↩️ روی پیام کاربر ریپلای کن:\n<code>/setbalance 100</code>")
        return
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    await db.ensure_member(message.chat.id, user.id, user.full_name, user.username or "")
    await db.set_member_field(message.chat.id, user.id, "balance", amount)
    _, new_rank = await sync_member_rank(
        bot, db, message.chat.id, user.id, amount, enforce=bool(chat["enforce_ranks"])
    )
    text = f"✅ موجودی {mention(user)} روی <b>{amount:,}</b> {chat['unit_name']} تنظیم شد."
    if new_rank is not None:
        text += f"\n🏅 رتبه: <b>{new_rank.label}</b>"
    await message.reply(text)


@router.message(Command("syncall"))
async def cmd_syncall(message: Message, bot: Bot, db: Database, config: Config) -> None:
    """هماهنگ‌سازی دسترسی همه اعضای ثبت‌شده با رتبه فعلی‌شان."""
    if not await _guard(message, bot, config):
        return
    chat = await db.ensure_chat(message.chat.id, message.chat.title or "")
    rows = await db.leaderboard(message.chat.id, "balance", 500)
    done = 0
    for row in rows:
        _, changed = await sync_member_rank(
            bot,
            db,
            message.chat.id,
            int(row["user_id"]),
            int(row["balance"]),
            enforce=bool(chat["enforce_ranks"]),
        )
        if changed is not None:
            done += 1
    await message.reply(f"🔄 هماهنگ‌سازی انجام شد. رتبه <b>{done}</b> نفر به‌روز شد.")
