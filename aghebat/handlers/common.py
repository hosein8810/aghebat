"""دستورات عمومی: شروع و راهنما."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import Config
from ..db import Database
from ..texts import render_start_promo
from ..utils import is_group, owner_contact_url, safe

router = Router(name="common")

# --------------------------------------------------------------- صفحات راهنما
# قالب ثابت هر خط: <code>/دستور</code> — توضیح کوتاه (عبارت فارسی معادل)

HELP_INTRO = (
    "📚 <b>راهنمای بات عاقبت</b>\n"
    "یک دسته را انتخاب کن تا لیست کاملش را ببینی:\n\n"
    "⚙️ تنظیمات گروه را با /settings داخل گروه باز کن."
)

HELP_GAME = (
    "🎮 <b>بازی و سرگرمی</b>\n\n"
    "<code>/start</code> — شروع و خوشامد\n"
    "<code>/daily</code> — عاقبت روزانه 🎲 (عاقبت)\n"
    "<code>/me</code> — کارنامه و موجودی من 📊\n"
    "<code>/top</code> — جدول برترین‌ها 🏆 (برترین‌ها)\n"
    "<code>/active</code> — فعال‌ترین اعضا 💬 (فعال‌ترین‌ها)\n"
    "<code>/ranks</code> — نردبان رتبه‌ها 🪜 (رتبه‌ها)\n"
    "<code>/tasks</code> — تسک‌ها و جایزه‌ها 🎯 (تسک‌ها)\n"
    "<code>/history</code> — تاریخچه تغییرات من 🧾 (تاریخچه)\n"
    "<code>/dice</code> — شرط‌بندی شانسی 🎰 (شرط)\n"
    "<code>/fal</code> — فال روزانه 🔮 (فال)\n"
    "<code>/gift</code> — هدیه دادن به دوستان 🎁\n"
    "<code>/ttt</code> — بازی دوز با بات یا دوست ❌⭕️ (دوز)"
)

HELP_ADMIN = (
    "🛠 <b>مدیریت گروه</b>\n\n"
    "<code>/settings</code> — پنل تنظیمات ⚙️ (تنظیمات)\n"
    "<code>/setrange</code> — بازه عدد روزانه\n"
    "<code>/setunit</code> — نام و ایموجی واحد امتیاز\n"
    "<code>/setmsgpoints</code> — امتیاز هر پیام\n"
    "<code>/toggle</code> — روشن/خاموش کردن قابلیت‌ها (سوییچ)\n"
    "<code>/addrank</code> — افزودن رتبه جدید\n"
    "<code>/delrank</code> — حذف یک رتبه\n"
    "<code>/resetranks</code> — بازگشت رتبه‌ها به پیش‌فرض\n"
    "<code>/settext</code> — تنظیم متن دلخواه\n"
    "<code>/deltext</code> — بازگرداندن متن به پیش‌فرض\n"
    "<code>/texts</code> — لیست کلیدهای متن\n"
    "<code>/give</code> — دادن امتیاز به کاربر (بده)\n"
    "<code>/take</code> — گرفتن امتیاز از کاربر (بگیر)\n"
    "<code>/setbalance</code> — تنظیم مستقیم موجودی\n"
    "<code>/syncall</code> — هماهنگ‌سازی دسترسی همه اعضا\n"
    "<code>/botadmins</code> — لیست ادمین‌های بات (ادمین‌های بات)\n\n"
    "💡 این دستورها فقط برای <b>ادمین‌های بات</b> گروه کار می‌کند."
)

HELP_OWNER = (
    "👑 <b>مالک بات</b>\n\n"
    "<code>/promote</code> — ترفیع کاربر به ادمین بات 🏅 (تنظیم ادمین)\n"
    "<code>/demote</code> — عزل ادمین بات 📉\n"
    "<code>/botadmins</code> — لیست ادمین‌های بات\n"
    "<code>/activate</code> — فعال‌سازی کاربر 🔑 (فعالسازی)\n"
    "<code>/deactivate</code> — غیرفعال‌سازی کاربر ⛔️\n"
    "<code>/addad</code> — افزودن تبلیغ 📣\n"
    "<code>/ads</code> — لیست تبلیغ‌ها 🗂\n"
    "<code>/delad</code> — حذف تبلیغ 🗑\n"
    "<code>/adtoggle</code> — فعال/غیرفعال کردن تبلیغ 🔄\n"
    "<code>/adinterval</code> — فاصله ارسال خودکار تبلیغ ⏱\n"
    "<code>/adnow</code> — ارسال فوری تبلیغ 🚀\n"
    "<code>/addtask</code> — افزودن تسک جایزه‌دار 🎯\n"
    "<code>/tasklist</code> — لیست همه تسک‌ها\n"
    "<code>/deltask</code> — حذف تسک\n"
    "<code>/toggletask</code> — فعال/غیرفعال کردن تسک 🔄\n"
    "<code>/stats</code> — آمار کلی بات 📊 (آمار)\n"
    "<code>/broadcast</code> — پیام همگانی به گروه‌ها 📢\n"
    "<code>/export</code> — خروجی تنظیمات گروه 📤 (خروجی تنظیمات)\n"
    "<code>/import</code> — بارگذاری تنظیمات 📥 (بارگذاری تنظیمات)\n\n"
    "💡 خروجی گرفتن از تنظیمات یک گروه و اعمال همان تنظیمات روی گروه دیگر.\n\n"
    "⚠️ همه دستورات مالک فقط با آیدی مالک کار می‌کنند."
)

HELP_TOOLS = (
    "🧰 <b>ابزارها</b>\n\n"
    "💱 <b>نرخ ارز و طلا</b>\n"
    "<code>/rates</code> — نرخ لحظه‌ای ارز، طلا و سکه (به تومان) (ارز)\n"
)

HELP_PAGES: dict[str, str] = {
    "game": HELP_GAME,
    "admin": HELP_ADMIN,
    "owner": HELP_OWNER,
    "tools": HELP_TOOLS,
}


def _help_main_markup() -> InlineKeyboardMarkup:
    """دکمه‌های دسته‌بندی صفحه اصلی راهنما."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 بازی و سرگرمی", callback_data="help:game")],
            [InlineKeyboardButton(text="🛠 مدیریت گروه", callback_data="help:admin")],
            [InlineKeyboardButton(text="👑 مالک بات", callback_data="help:owner")],
            [InlineKeyboardButton(text="🧰 ابزارها", callback_data="help:tools")],
        ]
    )


