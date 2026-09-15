"""دستورهای مالک برای خروجی گرفتن و بارگذاری تنظیمات گروه (فایل JSON).

`/export` تنظیمات یک گروه را به‌صورت فایل می‌فرستد (در گروه برای مالک و
ادمین بات، در چت خصوصی فقط مالک با انتخاب گروه) و `/import` فایل JSON را
روی گروه مقصد اعمال می‌کند (فقط مالک، در هر چتی). تایید نهایی با دکمه
شیشه‌ای است و بارگذاری‌های در انتظار در یک دیکشنری ماژول‌سطح با انقضای
۱۰ دقیقه‌ای نگهداری می‌شوند (بدون FSM Storage).
"""
from __future__ import annotations

import json
import secrets
import time
from io import BytesIO
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import Config
from ..db import Database
from ..services.config_io import (
    apply_config_import,
    build_config_export,
    validate_config_import,
)
from ..utils import is_group, parse_int, safe

router = Router(name="configio")

EXPORT_FILENAME = "aghebat-config.json"
MAX_IMPORT_BYTES = 512 * 1024
PENDING_TTL = 600  # ۱۰ دقیقه
MAX_PENDING = 50
GROUP_PICKER_LIMIT = 10
# اعتبار ۵۱۲ کیلوبایت بر حسب بایت؛ برای نمایش در پیام خطا یک‌بار حساب می‌شود.
MAX_IMPORT_KB = MAX_IMPORT_BYTES // 1024

# بارگذاری‌های در انتظار تایید: gid -> {data, owner_id, chat_id, expires}
PENDING_IMPORTS: dict[str, dict[str, Any]] = {}


def _prune_pending() -> None:
    """ورودی‌های منقضی را با نگاه تنبل پاک می‌کند."""
    now = time.time()
    for gid in [key for key, item in PENDING_IMPORTS.items() if item["expires"] <= now]:
        PENDING_IMPORTS.pop(gid, None)


def _store_pending(data: dict[str, Any], owner_id: int, chat_id: int) -> str:
    """بارگذاری جدید را ثبت و شناسه ۸ رقمی هگز آن را برمی‌گرداند."""
    _prune_pending()
    if len(PENDING_IMPORTS) >= MAX_PENDING:
        oldest = min(PENDING_IMPORTS, key=lambda key: PENDING_IMPORTS[key]["expires"])
        PENDING_IMPORTS.pop(oldest, None)
    gid = secrets.token_hex(4)
    PENDING_IMPORTS[gid] = {
        "data": data,
        "owner_id": owner_id,
        "chat_id": chat_id,
        "expires": time.time() + PENDING_TTL,
    }
    return gid


def _get_pending(gid: str) -> dict[str, Any] | None:
    """بارگذاری در انتظار را (پس از پاک‌سازی منقضی‌ها) برمی‌گرداند."""
    _prune_pending()
    return PENDING_IMPORTS.get(gid)


def _group_label(row: Any) -> str:
    """عنوان گروه برای دکمه/پیام؛ اگر خالی بود آیدی عددی."""
    title = str(row["title"] or "").strip()
    return title or str(int(row["chat_id"]))


def _button_label(text: str) -> str:
    """عنوان دکمه را به سقف بایت‌ی تلگرام نزدیک نگه می‌دارد."""
    return text if len(text) <= 25 else text[:24] + "…"


async def _known_groups(db: Database) -> list[Any]:
    """گروه‌های فعال، تازه‌ترین اول."""
    chats = await db.all_chats()
    return sorted(chats, key=lambda row: int(row["created_at"] or 0), reverse=True)


async def _send_export(message: Message, db: Database, chat_id: int) -> None:
    """فایل JSON خروجی گروه را به همان چت می‌فرستد."""
    export = await build_config_export(db, chat_id)
    payload = json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8")
    chat = await db.get_chat(chat_id)
    title = safe(str(chat["title"])) if chat is not None else ""
    await message.reply_document(
        BufferedInputFile(payload, filename=EXPORT_FILENAME),
        caption=f"📤 خروجی تنظیمات گروه <b>{title or chat_id}</b>",
    )


