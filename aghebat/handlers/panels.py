"""پنل تنظیمات شیشه‌ای گروه: منوی تودرتو که همه‌جا روی یک پیام ویرایش می‌شود."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import Config
from ..db import Database
from ..services.ranks import load_ranks
from ..texts import DEFAULT_TEXTS
from ..utils import is_group, mention_raw, safe

router = Router(name="panels")

# فیلدهای قابل سوییچ با دکمه شیشه‌ای + برچسب فارسی‌شان
TOGGLE_FIELDS: dict[str, str] = {
    "enabled": "🤖 بات",
    "fun_mode": "😂 حالت فان",
    "enforce_ranks": "🔒 اعمال دسترسی‌ها",
}

# راهنمای دستورها؛ کلید کوتاه در callback_data می‌نشیند (سقف ۶۴ بایت تلگرام).
USAGE_HINTS: dict[str, str] = {
    "setrange": "/setrange -5 20",
    "setmsgpoints": "/setmsgpoints 1 30",
    "setunit": "/setunit نام ایموجی — مثلاً /setunit سکه 🪙",
    "addrank": "/addrank عنوان ایموجی حداقل_موجودی دسترسی‌ها",
    "delrank": "/delrank شناسه",
    "resetranks": "/resetranks",
    "syncall": "/syncall",
    "settext": "/settext کلید متن",
    "give": "/give مقدار — روی پیام کاربر ریپلای کن",
    "take": "/take مقدار — روی پیام کاربر ریپلای کن",
    "setbalance": "/setbalance مقدار — روی پیام کاربر ریپلای کن",
    "promote": "/promote — روی پیام کاربر ریپلای کن",
    "demote": "/demote — روی پیام کاربر ریپلای کن",
}


def _back_button(label: str = "🔙 بازگشت", data: str = "set:main") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=data)


def _usage_button(label: str, hint: str) -> InlineKeyboardButton:
    """دکمه‌ای که فقط فرمت دقیق دستور را به‌صورت اعلان نشان می‌دهد."""
    return InlineKeyboardButton(text=label, callback_data=f"set:use:{hint}")


def _toggle_button(
    label: str, field: str, value: bool, view: str = "state"
) -> InlineKeyboardButton:
    """دکمه سوییچ زنده؛ با هر لمس وضعیت فیلد عوض و همان زیرمنو بازرندر می‌شود."""
    state = "✅" if value else "❌"
    data = f"set:tgl:{field}" if view == "state" else f"set:tgl:{field}:{view}"
    return InlineKeyboardButton(text=f"{label}: {state}", callback_data=data)


async def _view_main(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    chat = await db.ensure_chat(chat_id)
    members = await db.member_count(chat_id)
    text = (
        f"⚙️ <b>تنظیمات عاقبت — {safe(chat['title'])}</b>\n\n"
        "یکی از بخش‌ها را انتخاب کن؛ هر دکمه فرمت دستورش را هم نشانت می‌دهد.\n"
        f"👥 اعضای ثبت‌شده: <b>{members:,}</b>"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎲 بازی روزانه", callback_data="set:daily"),
                InlineKeyboardButton(text="🪜 رتبه‌ها و دسترسی‌ها", callback_data="set:ranks"),
            ],
            [
                InlineKeyboardButton(text="🪙 واحد امتیاز", callback_data="set:unit"),
                InlineKeyboardButton(text="📝 متن‌ها", callback_data="set:texts"),
            ],
            [
                InlineKeyboardButton(text="💰 موجودی اعضا", callback_data="set:balance"),
                InlineKeyboardButton(text="⚙️ وضعیت بات", callback_data="set:state"),
            ],
            [InlineKeyboardButton(text="🏅 ادمین‌های بات", callback_data="set:admins")],
        ]
    )
    return text, markup


async def _view_daily(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    chat = await db.ensure_chat(chat_id)
    text = (
        "🎲 <b>بازی روزانه</b>\n\n"
        f"بازه فعلی: <b>{int(chat['daily_min'])}</b> تا <b>{int(chat['daily_max'])}</b> | "
        f"امتیاز هر پیام: <b>{int(chat['msg_points'])}</b>\n"
        "هر عضو روزی یک‌بار عاقبت می‌گیرد؛ عدد می‌تواند منفی هم باشد!"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _usage_button("🎲 بازه روزانه", "setrange"),
                _usage_button("💬 امتیاز پیام", "setmsgpoints"),
            ],
            [_back_button()],
        ]
    )
    return text, markup


async def _view_ranks(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    chat = await db.ensure_chat(chat_id)
    ranks = await load_ranks(db, chat_id)
    text = (
        "🪜 <b>رتبه‌ها و دسترسی‌ها</b>\n\n"
        "هر رتبه با حداقل موجودی تعریف می‌شود؛ با رسیدن به آن، دسترسی‌های\n"
        "جدید گروه خودکار برای عضو باز می‌شود.\n"
        f"🏅 تعداد رتبه‌های فعلی: <b>{len(ranks)}</b>"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _usage_button("➕ رتبه جدید", "addrank"),
                _usage_button("🗑 حذف رتبه", "delrank"),
            ],
            [
                _usage_button("♻️ ریست رتبه‌ها", "resetranks"),
                _usage_button("🔄 هماهنگ‌سازی", "syncall"),
            ],
            [
                _toggle_button(
                    "🔒 اعمال دسترسی‌ها",
                    "enforce_ranks",
                    bool(chat["enforce_ranks"]),
                    view="ranks",
                )
            ],
            [_back_button()],
        ]
    )
    return text, markup


async def _view_unit(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    chat = await db.ensure_chat(chat_id)
    text = (
        "🪙 <b>واحد امتیاز</b>\n\n"
        f"واحد فعلی: {chat['unit_emoji']} <b>{safe(chat['unit_name'])}</b>\n"
        "نام و ایموجی واحد امتیاز گروه را عوض کن؛ مثلاً «سکه 🪙» یا «قیراغ 🌰»!"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [_usage_button("🪙 تغییر واحد", "setunit")],
            [_back_button()],
        ]
    )
    return text, markup


async def _view_texts(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "📝 <b>متن‌ها</b>\n\n"
        "متن پیام‌های بات (عاقبت روزانه، ترفیع رتبه و...) را می‌توانی\n"
        "مخصوص گروه خودت بازنویسی کنی."
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 دیدن کلیدهای متن", callback_data="set:txtkeys")],
            [_usage_button("✏️ تنظیم متن", "settext")],
            [_back_button()],
        ]
    )
    return text, markup


async def _view_text_keys(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    custom = await db.all_texts(chat_id)
    lines = [
        "📝 <b>کلیدهای متن</b>",
        "",
        "✏️ = شخصی‌سازی‌شده | ▫️ = پیش‌فرض",
        "",
    ]
    lines += [f"{'✏️' if key in custom else '▫️'} <code>{key}</code>" for key in DEFAULT_TEXTS]
    lines += ["", "تغییر: <code>/settext کلید متن</code> | بازگردانی: <code>/deltext کلید</code>"]
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [_usage_button("✏️ تنظیم متن", "settext")],
            [
                _back_button("🔙 بازگشت به متن‌ها", "set:texts"),
                _back_button("🏠 منوی اصلی", "set:main"),
            ],
        ]
    )
    return "\n".join(lines), markup


async def _view_balance(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "💰 <b>موجودی اعضا</b>\n\n"
        "برای کم و زیاد کردن موجودی، روی پیام کاربر ریپلای کن\n"
        "و دستور را همراه مقدار بفرست."
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _usage_button("➕ بده", "give"),
                _usage_button("➖ بگیر", "take"),
            ],
            [_usage_button("🎯 تنظیم موجودی", "setbalance")],
            [_back_button()],
        ]
    )
    return text, markup


async def _view_state(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    chat = await db.ensure_chat(chat_id)
    text = (
        "⚙️ <b>وضعیت بات</b>\n\n"
        "با لمس هر کلید، فوری روشن یا خاموش می‌شود.\n"
        "• بات: پاسخ‌گویی کلی بات در گروه\n"
        "• حالت فان: دستورهای سرگرمی مثل فال و شرط\n"
        "• اعمال دسترسی‌ها: بستن خودکار دسترسی‌های تلگرام بر اساس رتبه"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [_toggle_button("🤖 بات", "enabled", bool(chat["enabled"]))],
            [_toggle_button("😂 حالت فان", "fun_mode", bool(chat["fun_mode"]))],
            [
                _toggle_button(
                    "🔒 اعمال دسترسی‌ها", "enforce_ranks", bool(chat["enforce_ranks"])
                )
            ],
            [_back_button()],
        ]
    )
    return text, markup


async def _view_admins(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🏅 <b>ادمین‌های بات</b>\n\n"
        "ادمین بات کسی است که مالک بات با دستور <code>/promote</code> ترفیعش داده\n"
        "و به دستورهای مدیریتی همین گروه دسترسی دارد."
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _usage_button("🏅 ترفیع ادمین", "promote"),
                _usage_button("📉 عزل ادمین", "demote"),
            ],
            [InlineKeyboardButton(text="📋 دیدن ادمین‌ها", callback_data="set:adminlist")],
            [_back_button()],
        ]
    )
    return text, markup


async def _view_admin_list(db: Database, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    rows = await db.bot_admins(chat_id)
    if rows:
        lines = [f"🏅 <b>ادمین‌های بات این گروه ({len(rows)} نفر):</b>", ""]
        lines += [
            f"{index}. {mention_raw(int(row['user_id']), row['full_name'])}"
            for index, row in enumerate(rows, start=1)
        ]
    else:
        lines = [
            "📭 هنوز هیچ ادمین باتی در این گروه ثبت نشده.",
            "مالک می‌تواند با ریپلای روی پیام کاربر و دستور <code>/promote</code> "
            "اولین نفر را ترفیع دهد.",
        ]
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _back_button("🔙 بازگشت به ادمین‌ها", "set:admins"),
                _back_button("🏠 منوی اصلی", "set:main"),
            ]
        ]
    )
    return "\n".join(lines), markup


_VIEWS: dict[str, Callable[[Database, int], Awaitable[tuple[str, InlineKeyboardMarkup]]]] = {
    "main": _view_main,
    "daily": _view_daily,
    "ranks": _view_ranks,
    "unit": _view_unit,
    "texts": _view_texts,
    "txtkeys": _view_text_keys,
    "balance": _view_balance,
    "state": _view_state,
    "admins": _view_admins,
    "adminlist": _view_admin_list,
}


async def _edit_panel(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """همان پیام پنل را ویرایش می‌کند؛ خطای ویرایش بی‌صدا رد می‌شود."""
    if not isinstance(call.message, Message):
        return
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:  # noqa: BLE001 - محتوای تکراری یا پیام قدیمی حیاتی نیست
        pass


@router.message(Command("settings", "panel"))
async def cmd_settings(message: Message, db: Database, config: Config) -> None:
    """باز کردن پنل تنظیمات گروه (فقط مالک یا ادمین بات، فقط داخل گروه)."""
    if not is_group(message.chat):
        await message.reply("⚙️ این دستور فقط داخل گروه کار می‌کنه.")
        return
    user = message.from_user
    if user is None:
        return
    if not (config.is_owner(user.id) or await db.is_bot_admin(message.chat.id, user.id)):
        await message.reply(
            "🚫 این دستورها فقط مخصوص <b>ادمین‌های بات</b> است!\n"
            "ادمین بات کسی است که مالک بات با دستور <code>/promote</code> ترفیعش داده."
        )
        return
    await db.ensure_chat(message.chat.id, message.chat.title or "")
    text, markup = await _view_main(db, message.chat.id)
    await message.reply(text, reply_markup=markup)


@router.callback_query(F.data.startswith("set:"))
async def cb_panel(call: CallbackQuery, db: Database, config: Config) -> None:
    """ناوبری پنل، راهنمای دستورها و سوییچ‌های زنده روی همان پیام."""
    if call.data is None or not isinstance(call.message, Message):
        await call.answer("این پنل دیگر در دسترس نیست 🤷")
        return
    chat = call.message.chat
    if not is_group(chat):
        await call.answer("⚙️ پنل تنظیمات فقط داخل گروه کار می‌کند.")
        return
    user = call.from_user
    if not (config.is_owner(user.id) or await db.is_bot_admin(chat.id, user.id)):
        await call.answer("🚫 این پنل فقط مخصوص ادمین‌های بات است!", show_alert=True)
        return
    await db.ensure_chat(chat.id, chat.title or "")

    parts = call.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    # دکمه‌های راهنما فقط اعلان می‌دهند و پیام را ویرایش نمی‌کنند.
    if action == "use":
        hint = parts[2] if len(parts) > 2 else ""
        await call.answer(USAGE_HINTS.get(hint, "راهنمای این دستور در /help است."))
        return

    # سوییچ زنده: مقدار فیلد را برمی‌گرداند و همان زیرمنو را بازرندر می‌کند.
    if action == "tgl":
        field = parts[2] if len(parts) > 2 else ""
        if field not in TOGGLE_FIELDS:
            await call.answer()
            return
        view = parts[3] if len(parts) > 3 else "state"
        chat_row = await db.ensure_chat(chat.id)
        new_value = 0 if chat_row[field] else 1
        await db.set_chat_field(chat.id, field, new_value)
        state = "روشن شد ✅" if new_value else "خاموش شد ⛔️"
        await call.answer(f"{TOGGLE_FIELDS[field]} {state}")
        builder = _view_ranks if view == "ranks" else _view_state
        text, markup = await builder(db, chat.id)
        await _edit_panel(call, text, markup)
        return

    builder = _VIEWS.get(action)
    if builder is None:
        await call.answer()
        return
    text, markup = await builder(db, chat.id)
    await call.answer()
    await _edit_panel(call, text, markup)
