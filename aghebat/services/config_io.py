"""خروجی گرفتن و بارگذاری تنظیمات یک گروه به‌صورت فایل JSON.

ابزار مالک بات است: تنظیمات گروه (واحد امتیاز، بازه روزانه، رتبه‌ها و
متن‌های سفارشی) را در یک ساختار JSON می‌ریزد تا روی گروه دیگری اعمال شود.
عمداً عنوان گروه و وضعیت روشن/خاموش و همچنین موجودی اعضا جابه‌جا نمی‌شوند.
"""
from __future__ import annotations

import html
import json
import time
from typing import Any

from ..db import Database
from ..texts import DEFAULT_TEXTS
from .ranks import PERM_FIELDS

# فیلدهای قابل انتقال؛ آگاهانه بدون title و enabled.
EXPORTABLE_CHAT_FIELDS: tuple[str, ...] = (
    "unit_name",
    "unit_emoji",
    "daily_min",
    "daily_max",
    "msg_points",
    "msg_cooldown",
    "enforce_ranks",
    "fun_mode",
)

KIND_KEY = "aghebat_config"
KIND_VALUE = 1
VERSION_KEY = "version"
VERSION_VALUE = 1
MAX_RANKS = 100

_TEXT_FIELDS: tuple[str, ...] = ("unit_name", "unit_emoji")
_INT_FIELDS: tuple[str, ...] = tuple(
    field for field in EXPORTABLE_CHAT_FIELDS if field not in _TEXT_FIELDS
)
_REQUIRED_KEYS: tuple[str, ...] = (KIND_KEY, VERSION_KEY, "settings", "ranks", "texts")


