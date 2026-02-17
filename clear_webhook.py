import telebot

from bot.config import Settings


def main() -> None:
    settings = Settings.from_env()
    bot = telebot.TeleBot(settings.bot_token, parse_mode=None)

    # Delete webhook (if any) and drop pending updates to avoid stale callbacks.
    bot.delete_webhook(drop_pending_updates=True)
    print("Webhook deleted, pending updates dropped")


if __name__ == "__main__":
    main()
