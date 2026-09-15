"""بازی دوز ❌⭕️ در گروه: دو حالت «با بات» و «با دوست» (با تأیید حریف).

وضعیت بازی‌ها فقط در حافظه نگه داشته می‌شود؛ ری‌استارت بات بازی‌های نیمه‌کاره را
پاک می‌کند و این قابل قبول است. برای هر کاربر در هر گروه فقط یک بازی یا یک
دعوت‌نامه فعال مجاز است. انقضا تنبل است: هر callback زمان آخرین فعالیت را
می‌سنجد و بازی رهاشده را با پیام «لغو شد» می‌بندد.
"""
from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..db import Database
from ..services.tictactoe import (
    O,
    X,
    best_move,
    is_full,
    new_board,
    opponent,
    winner,
)
from ..utils import is_group, mention, mention_raw, parse_int, target_user

router = Router(name="tictactoe")

CELL_MARKS = {X: "❌", O: "⭕️"}
EMPTY_MARK = "▪️"
BOT_NAME = "بات 🤖"

MAX_STATES = 100
TTL_SECONDS = 600

FUN_OFF_TEXT = (
    "😂 حالت فان این گروه خاموشه!\n"
    "ادمین بات می‌تونه از <code>/settings</code> روشنش کنه."
)
EXPIRED_TEXT = "⌛️ بازی به دلیل بی‌توجهی لغو شد"
INVITE_EXPIRED_TEXT = "⌛️ دعوت‌نامه به دلیل بی‌توجهی منقضی شد"
REJECT_TEXT = "بازی رد شد 😌"
NOT_YOURS_TEXT = "این دعوت‌نامه برای تو نیست 😅"
NOT_YOUR_TURN_TEXT = "⏳ الان نوبت تو نیست!"
CELL_TAKEN_TEXT = "این خانه پره 🙂"
NO_GAME_TEXT = "این بازی دیگه فعال نیست 🤷"
NO_INVITE_TEXT = "این دعوت‌نامه دیگه معتبر نیست 🤷"


@dataclass
class Pending:
    """دعوت‌نامه دو نفره در انتظار تأیید حریف."""

    gid: str
    chat_id: int
    message_id: int
    challenger_id: int
    challenger_name: str
    opponent_id: int
    opponent_name: str
    created_at: float


@dataclass
class Game:
    """بازی در جریان؛ ``o_id`` تهی یعنی حریف بات است."""

    gid: str
    chat_id: int
    message_id: int
    board: list[str]
    x_id: int
    x_name: str
    o_id: int | None
    o_name: str
    turn: str
    vs_bot: bool
    last_action: float


# وضعیت ماژولی؛ کلید همه‌جا gid هشت‌کاراکتری هگز است.
GAMES: dict[str, Game] = {}
PENDING: dict[str, Pending] = {}
# کسی که منوی حالت را دیده است: (chat_id, message_id) → (user_id, ts).
PICKERS: dict[tuple[int, int], tuple[int, float]] = {}


def _cap(store: dict, stamp_of: Callable[[Any], float]) -> None:
    """قدیمی‌ترین کلیدها را حذف می‌کند تا دیکشنری‌های ماژول بی‌مرز رشد نکنند."""
    while len(store) > MAX_STATES:
        store.pop(min(store, key=stamp_of), None)


def _expired(stamp: float) -> bool:
    """آیا از آخرین فعالیت این رکورد بیشتر از حد مجاز گذشته است؟"""
    return time.monotonic() - stamp > TTL_SECONDS


def _new_gid() -> str:
    """شناسه تازه هشت‌کاراکتری هگز برای بازی یا دعوت‌نامه."""
    return secrets.token_hex(4)


def _game_of(chat_id: int, user_id: int) -> Game | None:
    """بازی فعال کاربر در این گروه (اگر باشد)."""
    for game in GAMES.values():
        if game.chat_id == chat_id and user_id in (game.x_id, game.o_id):
            return game
    return None


def _pending_of(chat_id: int, user_id: int) -> Pending | None:
    """دعوت‌نامه فعال کاربر در این گروه (اگر باشد)."""
    for invite in PENDING.values():
        if invite.chat_id == chat_id and user_id in (invite.challenger_id, invite.opponent_id):
            return invite
    return None


