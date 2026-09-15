"""موتور خالص بازی دوز (Tic-Tac-Toe) — بدون وابستگی به aiogram.

صفحه یک لیست ۹ خانه‌ای است (اندیس ۰ بالا-چپ تا ۸ پایین-راست)؛ خانه خالی رشته
تهی، و نشان‌ها ``X`` و ``O`` هستند. بازیکن اول همیشه ``X`` است.

حرکت بات با مینیمکس انتخاب می‌شود: میان حرکت‌های هم‌امتیاز یکی تصادفی
برداشته می‌شود و با احتمال ``MISTAKE_CHANCE`` به‌جای بهترین حرکت، یک خانه
خالی تصادفی بازی می‌شود تا بات هم شکست‌ناپذیر نباشد و هم احمق به‌نظر نرسد.
"""
from __future__ import annotations

import random

EMPTY = ""
X = "X"
O = "O"

# همه خط‌های برد: سه سطر، سه ستون و دو قطر.
LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)

# احتمال اینکه بات به‌جای بهترین حرکت، یک خانه خالی تصادفی انتخاب کند.
MISTAKE_CHANCE = 0.25


def opponent(player: str) -> str:
    """نشان حریف را برمی‌گرداند."""
    return O if player == X else X


def new_board() -> list[str]:
    """صفحه خالی ۹ خانه‌ای."""
    return [EMPTY] * 9


def winner(board: list[str]) -> str | None:
    """برنده صفحه را برمی‌گرداند؛ اگر بازی تمام نشده باشد None."""
    for first, second, third in LINES:
        mark = board[first]
        if mark and mark == board[second] == board[third]:
            return mark
    return None


def is_full(board: list[str]) -> bool:
    """آیا هیچ خانه خالی نمانده؟"""
    return all(board)


def empty_cells(board: list[str]) -> list[int]:
    """اندیس خانه‌های خالی به ترتیب."""
    return [index for index, mark in enumerate(board) if not mark]


def _minimax(board: list[str], player: str, turn: str) -> int:
    """امتیاز نهایی موقعیت از دید بازیکن ``player`` (برد ۱، مساوی ۰، باخت ۱-)."""
    win = winner(board)
    if win is not None:
        return 1 if win == player else -1
    cells = empty_cells(board)
    if not cells:
        return 0

    scores: list[int] = []
    for cell in cells:
        board[cell] = turn
        scores.append(_minimax(board, player, opponent(turn)))
        board[cell] = EMPTY
    return max(scores) if turn == player else min(scores)


def best_move(board: list[str], player: str, mistake_chance: float = MISTAKE_CHANCE) -> int:
    """بهترین خانه برای ``player``؛ میان هم‌امتیازها تصادفی انتخاب می‌شود.

    با احتمال ``mistake_chance`` یک خانه خالی تصادفی بازی می‌شود تا بازی برای
    کاربر قابل‌برد باشد. اگر صفحه پر باشد ValueError بالا می‌رود.
    """
    cells = empty_cells(board)
    if not cells:
        raise ValueError("هیچ خانه خالی برای حرکت نمانده است.")

    if mistake_chance > 0 and random.random() < mistake_chance:
        return random.choice(cells)

    scored: list[tuple[int, int]] = []
    for cell in cells:
        board[cell] = player
        scored.append((_minimax(board, player, opponent(player)), cell))
        board[cell] = EMPTY

    best_score = max(score for score, _cell in scored)
    return random.choice([cell for score, cell in scored if score == best_score])
