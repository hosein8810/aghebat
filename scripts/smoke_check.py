"""بررسی دودی (Smoke Test) عاقبت — بدون اتصال به تلگرام.

جداول و متدهای جدید دیتابیس را روی یک فایل موقت آزمایش می‌کند، ترجمه
عبارت‌های فارسی را با فیلتر واقعی Command در aiogram می‌سنجد و در پایان
روترها و لیست منوی دستورها را بررسی می‌کند.
اجرا: python scripts/smoke_check.py
"""
from __future__ import annotations

import asyncio
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# اجازه اجرای مستقیم از داخل پوشه scripts
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot  # noqa: E402

from aghebat.db import Database  # noqa: E402


async def check_db(tmp: str) -> None:
    """جداول جدید و رفت و برگشت متدها را روی دیتابیس موقت آزمایش می‌کند."""
    db = Database(Path(tmp) / "smoke.db")
    await db.connect()

    # ۱) وجود جداول جدید
    rows = await db.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
    existing = {r["name"] for r in rows}
    missing = {"bot_admins", "activated_users", "ads", "settings"} - existing
    assert not missing, f"جداول ساخته نشده‌اند: {missing}"

    # ۲) ادمین بات: افزودن، بررسی، لیست، تکرار (idempotent)، حذف
    assert not await db.is_bot_admin(-100, 42)
    await db.add_bot_admin(-100, 42, "علی", "ali", promoted_by=1)
    assert await db.is_bot_admin(-100, 42)
    assert not await db.is_bot_admin(-200, 42)
    admins = await db.bot_admins(-100)
    assert len(admins) == 1 and int(admins[0]["user_id"]) == 42
    await db.add_bot_admin(-100, 42, "علی دوم", "ali2", promoted_by=1)
    assert len(await db.bot_admins(-100)) == 1
    await db.remove_bot_admin(-100, 42)
    assert not await db.is_bot_admin(-100, 42)

    # ۳) فعال‌سازی: فعال/غیرفعال/شمارش
    assert not await db.is_activated(7)
    await db.activate_user(7, "سارا", "sara", activated_by=1)
    assert await db.is_activated(7)
    assert await db.activated_count() == 1
    await db.deactivate_user(7)
    assert not await db.is_activated(7)
    assert await db.activated_count() == 0

    # ۴) تبلیغ‌ها: ساخت، خواندن، فعال/غیرفعال، شمارش ارسال، حذف
    ad1 = await db.add_ad("تبلیغ آزمایشی")
    ad2 = await db.add_ad("تبلیغ عکسی", media_file_id="FILE123", media_type="photo")
    ad = await db.get_ad(ad1)
    assert ad is not None and ad["text"] == "تبلیغ آزمایشی" and bool(ad["active"])
    assert int(ad["sent_count"]) == 0
    ids = [int(r["id"]) for r in await db.ads()]
    assert ids == sorted(ids) == [ad1, ad2]
    assert len(await db.ads(only_active=True)) == 2
    await db.set_ad_active(ad2, False)
    assert len(await db.ads(only_active=True)) == 1
    await db.bump_ad_sent(ad1)
    await db.bump_ad_sent(ad1)
    ad = await db.get_ad(ad1)
    assert ad is not None and int(ad["sent_count"]) == 2
    await db.delete_ad(ad2)
    assert await db.get_ad(ad2) is None

    # ۵) تنظیمات: پیش‌فرض، ذخیره و بازنویسی
    assert await db.get_setting("nope") is None
    assert await db.get_setting("nope", "پیش‌فرض") == "پیش‌فرض"
    await db.set_setting("ads_interval_minutes", "90")
    await db.set_setting("ads_interval_minutes", "60")
    assert await db.get_setting("ads_interval_minutes") == "60"

    await db.close()


def check_routers() -> None:
    """روترهای هندلر (از جمله panels) با ترتیب درست ساخته می‌شوند؟"""
    from aghebat.handlers import build_router

    router = build_router()
    names = [r.name for r in router.sub_routers]
    for expected in (
        "common", "panels", "daily", "profile", "tasks",
        "admin", "owner", "botadmin", "ads", "fun", "group",
    ):
        assert expected in names, f"روتر {expected} ثبت نشده است: {names}"
    assert names.index("panels") == names.index("common") + 1, names
    assert names.index("owner") < names.index("botadmin") < names.index("ads") < names.index("fun"), names
    print("روترها:", " -> ".join(names))


