# BOTZD

Telegram bot (TeleBot / pyTelegramBotAPI + SQLite).

## Setup
1) Create `.env` (example below) and fill required values (`BOT_TOKEN`, `ADMIN_ID`). `ADMIN_IDS` and `DATABASE_PATH` are optional.
2) Install deps: `pip install -r requirements.txt`
3) Run from project root: `python __main__.py`

Example `.env`:
```env
BOT_TOKEN=your_bot_token
ADMIN_ID=123456789
ADMIN_IDS=987654321,555555555
DATABASE_PATH=bot.db
```
