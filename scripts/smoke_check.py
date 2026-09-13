"""بررسی دودی (Smoke Test) عاقبت — بدون اتصال به تلگرام.

جداول و متدهای جدید دیتابیس را روی یک فایل موقت آزمایش می‌کند و در پایان
روترهای هندلر را می‌سازد. اجرا: python scripts/smoke_check.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

# اجازه اجرای مستقیم از داخل پوشه scripts
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
    """روترهای هندلر (از جمله botadmin و ads) ساخته می‌شوند؟"""
    from aghebat.handlers import build_router

    router = build_router()
    names = [r.name for r in router.sub_routers]
    for expected in ("common", "daily", "profile", "tasks", "admin", "owner", "botadmin", "ads", "fun", "group"):
        assert expected in names, f"روتر {expected} ثبت نشده است: {names}"
    assert names.index("owner") < names.index("botadmin") < names.index("ads") < names.index("fun"), names
    print("روترها:", " -> ".join(names))


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        await check_db(tmp)
    check_routers()
    print("SMOKE CHECK OK ✅")


if __name__ == "__main__":
    asyncio.run(main())
