"""لایه دیتابیس (SQLite/aiosqlite) برای بات عاقبت."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Sequence

import aiosqlite

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS chats (
    chat_id       INTEGER PRIMARY KEY,
    title         TEXT    NOT NULL DEFAULT '',
    enabled       INTEGER NOT NULL DEFAULT 1,
    unit_name     TEXT    NOT NULL DEFAULT 'عاقبت',
    unit_emoji    TEXT    NOT NULL DEFAULT '🌱',
    daily_min     INTEGER NOT NULL DEFAULT -5,
    daily_max     INTEGER NOT NULL DEFAULT 20,
    msg_points    INTEGER NOT NULL DEFAULT 1,
    msg_cooldown  INTEGER NOT NULL DEFAULT 30,
    enforce_ranks INTEGER NOT NULL DEFAULT 1,
    fun_mode      INTEGER NOT NULL DEFAULT 1,
    created_at    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS members (
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    full_name   TEXT    NOT NULL DEFAULT '',
    username    TEXT    NOT NULL DEFAULT '',
    balance     INTEGER NOT NULL DEFAULT 0,
    points      INTEGER NOT NULL DEFAULT 0,
    messages    INTEGER NOT NULL DEFAULT 0,
    streak      INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    last_daily  TEXT    NOT NULL DEFAULT '',
    last_msg_ts INTEGER NOT NULL DEFAULT 0,
    rank_id     INTEGER NOT NULL DEFAULT 0,
    joined_at   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS ranks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    emoji       TEXT    NOT NULL DEFAULT '⭐️',
    min_balance INTEGER NOT NULL DEFAULT 0,
    perms       TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS texts (
    chat_id INTEGER NOT NULL,
    key     TEXT    NOT NULL,
    value   TEXT    NOT NULL,
    PRIMARY KEY (chat_id, key)
);

CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL DEFAULT 0,
    kind       TEXT    NOT NULL DEFAULT 'join',
    title      TEXT    NOT NULL,
    target     TEXT    NOT NULL DEFAULT '',
    url        TEXT    NOT NULL DEFAULT '',
    reward     INTEGER NOT NULL DEFAULT 10,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_claims (
    task_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL DEFAULT 0,
    done_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id, user_id)
);

CREATE TABLE IF NOT EXISTS ledger (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    amount  INTEGER NOT NULL,
    reason  TEXT    NOT NULL DEFAULT '',
    ts      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_members_balance ON members(chat_id, balance DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(chat_id, user_id, ts DESC);
"""

DEFAULT_RANKS: list[tuple[str, str, int, dict[str, bool]]] = [
    ("تخم‌مرغ", "🥚", -(10**9), {
        "can_send_messages": True,
        "can_send_audios": False,
        "can_send_documents": False,
        "can_send_photos": False,
        "can_send_videos": False,
        "can_send_video_notes": False,
        "can_send_voice_notes": False,
        "can_send_polls": False,
        "can_send_other_messages": False,
        "can_add_web_page_previews": False,
    }),
    ("جوجه", "🐣", 50, {
        "can_send_messages": True,
        "can_send_photos": True,
        "can_add_web_page_previews": True,
    }),
    ("مرغ", "🐔", 150, {
        "can_send_messages": True,
        "can_send_photos": True,
        "can_send_videos": True,
        "can_send_documents": True,
        "can_add_web_page_previews": True,
    }),
    ("عقاب", "🦅", 400, {
        "can_send_messages": True,
        "can_send_photos": True,
        "can_send_videos": True,
        "can_send_documents": True,
        "can_send_audios": True,
        "can_send_voice_notes": True,
        "can_send_video_notes": True,
        "can_send_other_messages": True,
        "can_add_web_page_previews": True,
    }),
    ("اژدها", "🐉", 1000, {
        "can_send_messages": True,
        "can_send_photos": True,
        "can_send_videos": True,
        "can_send_documents": True,
        "can_send_audios": True,
        "can_send_voice_notes": True,
        "can_send_video_notes": True,
        "can_send_other_messages": True,
        "can_send_polls": True,
        "can_add_web_page_previews": True,
        "can_invite_users": True,
    }),
]


