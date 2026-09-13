"""دستورات عمومی: شروع و راهنما."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import Config
from ..db import Database
from ..utils import is_group, safe

router = Router(name="common")

HELP_TEXT = (
    "🌱 <b>راهنمای بات عاقبت</b>\n\n"
    "<b>دستورات همگانی:</b>\n"
    "/daily — دریافت عاقبت روزانه 🎲\n"
    "/me — کارنامه و رتبه من 📊\n"
    "/top — جدول برترین‌ها 🏆\n"
    "/active — فعال‌ترین اعضا 💬\n"
    "/ranks — نردبان رتبه‌ها 🪜\n"
    "/tasks — تسک‌ها و جایزه‌ها 🎯\n"
    "/history — تاریخچه تغییرات 🧾\n"
    "/dice — شرط‌بندی شانسی 🎰\n"
    "/fal — فال روزانه 🔮\n"
    "/gift — هدیه دادن به دوستان 🎁\n\n"
    "<b>دستورات ادمین گروه:</b>\n"
    "/settings — پنل تنظیمات ⚙️\n"
    "/setrange — بازه عدد روزانه\n"
    "/setunit — نام واحد امتیاز\n"
    "/setmsgpoints — امتیاز هر پیام\n"
    "/addrank , /delrank , /resetranks — مدیریت رتبه‌ها\n"
    "/settext , /texts — شخصی‌سازی متن‌ها\n"
    "/give , /take , /setbalance — مدیریت موجودی\n"
    "/syncall — هماهنگ‌سازی دسترسی‌ها\n\n"
    "💡 <i>بات باید ادمین گروه باشد تا بتواند دسترسی‌ها را مدیریت کند.</i>"
)


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, config: Config) -> None:
    """پیام خوشامد در چت خصوصی و گروه."""
    if is_group(message.chat):
        await db.ensure_chat(message.chat.id, message.chat.title or "")
        await message.reply(
            "🌱 <b>عاقبت</b> فعال شد!\n\n"
            "هر روز /daily بزن تا ببینی عاقبتت چی می‌شه 🎲\n"
            "با چت کردن امتیاز بگیر، رتبه بگیر و دسترسی‌های جدید باز کن 🔓\n\n"
            "راهنما: /help"
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ افزودن به گروه",
                    url=f"https://t.me/{(await message.bot.me()).username}?startgroup=true",
                )
            ],
            [InlineKeyboardButton(text="📚 راهنما", callback_data="help")],
        ]
    )
    await message.answer(
        f"🌱 سلام {safe(message.from_user.full_name if message.from_user else '')}!\n\n"
        f"من <b>{safe(config.bot_name)}</b> هستم؛ بات فان و مدیریت گروه.\n\n"
        "هر روز به اعضای گروه یک عدد تصادفی می‌دم (گاهی مثبت، گاهی منفی!)، "
        "رتبه‌بندی می‌کنم و با بالا رفتن رتبه، دسترسی‌های گروه رو باز می‌کنم 🔓\n\n"
        "منو به گروهت اضافه کن و ادمین کن تا شروع کنیم 🚀",
        reply_markup=keyboard,
    )


@router.message(Command("help", "rahnama"))
@router.message(F.text.in_({"راهنما", "کمک"}))
async def cmd_help(message: Message) -> None:
    """نمایش راهنمای کامل."""
    await message.reply(HELP_TEXT)


@router.callback_query(F.data == "help")
async def cb_help(call) -> None:  # noqa: ANN001 - نوع CallbackQuery در ایمپورت بالا
    """راهنما از طریق دکمه شیشه‌ای."""
    if call.message is not None:
        await call.message.answer(HELP_TEXT)
    await call.answer()
