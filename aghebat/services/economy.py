"""منطق اقتصاد بات: قرعه روزانه، استریک و امتیاز پیام."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from ..db import Database

# تلگرام تاریخ را UTC می‌دهد؛ برای بازنشانی روزانه از وقت تهران استفاده می‌کنیم.
TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def today_key(now: datetime | None = None) -> str:
    """کلید روز جاری به وقت تهران (برای جلوگیری از دریافت چندباره)."""
    moment = now or datetime.now(TEHRAN_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(TEHRAN_TZ).date().isoformat()


def _yesterday_key() -> str:
    return (datetime.now(TEHRAN_TZ).date() - timedelta(days=1)).isoformat()


def roll_amount(daily_min: int, daily_max: int) -> int:
    """یک عدد تصادفی بین بازه تنظیم‌شده گروه (می‌تواند منفی باشد)."""
    low, high = (daily_min, daily_max) if daily_min <= daily_max else (daily_max, daily_min)
    return random.randint(low, high)


def streak_bonus(streak: int) -> int:
    """پاداش تشویقی برای روزهای متوالی."""
    if streak >= 30:
        return 25
    if streak >= 14:
        return 15
    if streak >= 7:
        return 10
    if streak >= 3:
        return 5
    return 0


@dataclass(slots=True)
class DailyResult:
    """نتیجه یک بار دریافت عاقبت روزانه."""

    claimed: bool
    amount: int = 0
    bonus: int = 0
    balance: int = 0
    streak: int = 0
    best_streak: int = 0

    @property
    def total(self) -> int:
        return self.amount + self.bonus


async def claim_daily(db: Database, chat_id: int, user_id: int) -> DailyResult:
    """عاقبت روزانه کاربر را محاسبه و ثبت می‌کند."""
    chat = await db.ensure_chat(chat_id)
    member = await db.ensure_member(chat_id, user_id)
    today = today_key()

    if member["last_daily"] == today:
        return DailyResult(
            claimed=False,
            balance=int(member["balance"]),
            streak=int(member["streak"]),
            best_streak=int(member["best_streak"]),
        )

    streak = int(member["streak"]) + 1 if member["last_daily"] == _yesterday_key() else 1
    best = max(int(member["best_streak"]), streak)
    amount = roll_amount(int(chat["daily_min"]), int(chat["daily_max"]))
    bonus = streak_bonus(streak)

    balance = await db.add_balance(chat_id, user_id, amount + bonus, reason="daily")
    await db.set_member_field(chat_id, user_id, "last_daily", today)
    await db.set_member_field(chat_id, user_id, "streak", streak)
    await db.set_member_field(chat_id, user_id, "best_streak", best)

    return DailyResult(
        claimed=True,
        amount=amount,
        bonus=bonus,
        balance=balance,
        streak=streak,
        best_streak=best,
    )


async def reward_message(db: Database, chat_id: int, user_id: int, now_ts: int) -> bool:
    """امتیاز فعالیت پیام را با رعایت کول‌داون ثبت می‌کند."""
    chat = await db.get_chat(chat_id)
    if chat is None or not chat["enabled"]:
        return False
    member = await db.get_member(chat_id, user_id)
    if member is None:
        return False
    cooldown = int(chat["msg_cooldown"])
    if now_ts - int(member["last_msg_ts"]) < cooldown:
        await db.execute(
            "UPDATE members SET messages = messages + 1 WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return False
    await db.bump_message(chat_id, user_id, now_ts, int(chat["msg_points"]))
    return True
