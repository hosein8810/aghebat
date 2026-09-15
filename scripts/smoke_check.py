"""بررسی دودی (Smoke Test) عاقبت — بدون اتصال به تلگرام.

جداول و متدهای جدید دیتابیس را روی یک فایل موقت آزمایش می‌کند، ترجمه
عبارت‌های فارسی را با فیلتر واقعی Command در aiogram می‌سنجد، نرخ‌های بازار را
روی یک فیکسچر آفلاین (بدون شبکه) تبدیل و قالب‌بندی می‌کند و در پایان روترها و
لیست منوی دستورها را بررسی می‌کند.
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


async def check_config_io(tmp: str) -> None:
    """خروجی، اعتبارسنجی و بارگذاری تنظیمات گروه روی دیتابیس موقت."""
    import json

    from aghebat.services.config_io import (
        apply_config_import,
        build_config_export,
        validate_config_import,
    )

    db = Database(Path(tmp) / "config_io.db")
    await db.connect()

    source, target = -1001, -1002
    await db.ensure_chat(source, "گروه مبدأ")
    await db.ensure_chat(target, "گروه مقصد")

    # ۱) تنظیمات غیرپیش‌فرض + دو رتبه سفارشی + یک متن بازنویسی‌شده روی مبدأ.
    for field, value in (
        ("unit_name", "سکه"),
        ("unit_emoji", "🪙"),
        ("daily_min", -3),
        ("daily_max", 12),
        ("msg_points", 2),
        ("msg_cooldown", 45),
        ("enforce_ranks", 0),
        ("fun_mode", 0),
    ):
        await db.set_chat_field(source, field, value)
    await db.execute("DELETE FROM ranks WHERE chat_id = ?", (source,))
    await db.add_rank(source, "برنز", "🥉", 0, {"can_send_messages": True})
    await db.add_rank(
        source, "نقره", "🥈", 500, {"can_send_messages": True, "can_send_photos": True}
    )
    await db.set_text(source, "daily_gain", "متن سفارشی {amount}")

    # مقصد: عنوان/وضعیت متفاوت + موجودی عضوی که نباید دست بخورد.
    await db.set_chat_field(target, "enabled", 0)
    await db.ensure_member(target, 42, "کاربر آزمایشی")
    await db.add_balance(target, 42, 100, "seed")

    # ۲) ساختار فایل خروجی.
    export = await build_config_export(db, source)
    assert export["aghebat_config"] == 1 and export["version"] == 1, export
    assert export["source_chat_id"] == source
    assert isinstance(export["exported_at"], int) and export["exported_at"] > 0
    assert export["settings"] == {
        "unit_name": "سکه",
        "unit_emoji": "🪙",
        "daily_min": -3,
        "daily_max": 12,
        "msg_points": 2,
        "msg_cooldown": 45,
        "enforce_ranks": 0,
        "fun_mode": 0,
    }, export["settings"]
    assert "title" not in export["settings"] and "enabled" not in export["settings"]
    assert [r["title"] for r in export["ranks"]] == ["برنز", "نقره"], export["ranks"]
    assert [r["min_balance"] for r in export["ranks"]] == [0, 500]
    assert export["ranks"][1]["perms"] == {
        "can_send_messages": True,
        "can_send_photos": True,
    }, export["ranks"][1]["perms"]
    assert export["texts"] == {"daily_gain": "متن سفارشی {amount}"}, export["texts"]

    # ۳) اعتبارسنجی فایل سالم؛ کلیدهای اضافه باید نادیده گرفته شوند.
    assert validate_config_import(export) == [], validate_config_import(export)
    extra = dict(export)
    extra["unknown_top"] = "نادیده"
    extra["settings"] = {**export["settings"], "unknown_setting": 5}
    assert validate_config_import(extra) == [], validate_config_import(extra)

    # ۴) اعمال روی مقصد: تنظیمات، رتبه‌ها و متن منتقل شوند.
    summary = await apply_config_import(db, target, export)
    assert summary == {"settings": 8, "ranks": 2, "texts": 1}, summary

    row = await db.get_chat(target)
    assert row is not None
    for field, expected in export["settings"].items():
        assert row[field] == expected, (field, row[field], expected)
    assert row["title"] == "گروه مقصد", "عنوان گروه مقصد نباید عوض شود"
    assert int(row["enabled"]) == 0, "وضعیت روشن/خاموش گروه مقصد نباید عوض شود"

    target_ranks = await db.ranks(target)
    assert [r["title"] for r in target_ranks] == ["برنز", "نقره"], target_ranks
    assert [int(r["min_balance"]) for r in target_ranks] == [0, 500]
    assert json.loads(target_ranks[1]["perms"]) == {
        "can_send_messages": True,
        "can_send_photos": True,
    }, target_ranks[1]["perms"]
    assert await db.all_texts(target) == {"daily_gain": "متن سفارشی {amount}"}
    member = await db.get_member(target, 42)
    assert member is not None and int(member["balance"]) == 100, "موجودی اعضا نباید عوض شود"

    # ۵) فایل خراب: نوع اشتباه + مقدار منفی + رتبه بدون عنوان + کلید ناشناخته.
    bad = {
        "aghebat_config": 1,
        "version": 1,
        "settings": {"daily_min": "خیلی", "daily_max": 5, "msg_points": -1},
        "ranks": [{"emoji": "⭐️", "min_balance": 0, "perms": {"bogus_perm": True}}],
        "texts": {"nope_key": "x"},
    }
    errors = validate_config_import(bad)
    assert len(errors) >= 4, errors
    assert all(isinstance(e, str) and e.startswith("❌") for e in errors), errors
    assert any("عدد" in e for e in errors), errors
    assert any("منفی" in e for e in errors), errors
    assert any("عنوان" in e for e in errors), errors
    assert any("ناشناخته" in e for e in errors), errors
    assert validate_config_import([]) != [], "ورودی غیرشیء باید رد شود"

    await db.close()
    print(f"خروجی/بارگذاری تنظیمات: OK ({summary})")


def check_routers() -> None:
    """روترهای هندلر (از جمله panels) با ترتیب درست ساخته می‌شوند؟"""
    from aghebat.handlers import build_router

    router = build_router()
    names = [r.name for r in router.sub_routers]
    for expected in (
        "common", "panels", "configio", "daily", "profile", "tasks",
        "admin", "owner", "botadmin", "ads", "market", "tictactoe", "fun", "group",
    ):
        assert expected in names, f"روتر {expected} ثبت نشده است: {names}"
    assert names.index("panels") == names.index("common") + 1, names
    assert names.index("configio") == names.index("panels") + 1, names
    assert names.index("owner") < names.index("botadmin") < names.index("ads") < names.index("fun"), names
    assert names.index("ads") < names.index("market") < names.index("fun"), names
    # دوز درست بعد از بازار و قبل از سرگرمی می‌نشیند.
    assert names.index("market") < names.index("tictactoe") < names.index("fun"), names
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
    assert resolve_alias("خروجی تنظیمات") == ("/export", "")
    assert resolve_alias("بارگذاری تنظیمات") == ("/import", "")
    assert resolve_alias("دوز") == ("/ttt", ""), resolve_alias("دوز")
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
    # نرخ‌ها هم در منوی عمومی گروه و هم در چت خصوصی هست.
    assert "rates" in public_names and "rates" in private_names, (public_names, private_names)

    # هر صفحه راهنما باید یک دکمه در صفحه اصلی داشته باشد (و برعکس).
    from aghebat.handlers.common import HELP_PAGES, _help_main_markup

    callbacks = {
        button.callback_data
        for row in _help_main_markup().inline_keyboard
        for button in row
    }
    assert callbacks == {f"help:{key}" for key in HELP_PAGES}, callbacks
    assert callbacks == {"help:game", "help:admin", "help:owner", "help:tools"}, callbacks
    print(f"منوی دستورها: عمومی={len(public_names)} مالک={len(owner_names)} OK")


# نمونه پاسخ واقعی منبع نرخ‌ها (شکل کلیدها عیناً مثل bonbast) — آزمون بدون شبکه.
_MARKET_FIXTURE = {
    "usd1": "231500",
    "usd2": "231400",
    "eur1": "268600",
    "eur2": "268400",
    "emami1": "235000000",
    "emami12": "231000000",
    "ounce": "4348.78",
    "bitcoin": "76811.72",
    "bourse": "1904324.2",
    "last_modified": "September 13, 2026 12:26",
}


def check_market() -> None:
    """تفسیر و قالب‌بندی نرخ‌ها: تبدیل ریال به تومان و استثناهای جهانی."""
    from aghebat.aliases import resolve_alias
    from aghebat.services.market import format_market, parse_market_payload

    snapshot = parse_market_payload(_MARKET_FIXTURE)
    sell, buy = snapshot["currencies"]["usd"]
    assert (sell, buy) == (231500, 231400), (sell, buy)
    assert sell // 10 == 23150, sell
    assert snapshot["currencies"]["eur"] == (268600, 268400)
    emami = snapshot["gold"]["emami"]
    assert isinstance(emami, tuple) and emami[0] // 10 == 23500000, emami
    assert emami == (235000000, 231000000), emami
    assert snapshot["last_modified"] == "September 13, 2026 12:26"

    # استثناها: انس و بیت‌کوین دلاری و بورس شاخص می‌مانند، بر ۱۰ تقسیم نمی‌شوند.
    assert snapshot["globals"]["ounce"] == 4348.78
    assert snapshot["globals"]["bitcoin"] == 76811.72
    assert snapshot["globals"]["bourse"] == 1904324.2

    text = format_market(snapshot)
    for header in ("💱 <b>ارز</b>", "🪙 <b>طلا و سکه</b>", "🌍 <b>جهانی</b>"):
        assert header in text, text
    assert "23,150 × 23,140 تومان" in text, text
    assert "23,500,000" in text, text
    assert "235,000,000" not in text, "ارزش ریالی نباید بدون تبدیل نمایش داده شود"
    assert "4,348.78 دلار" in text, text
    assert "434.878" not in text, "انس طلا نباید بر ۱۰ تقسیم شود"
    assert "76,811.72 دلار" in text, text
    assert "1,904,324.2 واحد" in text, text
    assert "تبدیل شده‌اند" in text, text
    assert "<i>به‌روزرسانی: September 13, 2026 12:26</i>" in text, text

    # کلیدهای غایب ساخته نمی‌شوند.
    assert "gbp" not in snapshot["currencies"], snapshot["currencies"]
    assert "mithqal" not in snapshot["gold"], snapshot["gold"]
    assert parse_market_payload({})["currencies"] == {}

    assert resolve_alias("ارز") == ("/rates", ""), resolve_alias("ارز")
    assert resolve_alias("نرخ ارز") == ("/rates", ""), resolve_alias("نرخ ارز")
    assert resolve_alias("قیمت طلا") == ("/rates", ""), resolve_alias("قیمت طلا")
    assert resolve_alias("طلا") == ("/rates", ""), resolve_alias("طلا")
    print("نرخ بازار (فیکسچر آفلاین): OK")


def check_tictactoe() -> None:
    """موتور دوز: برد سطر/ستون/قطر، مساوی، حرکت بات و پایان بازی بات-به-بات."""
    from aghebat.services import tictactoe as ttt

    assert ttt.new_board() == [""] * 9

    # برد در سطر، ستون و قطر.
    assert ttt.winner(["X", "X", "X", "", "O", "", "O", "", ""]) == "X"
    assert ttt.winner(["O", "X", "", "O", "X", "", "O", "", ""]) == "O"
    assert ttt.winner(["X", "O", "", "", "X", "O", "", "", "X"]) == "X"

    # وسط بازی هنوز برنده‌ای نیست.
    mid = ["X", "", "", "", "O", "", "", "", ""]
    assert ttt.winner(mid) is None
    assert ttt.empty_cells(mid) == [1, 2, 3, 5, 6, 7, 8], ttt.empty_cells(mid)
    assert not ttt.is_full(mid)

    # صفحه پر و مساوی: هیچ خطی صاحب ندارد.
    draw = ["X", "O", "X", "X", "O", "O", "O", "X", "X"]
    assert ttt.winner(draw) is None and ttt.is_full(draw)
    assert ttt.empty_cells(draw) == []

    # بهترین حرکت همیشه روی یک خانه خالی می‌نشیند.
    board = ttt.new_board()
    board[0], board[4] = "X", "O"
    for _ in range(20):
        assert ttt.best_move(board, "O") in ttt.empty_cells(board)

    # با خاموش‌کردن تصادف، بات برد فوری می‌زند و جلوی برد حریف را می‌گیرد.
    assert ttt.best_move(["O", "O", "", "X", "X", "", "", "", ""], "O", 0.0) == 2
    assert ttt.best_move(["X", "X", "", "", "O", "", "", "", ""], "O", 0.0) == 2

    # بازی بات-به-بات باید تمام شود و حالت پایانی معتبر بدهد.
    board = ttt.new_board()
    for index in range(9):
        if ttt.winner(board) is not None or ttt.is_full(board):
            break
        mark = ("X", "O")[index % 2]
        board[ttt.best_move(board, mark)] = mark
    final = ttt.winner(board)
    assert final in {"X", "O", None}, final
    assert final is not None or ttt.is_full(board), board

    # صفحه پر برای بات خطاست.
    try:
        ttt.best_move(draw, "X")
    except ValueError:
        pass
    else:
        raise AssertionError("حرکت روی صفحه پر باید خطا بدهد")
    print("موتور دوز: OK")


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        await check_db(tmp)
        await check_config_io(tmp)
    check_routers()
    check_aliases()
    check_menu()
    check_market()
    check_tictactoe()
    bot = Bot(token="123456:TEST-TOKEN")
    try:
        await check_alias_rewrite(bot)
    finally:
        await bot.session.close()
    print("SMOKE CHECK OK ✅")


if __name__ == "__main__":
    asyncio.run(main())
