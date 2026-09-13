"""متن‌های پیش‌فرض و قالب‌های قابل تنظیم بات عاقبت."""
from __future__ import annotations

import random

# قالب‌هایی که ادمین گروه می‌تواند با /settext بازنویسی کند.
# متغیرهای مجاز: {name} {mention} {amount} {balance} {unit} {emoji} {rank} {streak}
DEFAULT_TEXTS: dict[str, str] = {
    "daily_gain": (
        "{emoji} <b>عاقبتِ امروزِ {mention}</b>\n\n"
        "امروز <b>{amount}</b> {unit} به عاقبتت اضافه شد!\n"
        "موجودی کل: <b>{balance}</b> {unit}\n"
        "رتبه فعلی: {rank}\n"
        "🔥 استریک: <b>{streak}</b> روز"
    ),
    "daily_loss": (
        "💀 <b>عاقبتِ امروزِ {mention}</b>\n\n"
        "ای وای! امروز <b>{amount}</b> {unit} از عاقبتت کم شد...\n"
        "موجودی کل: <b>{balance}</b> {unit}\n"
        "رتبه فعلی: {rank}"
    ),
    "daily_zero": (
        "😐 <b>{mention}</b> امروز عاقبتت هیچ تغییری نکرد!\n"
        "موجودی: <b>{balance}</b> {unit}"
    ),
    "already_claimed": (
        "⏳ <b>{name}</b> جان، عاقبت امروزت رو گرفتی!\n"
        "فردا دوباره سر بزن. موجودی فعلی: <b>{balance}</b> {unit}"
    ),
    "rank_up": (
        "🎉🎊 <b>ترفیع!</b> 🎊🎉\n\n"
        "{mention} حالا <b>{rank}</b> شد!\n"
        "دسترسی‌های جدیدت در گروه باز شد. مبارکه! 🥳"
    ),
    "rank_down": (
        "📉 <b>تنزل رتبه</b>\n\n"
        "{mention} به رتبه <b>{rank}</b> برگشت.\n"
        "بیشتر فعالیت کن تا دوباره بالا بری! 💪"
    ),
    "welcome": (
        "{emoji} خوش اومدی {mention}!\n\n"
        "اینجا گروهیه که عاقبتت رو می‌سازی.\n"
        "هر روز /daily بزن تا عاقبتت زیاد (یا کم!) بشه.\n"
        "با چت کردن امتیاز بگیر و رتبه‌ات رو بالا ببر! 🚀"
    ),
    "task_done": (
        "✅ آفرین {name}!\n"
        "تسک «{title}» تایید شد و <b>{amount}</b> {unit} گرفتی.\n"
        "موجودی: <b>{balance}</b> {unit}"
    ),
}

# جملات فان تصادفی هنگام دریافت عاقبت روزانه
GAIN_FLAVOR: list[str] = [
    "ستاره‌های بخت امروز باهات یار بودن ✨",
    "انگار امروز از دنده راست بلند شدی 🦶",
    "فال حافظ گفت: خیره! 📖",
    "چرخ گردون امروز برات چرخید 🎡",
    "یه فرشته کوچولو برات آرزوی خیر کرد 👼",
    "کیهان امروز بدجوری هوات رو داشت 🌌",
    "دست به هرچی زدی طلا شد 🪙",
]

LOSS_FLAVOR: list[str] = [
    "کاسه چه کنم چه کنم دستت گرفتی 🥣",
    "امروز گربه سیاه از جلوت رد شد 🐈‍⬛",
    "عطسه کردی و راه افتادی، نتیجه‌اش همین شد 🤧",
    "انگار کسی پشت سرت حرف زده 🗣",
    "بخت ازت قهر کرده، نازش رو بکش 💔",
    "ای بابا... امروز روز تو نبود 😪",
    "شانس درِ خونه‌ت رو زد ولی تو خواب بودی 😴",
]

ZERO_FLAVOR: list[str] = [
    "نه سیخ سوخت نه کباب 🍢",
    "امروز دقیقا هیچ اتفاقی نیفتاد 🫥",
    "کیهان امروز مرخصی بود 🏖",
]

RANK_BAR_FULL = "█"
RANK_BAR_EMPTY = "░"


def get_flavor(amount: int) -> str:
    """یک جمله فان متناسب با مقدار تغییر عاقبت برمی‌گرداند."""
    if amount > 0:
        return random.choice(GAIN_FLAVOR)
    if amount < 0:
        return random.choice(LOSS_FLAVOR)
    return random.choice(ZERO_FLAVOR)


def progress_bar(current: int, target: int, width: int = 10) -> str:
    """نوار پیشرفت متنی برای نمایش فاصله تا رتبه بعدی."""
    if target <= 0:
        return RANK_BAR_FULL * width
    ratio = max(0.0, min(1.0, current / target))
    filled = int(ratio * width)
    return RANK_BAR_FULL * filled + RANK_BAR_EMPTY * (width - filled)
