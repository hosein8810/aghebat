"""نگاشت عبارت‌های فارسی به دستورهای اسلش‌دار بات عاقبت.

کاربر می‌تواند به‌جای دستور، عبارت فارسی بنویسد؛ مثلاً «تنظیم ادمین» همان
«/promote» است. ترجمه در میدل‌ور AliasMiddleware انجام می‌شود و فقط شکل
پیام عوض می‌شود؛ سد فعال‌سازی و گاردهای مالک/ادمین بات سر جایشان می‌مانند.
"""
from __future__ import annotations

from aiogram.types import Message, MessageEntity

# (عبارت فارسی, نام دستور بدون اسلش)
# نکته: برای عبارت‌هایی که هندلر متن خام دارند (عاقبت، پروفایل، برترین‌ها،
# رتبه‌ها، تسک‌ها، فال، راهنما، کمک و پیشوند «شرط») عبارتی تعریف نمی‌کنیم تا
# رفتار فعلی دست‌نخورده بماند.
ALIASES: list[tuple[str, str]] = [
    # ادمین‌های بات (فقط مالک)
    ("تنظیم ادمین", "promote"),
    ("ادمین کن", "promote"),
    ("عزل ادمین", "demote"),
    ("ادمینهای بات", "botadmins"),
    ("ادمین‌های بات", "botadmins"),
    ("لیست ادمینها", "botadmins"),
    ("لیست ادمین‌ها", "botadmins"),
    # فعال‌سازی کاربران (فقط مالک)
    ("فعالسازی", "activate"),
    ("فعال کن", "activate"),
    ("غیرفعالسازی", "deactivate"),
    ("غیرفعال کن", "deactivate"),
    # پنل تنظیمات گروه
    ("تنظیمات", "settings"),
    ("پنل تنظیمات", "settings"),
    # بازی روزانه
    ("بازه روزانه", "setrange"),
    ("امتیاز پیام", "setmsgpoints"),
    ("واحد امتیاز", "setunit"),
    # رتبه‌ها و دسترسی‌ها
    ("رتبه جدید", "addrank"),
    ("حذف رتبه", "delrank"),
    ("ریست رتبهها", "resetranks"),
    ("ریست رتبه‌ها", "resetranks"),
    ("هماهنگسازی", "syncall"),
    ("هماهنگ‌سازی", "syncall"),
    # متن‌های قابل تنظیم
    ("تنظیم متن", "settext"),
    ("حذف متن", "deltext"),
    ("متنها", "texts"),
    ("متن‌ها", "texts"),
    # موجودی اعضا
    ("بده", "give"),
    ("بگیر", "take"),
    ("تنظیم موجودی", "setbalance"),
    # تبلیغ‌ها (فقط مالک)
    ("تبلیغ جدید", "addad"),
    ("لیست تبلیغها", "ads"),
    ("لیست تبلیغ‌ها", "ads"),
    ("حذف تبلیغ", "delad"),
    ("سوییچ تبلیغ", "adtoggle"),
    ("بازه تبلیغ", "adinterval"),
    ("ارسال تبلیغ", "adnow"),
    # تسک‌ها و آمار (فقط مالک)
    ("تسک جدید", "addtask"),
    ("لیست تسکها", "tasklist"),
    ("لیست تسک‌ها", "tasklist"),
    ("حذف تسک", "deltask"),
    ("سوییچ تسک", "toggletask"),
    ("آمار", "stats"),
    ("پیام همگانی", "broadcast"),
    # سایر
    ("سوییچ", "toggle"),
    ("تاریخچه", "history"),
]

# عبارت‌های بلندتر اول بررسی می‌شوند تا مثلاً «سوییچ تبلیغ» به دستور
# /adtoggle برود، نه /toggle با آرگومان «تبلیغ».
_SORTED_ALIASES: list[tuple[str, str]] = sorted(
    ALIASES, key=lambda pair: len(pair[0]), reverse=True
)


def resolve_alias(text: str) -> tuple[str, str] | None:
    """عبارت فارسی را به (دستور اسلش‌دار, آرگومان‌ها) ترجمه می‌کند.

    عبارت باید کل متن باشد یا با یک فاصله در ابتدای آن بیاید؛ در حالت دوم
    بقیه متن عیناً به‌عنوان آرگومان حفظ می‌شود (ارقام فارسی دست‌نخورده
    می‌مانند و پایین‌دست با parse_int تبدیل می‌شوند). اگر متن خالی باشد، با
    اسلش شروع شود یا هیچ عبارتی مطابق نکند، None برمی‌گردد.
    """
    cleaned = text.strip()
    if not cleaned or cleaned.startswith("/"):
        return None
    for phrase, command in _SORTED_ALIASES:
        if cleaned == phrase:
            return f"/{command}", ""
        prefix = f"{phrase} "
        if cleaned.startswith(prefix):
            return f"/{command}", cleaned[len(prefix):].strip()
    return None


def rewrite_message(message: Message, command: str, args: str) -> Message:
    """کپی پیام با متن دستور اسلش‌دار و دقیقاً یک موجودیت bot_command.

    موجودیت روی توکن خود دستور (بدون آرگومان‌ها) می‌نشیند تا فیلترهای
    Command در aiogram پیام را مثل یک دستور واقعی تشخیص دهند و
    CommandObject.args باقی متن را حمل کند.
    """
    return message.model_copy(
        update={
            "text": f"{command} {args}".rstrip(),
            "entities": [
                MessageEntity(type="bot_command", offset=0, length=len(command))
            ],
        }
    )