def _busy(chat_id: int, user_id: int) -> bool:
    """آیا کاربر بازی یا دعوت‌نامه فعالی در این گروه دارد؟"""
    return _game_of(chat_id, user_id) is not None or _pending_of(chat_id, user_id) is not None


def _mark(cell: str) -> str:
    """نشان یک خانه برای نمایش (خالی، ❌ یا ⭕️)."""
    return CELL_MARKS.get(cell, EMPTY_MARK)


def _name_of(game: Game, player: str) -> str:
    """نام قابل منشن بازیکن آن نشان؛ بات منشن ندارد."""
    if player == X:
        return mention_raw(game.x_id, game.x_name)
    if game.o_id is None:
        return f"<b>{BOT_NAME}</b>"
    return mention_raw(game.o_id, game.o_name)


def _player_id(game: Game, player: str) -> int | None:
    """شناسه بازیکن آن نشان (بات شناسه ندارد)."""
    return game.x_id if player == X else game.o_id


def _board_keyboard(gid: str, board: list[str]) -> InlineKeyboardMarkup:
    """صفحه ۳×۳ شیشه‌ای؛ هر خانه یک callback کوتاه دارد."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_mark(board[row * 3 + col]),
                    callback_data=f"ttt:m:{gid}:{row * 3 + col}",
                )
                for col in range(3)
            ]
            for row in range(3)
        ]
    )


def _board_text(board: list[str]) -> str:
    """صفحه به‌صورت متن؛ برای پیام پایان بازی که کیبوردش برداشته می‌شود."""
    return "\n".join(
        " ".join(_mark(board[row * 3 + col]) for col in range(3)) for row in range(3)
    )


def _header(game: Game) -> str:
    """سرصفحه مشترک پیام بازی: هر دو حریف با منشن."""
    return (
        "🎮 <b>بازی دوز</b>\n"
        f"❌ {_name_of(game, X)}  در برابر  ⭕️ {_name_of(game, O)}"
    )


def _live_text(game: Game) -> str:
    """متن پیام در جریان بازی (صفحه در کیبورد نشان داده می‌شود)."""
    return f"{_header(game)}\n\n🎯 نوبت: {_mark(game.turn)} {_name_of(game, game.turn)}"


def _result_text(game: Game, mark: str | None) -> str:
    """خط نتیجه پایانی بازی."""
    if mark is None:
        return "🤝 مساوی!"
    if mark == O and game.vs_bot:
        return "😈 بات برد!"
    return f"🎉 {_name_of(game, mark)} بردی!"


def _final_text(game: Game, mark: str | None) -> str:
    """متن پایان بازی: صفحه ثابت به‌صورت متن + نتیجه."""
    return f"{_header(game)}\n\n{_board_text(game.board)}\n\n{_result_text(game, mark)}"


async def _edit(
    call: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """همان پیام بازی را ویرایش می‌کند؛ خطای ویرایش بی‌صدا رد می‌شود."""
    if not isinstance(call.message, Message):
        return
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:  # noqa: BLE001 - پیام قدیمی یا محتوای تکراری حیاتی نیست
        pass


async def _fun_enabled(db: Database, chat_id: int) -> bool:
    """آیا حالت فان این گروه روشن است؟"""
    chat = await db.ensure_chat(chat_id)
    return bool(int(chat["fun_mode"]))


def _picker_key(call: CallbackQuery) -> tuple[int, int] | None:
    """کلید پیام منوی حالت برای بررسی صاحب دکمه."""
    if not isinstance(call.message, Message):
        return None
    return (call.message.chat.id, call.message.message_id)


@router.message(Command("ttt", "tictactoe"))
async def cmd_ttt(message: Message, db: Database) -> None:
    """بدون ریپلای منوی حالت را می‌فرستد؛ با ریپلای حریف را به بازی دعوت می‌کند."""
    if not is_group(message.chat):
        await message.answer("❌⭕️ بازی دوز فقط داخل گروه!")
        return
    user = message.from_user
    if user is None:
        return
    if not await _fun_enabled(db, message.chat.id):
        await message.reply(FUN_OFF_TEXT)
        return
    if _busy(message.chat.id, user.id):
        await message.reply(
            "⏳ تو الان یک بازی یا دعوت‌نامه فعال داری؛ اول اون رو تموم کن!"
        )
        return

    if message.reply_to_message is None:
        sent = await message.reply(
            "🎮 <b>بازی دوز</b>\n\n"
            "می‌خوای با کی بازی کنی؟\n"
            "🤖 بات حریفت می‌شه و همیشه نوبت دومه\n"
            "👥 یا روی پیام حریفت ریپلای کن و <code>/ttt</code> بزن",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🤖 بازی با بات", callback_data="ttt:nb")],
                    [InlineKeyboardButton(text="👥 بازی با دوست", callback_data="ttt:pvp")],
                ]
            ),
        )
        PICKERS[(sent.chat.id, sent.message_id)] = (user.id, time.monotonic())
        _cap(PICKERS, lambda key: PICKERS[key][1])
        return

    challenged = target_user(message)
    if challenged is None:
        await message.reply(
            "↩️ روی پیام کسی که می‌خوای باهاش بازی کنی ریپلای کن و <code>/ttt</code> بزن."
        )
        return
    if challenged.id == user.id:
        await message.reply("🙃 با خودت نمی‌شه دوز بازی کرد!")
        return
    if challenged.is_bot:
        await message.reply(
            "🤖 با بات که دعوا نمی‌کنیم!\n"
            "برای بازی با بات، <code>/ttt</code> رو بدون ریپلای بزن."
        )
        return
    if _busy(message.chat.id, challenged.id):
        await message.reply(
            f"⏳ {mention(challenged)} الان یک بازی یا دعوت‌نامه فعال داره؛ "
            "یه‌کم بعد امتحان کن."
        )
        return

    gid = _new_gid()
    sent = await message.reply(
        "🎯 <b>دعوت به بازی دوز</b>\n\n"
        f"{mention(user)} تو رو به نبرد دعوت کرد {mention(challenged)}!\n"
        f"❌ شروع‌کننده: {mention(user)} | ⭕️ حریف: {mention(challenged)}\n\n"
        f"{mention(challenged)} جان، قبول می‌کنی؟",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ قبول می‌کنم", callback_data=f"ttt:acc:{gid}"
                    ),
                    InlineKeyboardButton(
                        text="❌ رد می‌کنم", callback_data=f"ttt:rej:{gid}"
                    ),
                ]
            ]
        ),
    )
    PENDING[gid] = Pending(
        gid=gid,
        chat_id=sent.chat.id,
        message_id=sent.message_id,
        challenger_id=user.id,
        challenger_name=user.full_name,
        opponent_id=challenged.id,
        opponent_name=challenged.full_name,
        created_at=time.monotonic(),
    )
    _cap(PENDING, lambda key: PENDING[key].created_at)


async def _start_bot_game(call: CallbackQuery, chat_id: int) -> None:
    """دکمه «بازی با بات» را به صفحه زنده تبدیل می‌کند؛ بات ⭕️ و نوبت دوم است."""
    user = call.from_user
    key = _picker_key(call)
    # صاحب منوی حالت تا وقتی پیام پابرجاست تنها کسی است که می‌تواند دکمه‌ها را بزند.
    owner = PICKERS.get(key) if key is not None else None
    if owner is not None and owner[0] != user.id:
        await call.answer("این دکمه مال صاحب دستوره 😅 خودت /ttt بزن.", show_alert=True)
        return
    if _busy(chat_id, user.id):
        await call.answer("⏳ تو الان یک بازی یا دعوت‌نامه فعال داری!", show_alert=True)
        return
    if not isinstance(call.message, Message):
        await call.answer(NO_GAME_TEXT)
        return

    gid = _new_gid()
    game = Game(
        gid=gid,
        chat_id=chat_id,
        message_id=call.message.message_id,
        board=new_board(),
        x_id=user.id,
        x_name=user.full_name,
        o_id=None,
        o_name=BOT_NAME,
        turn=X,
        vs_bot=True,
        last_action=time.monotonic(),
    )
    GAMES[gid] = game
    _cap(GAMES, lambda key: GAMES[key].last_action)
    await _edit(call, _live_text(game), _board_keyboard(gid, game.board))
    await call.answer("بات حریفته! تو ❌ هستی و اول شروع می‌کنی 🤖")


async def _accept(call: CallbackQuery, gid: str) -> None:
    """تأیید دعوت‌نامه: همان پیام به صفحه بازی تبدیل می‌شود و ❌ اول می‌زند."""
    invite = PENDING.get(gid)
    if invite is None:
        await call.answer(NO_INVITE_TEXT)
        return
    if _expired(invite.created_at):
        PENDING.pop(gid, None)
        await _edit(call, INVITE_EXPIRED_TEXT)
        await call.answer()
        return
    if call.from_user.id != invite.opponent_id:
        await call.answer(NOT_YOURS_TEXT, show_alert=True)
        return

    PENDING.pop(gid, None)
    game = Game(
        gid=gid,
        chat_id=invite.chat_id,
        message_id=invite.message_id,
        board=new_board(),
        x_id=invite.challenger_id,
        x_name=invite.challenger_name,
        o_id=invite.opponent_id,
        o_name=invite.opponent_name,
        turn=X,
        vs_bot=False,
        last_action=time.monotonic(),
    )
    GAMES[gid] = game
    _cap(GAMES, lambda key: GAMES[key].last_action)
    await _edit(call, _live_text(game), _board_keyboard(gid, game.board))
    await call.answer("بازی شروع شد! ❌ اول می‌زنه")


async def _reject(call: CallbackQuery, gid: str) -> None:
    """رد دعوت‌نامه: پیام با تأییدیه کوتاه بسته می‌شود."""
    invite = PENDING.get(gid)
    if invite is None:
        await call.answer(NO_INVITE_TEXT)
        return
    if _expired(invite.created_at):
        PENDING.pop(gid, None)
        await _edit(call, INVITE_EXPIRED_TEXT)
        await call.answer()
        return
    if call.from_user.id != invite.opponent_id:
        await call.answer(NOT_YOURS_TEXT, show_alert=True)
        return

    PENDING.pop(gid, None)
    await _edit(call, REJECT_TEXT)
    await call.answer("باشه، شاید یه‌وقت دیگه 😌")


async def _play(call: CallbackQuery, gid: str, cell: int | None) -> None:
    """یک حرکت انسان (+ پاسخ بات در حالت تک‌نفره) و بازرندر همان پیام."""
    game = GAMES.get(gid)
    if game is None:
        await call.answer(NO_GAME_TEXT)
        return
    if _expired(game.last_action):
        GAMES.pop(gid, None)
        await _edit(call, EXPIRED_TEXT)
        await call.answer()
        return
    if cell is None or not 0 <= cell <= 8:
        await call.answer()
        return
    if game.board[cell]:
        await call.answer(CELL_TAKEN_TEXT)
        return
    if call.from_user.id != _player_id(game, game.turn):
        await call.answer(NOT_YOUR_TURN_TEXT)
        return

    game.board[cell] = game.turn
    game.turn = opponent(game.turn)
    game.last_action = time.monotonic()

    if game.vs_bot and winner(game.board) is None and not is_full(game.board):
        # بات بلافاصله و در همان ویرایش پاسخ می‌دهد.
        game.board[best_move(game.board, O)] = O
        game.turn = X
        game.last_action = time.monotonic()

    mark = winner(game.board)
    if mark is not None or is_full(game.board):
        GAMES.pop(gid, None)
        await _edit(call, _final_text(game, mark))
    else:
        await _edit(call, _live_text(game), _board_keyboard(gid, game.board))
    await call.answer()


@router.callback_query(F.data.startswith("ttt:"))
async def cb_ttt(call: CallbackQuery, db: Database) -> None:
    """دکمه‌های منوی حالت، تأیید/رد دعوت‌نامه و حرکت‌های صفحه دوز."""
    if call.data is None or not isinstance(call.message, Message):
        await call.answer(NO_GAME_TEXT)
        return
    chat = call.message.chat
    if not is_group(chat):
        await call.answer("❌⭕️ بازی دوز فقط داخل گروه!")
        return
    if not await _fun_enabled(db, chat.id):
        await call.answer("😂 حالت فان این گروه خاموشه؛ ادمین بات با /settings روشنش کنه.")
        return

    parts = call.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    gid = parts[2] if len(parts) > 2 else ""

    if action == "nb":
        await _start_bot_game(call, chat.id)
        return
    if action == "pvp":
        await call.answer("👥 روی پیام حریفت ریپلای کن و /ttt بزن.")
        return
    if action == "acc":
        await _accept(call, gid)
        return
    if action == "rej":
        await _reject(call, gid)
        return
    if action == "m":
        await _play(call, gid, parse_int(parts[3]) if len(parts) > 3 else None)
        return
    await call.answer()