class Database:
    """پوشش نازک روی aiosqlite با کوئری‌های اختصاصی بات."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("دیتابیس متصل نیست؛ ابتدا connect() را صدا بزنید.")
        return self._conn

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        await self.conn.execute(sql, params)
        await self.conn.commit()

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    # ---------------------------------------------------------------- chats
    async def ensure_chat(self, chat_id: int, title: str = "") -> aiosqlite.Row:
        row = await self.fetchone("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        if row is None:
            await self.execute(
                "INSERT INTO chats (chat_id, title, created_at) VALUES (?, ?, ?)",
                (chat_id, title, int(time.time())),
            )
            await self.seed_ranks(chat_id)
            row = await self.fetchone("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        elif title and row["title"] != title:
            await self.execute("UPDATE chats SET title = ? WHERE chat_id = ?", (title, chat_id))
        assert row is not None
        return row

    async def get_chat(self, chat_id: int) -> aiosqlite.Row | None:
        return await self.fetchone("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))

    async def set_chat_field(self, chat_id: int, field: str, value: Any) -> None:
        allowed = {
            "title", "enabled", "unit_name", "unit_emoji", "daily_min", "daily_max",
            "msg_points", "msg_cooldown", "enforce_ranks", "fun_mode",
        }
        if field not in allowed:
            raise ValueError(f"فیلد نامعتبر: {field}")
        await self.execute(f"UPDATE chats SET {field} = ? WHERE chat_id = ?", (value, chat_id))

    async def all_chats(self) -> list[aiosqlite.Row]:
        return await self.fetchall("SELECT * FROM chats WHERE enabled = 1")

    # -------------------------------------------------------------- members
    async def ensure_member(
        self, chat_id: int, user_id: int, full_name: str = "", username: str = ""
    ) -> aiosqlite.Row:
        row = await self.fetchone(
            "SELECT * FROM members WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        if row is None:
            await self.execute(
                "INSERT INTO members (chat_id, user_id, full_name, username, joined_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, full_name, username, int(time.time())),
            )
            row = await self.fetchone(
                "SELECT * FROM members WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
            )
        elif full_name and (row["full_name"] != full_name or row["username"] != username):
            await self.execute(
                "UPDATE members SET full_name = ?, username = ? WHERE chat_id = ? AND user_id = ?",
                (full_name, username, chat_id, user_id),
            )
        assert row is not None
        return row

    async def get_member(self, chat_id: int, user_id: int) -> aiosqlite.Row | None:
        return await self.fetchone(
            "SELECT * FROM members WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )

    async def add_balance(self, chat_id: int, user_id: int, amount: int, reason: str = "") -> int:
        await self.conn.execute(
            "UPDATE members SET balance = balance + ? WHERE chat_id = ? AND user_id = ?",
            (amount, chat_id, user_id),
        )
        await self.conn.execute(
            "INSERT INTO ledger (chat_id, user_id, amount, reason, ts) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, amount, reason, int(time.time())),
        )
        await self.conn.commit()
        row = await self.fetchone(
            "SELECT balance FROM members WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        return int(row["balance"]) if row else 0

    async def bump_message(self, chat_id: int, user_id: int, ts: int, points: int) -> None:
        await self.execute(
            "UPDATE members SET messages = messages + 1, points = points + ?,"
            " last_msg_ts = ? WHERE chat_id = ? AND user_id = ?",
            (points, ts, chat_id, user_id),
        )

    async def set_member_field(self, chat_id: int, user_id: int, field: str, value: Any) -> None:
        allowed = {"balance", "points", "streak", "best_streak", "last_daily", "rank_id", "messages"}
        if field not in allowed:
            raise ValueError(f"فیلد نامعتبر: {field}")
        await self.execute(
            f"UPDATE members SET {field} = ? WHERE chat_id = ? AND user_id = ?",
            (value, chat_id, user_id),
        )

    async def leaderboard(
        self, chat_id: int, column: str = "balance", limit: int = 10
    ) -> list[aiosqlite.Row]:
        if column not in {"balance", "points", "messages", "best_streak"}:
            column = "balance"
        return await self.fetchall(
            f"SELECT * FROM members WHERE chat_id = ? ORDER BY {column} DESC, messages DESC LIMIT ?",
            (chat_id, limit),
        )

    async def rank_of(self, chat_id: int, user_id: int, column: str = "balance") -> int:
        if column not in {"balance", "points", "messages"}:
            column = "balance"
        row = await self.fetchone(
            f"SELECT COUNT(*) AS c FROM members WHERE chat_id = ? AND {column} > "
            f"(SELECT {column} FROM members WHERE chat_id = ? AND user_id = ?)",
            (chat_id, chat_id, user_id),
        )
        return int(row["c"]) + 1 if row else 1

    async def member_count(self, chat_id: int) -> int:
        row = await self.fetchone("SELECT COUNT(*) AS c FROM members WHERE chat_id = ?", (chat_id,))
        return int(row["c"]) if row else 0

    async def pending_daily(self, chat_id: int, today: str) -> list[aiosqlite.Row]:
        return await self.fetchall(
            "SELECT * FROM members WHERE chat_id = ? AND last_daily <> ?", (chat_id, today)
        )

    # ---------------------------------------------------------------- ranks
    async def seed_ranks(self, chat_id: int) -> None:
        existing = await self.fetchone(
            "SELECT COUNT(*) AS c FROM ranks WHERE chat_id = ?", (chat_id,)
        )
        if existing and int(existing["c"]) > 0:
            return
        for title, emoji, min_balance, perms in DEFAULT_RANKS:
            await self.conn.execute(
                "INSERT INTO ranks (chat_id, title, emoji, min_balance, perms)"
                " VALUES (?, ?, ?, ?, ?)",
                (chat_id, title, emoji, min_balance, json.dumps(perms, ensure_ascii=False)),
            )
        await self.conn.commit()

    async def ranks(self, chat_id: int) -> list[aiosqlite.Row]:
        return await self.fetchall(
            "SELECT * FROM ranks WHERE chat_id = ? ORDER BY min_balance ASC", (chat_id,)
        )

    async def add_rank(
        self, chat_id: int, title: str, emoji: str, min_balance: int, perms: dict[str, bool]
    ) -> None:
        await self.execute(
            "INSERT INTO ranks (chat_id, title, emoji, min_balance, perms) VALUES (?, ?, ?, ?, ?)",
            (chat_id, title, emoji, min_balance, json.dumps(perms, ensure_ascii=False)),
        )

    async def delete_rank(self, chat_id: int, rank_id: int) -> None:
        await self.execute("DELETE FROM ranks WHERE chat_id = ? AND id = ?", (chat_id, rank_id))

    async def reset_ranks(self, chat_id: int) -> None:
        await self.execute("DELETE FROM ranks WHERE chat_id = ?", (chat_id,))
        await self.seed_ranks(chat_id)

    # ---------------------------------------------------------------- texts
    async def get_text(self, chat_id: int, key: str) -> str | None:
        row = await self.fetchone(
            "SELECT value FROM texts WHERE chat_id = ? AND key = ?", (chat_id, key)
        )
        return row["value"] if row else None

    async def set_text(self, chat_id: int, key: str, value: str) -> None:
        await self.execute(
            "INSERT INTO texts (chat_id, key, value) VALUES (?, ?, ?)"
            " ON CONFLICT(chat_id, key) DO UPDATE SET value = excluded.value",
            (chat_id, key, value),
        )

    async def clear_text(self, chat_id: int, key: str) -> None:
        await self.execute("DELETE FROM texts WHERE chat_id = ? AND key = ?", (chat_id, key))

    async def all_texts(self, chat_id: int) -> dict[str, str]:
        rows = await self.fetchall("SELECT key, value FROM texts WHERE chat_id = ?", (chat_id,))
        return {r["key"]: r["value"] for r in rows}

    # ---------------------------------------------------------------- tasks
    async def add_task(
        self,
        title: str,
        target: str,
        reward: int,
        chat_id: int = 0,
        kind: str = "join",
        url: str = "",
    ) -> int:
        cur = await self.conn.execute(
            "INSERT INTO tasks (chat_id, kind, title, target, url, reward, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chat_id, kind, title, target, url, reward, int(time.time())),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def tasks(self, chat_id: int, only_active: bool = True) -> list[aiosqlite.Row]:
        sql = "SELECT * FROM tasks WHERE (chat_id = 0 OR chat_id = ?)"
        if only_active:
            sql += " AND active = 1"
        sql += " ORDER BY id DESC"
        return await self.fetchall(sql, (chat_id,))

    async def get_task(self, task_id: int) -> aiosqlite.Row | None:
        return await self.fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))

    async def set_task_active(self, task_id: int, active: bool) -> None:
        await self.execute("UPDATE tasks SET active = ? WHERE id = ?", (int(active), task_id))

    async def delete_task(self, task_id: int) -> None:
        await self.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await self.execute("DELETE FROM task_claims WHERE task_id = ?", (task_id,))

    async def claimed_tasks(self, user_id: int) -> set[int]:
        rows = await self.fetchall("SELECT task_id FROM task_claims WHERE user_id = ?", (user_id,))
        return {int(r["task_id"]) for r in rows}

    async def claim_task(self, task_id: int, user_id: int, chat_id: int) -> bool:
        try:
            await self.execute(
                "INSERT INTO task_claims (task_id, user_id, chat_id, done_at) VALUES (?, ?, ?, ?)",
                (task_id, user_id, chat_id, int(time.time())),
            )
            return True
        except aiosqlite.IntegrityError:
            return False

    # --------------------------------------------------------------- ledger
    async def history(self, chat_id: int, user_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        return await self.fetchall(
            "SELECT * FROM ledger WHERE chat_id = ? AND user_id = ? ORDER BY ts DESC LIMIT ?",
            (chat_id, user_id, limit),
        )

    async def global_stats(self) -> dict[str, int]:
        chats = await self.fetchone("SELECT COUNT(*) AS c FROM chats")
        members = await self.fetchone("SELECT COUNT(*) AS c FROM members")
        msgs = await self.fetchone("SELECT COALESCE(SUM(messages), 0) AS c FROM members")
        tasks = await self.fetchone("SELECT COUNT(*) AS c FROM tasks WHERE active = 1")
        return {
            "chats": int(chats["c"]) if chats else 0,
            "members": int(members["c"]) if members else 0,
            "messages": int(msgs["c"]) if msgs else 0,
            "tasks": int(tasks["c"]) if tasks else 0,
        }
