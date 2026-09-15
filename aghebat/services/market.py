"""نرخ لحظه‌ای ارز، طلا و سکه از bonbast.com — با نمایش به تومان.

منبع، مقادیر ریالی می‌دهد؛ همه‌جا با تقسیم بر ۱۰ به تومان تبدیل می‌شوند، جز
سه قلم جهانی: «ounce» و «bitcoin» دلاری‌اند و «bourse» شاخص بورس است و هیچ‌کدام
نباید بر ۱۰ تقسیم شوند.

جریان شبکه دو مرحله‌ای است: صفحه اصلی با User-Agent مرورگر گرفته می‌شود تا توکن
درون‌خطی (مقدار مرکب `param`) از جاوااسکریپت صفحه استخراج شود، سپس همان توکن با
POST در همان نشست به /json فرستاده می‌شود. اگر منبع پاسخ کهنه `{"reset": "1"}`
بدهد، یک‌بار دیگر صفحه اصلی گرفته و POST تکرار می‌شود.

هر فراخوانی دستورها از کش ۱۸۰ ثانیه‌ای ماژول استفاده می‌کند تا فشار روی منبع و
تأخیر پاسخ کم بماند.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import aiohttp

from ..utils import format_number

logger = logging.getLogger(__name__)

HOME_URL = "https://bonbast.com/"
JSON_URL = "https://bonbast.com/json"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# توکن درخواست، درون جاوااسکریپت صفحه اصلی: $.post('/json', {param: "<توکن>" ...})
PARAM_PATTERN = re.compile(r'param:\s*"([^"]+)"')

REQUEST_TIMEOUT_SECONDS = 15
CACHE_TTL_SECONDS = 180

# ارزها: (کد, برچسب نمایشی با پرچم). کلید فروش «<کد>1» و کلید خرید «<کد>2» است.
CURRENCIES: tuple[tuple[str, str], ...] = (
    ("usd", "🇺🇸 دلار"),
    ("eur", "🇪🇺 یورو"),
    ("gbp", "🇬🇧 پوند انگلیس"),
    ("try", "🇹🇷 لیر ترکیه"),
    ("aed", "🇦🇪 درهم امارات"),
    ("cny", "🇨🇳 یوان چین"),
    ("rub", "🇷🇺 روبل روسیه"),
    ("sar", "🇸🇦 ریال عربستان"),
    ("azn", "🇦🇿 مانات آذربایجان"),
)

# طلا و سکه: (کلید, کلید فروش, کلید خرید یا None, برچسب نمایشی). همه ریالی‌اند.
# «کلید» نام پایدار داخلی است تا قالب نمایش به نام‌گذاری منبع گره نخورد.
GOLD_ITEMS: tuple[tuple[str, str, str | None, str], ...] = (
    ("emami", "emami1", "emami12", "تمام سکه امامی"),
    ("azadi", "azadi1", "azadi12", "سکه بهار آزادی"),
    ("nim", "azadi1_2", "azadi1_22", "نیم سکه"),
    ("rob", "azadi1_4", "azadi1_42", "ربع سکه"),
    ("gerami", "azadi1g", "azadi1g2", "سکه گرمی"),
    ("gol18", "gol18", None, "طلای ۱۸ عیار (گرم)"),
    ("mithqal", "mithqal", None, "مثقال طلا"),
)

# اقلام جهانی: (کلید, برچسب, یکا). این‌ها هرگز ریال به تومان تبدیل نمی‌شوند.
GLOBAL_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("ounce", "🥇 انس طلا", "دلار"),
    ("bitcoin", "🪙 بیت‌کوین", "دلار"),
    ("bourse", "📈 شاخص بورس", "واحد"),
)

FOOTNOTE = "💡 قیمت‌ها از ریال به تومان تبدیل شده‌اند."


class MarketError(Exception):
    """گرفتن یا تفسیر نرخ‌ها از منبع ناموفق بود."""


def _to_rial(value: Any) -> int | None:
    """مقدار ریالی منبع را به عدد صحیح تبدیل می‌کند؛ نامعتبر → None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    """مقدار اعشاری (انس، بیت‌کوین، شاخص) را تبدیل می‌کند؛ نامعتبر → None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_market_payload(raw: dict) -> dict:
    """پاسخ خام منبع را به ساختار تمیز و بدون شبکه تبدیل می‌کند.

    خروجی: ``currencies`` (کد → (فروش, خرید) ریالی)، ``gold`` (کلید → زوج یا
    تک‌عدد ریالی)، ``globals`` (کلید → عدد اعشاری خام)، و ``last_modified``.
    کلیدهای غایب حذف می‌شوند و هرگز مقدار ساختگی ساخته نمی‌شود؛ اگر یک طرف
    زوج (فروش یا خرید) در پاسخ نباشد، همان طرف None می‌ماند.
    """
    currencies: dict[str, tuple[int | None, int | None]] = {}
    for code, _label in CURRENCIES:
        sell = _to_rial(raw.get(f"{code}1"))
        buy = _to_rial(raw.get(f"{code}2"))
        if sell is None and buy is None:
            continue
        currencies[code] = (sell, buy)

    gold: dict[str, tuple[int | None, int | None] | int] = {}
    for key, sell_key, buy_key, _label in GOLD_ITEMS:
        sell = _to_rial(raw.get(sell_key))
        buy = _to_rial(raw.get(buy_key)) if buy_key else None
        if sell is None and buy is None:
            continue
        # اقلام تک‌نرخی (مثقال، طلای ۱۸ عیار) عدد ساده می‌مانند.
        gold[key] = (sell, buy) if buy_key else sell  # type: ignore[assignment]

    globals_: dict[str, float] = {}
    for key, _label, _unit in GLOBAL_ITEMS:
        value = _to_float(raw.get(key))
        if value is not None:
            globals_[key] = value

    last_modified = str(raw.get("last_modified") or "").strip()
    return {
        "currencies": currencies,
        "gold": gold,
        "globals": globals_,
        "last_modified": last_modified,
    }


def _toman(rial: int) -> str:
    """مقدار ریالی را به تومان با جداکننده هزارگان تبدیل می‌کند."""
    return format_number(rial // 10)


def _pair_line(label: str, sell: int | None, buy: int | None) -> str:
    """خط یک قلم دوطرفه (فروش × خرید) یا تک‌طرفه، به تومان."""
    if sell is not None and buy is not None:
        return f"<b>{label}</b>: {_toman(sell)} × {_toman(buy)} تومان"
    value = sell if sell is not None else buy
    if value is None:
        return ""
    return f"<b>{label}</b>: {_toman(value)} تومان"


def _decimal(value: float) -> str:
    """عدد اعشاری با جداکننده هزارگان و حداکثر دو رقم، بدون صفر اضافه."""
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def format_market(snapshot: dict) -> str:
    """اسنپ‌شات را به متن HTML سه‌بخشی (ارز، طلا و سکه، جهانی) تبدیل می‌کند."""
    currencies: dict[str, tuple[int | None, int | None]] = snapshot.get("currencies") or {}
    gold: dict[str, tuple[int | None, int | None] | int] = snapshot.get("gold") or {}
    globals_: dict[str, float] = snapshot.get("globals") or {}

    lines: list[str] = ["💹 <b>نرخ لحظه‌ای بازار</b>"]

    currency_lines = [
        _pair_line(label, *currencies[code])
        for code, label in CURRENCIES
        if code in currencies
    ]
    currency_lines = [line for line in currency_lines if line]
    if currency_lines:
        lines += ["", "💱 <b>ارز</b>", *currency_lines]

    gold_lines: list[str] = []
    for key, _sell_key, _buy_key, label in GOLD_ITEMS:
        if key not in gold:
            continue
        value = gold[key]
        if isinstance(value, tuple):
            gold_lines.append(_pair_line(label, *value))
        else:
            gold_lines.append(f"<b>{label}</b>: {_toman(value)} تومان")
    gold_lines = [line for line in gold_lines if line]
    if gold_lines:
        lines += ["", "🪙 <b>طلا و سکه</b>", *gold_lines]

    global_lines = [
        f"<b>{label}</b>: {_decimal(globals_[key])} {unit}"
        for key, label, unit in GLOBAL_ITEMS
        if key in globals_
    ]
    if global_lines:
        lines += ["", "🌍 <b>جهانی</b>", *global_lines]

    lines += ["", f"<i>{FOOTNOTE}</i>"]
    last_modified = str(snapshot.get("last_modified") or "").strip()
    if last_modified:
        lines.append(f"<i>به‌روزرسانی: {last_modified}</i>")
    return "\n".join(lines)


def _base_headers() -> dict[str, str]:
    """سرصفحه‌های مشترک مرورگری برای هر دو درخواست."""
    return {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    }


def _extract_param(html_text: str) -> str:
    """توکن درخواست را از جاوااسکریپت صفحه اصلی بیرون می‌کشد."""
    match = PARAM_PATTERN.search(html_text)
    if match is None:
        raise MarketError("توکن درخواست در صفحه منبع پیدا نشد.")
    return match.group(1)


async def _get_text(session: aiohttp.ClientSession, url: str) -> str:
    """یک GET متنی با بررسی وضعیت HTTP."""
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def _post_json(session: aiohttp.ClientSession, param: str) -> dict:
    """POST فرم‌محور به /json در همان نشست (کوکی‌های صفحه اصلی)."""
    headers = {
        "Referer": HOME_URL,
        "Origin": "https://bonbast.com",
        "X-Requested-With": "XMLHttpRequest",
    }
    async with session.post(JSON_URL, data={"param": param}, headers=headers) as response:
        response.raise_for_status()
        text = await response.text()
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise MarketError("پاسخ منبع نرخ‌ها JSON معتبر نبود.") from exc
    return data if isinstance(data, dict) else {}


async def _fetch_raw_payload() -> dict:
    """جریان دو مرحله‌ای منبع (توکن صفحه اصلی + POST) با یک تلاش تازه."""
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(
            timeout=timeout, headers=_base_headers()
        ) as session:
            param = _extract_param(await _get_text(session, HOME_URL))
            data = await _post_json(session, param)
            if not data or "reset" in data:
                # توکن صفحه‌ای که گرفتیم کهنه بود؛ یک‌بار دیگر از اول.
                logger.info("پاسخ کهنه از منبع نرخ‌ها؛ یک‌بار دیگر تلاش می‌کنیم.")
                param = _extract_param(await _get_text(session, HOME_URL))
                data = await _post_json(session, param)
    except MarketError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise MarketError(f"ارتباط با منبع نرخ‌ها ناموفق بود: {exc}") from exc
    if not data or "reset" in data:
        raise MarketError("منبع نرخ‌ها پاسخ معتبری نداد.")
    return data


# کش ماژولی: یک اسنپ‌شات مشترک برای همه دستورها تا ۱۸۰ ثانیه.
_cache: dict[str, Any] = {"data": None, "expires": 0.0}
_lock = asyncio.Lock()


async def get_market() -> dict:
    """اسنپ‌شات نرخ‌ها را با کش ۱۸۰ ثانیه‌ای برمی‌گرداند.

    قفل، هم‌زمانی دستورها را به یک درخواست شبکه تبدیل می‌کند. در خطای کامل
    (شبکه، توکن، JSON) استثنای MarketError بالا می‌رود.
    """
    now = time.monotonic()
    cached = _cache["data"]
    if cached is not None and now < float(_cache["expires"]):
        return cached

    async with _lock:
        now = time.monotonic()
        cached = _cache["data"]
        if cached is not None and now < float(_cache["expires"]):
            return cached  # درخواست دیگری در همین فاصله کش را پر کرد.
        snapshot = parse_market_payload(await _fetch_raw_payload())
        _cache["data"] = snapshot
        _cache["expires"] = now + CACHE_TTL_SECONDS
        return snapshot
