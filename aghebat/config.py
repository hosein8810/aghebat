"""بارگذاری تنظیمات از متغیرهای محیطی."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    ids: list[int] = []
    for chunk in raw.replace(" ", "").split(","):
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            continue
    return ids


@dataclass(slots=True)
class Config:
    bot_token: str
    owners: list[int] = field(default_factory=list)
    db_path: Path = Path("data/aghebat.db")
    bot_name: str = "عاقبت"
    log_chat_id: int | None = None

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN تنظیم نشده است. فایل .env را بسازید.")
        log_raw = os.getenv("LOG_CHAT_ID", "").strip()
        return cls(
            bot_token=token,
            owners=_parse_ids(os.getenv("OWNERS")),
            db_path=Path(os.getenv("DB_PATH", "data/aghebat.db")),
            bot_name=os.getenv("BOT_NAME", "عاقبت").strip() or "عاقبت",
            log_chat_id=int(log_raw) if log_raw.lstrip("-").isdigit() else None,
        )

    def is_owner(self, user_id: int) -> bool:
        return user_id in self.owners