def _is_int(value: Any) -> bool:
    """عدد صحیح واقعی (بدون در نظر گرفتن bool که زیرکلاس int است)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _load_perms(raw: Any) -> dict[str, bool]:
    """دسترسی‌های ذخیره‌شده (JSON یا dict) را به دیکشنری امن تبدیل می‌کند."""
    if isinstance(raw, dict):
        data: Any = raw
    else:
        try:
            data = json.loads(raw) or {}
        except (json.JSONDecodeError, TypeError):
            data = {}
    if not isinstance(data, dict):
        return {}
    return {key: bool(value) for key, value in data.items() if key in PERM_FIELDS}


async def build_config_export(db: Database, chat_id: int) -> dict[str, Any]:
    """ساختار قابل سریالایز تنظیمات گروه را برمی‌گرداند."""
    chat = await db.get_chat(chat_id)
    if chat is None:
        await db.ensure_chat(chat_id)
        chat = await db.get_chat(chat_id)
    assert chat is not None

    settings = {field: chat[field] for field in EXPORTABLE_CHAT_FIELDS}
    ranks = [
        {
            "title": row["title"],
            "emoji": row["emoji"],
            "min_balance": int(row["min_balance"]),
            "perms": _load_perms(row["perms"]),
        }
        for row in await db.ranks(chat_id)
    ]
    # فقط متن‌های بازنویسی‌شده (ردیف‌های جدول texts) و فقط کلیدهای معتبر.
    custom = await db.all_texts(chat_id)
    texts = {key: value for key, value in custom.items() if key in DEFAULT_TEXTS}

    return {
        KIND_KEY: KIND_VALUE,
        VERSION_KEY: VERSION_VALUE,
        "exported_at": int(time.time()),
        "source_chat_id": chat_id,
        "settings": settings,
        "ranks": ranks,
        "texts": texts,
    }


def validate_config_import(data: Any) -> list[str]:
    """اعتبارسنجی فایل ورودی؛ لیست خطاهای فارسی (لیست خالی یعنی معتبر)."""
    if not isinstance(data, dict):
        return ["❌ فایل تنظیمات معتبر نیست: ساختار باید یک شیء JSON باشد."]

    missing = [key for key in _REQUIRED_KEYS if key not in data]
    if missing:
        return [f"❌ کلید «{html.escape(key)}» در فایل تنظیمات نیست." for key in missing]

    errors: list[str] = []
    if data[KIND_KEY] != KIND_VALUE:
        errors.append("❌ این فایل مربوط به تنظیمات بات عاقبت نیست.")
    if data[VERSION_KEY] != VERSION_VALUE:
        errors.append(
            f"❌ نسخه فایل پشتیبانی نمی‌شود: <code>{html.escape(str(data[VERSION_KEY]))}</code> "
            "(نسخه ۱ مجاز است)."
        )

    settings = data["settings"]
    if not isinstance(settings, dict):
        errors.append("❌ بخش settings باید یک شیء باشد.")
    else:
        errors.extend(_validate_settings(settings))

    ranks = data["ranks"]
    if not isinstance(ranks, list):
        errors.append("❌ بخش ranks باید یک لیست باشد.")
    else:
        errors.extend(_validate_ranks(ranks))

    texts = data["texts"]
    if not isinstance(texts, dict):
        errors.append("❌ بخش texts باید یک شیء باشد.")
    else:
        errors.extend(_validate_texts(texts))

    return errors


def _validate_settings(settings: dict[str, Any]) -> list[str]:
    """نوع و بازه مقادیر بخش settings را بررسی می‌کند."""
    errors: list[str] = []
    for field in _TEXT_FIELDS:
        if field in settings and not isinstance(settings[field], str):
            errors.append(f"❌ مقدار «{field}» باید متن باشد.")
    for field in _INT_FIELDS:
        if field in settings and not _is_int(settings[field]):
            errors.append(f"❌ مقدار «{field}» باید عدد باشد.")

    low, high = settings.get("daily_min"), settings.get("daily_max")
    if _is_int(low) and _is_int(high) and low > high:
        errors.append("❌ بازه روزانه نامعتبر است: کمینه نباید از بیشینه بزرگ‌تر باشد.")
    for field in ("msg_points", "msg_cooldown"):
        value = settings.get(field)
        if _is_int(value) and value < 0:
            errors.append(f"❌ مقدار «{field}» نباید منفی باشد.")
    return errors


def _validate_ranks(ranks: list[Any]) -> list[str]:
    """عنوان، حداقل موجودی و کلیدهای دسترسی هر رتبه را بررسی می‌کند."""
    errors: list[str] = []
    if len(ranks) > MAX_RANKS:
        errors.append(f"❌ تعداد رتبه‌ها از حد مجاز (<b>{MAX_RANKS}</b>) بیشتر است.")
    for index, rank in enumerate(ranks, start=1):
        if not isinstance(rank, dict):
            errors.append(f"❌ رتبه #{index}: ساختار نامعتبر است.")
            continue
        title = rank.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"❌ رتبه #{index}: عنوان نمی‌تواند خالی باشد.")
        if not _is_int(rank.get("min_balance")):
            errors.append(f"❌ رتبه #{index}: حداقل موجودی باید عدد باشد.")
        perms = rank.get("perms", {})
        if not isinstance(perms, dict):
            errors.append(f"❌ رتبه #{index}: دسترسی‌ها باید یک شیء باشند.")
            continue
        unknown = sorted(str(key) for key in perms if str(key) not in PERM_FIELDS)
        if unknown:
            joined = "، ".join(html.escape(key) for key in unknown)
            errors.append(f"❌ رتبه #{index}: دسترسی ناشناخته: <code>{joined}</code>")
    return errors


def _validate_texts(texts: dict[str, Any]) -> list[str]:
    """کلید متن‌ها را با فهرست کلیدهای مجاز می‌سنجد."""
    errors: list[str] = []
    for key, value in texts.items():
        if key not in DEFAULT_TEXTS:
            errors.append(f"❌ کلید متن ناشناخته: <code>{html.escape(str(key))}</code>")
        elif not isinstance(value, str):
            errors.append(f"❌ متن «{html.escape(str(key))}» باید رشته باشد.")
    return errors


async def apply_config_import(db: Database, chat_id: int, data: dict[str, Any]) -> dict[str, int]:
    """تنظیمات را روی گروه اعمال می‌کند و خلاصه تعدادها را برمی‌گرداند.

    رتبه‌ها و متن‌های سفارشی کاملاً جایگزین می‌شوند؛ اعضا، موجودی‌ها، عنوان و
    وضعیت روشن/خاموش گروه دست‌نخورده می‌مانند.
    """
    if await db.get_chat(chat_id) is None:
        await db.ensure_chat(chat_id)

    settings = data.get("settings") or {}
    applied_settings = 0
    if isinstance(settings, dict):
        for field in EXPORTABLE_CHAT_FIELDS:
            if field not in settings:
                continue
            value = settings[field]
            if field in _TEXT_FIELDS:
                if not isinstance(value, str):
                    continue
            elif not _is_int(value):
                continue
            await db.set_chat_field(chat_id, field, value)
            applied_settings += 1

    ranks = data.get("ranks") or []
    applied_ranks = 0
    if isinstance(ranks, list):
        await db.execute("DELETE FROM ranks WHERE chat_id = ?", (chat_id,))
        for rank in ranks:
            if not isinstance(rank, dict):
                continue
            title = rank.get("title")
            minimum = rank.get("min_balance")
            if not isinstance(title, str) or not title.strip() or not _is_int(minimum):
                continue
            emoji = rank.get("emoji")
            perms = _load_perms(rank.get("perms"))
            await db.add_rank(
                chat_id, title, emoji if isinstance(emoji, str) else "⭐️", minimum, perms
            )
            applied_ranks += 1

    texts = data.get("texts") or {}
    applied_texts = 0
    if isinstance(texts, dict):
        for key in list(await db.all_texts(chat_id)):
            await db.clear_text(chat_id, key)
        for key, value in texts.items():
            if key in DEFAULT_TEXTS and isinstance(value, str):
                await db.set_text(chat_id, key, value)
                applied_texts += 1

    return {"settings": applied_settings, "ranks": applied_ranks, "texts": applied_texts}