async def _confirm_view(db: Database, gid: str, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """خلاصه تایید بارگذاری برای گروه مقصد."""
    entry = PENDING_IMPORTS.get(gid) or {}
    data = entry.get("data") or {}
    settings = data.get("settings") or {}
    ranks = data.get("ranks") or []
    texts = data.get("texts") or {}
    chat = await db.get_chat(chat_id)
    title = safe(str(chat["title"])) if chat is not None else ""
    unit_name = safe(str(settings.get("unit_name", "")))
    unit_emoji = str(settings.get("unit_emoji", ""))
    text = (
        "📥 <b>تایید بارگذاری تنظیمات</b>\n\n"
        f"🎯 گروه مقصد: <b>{title or chat_id}</b>\n"
        f"🪙 واحد امتیاز: {unit_emoji} <b>{unit_name}</b>\n"
        f"🎲 بازه روزانه: <b>{settings.get('daily_min')}</b> تا "
        f"<b>{settings.get('daily_max')}</b>\n"
        f"💬 امتیاز پیام: <b>{settings.get('msg_points')}</b> "
        f"(هر {settings.get('msg_cooldown')} ثانیه)\n"
        f"🔒 اعمال دسترسی‌ها: {'✅' if settings.get('enforce_ranks') else '❌'} | "
        f"😂 حالت فان: {'✅' if settings.get('fun_mode') else '❌'}\n"
        f"🪜 رتبه‌ها: <b>{len(ranks)}</b> | 📝 متن‌های سفارشی: <b>{len(texts)}</b>\n\n"
        "⚠️ رتبه‌ها و متن‌های سفارشی فعلی این گروه جایگزین می‌شوند؛ موجودی اعضا، "
        "عنوان و وضعیت روشن/خاموش گروه دست‌نخورده می‌ماند."
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ اعمال کن", callback_data=f"cfg:imp:{gid}:ok"),
                InlineKeyboardButton(text="❌ لغو", callback_data=f"cfg:imp:{gid}:no"),
            ]
        ]
    )
    return text, markup


async def _edit_message(call: CallbackQuery, text: str) -> None:
    """پیام دکمه‌دار را ویرایش می‌کند؛ خطای پیام قدیمی بی‌صدا رد می‌شود."""
    if not isinstance(call.message, Message):
        return
    try:
        await call.message.edit_text(text)
    except Exception:  # noqa: BLE001 - ویرایش تکراری یا پیام قدیمی حیاتی نیست
        pass


