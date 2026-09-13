"""موتور رتبه‌بندی و اعمال دسترسی‌های تلگرام بر اساس موجودی عاقبت."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatPermissions

from ..db import Database

logger = logging.getLogger(__name__)

PERM_FIELDS: tuple[str, ...] = (
    "can_send_messages",
    "can_send_audios",
    "can_send_documents",
    "can_send_photos",
    "can_send_videos",
    "can_send_video_notes",
    "can_send_voice_notes",
    "can_send_polls",
    "can_send_other_messages",
    "can_add_web_page_previews",
    "can_change_info",
    "can_invite_users",
    "can_pin_messages",
    "can_manage_topics",
)

PERM_LABELS: dict[str, str] = {
    "can_send_messages": "ارسال پیام 💬",
    "can_send_audios": "ارسال آهنگ 🎵",
    "can_send_documents": "ارسال فایل 📎",
    "can_send_photos": "ارسال عکس 🖼",
    "can_send_videos": "ارسال ویدیو 🎬",
    "can_send_video_notes": "ویدیو مسیج ⭕️",
    "can_send_voice_notes": "ویس 🎙",
    "can_send_polls": "نظرسنجی 📊",
    "can_send_other_messages": "استیکر و گیف 🎭",
    "can_add_web_page_previews": "پیش‌نمایش لینک 🔗",
    "can_change_info": "تغییر اطلاعات گروه ⚙️",
    "can_invite_users": "دعوت اعضا ➕",
    "can_pin_messages": "سنجاق پیام 📌",
    "can_manage_topics": "مدیریت تاپیک 🗂",
}


@dataclass(slots=True)
class Rank:
    """نمایش یک رتبه به همراه دسترسی‌هایش."""

    id: int
    title: str
    emoji: str
    min_balance: int
    perms: dict[str, bool]

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.title}"

    def to_permissions(self) -> ChatPermissions:
        data: dict[str, Any] = {field: bool(self.perms.get(field, False)) for field in PERM_FIELDS}
        return ChatPermissions(**data)

    def allowed_labels(self) -> list[str]:
        return [PERM_LABELS[f] for f in PERM_FIELDS if self.perms.get(f)]


def _row_to_rank(row: Any) -> Rank:
    try:
        perms = json.loads(row["perms"]) or {}
    except (json.JSONDecodeError, TypeError):
        perms = {}
    return Rank(
        id=int(row["id"]),
        title=row["title"],
        emoji=row["emoji"],
        min_balance=int(row["min_balance"]),
        perms={k: bool(v) for k, v in perms.items()},
    )


async def load_ranks(db: Database, chat_id: int) -> list[Rank]:
    """همه رتبه‌های گروه را مرتب بر اساس حداقل موجودی برمی‌گرداند."""
    rows = await db.ranks(chat_id)
    if not rows:
        await db.seed_ranks(chat_id)
        rows = await db.ranks(chat_id)
    return [_row_to_rank(r) for r in rows]


def resolve_rank(ranks: list[Rank], balance: int) -> Rank | None:
    """بالاترین رتبه‌ای که کاربر با این موجودی واجدش است."""
    current: Rank | None = None
    for rank in ranks:
        if balance >= rank.min_balance:
            current = rank
        else:
            break
    return current or (ranks[0] if ranks else None)


def next_rank(ranks: list[Rank], balance: int) -> Rank | None:
    """رتبه بعدی که کاربر هنوز به آن نرسیده است."""
    for rank in ranks:
        if balance < rank.min_balance:
            return rank
    return None


async def apply_permissions(bot: Bot, chat_id: int, user_id: int, rank: Rank) -> bool:
    """دسترسی‌های رتبه را روی کاربر در گروه اعمال می‌کند."""
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=rank.to_permissions(),
        )
        return True
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.warning("اعمال دسترسی ناموفق (chat=%s user=%s): %s", chat_id, user_id, exc)
        return False


async def sync_member_rank(
    bot: Bot,
    db: Database,
    chat_id: int,
    user_id: int,
    balance: int,
    enforce: bool = True,
) -> tuple[Rank | None, Rank | None]:
    """رتبه کاربر را با موجودی فعلی هماهنگ می‌کند.

    خروجی: (رتبه قبلی, رتبه جدید) — اگر تغییری نکرده باشد، رتبه جدید None است.
    """
    ranks = await load_ranks(db, chat_id)
    target = resolve_rank(ranks, balance)
    if target is None:
        return None, None

    member = await db.get_member(chat_id, user_id)
    old_id = int(member["rank_id"]) if member else 0
    if old_id == target.id:
        return target, None

    previous = next((r for r in ranks if r.id == old_id), None)
    await db.set_member_field(chat_id, user_id, "rank_id", target.id)
    if enforce:
        await apply_permissions(bot, chat_id, user_id, target)
    return previous, target
