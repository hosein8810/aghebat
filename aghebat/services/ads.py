"""ارسال و زمان‌بندی تبلیغ‌های مالک به گروه‌های فعال."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from ..config import Config
from ..db import Database

logger = logging.getLogger(__name__)

SEND_DELAY_SECONDS = 0.05
LOOP_TICK_SECONDS = 20
MIN_INTERVAL_MINUTES = 5
DEFAULT_INTERVAL_MINUTES = 180

INTERVAL_SETTING = "ads_interval_minutes"
LAST_AD_SETTING = "last_ad_id"
NEXT_SEND_SETTING = "next_send_ts"


async def broadcast_ad(bot: Bot, db: Database, ad_row: Any) -> tuple[int, int]:
    """تبلیغ را برای همه گروه‌های فعال می‌فرستد و (موفق، ناموفق) برمی‌گرداند."""
    chats = await db.all_chats()
    text = ad_row["text"]
    file_id = ad_row["media_file_id"] or ""
    media_type = ad_row["media_type"] or ""
    sent = failed = 0
    for chat in chats:
        chat_id = int(chat["chat_id"])
        if chat_id >= 0:
            continue  # فقط گروه‌ها/سوپرگروه‌ها (آیدی منفی)
        try:
            if file_id and media_type == "photo":
                await bot.send_photo(chat_id, photo=file_id, caption=text)
            else:
                await bot.send_message(chat_id, text)
            sent += 1
        except TelegramForbiddenError:
            # بات از گروه اخراج/مسدود شده؛ دیگر تلاشی نمی‌کنیم.
            logger.info("تبلیغ برای گروه %s مسدود بود؛ غیرفعالش کردم.", chat_id)
            await db.set_chat_field(chat_id, "enabled", 0)
            failed += 1
        except TelegramAPIError as exc:
            logger.warning("ارسال تبلیغ به گروه %s ناموفق بود: %s", chat_id, exc)
            failed += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)
    await db.bump_ad_sent(int(ad_row["id"]))
    return sent, failed


async def _interval_minutes(db: Database, config: Config | None = None) -> int:
    """فاصله ارسال را از تنظیمات می‌خواند (با کف ۵ دقیقه)."""
    raw = await db.get_setting(INTERVAL_SETTING)
    if raw is not None and raw.strip().isdigit():
        minutes = int(raw)
    else:
        minutes = config.ads_interval_minutes if config else DEFAULT_INTERVAL_MINUTES
    return max(MIN_INTERVAL_MINUTES, minutes)


async def _next_ad(db: Database, ad_id: int | None = None) -> Any | None:
    """تبلیغ مشخص یا تبلیغ بعدی نوبت (رفت‌وبرگشتی بر اساس id) را برمی‌گرداند."""
    if ad_id is not None:
        return await db.get_ad(ad_id)
    rows = await db.ads(only_active=True)
    if not rows:
        return None
    raw_last = await db.get_setting(LAST_AD_SETTING)
    last_id = int(raw_last) if raw_last is not None and raw_last.strip().isdigit() else 0
    for row in rows:
        if int(row["id"]) > last_id:
            return row
    return rows[0]  # بعد از آخرین تبلیغ، از اول شروع می‌شود.


async def ads_loop(bot: Bot, db: Database, config: Config) -> None:
    """حلقه همیشگی ارسال خودکار تبلیغ‌ها.

    زمان ارسال بعدی در تنظیمات ذخیره می‌شود تا ری‌استارت باعث اسپم یا از دست
    رفتن نوبت نشود؛ هر ۲۰ ثانیه بیدار می‌شود تا تغییر بازه و /adnow فوری اثر کند.
    """
    logger.info("زمان‌بند تبلیغ‌ها راه افتاد.")
    while True:
        try:
            now = int(time.time())
            interval = await _interval_minutes(db, config)
            raw_next = await db.get_setting(NEXT_SEND_SETTING)
            next_ts = int(raw_next) if raw_next is not None and raw_next.strip().isdigit() else 0
            if next_ts <= 0:
                # اولین اجرا: فقط زمان‌بندی می‌کنیم تا ناگهانی اسپم نشود.
                await db.set_setting(NEXT_SEND_SETTING, str(now + interval * 60))
            elif now >= next_ts:
                ad = await _next_ad(db)
                if ad is None:
                    logger.info("تبلیغ فعالی برای ارسال وجود ندارد.")
                else:
                    sent, failed = await broadcast_ad(bot, db, ad)
                    await db.set_setting(LAST_AD_SETTING, str(int(ad["id"])))
                    logger.info(
                        "تبلیغ #%s ارسال شد: موفق %s، ناموفق %s", ad["id"], sent, failed
                    )
                await db.set_setting(NEXT_SEND_SETTING, str(now + interval * 60))
            await asyncio.sleep(LOOP_TICK_SECONDS)
        except asyncio.CancelledError:
            logger.info("زمان‌بند تبلیغ‌ها متوقف شد.")
            raise
        except Exception:  # noqa: BLE001 - هیچ خطایی نباید حلقه را بکشد
            logger.exception("خطا در حلقه تبلیغ‌ها؛ ۳۰ ثانیه دیگر تلاش می‌کنیم.")
            await asyncio.sleep(30)


async def send_ad_now(
    bot: Bot, db: Database, ad_id: int | None = None
) -> tuple[int, int, int] | None:
    """ارسال فوری یک تبلیغ؛ خروجی (شناسه تبلیغ، موفق، ناموفق) یا None."""
    ad = await _next_ad(db, ad_id)
    if ad is None:
        return None
    sent, failed = await broadcast_ad(bot, db, ad)
    now = int(time.time())
    await db.set_setting(LAST_AD_SETTING, str(int(ad["id"])))
    await db.set_setting(NEXT_SEND_SETTING, str(now + await _interval_minutes(db) * 60))
    return int(ad["id"]), sent, failed
