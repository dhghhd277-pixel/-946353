from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_id: int
    admin_ids: frozenset[int]
    database_path: str
    bot_username: str | None = None
    channel_chat_id: int | None = None
    channel_url: str | None = None
    channel_display: str | None = None

    @staticmethod
    def from_env() -> "Settings":
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN is not set. Create .env from .env.example")

        admin_id_raw = os.getenv("ADMIN_ID", "").strip()
        if not admin_id_raw:
            raise RuntimeError("ADMIN_ID is not set")

        admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
        admin_ids: set[int] = set()
        try:
            admin_ids.add(int(admin_id_raw))
        except Exception:
            pass
        if admin_ids_raw:
            for part in admin_ids_raw.replace(";", ",").replace(" ", ",").split(","):
                part = part.strip()
                if not part:
                    continue
                if part.lstrip("-").isdigit():
                    try:
                        admin_ids.add(int(part))
                    except Exception:
                        pass

        db_path = os.getenv("DATABASE_PATH", "bot.db").strip() or "bot.db"
        bot_username = os.getenv("BOT_USERNAME", "").strip() or None

        channel_chat_id_raw = os.getenv("CHANNEL_CHAT_ID", "").strip()
        if channel_chat_id_raw:
            channel_chat_id = int(channel_chat_id_raw)
        else:
            # Default channel (can be overridden via .env)
            channel_chat_id = -1003594652918

        channel_url = os.getenv("CHANNEL_URL", "").strip() or "https://t.me/+3JyJWd_DKI5jNTEy"
        channel_display = os.getenv("CHANNEL_DISPLAY", "").strip() or "канал"

        return Settings(
            bot_token=token,
            admin_id=int(admin_id_raw),
            admin_ids=frozenset(admin_ids or {int(admin_id_raw)}),
            database_path=db_path,
            bot_username=bot_username,
            channel_chat_id=channel_chat_id,
            channel_url=channel_url,
            channel_display=channel_display,
        )
