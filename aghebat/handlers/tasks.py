"""تسک‌های تبلیغاتی: نمایش لیست و تایید عضویت کاربر."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..db import Database
from ..services.ranks import sync_member_rank
from ..services.tasks import is_member, task_url
from ..utils import is_group, mention, render, safe

router = Router(name="tasks")


async def _tasks_keyboard(db: Database, chat_id: int, user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    """متن و کیبورد تسک‌های باقی‌مانده کاربر را می‌سازد."""
    chat = await db.ensure_chat(chat_id)
    rows = await db.tasks(chat_id)
    claimed = await db.claimed_tasks(user_id)
    pending = [r for r in rows if int(r["id"]) not in claimed]

    if not rows:
        return "📭 فعلاً هیچ تسکی تعریف نشده! بعداً سر بزن.", None
    if not pending:
        return "🎉 آفرین! همه تسک‌ها رو انجام دادی. منتظر تسک‌های بعدی باش 😎", None

    lines = [
        "🎯 <b>تسک‌های فعال</b>",
        "",
        "توی کانال‌های زیر عضو شو، بعد دکمه «بررسی» رو بزن تا جایزه‌ات رو بگیری:",
        "",
    ]
    buttons: list[list[InlineKeyboardButton]] = []
    for row in pending:
        reward = int(row["reward"])
        lines.append(f"• <b>{safe(row['title'])}</b> — 🎁 {reward:,} {chat['unit_name']}")
        url = task_url(row["target"], row["url"])
        line: list[InlineKeyboardButton] = []
        if url:
            line.append(InlineKeyboardButton(text=f"🔗 {row['title'][:20]}", url=url))
        line.append(
            InlineKeyboardButton(text="✅ بررسی", callback_data=f"task:{row['id']}")
        )
        buttons.append(line)

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("tasks"))
@router.message(F.text.in_({"تسک", "تسک‌ها", "تسک ها", "ماموریت"}))
async def cmd_tasks(message: Message, db: Database) -> None:
    """لیست تسک‌های تبلیغاتی فعال."""
    user = message.from_user
    if user is None:
        return
    chat_id = message.chat.id if is_group(message.chat) else 0
    if chat_id:
        await db.ensure_member(chat_id, user.id, user.full_name, user.username or "")
    text, keyboard = await _tasks_keyboard(db, chat_id, user.id)
    await message.reply(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("task:"))
async def cb_task_check(call: CallbackQuery, bot: Bot, db: Database) -> None:
    """عضویت کاربر را بررسی و در صورت تایید جایزه می‌دهد."""
    if call.data is None or call.message is None:
        return
    task_id = int(call.data.split(":", 1)[1])
    user = call.from_user
    task = await db.get_task(task_id)

    if task is None or not task["active"]:
        await call.answer("این تسک دیگه فعال نیست 🚫", show_alert=True)
        return

    chat_id = call.message.chat.id if is_group(call.message.chat) else int(task["chat_id"])
    if task_id in await db.claimed_tasks(user.id):
        await call.answer("قبلاً این تسک رو انجام دادی ✅", show_alert=True)
        return

    if not await is_member(bot, task["target"], user.id):
        await call.answer(
            "هنوز عضو نشدی! اول توی کانال عضو شو بعد دوباره بررسی کن 👀", show_alert=True
        )
        return

    if not await db.claim_task(task_id, user.id, chat_id):
        await call.answer("این تسک قبلاً ثبت شده ✅", show_alert=True)
        return

    reward = int(task["reward"])
    balance = reward
    if chat_id:
        chat = await db.ensure_chat(chat_id)
        await db.ensure_member(chat_id, user.id, user.full_name, user.username or "")
        balance = await db.add_balance(chat_id, user.id, reward, reason="task")
        await sync_member_rank(
            bot, db, chat_id, user.id, balance, enforce=bool(chat["enforce_ranks"])
        )
        unit = chat["unit_name"]
        text = await render(
            db,
            chat_id,
            "task_done",
            name=user.full_name,
            mention=mention(user),
            title=task["title"],
            amount=f"{reward:,}",
            balance=f"{balance:,}",
            unit=unit,
            emoji=chat["unit_emoji"],
        )
        await call.message.answer(text)

    await call.answer(f"🎉 تایید شد! {reward:,} امتیاز گرفتی.", show_alert=True)

    text, keyboard = await _tasks_keyboard(db, chat_id, user.id)
    try:
        await call.message.edit_text(text, reply_markup=keyboard)
    except Exception:  # noqa: BLE001 - ویرایش پیام حیاتی نیست
        pass