@router.message(Command("export"))
async def cmd_export(message: Message, db: Database, config: Config) -> None:
    """خروجی تنظیمات گروه به‌صورت فایل JSON."""
    user = message.from_user
    if user is None:
        return

    if is_group(message.chat):
        if not (config.is_owner(user.id) or await db.is_bot_admin(message.chat.id, user.id)):
            await message.reply(
                "🚫 خروجی تنظیمات فقط برای <b>مالک بات</b> و <b>ادمین‌های بات</b> همین گروه است."
            )
            return
        await db.ensure_chat(message.chat.id, message.chat.title or "")
        await _send_export(message, db, message.chat.id)
        return

    if not config.is_owner(user.id):
        return
    chats = await _known_groups(db)
    if not chats:
        await message.answer(
            "📭 هنوز هیچ گروهی برای بات ثبت نشده.\n"
            "بات را به یک گروه اضافه کن و <code>/start</code> بزن."
        )
        return
    rows = [
        [
            InlineKeyboardButton(
                text=_button_label(_group_label(row)),
                callback_data=f"cfg:exp:{int(row['chat_id'])}",
            )
        ]
        for row in chats[:GROUP_PICKER_LIMIT]
    ]
    await message.answer(
        "📤 <b>خروجی تنظیمات</b>\n\nگروه موردنظر را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(Command("import"))
async def cmd_import(message: Message, bot: Bot, db: Database, config: Config) -> None:
    """بارگذاری فایل JSON تنظیمات روی گروه (فقط مالک، در هر چتی)."""
    user = message.from_user
    if user is None or not config.is_owner(user.id):
        return

    reply = message.reply_to_message
    if reply is None:
        await message.reply(
            "📥 برای بارگذاری، فایل JSON خروجی را روی پیام ریپلای کن و <code>/import</code> بزن."
        )
        return
    document = reply.document
    if document is None:
        await message.reply("📄 این پیام فایل نیست! فایل <code>.json</code> خروجی را ریپلای کن.")
        return
    if document.file_size is not None and document.file_size > MAX_IMPORT_BYTES:
        await message.reply(
            f"❌ فایل خیلی بزرگ است؛ حداکثر <b>{MAX_IMPORT_KB}</b> کیلوبایت مجاز است."
        )
        return

    try:
        stream = await bot.download(document)
    except Exception:  # noqa: BLE001 - خطای شبکه/تلگرام باید پیام محترمانه بدهد
        await message.reply("❌ دانلود فایل ناموفق بود؛ چند لحظه بعد دوباره تلاش کن.")
        return
    raw = stream.getvalue() if isinstance(stream, BytesIO) else stream.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        await message.reply("❌ فایل باید متن UTF-8 باشد.")
        return
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        await message.reply("❌ محتوای فایل JSON معتبر نیست.")
        return

    errors = validate_config_import(data)
    if errors:
        await message.reply("❌ <b>فایل تنظیمات معتبر نیست:</b>\n\n" + "\n".join(errors))
        return

    target = message.chat.id if is_group(message.chat) else 0
    gid = _store_pending(data, user.id, target)
    if target:
        text_view, markup = await _confirm_view(db, gid, target)
        await message.reply(text_view, reply_markup=markup)
        return

    chats = await _known_groups(db)
    if not chats:
        PENDING_IMPORTS.pop(gid, None)
        await message.reply(
            "📭 هنوز هیچ گروهی برای بات ثبت نشده؛ بدون گروه مقصد نمی‌توان تنظیمات را اعمال کرد."
        )
        return
    rows = [
        [
            InlineKeyboardButton(
                text=_button_label(_group_label(row)),
                callback_data=f"cfg:pick:{gid}:{int(row['chat_id'])}",
            )
        ]
        for row in chats[:GROUP_PICKER_LIMIT]
    ]
    await message.reply(
        "📥 <b>گروه مقصد را انتخاب کن</b>\n\nتنظیمات روی گروه انتخابی اعمال می‌شود:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _cb_export(call: CallbackQuery, db: Database, config: Config, parts: list[str]) -> None:
    """ارسال فایل خروجی گروه انتخاب‌شده (فقط مالک)."""
    if not config.is_owner(call.from_user.id):
        await call.answer("👑 این خروجی فقط برای مالک بات است.", show_alert=True)
        return
    chat_id = parse_int(parts[2]) if len(parts) > 2 else None
    if chat_id is None:
        await call.answer()
        return
    if await db.get_chat(chat_id) is None:
        await call.answer("❌ این گروه دیگر ثبت نشده.", show_alert=True)
        return
    if not isinstance(call.message, Message):
        await call.answer()
        return
    await call.answer("در حال ارسال فایل 📤")
    await _send_export(call.message, db, chat_id)


async def _cb_pick(call: CallbackQuery, db: Database, parts: list[str]) -> None:
    """انتخاب گروه مقصد در چت خصوصی و نمایش خلاصه تایید."""
    gid = parts[2] if len(parts) > 2 else ""
    chat_id = parse_int(parts[3]) if len(parts) > 3 else None
    entry = _get_pending(gid) if gid else None
    if entry is None or chat_id is None:
        await call.answer("⏳ این درخواست منقضی شده؛ دوباره /import بزن.", show_alert=True)
        return
    if call.from_user.id != entry["owner_id"]:
        await call.answer("🚫 این تایید فقط برای مالک بات است.", show_alert=True)
        return
    if await db.get_chat(chat_id) is None:
        await call.answer("❌ این گروه دیگر ثبت نشده.", show_alert=True)
        return
    entry["chat_id"] = chat_id
    text, markup = await _confirm_view(db, gid, chat_id)
    if isinstance(call.message, Message):
        try:
            await call.message.edit_text(text, reply_markup=markup)
        except Exception:  # noqa: BLE001 - پیام قدیمی حیاتی نیست
            pass
    await call.answer()


async def _cb_import(call: CallbackQuery, db: Database, parts: list[str]) -> None:
    """تایید یا لغو نهایی بارگذاری و اعمال آن روی گروه مقصد."""
    gid = parts[2] if len(parts) > 2 else ""
    decision = parts[3] if len(parts) > 3 else ""
    entry = _get_pending(gid) if gid else None
    if entry is None:
        await call.answer("⏳ این درخواست منقضی شده؛ دوباره /import بزن.", show_alert=True)
        return
    if call.from_user.id != entry["owner_id"]:
        await call.answer("🚫 این تایید فقط برای مالک بات است.", show_alert=True)
        return

    if decision == "no":
        PENDING_IMPORTS.pop(gid, None)
        await _edit_message(call, "❌ بارگذاری تنظیمات لغو شد.")
        await call.answer()
        return
    if decision != "ok":
        await call.answer()
        return

    chat_id = int(entry["chat_id"] or 0)
    PENDING_IMPORTS.pop(gid, None)
    if not chat_id:
        await call.answer("❌ گروه مقصد مشخص نیست.", show_alert=True)
        return

    summary = await apply_config_import(db, chat_id, entry["data"])
    chat = await db.get_chat(chat_id)
    title = safe(str(chat["title"])) if chat is not None else ""
    await _edit_message(
        call,
        "✅ <b>تنظیمات با موفقیت اعمال شد!</b>\n\n"
        f"🎯 گروه: <b>{title or chat_id}</b>\n"
        f"⚙️ فیلدهای تنظیمات: <b>{summary['settings']}</b>\n"
        f"🪜 رتبه‌ها: <b>{summary['ranks']}</b>\n"
        f"📝 متن‌های سفارشی: <b>{summary['texts']}</b>\n\n"
        "موجودی اعضا، عنوان و وضعیت گروه دست‌نخورده ماند.",
    )
    await call.answer("تنظیمات اعمال شد ✅")


@router.callback_query(F.data.startswith("cfg:"))
async def cb_config_io(call: CallbackQuery, db: Database, config: Config) -> None:
    """مسیردهی دکمه‌های خروجی/انتخاب گروه/تایید بارگذاری."""
    if call.data is None:
        await call.answer()
        return
    parts = call.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "exp":
        await _cb_export(call, db, config, parts)
    elif action == "pick":
        await _cb_pick(call, db, parts)
    elif action == "imp":
        await _cb_import(call, db, parts)
    else:
        await call.answer()
