from __future__ import annotations

import traceback
import os
import sys

import telebot

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.config import Settings


def main() -> None:
    s = Settings.from_env()
    bot = telebot.TeleBot(s.bot_token, parse_mode=None)

    print("token_len", len(s.bot_token))

    try:
        me = bot.get_me()
        print("me", getattr(me, "username", None), getattr(me, "id", None))
    except Exception as e:
        print("get_me_error", repr(e))
        traceback.print_exc()

    try:
        wh = bot.get_webhook_info()
        print("webhook", wh)
    except Exception as e:
        print("get_webhook_error", repr(e))
        traceback.print_exc()

    try:
        # One lightweight getUpdates call to surface 401/409 issues.
        updates = bot.get_updates(limit=1, timeout=1, allowed_updates=[])
        print("updates_ok", len(updates))
    except Exception as e:
        print("get_updates_error", repr(e))
        traceback.print_exc()


if __name__ == "__main__":
    main()