def _help_back_markup() -> InlineKeyboardMarkup:
    """دکمه بازگشت زیر هر دسته راهنما."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="help:main")]
        ]
    )


async def promo_reply_markup(bot: Bot, config: Config) -> InlineKeyboardMarkup:
    """کیبورد پیام تبلیغاتی شروع (افزودن به گروه + دکمه اختیاری تماس با مالک)."""
    me = await bot.me()
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="➕ افزودن به گروه",
                url=f"https://t.me/{me.username}?startgroup=true",
            )
        ]
    ]
    if config.owner_contact:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📞 تماس با مالک",
                    url=owner_contact_url(config.owner_contact),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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

    user = message.from_user
    if user is None or not (config.is_owner(user.id) or await db.is_activated(user.id)):
        # کاربر فعال‌نشده: فقط پیام تبلیغاتی و راه تماس با مالک.
        await message.answer(
            render_start_promo(config.owner_contact),
            reply_markup=await promo_reply_markup(message.bot, config),
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
        f"🌱 سلام {safe(user.full_name)}!\n\n"
        f"من <b>{safe(config.bot_name)}</b> هستم؛ بات فان و مدیریت گروه.\n\n"
        "هر روز به اعضای گروه یک عدد تصادفی می‌دم (گاهی مثبت، گاهی منفی!)، "
        "رتبه‌بندی می‌کنم و با بالا رفتن رتبه، دسترسی‌های گروه رو باز می‌کنم 🔓\n\n"
        "منو به گروهت اضافه کن و ادمین کن تا شروع کنیم 🚀",
        reply_markup=keyboard,
    )


@router.message(Command("help", "rahnama"))
@router.message(F.text.in_({"راهنما", "کمک"}))
async def cmd_help(message: Message) -> None:
    """صفحه اصلی راهنما با دکمه‌های دسته‌بندی (بدون سد دسترسی)."""
    await message.reply(HELP_INTRO, reply_markup=_help_main_markup())


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery) -> None:
    """راهنما از طریق دکمه شیشه‌ای قدیمی؛ صفحه اصلی را پیام تازه می‌فرستد."""
    if call.message is not None:
        await call.message.answer(HELP_INTRO, reply_markup=_help_main_markup())
    await call.answer()


@router.callback_query(F.data.startswith("help:"))
async def cb_help_category(call: CallbackQuery) -> None:
    """نمایش دسته‌های راهنما با ویرایش همان پیام (بدون پیام جدید)."""
    if call.data is None or not isinstance(call.message, Message):
        await call.answer()
        return
    page = call.data.split(":", 1)[1]
    if page == "main":
        text, markup = HELP_INTRO, _help_main_markup()
    elif page in HELP_PAGES:
        text, markup = HELP_PAGES[page], _help_back_markup()
    else:
        await call.answer()
        return
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:  # noqa: BLE001 - ویرایش تکراری یا پیام قدیمی حیاتی نیست
        pass
    await call.answer()