def check_aliases() -> None:
    """ترجمه عبارت‌های فارسی به دستور، مطابق جدول ALIASES."""
    from aghebat.aliases import ALIASES, resolve_alias

    assert resolve_alias("تنظیم ادمین") == ("/promote", ""), resolve_alias("تنظیم ادمین")
    assert resolve_alias("بازه روزانه ۵ ۲۰") == ("/setrange", "۵ ۲۰")
    assert resolve_alias("غیرفعالسازی") == ("/deactivate", "")
    assert resolve_alias("فعالسازی") == ("/activate", "")
    assert resolve_alias("ادمین") is None
    assert resolve_alias("/promote") is None
    assert resolve_alias("سلام") is None
    assert resolve_alias("ارسال تبلیغ") == ("/adnow", "")
    assert resolve_alias("تنظیمات") == ("/settings", "")
    # طولانی‌ترین عبارت اول: «سوییچ تبلیغ» نباید «/toggle تبلیغ» شود.
    assert resolve_alias("سوییچ تبلیغ") == ("/adtoggle", "")
    # فاصله‌های اضافه و متن خالی
    assert resolve_alias("  عزل ادمین  ") == ("/demote", "")
    assert resolve_alias("   ") is None

    # نام همه دستورهای جدول با قاعده تلگرام جور است.
    for phrase, command in ALIASES:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", command), (phrase, command)
    # عبارت‌هایی که هندلر متن خام دارند نباید در جدول باشند.
    protected = {"عاقبت", "پروفایل", "برترین‌ها", "فعال‌ترین‌ها", "رتبه‌ها", "تسک‌ها", "فال", "راهنما", "کمک"}
    phrases = {phrase for phrase, _ in ALIASES}
    assert not (phrases & protected), phrases & protected
    print("عبارت‌های فارسی:", len(ALIASES), "مورد OK")


def _make_message(text: str):  # noqa: ANN202 - فقط برای تست محلی
    """یک پیام متنی کمینه برای آزمایش فیلترهای aiogram می‌سازد."""
    from aiogram.types import Chat, Message, User

    return Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=-100123, type="supergroup", title="گروه آزمایشی"),
        from_user=User(id=42, is_bot=False, first_name="علی"),
        text=text,
    )


async def check_alias_rewrite(bot: Bot) -> None:
    """بازنویسی پیام باید فیلتر واقعی Command در aiogram را قانع کند."""
    from aiogram.filters import Command

    from aghebat.aliases import resolve_alias, rewrite_message
    from aghebat.middlewares.aliases import AliasMiddleware

    # مسیر کامل میدل‌ور: عبارت فارسی داخل، پیام دستوردار بیرون.
    captured: dict[str, object] = {}

    async def handler(event, data):  # noqa: ANN001, ANN202 - هندلر جعلی تست
        captured["message"] = event

    await AliasMiddleware()(handler, _make_message("تنظیم ادمین"), {})
    rewritten = captured["message"]
    assert rewritten.text == "/promote", rewritten.text
    assert len(rewritten.entities or []) == 1
    entity = rewritten.entities[0]
    assert entity.type == "bot_command"
    assert entity.offset == 0 and entity.length == len("/promote")

    # فیلتر Command روی همان پیامِ بازنویسی‌شده
    result = await Command("promote")(message=rewritten, bot=bot)
    assert isinstance(result, dict), "فیلتر Command عبارت ترجمه‌شده را نپذیرفت"
    assert (result["command"].args or "") == ""

    # آرگومان‌ها (ارقام فارسی دست‌نخورده) با فیلتر واقعی Command می‌رسند.
    command, args = resolve_alias("بازه روزانه ۵ ۲۰")
    candidate = rewrite_message(_make_message("بازه روزانه ۵ ۲۰"), command, args)
    assert candidate.text == "/setrange ۵ ۲۰"
    result = await Command("setrange")(message=candidate, bot=bot)
    assert isinstance(result, dict)
    assert result["command"].args == "۵ ۲۰", result["command"].args

    # پیام بدون معادل باید دست‌نخورده رد شود.
    await AliasMiddleware()(handler, _make_message("سلام"), {})
    assert captured["message"].text == "سلام"
    print("بازنویسی پیام + فیلتر Command: OK")


def check_menu() -> None:
    """لیست‌های منوی دستورها معتبر، بدون تکرار و به‌ترتیب درست‌اند؟"""
    from aghebat.services.menu import (
        OWNER_COMMANDS,
        PRIVATE_COMMANDS,
        PUBLIC_GROUP_COMMANDS,
    )

    for source in (PUBLIC_GROUP_COMMANDS, PRIVATE_COMMANDS, OWNER_COMMANDS):
        for item in source:
            assert re.fullmatch(r"[a-z0-9_]{1,32}", item.command), item.command
            assert 1 <= len(item.description) <= 256, item.command

    public_names = {item.command for item in PUBLIC_GROUP_COMMANDS}
    private_names = {item.command for item in PRIVATE_COMMANDS}
    owner_names = {item.command for item in OWNER_COMMANDS}
    assert public_names <= owner_names, "لیست مالک باید شامل لیست عمومی باشد"
    assert private_names <= owner_names, "لیست مالک باید شامل لیست خصوصی باشد"
    assert len(owner_names) == len(OWNER_COMMANDS), "دستور تکراری در لیست مالک"
    print(f"منوی دستورها: عمومی={len(public_names)} مالک={len(owner_names)} OK")


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        await check_db(tmp)
    check_routers()
    check_aliases()
    check_menu()
    bot = Bot(token="123456:TEST-TOKEN")
    try:
        await check_alias_rewrite(bot)
    finally:
        await bot.session.close()
    print("SMOKE CHECK OK ✅")


if __name__ == "__main__":
    asyncio.run(main())
