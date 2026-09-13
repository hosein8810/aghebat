"""دستورات مالک برای مدیریت و ارسال تبلیغ‌ها (همه فقط مالک)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database
from ..services.ads import INTERVAL_SETTING, send_ad_now
from ..utils import parse_int, safe

router = Router(name="ads")

MAX_TEXT_LEN = 4000
MAX_CAPTION_LEN = 1000
MIN_INTERVAL = 5


def _is_owner(message: Message, config: Config) -> bool:
    """آیا فرستنده مالک بات است؟ (در غیر این صورت بی‌صدا نادیده گرفته می‌شود.)"""
    return message.from_user is not None and config.is_owner(message.from_user.id)


def _photo_ad_text(caption: str) -> str:
    """متن تبلیغ را از کپشن عکس (مثل «/addad@mybot متن») جدا می‌کند."""
    rest = caption[len("/addad"):].strip()
    if rest.startswith("@"):
        parts = rest.split(maxsplit=1)
        rest = parts[1].strip() if len(parts) > 1 else ""
    return rest


@router.message(F.photo & F.caption.startswith("/addad"))
async def cmd_addad_photo(message: Message, db: Database, config: Config) -> None:
    """افزودن تبلیغ عکسی؛ متن تبلیغ کپشن عکس است."""
    if not _is_owner(message, config):
        return
    text = _photo_ad_text(message.caption or "")
    if not text:
        await message.reply(
            "فرمت درست:\n<code>/addad متن تبلیغ</code> (به‌صورت کپشن روی عکس)"
        )
        return
    if len(text) > MAX_CAPTION_LEN:
        await message.reply(
            f"❌ متن تبلیغ عکسی نباید از <b>{MAX_CAPTION_LEN}</b> کاراکتر بیشتر باشه."
        )
        return
    photo = message.photo[-1] if message.photo else None
    if photo is None:
        return
    ad_id = await db.add_ad(text=text, media_file_id=photo.file_id, media_type="photo")
    await message.reply(f"✅ تبلیغ عکسی <b>#{ad_id}</b> ثبت شد.")


@router.message(Command("addad"))
async def cmd_addad(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """افزودن تبلیغ متنی."""
    if not _is_owner(message, config):
        return
    text = (command.args or "").strip()
    if not text:
        await message.reply(
            "فرمت درست:\n<code>/addad متن تبلیغ</code>\n"
            "برای تبلیغ عکسی، عکس رو با کپشن <code>/addad متن</code> بفرست."
        )
        return
    if len(text) > MAX_TEXT_LEN:
        await message.reply(f"❌ متن تبلیغ نباید از <b>{MAX_TEXT_LEN}</b> کاراکتر بیشتر باشه.")
        return
    ad_id = await db.add_ad(text=text)
    await message.reply(f"✅ تبلیغ <b>#{ad_id}</b> ثبت شد.")


@router.message(Command("ads"))
async def cmd_ads(message: Message, db: Database, config: Config) -> None:
    """لیست همه تبلیغ‌ها."""
    if not _is_owner(message, config):
        return
    rows = await db.ads()
    if not rows:
        await message.reply("📭 هیچ تبلیغی ثبت نشده. با /addad بساز.")
        return
    interval = await db.get_setting(INTERVAL_SETTING)
    lines = [
        "📣 <b>همه تبلیغ‌ها</b>",
        f"⏱ فاصله ارسال خودکار: <b>{int(interval) if interval and interval.isdigit() else 180}</b> دقیقه",
        "",
    ]
    for row in rows:
        state = "✅" if row["active"] else "⛔️"
        media = "🖼 عکس" if row["media_type"] == "photo" else "📝 متن"
        full_text = row["text"] or ""
        excerpt = full_text[:40] + ("…" if len(full_text) > 40 else "")
        lines.append(
            f"{state} <b>#{row['id']}</b> {media} | ارسال: <b>{int(row['sent_count']):,}</b>\n"
            f"   └ {safe(excerpt)}"
        )
    lines += [
        "",
        "<code>/delad 1</code> حذف | <code>/adtoggle 1</code> فعال/غیرفعال\n"
        "<code>/adnow</code> ارسال فوری | <code>/adinterval 180</code> تغییر بازه",
    ]
    await message.reply("\n".join(lines))


async def _find_ad(db: Database, raw: str | None) -> tuple[int | None, str | None]:
    """شناسه تبلیغ را از آرگومان می‌خواند؛ در خطا پیام راهنما برمی‌گرداند."""
    ad_id = parse_int(raw or "")
    if ad_id is None:
        return None, "فرمت درست:\n<code>/delad 3</code> یا <code>/adtoggle 3</code>"
    if await db.get_ad(ad_id) is None:
        return None, f"❌ تبلیغ #{ad_id} پیدا نشد."
    return ad_id, None


@router.message(Command("delad"))
async def cmd_delad(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """حذف یک تبلیغ."""
    if not _is_owner(message, config):
        return
    ad_id, error = await _find_ad(db, command.args)
    if ad_id is None:
        await message.reply(error or "❌ تبلیغ پیدا نشد.")
        return
    await db.delete_ad(ad_id)
    await message.reply(f"🗑 تبلیغ #{ad_id} حذف شد.")


@router.message(Command("adtoggle"))
async def cmd_adtoggle(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """فعال/غیرفعال کردن یک تبلیغ."""
    if not _is_owner(message, config):
        return
    ad_id, error = await _find_ad(db, command.args)
    if ad_id is None:
        await message.reply(error or "❌ تبلیغ پیدا نشد.")
        return
    ad = await db.get_ad(ad_id)
    if ad is None:
        await message.reply(f"❌ تبلیغ #{ad_id} پیدا نشد.")
        return
    new_state = not bool(ad["active"])
    await db.set_ad_active(ad_id, new_state)
    await message.reply(f"تبلیغ #{ad_id} {'فعال شد ✅' if new_state else 'غیرفعال شد ⛔️'}")


@router.message(Command("adinterval"))
async def cmd_adinterval(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """تغییر فاصله ارسال خودکار تبلیغ‌ها (دقیقه)."""
    if not _is_owner(message, config):
        return
    minutes = parse_int(command.args or "")
    if minutes is None or minutes < MIN_INTERVAL:
        await message.reply(
            f"⏱ فاصله ارسال باید عددی و حداقل <b>{MIN_INTERVAL}</b> دقیقه باشه:\n"
            "<code>/adinterval 180</code>"
        )
        return
    await db.set_setting(INTERVAL_SETTING, str(minutes))
    await message.reply(f"✅ فاصله ارسال خودکار تبلیغ‌ها روی <b>{minutes}</b> دقیقه تنظیم شد.")


@router.message(Command("adnow"))
async def cmd_adnow(
    message: Message, db: Database, config: Config, command: CommandObject
) -> None:
    """ارسال فوری تبلیغ مشخص یا تبلیغ بعدی نوبت."""
    if not _is_owner(message, config):
        return
    raw = (command.args or "").strip()
    ad_id = parse_int(raw) if raw else None
    if raw and ad_id is None:
        await message.reply("فرمت درست:\n<code>/adnow</code> یا <code>/adnow 2</code>")
        return
    if ad_id is not None and await db.get_ad(ad_id) is None:
        await message.reply(f"❌ تبلیغ #{ad_id} پیدا نشد.")
        return
    result = await send_ad_now(message.bot, db, ad_id)
    if result is None:
        await message.reply("📭 تبلیغ فعالی برای ارسال نیست. اول با /addad یکی بساز.")
        return
    sent_id, sent, failed = result
    await message.reply(
        f"📣 تبلیغ <b>#{sent_id}</b> ارسال شد.\n"
        f"✅ موفق: <b>{sent}</b> | ⚠️ ناموفق: <b>{failed}</b>"
    )
