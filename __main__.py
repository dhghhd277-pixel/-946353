
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR
from html import escape as html_escape
import json
import random
import math
import datetime as dt
import logging
import os
import sys
import socket
import threading
import time
import traceback
import signal
import subprocess


def _early_spawn_debug_setup() -> None:
    """Very early spawn instrumentation.

    This runs near the top of the module to catch any process-spawning that
    happens before the singleton guards are reached.
    Enable with BOT_SPAWN_DEBUG=1.
    """

    if str(os.getenv("BOT_SPAWN_DEBUG", "")).strip().lower() not in ("1", "true", "yes", "y", "on"):
        return

    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    except Exception:
        root_dir = os.getcwd()
    log_path = os.path.join(root_dir, "bot_spawn.log")

    def _log(line: str) -> None:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
                if not line.endswith("\n"):
                    f.write("\n")
        except Exception:
            pass

    def _stack() -> str:
        try:
            return "".join(traceback.format_stack(limit=50))
        except Exception:
            return "(no stack)"

    try:
        _orig_popen = subprocess.Popen

        def _popen(*args, **kwargs):  # type: ignore[no-untyped-def]
            _log(
                f"\n[spawn-early] pid={os.getpid()} ppid={getattr(os, 'getppid', lambda: -1)()} "
                f"exe={sys.executable} argv={sys.argv}\n"
                f"Popen args={args} kwargs={list(kwargs.keys())}\n{_stack()}"
            )
            return _orig_popen(*args, **kwargs)

        subprocess.Popen = _popen  # type: ignore[assignment]
    except Exception:
        pass

    try:
        _orig_system = os.system

        def _system(cmd: str) -> int:
            _log(
                f"\n[spawn-early] pid={os.getpid()} ppid={getattr(os, 'getppid', lambda: -1)()} "
                f"exe={sys.executable} argv={sys.argv}\n"
                f"system cmd={cmd!r}\n{_stack()}"
            )
            return _orig_system(cmd)

        os.system = _system  # type: ignore[assignment]
    except Exception:
        pass


try:
    _early_spawn_debug_setup()
except Exception:
    pass

try:
    import msvcrt  # type: ignore
except Exception:
    msvcrt = None  # type: ignore

try:
    import fcntl  # type: ignore
except Exception:
    fcntl = None  # type: ignore

try:
    import ctypes
    from ctypes import wintypes
except Exception:
    ctypes = None  # type: ignore
    wintypes = None  # type: ignore

import telebot
from telebot.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    ReplyKeyboardMarkup,
)

from types import ModuleType


def _fmt_int(n: int | None) -> str:
    """Format integers with thousands grouping for Telegram UI."""
    try:
        # Use a narrow no-break space so Telegram doesn't collapse/wrap groups.
        return f"{int(n or 0):,}".replace(",", "\u202f")
    except Exception:
        return "0"


def _fmt_points_ui(n: int | None) -> str:
    """Format points for UI (same as `_fmt_int`)."""
    return _fmt_int(n)


def _resolve_bot_imports() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    """Make imports work in multiple run modes.

    Supported:
    - `python -m bot` (preferred)
    - `python bot/__main__.py`
    - a relocated entrypoint like `/app/__main__.py` next to `config.py`, `db.py`, etc.
    """

    errors: list[Exception] = []

    # Preferred: package execution.
    try:
        from . import config as _config
        from . import constants as _constants
        from . import db as _db
        from . import keyboards as _keyboards
        return _config, _constants, _db, _keyboards
    except Exception as exc:
        errors.append(exc)

    # If executed as a script, ensure repo root is on sys.path.
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        parent = os.path.dirname(here)
        if parent and parent not in sys.path:
            sys.path.insert(0, parent)
    except Exception:
        pass

    # Common repo layout: package is named `bot`.
    try:
        import bot.config as _config  # type: ignore
        import bot.constants as _constants  # type: ignore
        import bot.db as _db  # type: ignore
        import bot.keyboards as _keyboards  # type: ignore
        return _config, _constants, _db, _keyboards
    except Exception as exc:
        errors.append(exc)

    # Last resort: sibling-module layout.
    try:
        import config as _config  # type: ignore
        import constants as _constants  # type: ignore
        import db as _db  # type: ignore
        import keyboards as _keyboards  # type: ignore
        return _config, _constants, _db, _keyboards
    except Exception as exc:
        errors.append(exc)

    raise ImportError("Failed to import bot modules") from errors[-1]


_config, _constants, _db, kb_module = _resolve_bot_imports()

Settings = _config.Settings
Database = _db.Database

BANK_OPTIONS = _constants.BANK_OPTIONS
MIN_WITHDRAW_POINTS = _constants.MIN_WITHDRAW_POINTS
POINTS_PER_RUB = _constants.POINTS_PER_RUB
REFERRAL_BONUS_POINTS = _constants.REFERRAL_BONUS_POINTS
WITHDRAW_OPTIONS_RUB = _constants.WITHDRAW_OPTIONS_RUB

# Export keyboard builders into this module namespace (the rest of the file
# expects to call them as plain functions).
admin_add_task_type_kb = kb_module.admin_add_task_type_kb
admin_chat_stop_kb = kb_module.admin_chat_stop_kb
admin_duel_server_add_game_kb = kb_module.admin_duel_server_add_game_kb
admin_duel_server_add_stake_kb = kb_module.admin_duel_server_add_stake_kb
admin_duel_server_kb = kb_module.admin_duel_server_kb
admin_duel_server_limit_kb = kb_module.admin_duel_server_limit_kb
admin_duel_server_quick_kb = kb_module.admin_duel_server_quick_kb
admin_duel_server_random_kb = kb_module.admin_duel_server_random_kb
admin_gift_confirm_kb = kb_module.admin_gift_confirm_kb
admin_gift_user_kb = kb_module.admin_gift_user_kb
admin_menu_kb = kb_module.admin_menu_kb
admin_review_submission_kb = kb_module.admin_review_submission_kb
admin_review_withdraw_kb = kb_module.admin_review_withdraw_kb
back_inline_kb = kb_module.back_inline_kb
banks_kb = kb_module.banks_kb
boosts_kb = kb_module.boosts_kb
bot_rematch_kb = kb_module.bot_rematch_kb
channel_task_kb = kb_module.channel_task_kb
dialog_admin_kb = kb_module.dialog_admin_kb
dialog_user_kb = kb_module.dialog_user_kb
dialog_user_open_kb = kb_module.dialog_user_open_kb
confirm_withdraw_kb = kb_module.confirm_withdraw_kb
cryptomine_category_kb = kb_module.cryptomine_category_kb
cryptomine_farm_kb = kb_module.cryptomine_farm_kb
cryptomine_farm_reply_kb = kb_module.cryptomine_farm_reply_kb
cryptomine_item_kb = kb_module.cryptomine_item_kb
cryptomine_market_kb = kb_module.cryptomine_market_kb
cryptomine_mining_kb = kb_module.cryptomine_mining_kb
cryptomine_shop_main_kb = kb_module.cryptomine_shop_main_kb
dice_again_kb = kb_module.dice_again_kb
dice_kb = kb_module.dice_kb
duel2_friend_actions_kb = kb_module.duel2_friend_actions_kb
duel2_invite_link_back_kb = kb_module.duel2_invite_link_back_kb
duel2_menu_kb = kb_module.duel2_menu_kb
duel2_stake_kb = kb_module.duel2_stake_kb
duel_friend_actions_kb = kb_module.duel_friend_actions_kb
duel_invite_link_back_kb = kb_module.duel_invite_link_back_kb
duel_rematch_answer_kb = kb_module.duel_rematch_answer_kb
duel_rematch_offer_kb = kb_module.duel_rematch_offer_kb
duel_rematch_opponent_choice_kb = kb_module.duel_rematch_opponent_choice_kb
duel_rematch_stake_kb = kb_module.duel_rematch_stake_kb
duel_rps_kb = kb_module.duel_rps_kb
duel_stake_kb = kb_module.duel_stake_kb
duel_type_kb = kb_module.duel_type_kb
duels_main_kb = kb_module.duels_main_kb
farm_points_kb = kb_module.farm_points_kb
ladder_bet_kb = kb_module.ladder_bet_kb
ladder_field_kb = kb_module.ladder_field_kb
ladder_result_kb = kb_module.ladder_result_kb
main_menu_kb = kb_module.main_menu_kb
mines_confirm_kb = kb_module.mines_confirm_kb
mines_field_kb = kb_module.mines_field_kb
mines_mines_kb = kb_module.mines_mines_kb
mines_params_kb = kb_module.mines_params_kb
mines_size_kb = kb_module.mines_size_kb
mines_timeout_kb = kb_module.mines_timeout_kb
minigames_menu_kb = kb_module.minigames_menu_kb
profile_kb = kb_module.profile_kb
rating_back_kb = kb_module.rating_back_kb
rating_main_kb = kb_module.rating_main_kb
repeat_offer_kb = kb_module.repeat_offer_kb
rps_kb = kb_module.rps_kb
rps_result_kb = kb_module.rps_result_kb
rps_stake_kb = kb_module.rps_stake_kb
server_duels_list_kb = kb_module.server_duels_list_kb
shop_confirm_kb = kb_module.shop_confirm_kb
shop_emoji_kb = kb_module.shop_emoji_kb
shop_emoji_pack_kb = kb_module.shop_emoji_pack_kb
shop_emoji_success_kb = kb_module.shop_emoji_success_kb
shop_farm_kb = kb_module.shop_farm_kb
shop_farm_success_kb = kb_module.shop_farm_success_kb
shop_insurance_kb = kb_module.shop_insurance_kb
shop_insurance_success_kb = kb_module.shop_insurance_success_kb
shop_main_kb = kb_module.shop_main_kb
shop_nick_colors_kb = kb_module.shop_nick_colors_kb
shop_titles_kb = kb_module.shop_titles_kb
shop_titles_ready_kb = kb_module.shop_titles_ready_kb
shop_vip_extend_kb = kb_module.shop_vip_extend_kb
shop_vip_kb = kb_module.shop_vip_kb
shop_vip_success_kb = kb_module.shop_vip_success_kb
support_kb = kb_module.support_kb
tasks_menu_kb = kb_module.tasks_menu_kb
tiktok_task_kb = kb_module.tiktok_task_kb
tournaments_menu_kb = kb_module.tournaments_menu_kb
weekly_tasks_kb = kb_module.weekly_tasks_kb
wheel_kb = kb_module.wheel_kb
wheel_result_kb = kb_module.wheel_result_kb
wheel_top_kb = kb_module.wheel_top_kb
withdraw_menu_kb = kb_module.withdraw_menu_kb
game_bet_kb = kb_module.game_bet_kb

del _config, _constants, _db


@dataclass
class Session:
    # user flow
    awaiting_proof_task_id: int | None = None
    awaiting_proof_task_code: str | None = None

    # universal custom bet input
    awaiting_bet_for_game: str | None = None  # mines|dice|wheel|ladder|rps
    awaiting_bet_chat_id: int | None = None
    awaiting_bet_message_id: int | None = None

    withdraw_amount_rub: int | None = None
    withdraw_bank: str | None = None
    withdraw_requisites: str | None = None

    # last sent channel task message (for cleanup)
    last_channel_task_chat_id: int | None = None
    last_channel_task_message_id: int | None = None
    warned_channel_check_unavailable: bool = False

    # admin flows (Session-step style)
    admin_expect_user_lookup: bool = False

    # admin users panel (edit-in-place)
    admin_users_expect: str | None = None  # search|block_reason|points_amount|points_message
    admin_users_query: str | None = None
    admin_users_page: int = 0
    admin_users_blocked_only: bool = False
    admin_users_notify: bool = True
    admin_users_allow_negative: bool = False
    admin_users_target_user_id: int | None = None
    admin_users_pending_action: str | None = None  # block|unblock|points
    admin_users_points_sign: int = 1
    admin_users_pending_value: int | None = None
    admin_users_pending_text: str | None = None
    admin_users_error: str | None = None

    admin_add_task_step: str | None = None
    admin_add_task_code: str | None = None
    admin_add_task_title: str | None = None
    admin_add_task_desc: str | None = None
    admin_add_task_reward: int | None = None
    admin_add_task_limits: str | None = None
    admin_add_task_comment_text: str | None = None

    admin_duel_server_step: str | None = None
    admin_duel_server_game_type: str | None = None
    admin_duel_server_stake: int | None = None
    admin_duel_server_add_one: bool = False

    admin_target_user_id: int | None = None
    admin_flow: str | None = None
    admin_gift_amount: int | None = None
    admin_gift_text: str | None = None
    admin_gift_notify: bool = True

    # dialogs (DB-backed)
    dialog_expect: str | None = None  # user_reply|admin_reply
    dialog_id: int | None = None
    dialog_role: str | None = None  # user|admin

    # mini games: mines 3.0
    mines_state: str = "none"  # none|setup|confirm|active
    mines_mode: str = "classic"  # classic|hardcore|nobet
    mines_round_id: int | None = None
    mines_size: int | None = None
    mines_mines: int | None = None
    mines_bet: int | None = None
    mines_opened: set[int] = field(default_factory=set)
    mines_mine_cells: set[int] = field(default_factory=set)
    mines_started_at: float | None = None
    mines_insurance: bool = False
    mines_luck_boost_active: bool = False

    # tournaments (MVP)
    tourn_selected_id: int | None = None
    tourn_active_tournament_id: int | None = None
    tourn_active_match_id: int | None = None
    tourn_active_game_index: int | None = None

    # admin tournament wizard (MVP)
    admin_tourn_step: str | None = None
    admin_tourn_max_players: int | None = None
    admin_tourn_start_in_min: int | None = None
    admin_tourn_entry_fee: int | None = None
    admin_tourn_prize1: int | None = None
    admin_tourn_prize2: int | None = None
    admin_tourn_prize3: int | None = None

    # crypto-mine farm panel message (single message we keep editing)
    cmf_chat_id: int | None = None
    cmf_message_id: int | None = None
    cmf_kb_message_id: int | None = None
    cmf_mode: bool = False

    # crypto-mine shop: buy quantity step
    cm_buy_pending: bool = False
    cm_buy_category: str | None = None
    cm_buy_code: str | None = None
    cm_buy_prefix: str | None = None  # cm|cms
    cm_buy_panel_chat_id: int | None = None
    cm_buy_panel_message_id: int | None = None
    cm_buy_prompt_chat_id: int | None = None
    cm_buy_prompt_message_id: int | None = None
    cm_buy_max_qty: int | None = None

    # global panel mode (single message for whole bot)
    panel_chat_id: int | None = None
    panel_message_id: int | None = None
    panel_screen: str = "main"
    panel_history: list[str] = field(default_factory=list)
    panel_mode: bool = True

    # crypto-mine farm delete UI (multi-select)
    cmf_delete_cat: str | None = None  # gpu|cool|psu
    cmf_delete_selected: set[int] = field(default_factory=set)

    # crypto-mine temperature animation / auto-refresh
    cmf_animation_thread: threading.Thread | None = None
    cmf_animation_active: bool = False
    cmf_animation_chat_id: int | None = None
    cmf_animation_message_id: int | None = None
    cmf_animation_view: str | None = None  # e.g. 'mine'
    cmf_animation_last_sig: str | None = None

    # dice vs bot (Telegram 🎲)
    dice_active: bool = False
    dice_bet: int | None = None
    dice_bot_value: int | None = None
    dice_insurance: bool = False

    # ladder mini-game
    ladder_active: bool = False
    ladder_bet: int | None = None
    ladder_step: int = 0
    ladder_multiplier: float = 1.0
    ladder_message_id: int | None = None
    ladder_chat_id: int | None = None
    ladder_rows: list[dict] = field(default_factory=list)
    ladder_current_mine: int | None = None
    ladder_mines: list[int] = field(default_factory=list)
    ladder_choices: list[int | None] = field(default_factory=list)
    ladder_insurance: bool = False

    # wheel (Telegram 🎲)
    wheel_active: bool = False
    wheel_bet: int | None = None
    wheel_insurance: bool = False

    # duels creation
    duel_mode: str = "friend"  # friend|public
    duel_stake: int | None = None
    duel_game_type: str | None = None

    # server duels filters
    server_duels_games: set[str] = field(default_factory=lambda: {"dice", "rps", "ttt"})
    server_duels_stakes: set[int] = field(default_factory=lambda: {10, 100, 1000, 2500, 5000, 10000})
    server_duels_page: int = 0

    # RPS vs bot
    rps_active: bool = False
    rps_stake: int | None = None
    rps_last_stake: int | None = None
    rps_bot_choice: str | None = None
    rps_insurance: bool = False

    # rematch (KNB) state
    rematch_with_user: int | None = None
    rematch_base_duel_id: int | None = None
    rematch_pending_stake: int | None = None
    rematch_role: str | None = None  # initiator|opponent

    # rematch service messages (for cleanup)
    rematch_status_chat_id: int | None = None
    rematch_status_message_id: int | None = None
    rematch_offer_chat_id: int | None = None
    rematch_offer_message_id: int | None = None
    rematch_wait_chat_id: int | None = None
    rematch_wait_message_id: int | None = None

    # shop (custom title)
    shop_vip_plan: str | None = None
    shop_farm_plan: str | None = None
    shop_insurance_plan: str | None = None
    shop_expect_custom_title: bool = False
    shop_custom_title_pending: str | None = None

    # temp one-off notices (auto-deleted on next button press)
    temp_notice_chat_id: int | None = None
    temp_notice_message_id: int | None = None

    # game inactivity tracking (60s)
    game_last_action_at: dict[str, float] = field(default_factory=dict)
    game_inactivity_token: dict[str, str] = field(default_factory=dict)
    game_inactivity_target: dict[str, tuple[int, int]] = field(default_factory=dict)


def _safe_delete_message(bot: telebot.TeleBot, chat_id: int, message_id: int) -> None:
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def _rematch_clear_service_messages(*, user_id: int, skip_chat_id: int | None = None, skip_message_id: int | None = None) -> None:
    s = session(int(user_id))
    try:
        if s.rematch_status_chat_id and s.rematch_status_message_id:
            if not (skip_chat_id == int(s.rematch_status_chat_id) and skip_message_id == int(s.rematch_status_message_id)):
                _safe_delete_message(bot, int(s.rematch_status_chat_id), int(s.rematch_status_message_id))
    except Exception:
        pass
    try:
        if s.rematch_offer_chat_id and s.rematch_offer_message_id:
            if not (skip_chat_id == int(s.rematch_offer_chat_id) and skip_message_id == int(s.rematch_offer_message_id)):
                _safe_delete_message(bot, int(s.rematch_offer_chat_id), int(s.rematch_offer_message_id))
    except Exception:
        pass
    try:
        if s.rematch_wait_chat_id and s.rematch_wait_message_id:
            if not (skip_chat_id == int(s.rematch_wait_chat_id) and skip_message_id == int(s.rematch_wait_message_id)):
                _safe_delete_message(bot, int(s.rematch_wait_chat_id), int(s.rematch_wait_message_id))
    except Exception:
        pass

    s.rematch_status_chat_id = None
    s.rematch_status_message_id = None
    s.rematch_offer_chat_id = None
    s.rematch_offer_message_id = None
    s.rematch_wait_chat_id = None
    s.rematch_wait_message_id = None


def _rematch_amount_options(base_stake: int) -> list[int]:
    """Stake presets for rematch.

    If the base duel is a low-stake duel (mini-games), keep mini-game presets.
    Otherwise, use the regular duel presets.
    """
    try:
        base_stake_int = int(base_stake)
    except Exception:
        base_stake_int = 0
    if base_stake_int in (50, 100, 250, 500) or (0 < base_stake_int < 200):
        return [50, 100, 250, 500]
    return [200, 500, 1000]


def _build_rematch_stake_kb(base_duel_id: int, base_stake: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for amount in _rematch_amount_options(int(base_stake)):
        kb.add(
            InlineKeyboardButton(
                text=f"Ставка {_fmt_points_ui(int(amount))}",
                callback_data=f"duel:rematch_stake:{int(base_duel_id)}:{int(amount)}",
            )
        )
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:menu"))
    return kb


def _norm_reply_text(t: str | None) -> str:
    # Telegram clients may include emoji variation selector (\ufe0f),
    # which breaks strict equality checks for reply-keyboard texts.
    return (t or "").replace("\ufe0f", "").strip()


INACTIVITY_TIMEOUT_SECONDS = 60.0
INACTIVITY_NOTICE_DELETE_SECONDS = 10.0

# --- Insurance system (global, for all mini-games) ---
INSURANCE_BASE_REFUND_PCT = 30
INSURANCE_BONUS_REFUND_PCT = 50
INSURANCE_BONUS_CHANCE_PCT = 10
INSURANCE_LOW_STOCK_WARN_AT = 10


def _send_autodelete_notice(bot: telebot.TeleBot, *, chat_id: int, text: str, delay_seconds: float = INACTIVITY_NOTICE_DELETE_SECONDS) -> None:
    try:
        msg = bot.send_message(int(chat_id), str(text))
    except Exception:
        return

    def _worker() -> None:
        try:
            time.sleep(float(delay_seconds))
        except Exception:
            pass
        try:
            _safe_delete_message(bot, int(chat_id), int(msg.message_id))
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def _is_message_not_modified_error(exc: Exception) -> bool:
    return "message is not modified" in str(exc).lower()


def _is_ignorable_edit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    ignorable = (
        "message is not modified",
        "message to edit not found",
        "message can't be edited",
        "message to edit not found",
        "chat not found",
        "bot was blocked by the user",
        "bot was kicked",
        "not enough rights",
        "have no rights",
        "message identifier is not specified",
    )
    return any(x in msg for x in ignorable)


def _safe_edit_message_text(
    bot: telebot.TeleBot,
    text: str,
    *,
    chat_id: int,
    message_id: int,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    try:
        bot.edit_message_text(
            str(text),
            chat_id=int(chat_id),
            message_id=int(message_id),
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception as e:
        if _is_ignorable_edit_error(e):
            return
        raise


def _ladder_next_multiplier(step: int) -> float:
    # Simple growth curve; tuned for a fast casual game
    step = max(0, int(step))
    base = 1.0
    increments = [0.20, 0.30, 0.40, 0.55, 0.75, 1.00, 1.35]
    if step <= 0:
        return base
    idx = min(step - 1, len(increments) - 1)
    return base + increments[idx]


def _ladder_fail_chance(step: int) -> float:
    # Risk increases with steps
    step = max(0, int(step))
    return min(0.65, 0.20 + 0.07 * step)


def _ladder_cashout_amount(bet: int, mult: float) -> int:
    bet = int(bet)
    return int(math.floor(max(0.0, float(bet) * float(mult))))


def _ladder_row_emojis(*, mine_idx: int, chosen_idx: int | None) -> list[str]:
    mine_idx = int(mine_idx)
    base = ["💎", "💎", "💎"]
    if 0 <= mine_idx < 3:
        base[mine_idx] = "💣"
    if chosen_idx is None:
        return base
    chosen_idx = int(chosen_idx)
    if 0 <= chosen_idx < 3:
        if chosen_idx == mine_idx:
            base[chosen_idx] = "💥"
        else:
            base[chosen_idx] = "✅"
    return base


def _ladder_board_text_v3(
    *,
    mines: list[int],
    choices: list[int | None],
    step: int,
    reveal: bool,
) -> str:
    """Render a fixed 3×6 ladder board.

    Levels are 0..5 where 0 is the bottom (first), 5 is the top (sixth).
    """
    total_levels = 6
    lines: list[str] = []
    for level in range(total_levels - 1, -1, -1):
        mine_idx = int(mines[level]) if level < len(mines) else 0
        chosen = choices[level] if level < len(choices) else None

        if reveal:
            row = ["💎", "💎", "💎"]
            if 0 <= mine_idx < 3:
                row[mine_idx] = "💣"
            if chosen is not None:
                chosen_i = int(chosen)
                if 0 <= chosen_i < 3:
                    if chosen_i == mine_idx:
                        row[chosen_i] = "💥"
                    else:
                        row[chosen_i] = "✅"
            lines.append("  ".join(row))
            continue

        # Not revealed: show only progress + current active level
        if level > int(step):
            lines.append("⬛  ⬛  ⬛")
        elif level == int(step):
            lines.append("❓  ❓  ❓")
        else:
            # already passed level: show chosen cell as ✅, others locked
            row = ["⬛", "⬛", "⬛"]
            if chosen is not None:
                chosen_i = int(chosen)
                if 0 <= chosen_i < 3:
                    row[chosen_i] = "✅"
            lines.append("  ".join(row))

    return "\n".join(lines)


def _ladder_screen_text_v3(*, bet: int, step: int, mult: float, mines: list[int], choices: list[int | None]) -> str:
    step_i = max(0, int(step))
    win = _ladder_cashout_amount(int(bet), float(mult)) if step_i > 0 else 0
    base = "🪜 ЛЕСЕНКА\n\n" + f"Ставка: {_fmt_points_ui(int(bet))}\n"
    if step_i > 0:
        return base + f"👉 Ты можешь забрать {_fmt_points_ui(int(win))} 💰"
    return base + "Сделайте первый ход:"


def _ladder_board_text(*, rows: list[dict], current_mine: int | None, reveal_current: bool = False, current_choice: int | None = None) -> str:
    lines: list[str] = []
    if current_mine is not None:
        if reveal_current:
            cur = _ladder_row_emojis(mine_idx=int(current_mine), chosen_idx=current_choice)
            lines.append("  ".join(cur))
        else:
            lines.append("❓  ❓  ❓")
    for row in reversed(rows or []):
        mine_idx = int(row.get("mine") or 0)
        chosen_idx = row.get("chosen")
        emojis = _ladder_row_emojis(mine_idx=mine_idx, chosen_idx=chosen_idx if chosen_idx is not None else None)
        lines.append("  ".join(emojis))
    return "\n".join(lines) if lines else "❓  ❓  ❓"


def _ladder_screen_text_v2(*, bet: int, step: int, mult: float, rows: list[dict], current_mine: int | None) -> str:
    win = _ladder_cashout_amount(int(bet), float(mult))
    board = _ladder_board_text(rows=rows, current_mine=current_mine, reveal_current=False)
    return (
        "🪜 ЛЕСЕНКА\n\n"
        "В каждой строке: 2 💎 и 1 💣.\n"
        "Нажмите на одну из трёх клеток.\n\n"
        f"👉 Ты можешь забрать {_fmt_points_ui(int(win))} 💰\n\n"
        f"{board}"
    )


def _parse_start_ref(text: str) -> int | None:
    # expected: "/start 123456789" (inviter user_id)
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    if payload.isdigit():
        try:
            return int(payload)
        except ValueError:
            return None
    return None


def _is_admin(user_id: int, settings: Settings) -> bool:
    try:
        return int(user_id) in set(getattr(settings, "admin_ids", frozenset({settings.admin_id})))
    except Exception:
        return int(user_id) == int(settings.admin_id)


def _acquire_single_instance_lock(lock_path: str) -> object | None:
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)

    # Binary mode avoids text translation quirks and makes locking deterministic.
    f = open(lock_path, "a+b")
    try:
        # Always lock the first byte of the file.
        f.seek(0)
        if os.name == "nt" and msvcrt is not None:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        elif fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        else:
            # No locking backend available; best-effort single instance.
            pass

        # Record PID/PPID for diagnostics (does not affect the lock).
        try:
            pid = os.getpid()
            ppid = getattr(os, "getppid", lambda: -1)()
            payload = f"pid={pid} ppid={ppid}\n".encode("utf-8", errors="replace")
            f.seek(0)
            f.truncate(0)
            f.write(payload)
            f.flush()

            # Also write a separate, non-locked PID file for operational tooling.
            # (Reading BOT.lock may fail because it is intentionally locked.)
            try:
                pid_path = os.path.join(os.path.dirname(lock_path) or ".", "BOT.pid")
                with open(pid_path, "w", encoding="utf-8") as pf:
                    pf.write(str(pid))
            except Exception:
                pass
        except Exception:
            pass
    except OSError:
        try:
            f.close()
        except Exception:
            pass
        return None

    return f


def _acquire_single_instance_port(port: int) -> socket.socket | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("127.0.0.1", int(port)))
        s.listen(1)
    except OSError:
        try:
            s.close()
        except Exception:
            pass
        return None
    return s


def _acquire_windows_mutex(name: str) -> int | None:
    """Best-effort single-instance guard.

    On Windows, this uses a named mutex. Returns a handle (int) on success,
    or None if another instance already holds/created the mutex.
    """

    if os.name != "nt" or ctypes is None:
        return 1

    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        ERROR_ALREADY_EXISTS = 183

        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return None

        last_error = int(kernel32.GetLastError())
        if last_error == ERROR_ALREADY_EXISTS:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
            return None

        return int(handle)
    except Exception:
        # If mutex API fails for any reason, don't brick startup; fall back to file lock.
        return 1


_SINGLE_INSTANCE_MUTEX_HANDLE: int | None = None
_SINGLE_INSTANCE_LOCK_HANDLE = None
_SINGLE_INSTANCE_PORT_SOCKET: socket.socket | None = None


def _singleton_trace(event: str) -> None:
    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    except Exception:
        root_dir = os.getcwd()
    try:
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        ts = str(time.time())
    try:
        pid = os.getpid()
        ppid = getattr(os, "getppid", lambda: -1)()
    except Exception:
        pid, ppid = -1, -1
    try:
        line = (
            f"{ts} event={event} pid={pid} ppid={ppid} name={__name__} "
            f"exe={sys.executable} argv={sys.argv}\n"
        )
        with open(os.path.join(root_dir, "singleton_trace.log"), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _install_signal_debug_handlers() -> None:
    """Log termination signals to help diagnose unexpected KeyboardInterrupt in VS Code terminals."""

    def _handler(sig: int, frame) -> None:  # type: ignore[no-untyped-def]
        try:
            name = signal.Signals(sig).name
        except Exception:
            name = str(sig)

        try:
            msg = (
                f"\n[signal] pid={os.getpid()} ppid={getattr(os, 'getppid', lambda: -1)()} "
                f"sig={sig}({name})\n"
            )
            sys.stderr.write(msg)
            sys.stderr.flush()
        except Exception:
            pass

        try:
            st = "".join(traceback.format_stack(frame)) if frame is not None else "(no frame)"
        except Exception:
            st = "(failed to format stack)"

        try:
            with open(os.path.join(os.getcwd(), "bot_run.err"), "a", encoding="utf-8") as f:
                f.write(msg)
                f.write(st)
                f.write("\n")
        except Exception:
            pass

        # Let default KeyboardInterrupt handling take over.
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGINT, _handler)
    except Exception:
        pass
    try:
        signal.signal(signal.SIGTERM, _handler)
    except Exception:
        pass
    # Windows-specific
    if hasattr(signal, "SIGBREAK"):
        try:
            signal.signal(signal.SIGBREAK, _handler)  # type: ignore[attr-defined]
        except Exception:
            pass


def _ensure_single_instance_or_exit() -> None:
    """Acquire single-instance guards early, or exit the process.

    Important: this must run before the rest of the module does heavy work.
    """

    global _SINGLE_INSTANCE_MUTEX_HANDLE, _SINGLE_INSTANCE_LOCK_HANDLE, _SINGLE_INSTANCE_PORT_SOCKET

    pid = os.getpid()
    ppid = getattr(os, "getppid", lambda: -1)()

    _singleton_trace("ensure_enter")

    # If a project-local venv exists, refuse to run under a different interpreter.
    # This mitigates the observed "parent venv python -> child system python" double-run.
    try:
        if os.name == "nt":
            expected = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", ".venv", "Scripts", "python.exe")
            )
            current = os.path.abspath(sys.executable)
            if os.path.exists(expected) and os.path.normcase(current) != os.path.normcase(expected):
                print(
                    "BOTZD: обнаружен запуск НЕ из .venv. "
                    f"current={current} expected={expected} pid={pid} ppid={ppid}. Выходим."
                )
                raise SystemExit(1)
    except SystemExit:
        raise
    except Exception:
        pass

    # Single-instance guard (Windows mutex): if another copy is running, exit.
    mutex_name = "Local\\BOTZD_TELEGRAM_BOT_LOCK"
    mutex = _acquire_windows_mutex(mutex_name)
    if mutex is None:
        try:
            print(
                f"BOTZD: уже запущен другой экземпляр (mutex={mutex_name}). "
                f"pid={pid} ppid={ppid}"
            )
        except Exception:
            pass
        raise SystemExit(1)

    # Strong guard: bind an exclusive localhost port.
    # This is enforced by the OS and reliably prevents duplicate instances even
    # if file locks / mutexes behave unexpectedly in the hosting environment.
    port = 48123
    port_socket = _acquire_single_instance_port(port)
    if port_socket is None:
        try:
            print(
                f"BOTZD: уже запущен другой экземпляр (tcp-port={port}). "
                f"pid={pid} ppid={ppid}"
            )
        except Exception:
            pass
        raise SystemExit(1)

    # Use a stable lock path (repo root) instead of current working directory.
    # This prevents multiple instances when started from different folders.
    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    except Exception:
        root_dir = os.getcwd()
    lock_path = os.path.join(root_dir, "BOT.lock")
    lock_handle = _acquire_single_instance_lock(lock_path)
    if lock_handle is None:
        try:
            print(
                f"BOTZD: уже запущен другой экземпляр (file lock={lock_path}). "
                f"pid={pid} ppid={ppid}"
            )
        except Exception:
            pass
        raise SystemExit(1)

    _SINGLE_INSTANCE_MUTEX_HANDLE = mutex
    _SINGLE_INSTANCE_LOCK_HANDLE = lock_handle
    _SINGLE_INSTANCE_PORT_SOCKET = port_socket

    _singleton_trace("ensure_ok")


# Acquire the single-instance lock early (before the rest of this large module
# registers handlers / starts threads). This prevents accidental double-starts
# from doing heavy work.
if __name__ == "__main__":
    _ensure_single_instance_or_exit()


def _install_spawn_debug() -> None:
    """Optional: log process-spawning calls to help diagnose extra python process.

    Enable with BOT_SPAWN_DEBUG=1.
    """

    if str(os.getenv("BOT_SPAWN_DEBUG", "")).strip().lower() not in ("1", "true", "yes", "y", "on"):
        return

    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    except Exception:
        root_dir = os.getcwd()
    log_path = os.path.join(root_dir, "bot_spawn.log")

    def _log(line: str) -> None:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
                if not line.endswith("\n"):
                    f.write("\n")
        except Exception:
            pass

    def _stack() -> str:
        try:
            return "".join(traceback.format_stack(limit=40))
        except Exception:
            return "(no stack)"

    # Wrap subprocess.Popen / run
    _orig_popen = subprocess.Popen
    _orig_run = subprocess.run

    def _popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        _log(
            f"\n[spawn] pid={os.getpid()} ppid={getattr(os, 'getppid', lambda: -1)()} "
            f"Popen args={args} kwargs={list(kwargs.keys())}\n{_stack()}"
        )
        return _orig_popen(*args, **kwargs)

    def _run(*args, **kwargs):  # type: ignore[no-untyped-def]
        _log(
            f"\n[spawn] pid={os.getpid()} ppid={getattr(os, 'getppid', lambda: -1)()} "
            f"run args={args} kwargs={list(kwargs.keys())}\n{_stack()}"
        )
        return _orig_run(*args, **kwargs)

    subprocess.Popen = _popen  # type: ignore[assignment]
    subprocess.run = _run  # type: ignore[assignment]

    # Wrap os.system and os.exec* if present
    try:
        _orig_system = os.system

        def _system(cmd: str) -> int:
            _log(
                f"\n[spawn] pid={os.getpid()} ppid={getattr(os, 'getppid', lambda: -1)()} "
                f"system cmd={cmd!r}\n{_stack()}"
            )
            return _orig_system(cmd)

        os.system = _system  # type: ignore[assignment]
    except Exception:
        pass

    for _name in ("execv", "execve", "execl", "execlp", "execvp", "execvpe"):
        if hasattr(os, _name):
            try:
                _orig = getattr(os, _name)

                def _wrap(orig):  # type: ignore[no-untyped-def]
                    def _inner(*a, **k):  # type: ignore[no-untyped-def]
                        _log(
                            f"\n[spawn] pid={os.getpid()} ppid={getattr(os, 'getppid', lambda: -1)()} "
                            f"{orig.__name__} args={a} kwargs={list(k.keys())}\n{_stack()}"
                        )
                        return orig(*a, **k)

                    return _inner

                setattr(os, _name, _wrap(_orig))
            except Exception:
                pass


def main() -> None:

    _singleton_trace("main_enter")

    try:
        _install_spawn_debug()
    except Exception:
        pass

    # Safety net: if this module was imported and main() is called manually,
    # still enforce single-instance.
    try:
        if _SINGLE_INSTANCE_LOCK_HANDLE is None:
            _ensure_single_instance_or_exit()
    except SystemExit:
        raise
    except Exception:
        pass

    settings = Settings.from_env()

    debug = str(os.getenv("BOT_DEBUG", "")).strip().lower() in ("1", "true", "yes", "y", "on")
    log_level = logging.DEBUG if debug else logging.INFO
    try:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s (%(filename)s:%(lineno)d %(threadName)s) %(levelname)s - %(name)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
            force=True,
        )
    except Exception:
        pass

    try:
        _install_signal_debug_handlers()
    except Exception:
        pass

    try:
        print(f"BOOT pid={os.getpid()} ppid={getattr(os, 'getppid', lambda: -1)()}")
    except Exception:
        pass

    db = Database(settings.database_path)
    db.init()
    db.ensure_default_tasks()

    # Safety: admins must never be blocked.
    try:
        admin_ids = set(getattr(settings, "admin_ids", frozenset({settings.admin_id})))
        for aid in admin_ids:
            try:
                db.ensure_user(int(aid), None, None)
            except Exception:
                pass
            try:
                db.set_blocked(int(aid), False)
            except Exception:
                pass
    except Exception:
        pass

    bot = telebot.TeleBot(settings.bot_token, parse_mode=None)

    try:
        telebot.logger.setLevel(log_level)
    except Exception:
        pass

    # Network resilience: Telegram API calls can time out on unstable networks.
    # Make timeouts a bit more forgiving to reduce polling exits.
    try:
        from telebot import apihelper  # type: ignore

        apihelper.CONNECT_TIMEOUT = 30
        apihelper.READ_TIMEOUT = 60
        apihelper.LONG_POLLING_TIMEOUT = 30

        if debug:
            apihelper.DEBUG = True
    except Exception:
        pass

    # Make edits safe globally (prevents 400/403 from crashing callback flows).
    _orig_edit_message_text = bot.edit_message_text
    _orig_edit_message_reply_markup = bot.edit_message_reply_markup
    _orig_answer_callback_query = bot.answer_callback_query

    def _is_ignorable_callback_answer_error(e: Exception) -> bool:
        msg = str(e) or ""
        # Telegram can return this when user clicks an old inline button or
        # when bot answers too late. It's safe to ignore.
        return (
            "query is too old" in msg.lower()
            or "response timeout expired" in msg.lower()
            or "query id is invalid" in msg.lower()
        )

    def _wrapped_edit_message_text(*args, **kwargs):  # type: ignore
        try:
            return _orig_edit_message_text(*args, **kwargs)
        except Exception as e:
            if _is_ignorable_edit_error(e):
                return None
            raise

    def _wrapped_edit_message_reply_markup(*args, **kwargs):  # type: ignore
        try:
            return _orig_edit_message_reply_markup(*args, **kwargs)
        except Exception as e:
            if _is_ignorable_edit_error(e):
                return None
            raise

    def _wrapped_answer_callback_query(*args, **kwargs):  # type: ignore
        try:
            return _orig_answer_callback_query(*args, **kwargs)
        except Exception as e:
            if _is_ignorable_callback_answer_error(e):
                return None
            raise

    try:
        bot.edit_message_text = _wrapped_edit_message_text  # type: ignore
        bot.edit_message_reply_markup = _wrapped_edit_message_reply_markup  # type: ignore
        bot.answer_callback_query = _wrapped_answer_callback_query  # type: ignore
    except Exception:
        pass
    sessions: dict[int, Session] = {}
    sessions_lock = threading.Lock()
    warned_admin_channel_access: bool = False

    # In-memory admin↔user chat mode: user_id -> admin_id
    admin_chat_map: dict[int, int] = {}
    admin_chat_lock = threading.Lock()

    def session(user_id: int) -> Session:
        with sessions_lock:
            if user_id not in sessions:
                sessions[user_id] = Session()
            return sessions[user_id]

    def _touch_game(uid_local: int, *, game: str, chat_id: int | None = None, message_id: int | None = None) -> None:
        try:
            s_local = session(int(uid_local))
            s_local.game_last_action_at[str(game)] = float(time.time())
            if chat_id is not None and message_id is not None:
                s_local.game_inactivity_target[str(game)] = (int(chat_id), int(message_id))
        except Exception:
            pass

    def _schedule_game_inactivity(uid_local: int, *, game: str, chat_id: int | None = None, message_id: int | None = None) -> None:
        """Arm a 60s inactivity timer for a game.

        When fired, it re-checks that the token still matches and that the game is still active.
        """
        game = str(game)
        _touch_game(int(uid_local), game=game, chat_id=chat_id, message_id=message_id)
        try:
            s_local = session(int(uid_local))
        except Exception:
            return

        token = ""
        try:
            token = os.urandom(8).hex()
        except Exception:
            token = str(time.time())

        try:
            s_local.game_inactivity_token[game] = str(token)
        except Exception:
            return

        def _timer_worker() -> None:
            try:
                s_now = session(int(uid_local))
            except Exception:
                return

            try:
                current_token = str(s_now.game_inactivity_token.get(game, "") or "")
            except Exception:
                current_token = ""
            if current_token != str(token):
                return

            try:
                last_at = float(s_now.game_last_action_at.get(game, 0.0) or 0.0)
            except Exception:
                last_at = 0.0
            if last_at <= 0:
                return
            if (time.time() - last_at) < float(INACTIVITY_TIMEOUT_SECONDS):
                return

            try:
                _handle_game_inactivity_timeout(int(uid_local), game=game)
            except Exception:
                pass

        t = threading.Timer(float(INACTIVITY_TIMEOUT_SECONDS) + 1.0, _timer_worker)
        try:
            t.daemon = True
        except Exception:
            pass
        t.start()

    def _handle_game_inactivity_timeout(uid_local: int, *, game: str) -> None:
        uid_local = int(uid_local)
        game = str(game)
        s_local = session(uid_local)

        try:
            target = s_local.game_inactivity_target.get(game)
        except Exception:
            target = None
        if target and isinstance(target, tuple) and len(target) == 2:
            chat_id, message_id = int(target[0]), int(target[1])
        else:
            chat_id, message_id = 0, 0

        if game == "mines":
            if str(getattr(s_local, "mines_state", "none")) != "active" or not getattr(s_local, "mines_round_id", None):
                return
            now_ts = int(time.time())
            bet_snapshot = 0
            try:
                bet_snapshot = int(getattr(s_local, "mines_bet", 0) or 0)
            except Exception:
                bet_snapshot = 0
            try:
                _audit_mines("timeout_inactivity", user_id=uid_local, round_id=int(s_local.mines_round_id), mode=str(getattr(s_local, "mines_mode", "classic")))
            except Exception:
                pass

            rnd_timeout = None
            try:
                rnd_timeout = db.get_mines_round(int(s_local.mines_round_id))
            except Exception:
                rnd_timeout = None
            if rnd_timeout and str(rnd_timeout.get("mode") or "") == "nobet":
                try:
                    opened = set(int(x) for x in json.loads(str(rnd_timeout.get("opened_cells") or "[]")))
                except Exception:
                    opened = set()
                try:
                    _tourn_submit_from_mines_round(rnd=rnd_timeout, user_id=uid_local, score=len(opened), now_ts=now_ts)
                except Exception:
                    pass

            # Requested UX: after 60s inactivity, reset parameters too.
            _mines_reset(uid_local, preserve_params=False)

            if chat_id and message_id:
                try:
                    bet_line = f"\n\nТвоя ставка: {_fmt_points_ui(int(bet_snapshot))}" if bet_snapshot > 0 else ""
                    bot.edit_message_text(
                        "⏳ Бездействие 60 секунд. Раунд закрыт." + bet_line,
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=mines_timeout_kb(),
                    )
                except Exception:
                    pass
            return

        if game == "ladder":
            if not bool(getattr(s_local, "ladder_active", False)) or not getattr(s_local, "ladder_bet", None):
                return
            bet = int(s_local.ladder_bet)
            mines_snapshot = list(getattr(s_local, "ladder_mines", []) or [])
            choices_snapshot = list(getattr(s_local, "ladder_choices", []) or [])
            step_snapshot = int(getattr(s_local, "ladder_step", 0) or 0)

            s_local.ladder_active = False
            s_local.ladder_bet = None
            s_local.ladder_step = 0
            s_local.ladder_multiplier = 1.0
            s_local.ladder_current_mine = None
            s_local.ladder_mines = []
            s_local.ladder_choices = []

            if len(mines_snapshot) < 6:
                mines_snapshot = [random.randint(0, 2) for _ in range(6)]
            if len(choices_snapshot) < 6:
                choices_snapshot = [None for _ in range(6)]
            reveal_step = max(0, step_snapshot - 1)

            if chat_id and message_id:
                try:
                    bot.edit_message_text(
                        "⏳ Бездействие 60 секунд.\n\n❌ Ты проиграл ставку.",
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=ladder_result_kb(bet=bet, mines=mines_snapshot, choices=choices_snapshot, step=reveal_step),
                    )
                except Exception:
                    pass
            return

        if game == "rps":
            if not bool(getattr(s_local, "rps_active", False)) or getattr(s_local, "rps_stake", None) is None:
                return
            stake = int(s_local.rps_stake or 0)
            s_local.rps_active = False
            s_local.rps_stake = None
            s_local.rps_bot_choice = None

            if chat_id and message_id:
                try:
                    bot.edit_message_text(
                        f"⏳ Бездействие 60 секунд.\n\n😢 Проигрыш. Ты потерял ставку {_fmt_points_ui(int(stake))} баллов.",
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=rps_result_kb(),
                    )
                except Exception:
                    pass
            return

        if game == "wheel":
            if not bool(getattr(s_local, "wheel_active", False)) or getattr(s_local, "wheel_bet", None) is None:
                return
            s_local.wheel_active = False
            s_local.wheel_bet = None

            if chat_id and message_id:
                try:
                    bot.edit_message_text(
                        "⏳ Бездействие 60 секунд.\n\nСтавка отменена.",
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=wheel_result_kb(),
                    )
                except Exception:
                    try:
                        bot.edit_message_text(
                            "⏳ Бездействие 60 секунд. Ставка отменена.",
                            chat_id=chat_id,
                            message_id=message_id,
                            reply_markup=None,
                        )
                    except Exception:
                        pass
            return

    def _remember_temp_notice(uid_local: int, msg: Message | None) -> None:
        if msg is None:
            return
        try:
            s = session(int(uid_local))
            s.temp_notice_chat_id = int(msg.chat.id)
            s.temp_notice_message_id = int(msg.message_id)
        except Exception:
            pass

    def _clear_temp_notice(uid_local: int) -> None:
        try:
            s = session(int(uid_local))
        except Exception:
            return

        try:
            cid = int(getattr(s, "temp_notice_chat_id", 0) or 0)
            mid = int(getattr(s, "temp_notice_message_id", 0) or 0)
        except Exception:
            cid = 0
            mid = 0

        # Safety: never delete the user's main panel message even if ids got mixed up.
        try:
            panel_cid = int(getattr(s, "panel_chat_id", 0) or 0)
            panel_mid = int(getattr(s, "panel_message_id", 0) or 0)
        except Exception:
            panel_cid = 0
            panel_mid = 0

        if cid and mid and not (panel_cid and panel_mid and cid == panel_cid and mid == panel_mid):
            _safe_delete_message(bot, cid, mid)

        try:
            s.temp_notice_chat_id = None
            s.temp_notice_message_id = None
        except Exception:
            pass

    def panel_send_or_edit(
        *,
        chat_id: int,
        user_id: int,
        text: str,
        kb: InlineKeyboardMarkup | None,
        screen: str,
        push_history: bool = True,
    ) -> None:
        s = session(int(user_id))
        if not bool(getattr(s, "panel_mode", True)):
            try:
                bot.send_message(int(chat_id), str(text), reply_markup=kb)
            except Exception:
                pass
            return

        chat_id = int(chat_id)
        screen = str(screen)

        # If panel is in another chat, recreate it and reset history.
        if s.panel_chat_id != chat_id:
            s.panel_chat_id = chat_id
            s.panel_message_id = None
            try:
                s.panel_history.clear()
            except Exception:
                s.panel_history = []
            s.panel_screen = "main"

        # Back stack
        try:
            if push_history and s.panel_screen != screen:
                s.panel_history.append(str(s.panel_screen))
        except Exception:
            pass
        s.panel_screen = screen

        # Try edit existing panel message
        if s.panel_message_id:
            try:
                bot.edit_message_text(
                    str(text),
                    chat_id=chat_id,
                    message_id=int(s.panel_message_id),
                    reply_markup=kb,
                )
                return
            except Exception as e:
                try:
                    s.panel_last_error = f"edit failed: {type(e).__name__}: {e}"
                except Exception:
                    pass

                # If panel edit fails, we will fall back to sending a new message.

        # Fallback: send a new panel message
        try:
            msg = bot.send_message(chat_id, str(text), reply_markup=kb)
            s.panel_message_id = int(msg.message_id)
        except Exception as e:
            try:
                s.panel_last_error = f"send failed: {type(e).__name__}: {e}"
            except Exception:
                pass

            # One more fallback: try without keyboard (often fixes invalid markup issues)
            try:
                msg2 = bot.send_message(chat_id, str(text))
                s.panel_message_id = int(msg2.message_id)
                return
            except Exception:
                pass

            # Debug for admins: show the real reason (without inline keyboard), otherwise it looks like "nothing happened".
            try:
                if _is_admin(int(user_id), settings):
                    bot.send_message(
                        int(chat_id),
                        "⚠️ Panel error: " + str(getattr(s, "panel_last_error", "unknown")) + f"\nЭкран: {screen}",
                    )
            except Exception:
                pass

    def _profile_build_text(uid_local: int) -> str:
        uid_local = int(uid_local)
        info = db.get_user_level_info(uid_local) or {}
        prof = db.get_profile(uid_local) if not info else None

        user_id = int(info.get("user_id") or (prof.get("user_id") if prof else uid_local) or uid_local)
        balance_points = int(info.get("balance_points") or (prof.get("balance_points") if prof else 0) or 0)
        completed_tasks = int(info.get("completed_tasks") or (prof.get("completed_tasks") if prof else 0) or 0)
        referrals_count = int(info.get("referrals_count") or (prof.get("referrals_count") if prof else 0) or 0)

        vip_active = bool(info.get("vip_active"))
        vip_until = int(info.get("vip_until") or 0)

        # Extra stats
        try:
            mining = db.get_mining_rank_position(user_id) or {}
            mined_btc = float(mining.get("mining_btc") or 0.0)
        except Exception:
            mined_btc = 0.0

        snap = None
        try:
            snap = db.get_user_stats_snapshot(user_id)
        except Exception:
            snap = None
        duel_wins = int((snap or {}).get("duel_wins") or 0)
        duel_games = int((snap or {}).get("duel_games") or 0)

        try:
            games_played = int(db.get_user_games_count(user_id) or 0)
        except Exception:
            games_played = 0

        lines: list[str] = []
        lines.append("👤 МОЙ ПРОФИЛЬ")
        lines.append("")
        lines.append(f"🆔 ID: {user_id}")
        lines.append(f"💰 Баланс: {_fmt_points_ui(balance_points)} баллов")
        try:
            ins = db.get_insurance_state(user_id) or {}
            insurance_balance = int(ins.get("balance") or 0)
            insurance_next = bool(int(ins.get("next") or 0))
            insurance_blocked = bool(int(ins.get("block") or 0))
            lines.append(
                "🛡 Страховки: "
                f"{max(0, insurance_balance)} "
                f"(включены: {'ВКЛ' if insurance_next else 'ВЫКЛ'}, блок: {'ДА' if insurance_blocked else 'НЕТ'})"
            )
        except Exception:
            pass
        lines.append("")
        if vip_active and vip_until > 0:
            now_ts = int(time.time())
            if vip_until >= now_ts + 100 * 365 * 24 * 3600:
                lines.append("👑 VIP: ✅ навсегда")
            else:
                lines.append(f"👑 VIP: ✅ активен до {_fmt_date_ddmmyyyy(vip_until)}")
        else:
            lines.append("👑 VIP: ❌ не активен")
            lines.append("💎 Купить VIP — бонусы x2!")

        lines.append("")
        lines.append("📈 Статистика")
        lines.append(f"✅ Заданий выполнено: {_fmt_int(completed_tasks)}")
        lines.append(f"👥 Приглашено друзей: {_fmt_int(referrals_count)}")
        lines.append(f"⛏️ Добыто BTC: {mined_btc:.4f}")
        lines.append(f"🎮 Игр сыграно: {_fmt_int(games_played)}")
        lines.append(f"🏆 Побед в дуэлях: {_fmt_int(duel_wins)}/{_fmt_int(duel_games)}")

        return "\n".join(lines)

    def show_screen(*, chat_id: int, user_id: int, screen: str, push_history: bool = True) -> None:
        screen = str(screen)
        chat_id = int(chat_id)
        user_id = int(user_id)

        if screen.startswith("admin_users:"):
            if not _is_admin(user_id, settings):
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="Экран недоступен.", kb=kb, screen=screen, push_history=push_history)
                return

            s_admin = session(int(user_id))
            parts = screen.split(":")
            view = parts[1] if len(parts) > 1 else "home"

            if view == "home":
                show_screen(chat_id=chat_id, user_id=user_id, screen="admin_users:list:0", push_history=False)
                return

            if view == "search":
                # Allow typing immediately after opening the search screen.
                s_admin.admin_users_expect = "search"
                err = (s_admin.admin_users_error or "").strip()
                text = "🔎 Поиск пользователя\n\nВведите ID или @username."
                if err:
                    text = f"❌ {err}\n\n" + text
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:list:{int(s_admin.admin_users_page or 0)}"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "list":
                page = 0
                if len(parts) > 2 and str(parts[2]).isdigit():
                    page = int(parts[2])
                else:
                    page = int(getattr(s_admin, "admin_users_page", 0) or 0)

                q = (s_admin.admin_users_query or "").strip() or None

                per_page = 15
                total = int(db.count_users_filtered(blocked_only=False, query=q) or 0)
                total_pages = max(1, (total + per_page - 1) // per_page)
                page = max(0, min(page, total_pages - 1))
                s_admin.admin_users_page = int(page)

                items = db.list_users_filtered(
                    blocked_only=False,
                    query=q,
                    limit=per_page,
                    offset=page * per_page,
                )

                # Keep the message non-empty (Telegram requirement) but minimal.
                # User list is still shown only as buttons.
                text = "👤 Пользователи"

                kb = InlineKeyboardMarkup()

                n = len(items)
                if n <= 5:
                    cols = 1
                elif n <= 10:
                    cols = 2
                else:
                    cols = 3

                buttons: list[InlineKeyboardButton] = []
                for u in items:
                    uid_local = int(u.get("user_id") or 0)
                    buttons.append(InlineKeyboardButton(_admin_users_short_name(u), callback_data=f"admusr:card:{uid_local}"))

                rows = 5
                for r in range(rows):
                    row_btns: list[InlineKeyboardButton] = []
                    for c in range(cols):
                        idx = r + c * rows
                        if idx < len(buttons):
                            row_btns.append(buttons[idx])
                    if row_btns:
                        kb.row(*row_btns)

                # Pagination only if 16+ users exist.
                if total > per_page:
                    prev_page = max(0, page - 1)
                    next_page = min(total_pages - 1, page + 1)
                    kb.row(
                        InlineKeyboardButton("⬅", callback_data=f"admusr:list:{prev_page}"),
                        InlineKeyboardButton("Перелистнуть ➡", callback_data=f"admusr:list:{next_page}"),
                    )

                kb.row(InlineKeyboardButton("🔎 Поиск пользователей", callback_data="admusr:search"))
                if q:
                    kb.row(InlineKeyboardButton("🧹 Сбросить поиск", callback_data="admusr:clear"))

                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "card":
                if len(parts) < 3 or not str(parts[2]).isdigit():
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("⬅ Назад", callback_data="admusr:list:0"))
                    panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="❌ Некорректный пользователь.", kb=kb, screen=screen, push_history=push_history)
                    return

                target_id = int(parts[2])
                s_admin.admin_users_target_user_id = int(target_id)
                text = _admin_users_card_text(target_id)

                u = db.find_user(target_id) or {}
                blocked_flag = bool(int(u.get("blocked") or 0))

                kb = InlineKeyboardMarkup()
                kb.row(
                    InlineKeyboardButton("💬 Написать", callback_data=f"admusr:chat:start:{target_id}"),
                    InlineKeyboardButton("💰 Баллы", callback_data=f"admusr:points_menu:{target_id}"),
                )
                if blocked_flag:
                    kb.row(InlineKeyboardButton("✅ Разблокировать", callback_data=f"admusr:blkask:0:{target_id}"))
                else:
                    kb.row(InlineKeyboardButton("⛔ Заблокировать", callback_data=f"admusr:blkask:1:{target_id}"))
                kb.row(
                    InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:list:{int(s_admin.admin_users_page or 0)}"),
                )
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "blkask":
                if len(parts) < 4 or not str(parts[2]).isdigit() or not str(parts[3]).isdigit():
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("⬅ Назад", callback_data="admusr:home"))
                    panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="❌ Некорректное действие.", kb=kb, screen=screen, push_history=push_history)
                    return

                do_block = int(parts[2])  # 1 block, 0 unblock
                target_id = int(parts[3])
                s_admin.admin_users_target_user_id = int(target_id)
                s_admin.admin_users_pending_action = "block" if do_block == 1 else "unblock"

                title = "⛔ Блокировка" if do_block == 1 else "✅ Разблокировка"
                text = (
                    f"{title}\n\n"
                    f"Пользователь: {target_id}\n"
                    f"Уведомления: {'ВКЛ' if bool(s_admin.admin_users_notify) else 'ВЫКЛ'}\n\n"
                    "Выберите вариант:"
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("Без причины", callback_data=f"admusr:blkdo:{do_block}:{target_id}"))
                kb.row(InlineKeyboardButton("✍ Ввести причину", callback_data=f"admusr:blkreason:{do_block}:{target_id}"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:card:{target_id}"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "block_reason":
                if len(parts) < 4 or not str(parts[2]).isdigit() or not str(parts[3]).isdigit():
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("⬅ Назад", callback_data="admusr:home"))
                    panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="❌ Некорректное действие.", kb=kb, screen=screen, push_history=push_history)
                    return

                do_block = int(parts[2])
                target_id = int(parts[3])
                title = "⛔ Блокировка" if do_block == 1 else "✅ Разблокировка"
                text = f"{title}\n\nПользователь: {target_id}\n\nОтправьте причину сообщением:"
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:blkask:{do_block}:{target_id}"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "points_menu":
                if len(parts) < 3 or not str(parts[2]).isdigit():
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("⬅ Назад", callback_data="admusr:home"))
                    panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="❌ Некорректное действие.", kb=kb, screen=screen, push_history=push_history)
                    return

                target_id = int(parts[2])
                try:
                    bal = int(db.get_balance(int(target_id)) or 0)
                except Exception:
                    bal = 0

                text = "💰 Баллы\n\n" f"Пользователь: {target_id}\n" f"Баланс: {_fmt_money(bal)}\n\n" "Выберите действие:"
                kb = InlineKeyboardMarkup()
                kb.row(
                    InlineKeyboardButton("🎁 Подарить", callback_data=f"admusr:points:+:{target_id}"),
                    InlineKeyboardButton("🧾 Забрать", callback_data=f"admusr:points:-:{target_id}"),
                )
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:card:{target_id}"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "chat":
                if len(parts) < 3 or not str(parts[2]).isdigit():
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("⬅ Назад", callback_data="admusr:home"))
                    panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="❌ Некорректное действие.", kb=kb, screen=screen, push_history=push_history)
                    return

                target_id = int(parts[2])
                u = db.find_user(int(target_id)) or {}
                uname = u.get("username")
                uname_txt = f"@{uname}" if uname else "без_ника"

                did = 0
                try:
                    did = int(db.get_or_create_dialog(user_id=int(target_id), admin_id=int(user_id), now_ts=int(time.time())) or 0)
                except Exception:
                    did = 0

                d_status = ""
                try:
                    d = db.get_dialog(int(did)) if did else None
                    if d:
                        d_status = str(d.get("status") or "")
                except Exception:
                    d_status = ""

                text = (
                    "💬 Диалог\n\n"
                    f"Пользователь: {target_id} ({uname_txt})\n"
                    + (f"Диалог: #{did} ({d_status})\n\n" if did else "\n")
                    + "Используйте кнопки ниже для ответа/истории/завершения."
                )
                if did:
                    kb = dialog_admin_kb(int(did), history_count=5)
                else:
                    kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:card:{target_id}"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "points_amount":
                if len(parts) < 4:
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("⬅ Назад", callback_data="admusr:home"))
                    panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="❌ Некорректное действие.", kb=kb, screen=screen, push_history=push_history)
                    return

                sign_raw = str(parts[2])
                target_id = int(parts[3])
                sign = 1 if sign_raw == "+" else -1
                s_admin.admin_users_target_user_id = int(target_id)
                s_admin.admin_users_points_sign = int(sign)
                s_admin.admin_users_pending_action = "points"

                err = (s_admin.admin_users_error or "").strip()
                header = "➕ Начисление баллов" if sign == 1 else "➖ Списание баллов"
                text = f"{header}\n\nПользователь: {target_id}\n"
                if err:
                    text = f"❌ {err}\n\n" + text
                text += "Введите сумму (например 1.000.000):"
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:points_menu:{target_id}"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "points_confirm":
                if len(parts) < 3 or not str(parts[2]).isdigit():
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("⬅ Назад", callback_data="admusr:home"))
                    panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="❌ Некорректное действие.", kb=kb, screen=screen, push_history=push_history)
                    return

                target_id = int(parts[2])
                delta = int(s_admin.admin_users_pending_value or 0)
                msg = (s_admin.admin_users_pending_text or "").strip()
                delta_txt = ("+" + _fmt_money(delta)) if delta >= 0 else _fmt_money(delta)
                err = (s_admin.admin_users_error or "").strip()
                text = (
                    "💰 Подтверждение\n\n"
                    f"Пользователь: {target_id}\n"
                    f"Изменение: {delta_txt} баллов\n"
                    f"Уведомления: {'ВКЛ' if bool(s_admin.admin_users_notify) else 'ВЫКЛ'}\n"
                    + f"Сообщение: {msg if msg else '(нет)'}"
                )
                if err:
                    text = f"❌ {err}\n\n" + text
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("✅ Подтвердить", callback_data=f"admusr:pointsdo:{target_id}"))
                kb.row(InlineKeyboardButton("✍ Сообщение", callback_data=f"admusr:pointsmsg:{target_id}"))
                if msg:
                    kb.row(InlineKeyboardButton("🧹 Очистить сообщение", callback_data=f"admusr:pointsclear:{target_id}"))
                kb.row(
                    InlineKeyboardButton(
                        f"🔔 Уведомления: {'ВКЛ' if bool(s_admin.admin_users_notify) else 'ВЫКЛ'}",
                        callback_data="admusr:toggle_notify",
                    )
                )
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:points_menu:{target_id}"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "points_message":
                if len(parts) < 3 or not str(parts[2]).isdigit():
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("⬅ Назад", callback_data="admusr:home"))
                    panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="❌ Некорректное действие.", kb=kb, screen=screen, push_history=push_history)
                    return

                target_id = int(parts[2])
                text = (
                    "✍ Сообщение пользователю\n\n"
                    f"Пользователь: {target_id}\n\n"
                    "Отправьте текст сообщением (или '-' чтобы убрать):"
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data=f"admusr:points_confirm:{target_id}"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admusr:home"))
            panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="Экран не найден.", kb=kb, screen=screen, push_history=push_history)
            return

        if screen.startswith("admin_stats:"):
            if not _is_admin(user_id, settings):
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="Экран недоступен.", kb=kb, screen=screen, push_history=push_history)
                return

            parts = screen.split(":")
            view = parts[1] if len(parts) > 1 else "menu"

            now_ts = int(time.time())
            since_ts = now_ts - 24 * 60 * 60
            since_iso = (dt.datetime.utcnow() - dt.timedelta(hours=24)).isoformat()

            def _menu_kb() -> InlineKeyboardMarkup:
                kb2 = InlineKeyboardMarkup()
                kb2.row(
                    InlineKeyboardButton("👥 Пользователи", callback_data="ui:go:admin_stats:users"),
                    InlineKeyboardButton("💳 Финансы", callback_data="ui:go:admin_stats:finances"),
                )
                kb2.row(
                    InlineKeyboardButton("🎮 Мини-игры", callback_data="ui:go:admin_stats:minigames"),
                    InlineKeyboardButton("⛏ Ферма", callback_data="ui:go:admin_stats:farm"),
                )
                kb2.row(InlineKeyboardButton("⚡ Активность", callback_data="ui:go:admin_stats:activity"))
                kb2.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                return kb2

            if view in {"menu", "home"}:
                text = "📊 Статистика\n\nВыберите раздел:" 
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=_menu_kb(), screen=screen, push_history=push_history)
                return

            if view == "users":
                st = db.admin_stats_users(now_ts=now_ts, since_iso=since_iso)
                text = (
                    "👥 Пользователи\n\n"
                    f"Всего: {int(st.get('total') or 0)}\n"
                    f"Активных (не заблок.): {int(st.get('active') or 0)}\n"
                    f"Заблокировано: {int(st.get('blocked') or 0)}\n"
                    f"Новых за 24ч: {int(st.get('new_since') or 0)}\n"
                    f"VIP активных: {int(st.get('vip_active') or 0)}\n\n"
                    f"Сумма балансов: {_fmt_money(int(st.get('balances_sum') or 0))}\n"
                    f"Макс. баланс: {_fmt_money(int(st.get('balance_max') or 0))}"
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🏠 Меню статистики", callback_data="ui:go:admin_stats:menu"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "finances":
                st = db.admin_stats_withdrawals(since_iso=since_iso)
                text = (
                    "💳 Финансы (выводы)\n\n"
                    f"Всего заявок: {int(st.get('total') or 0)}\n"
                    f"Новых за 24ч: {int(st.get('new_since') or 0)}\n\n"
                    f"⏳ Pending: {int(st.get('pending_cnt') or 0)}\n"
                    f"✅ Paid: {int(st.get('paid_cnt') or 0)}\n"
                    f"❌ Rejected: {int(st.get('rejected_cnt') or 0)}\n\n"
                    f"Выплачено (баллы): {_fmt_money(int(st.get('paid_points') or 0))}\n"
                    f"Выплачено (руб): {int(st.get('paid_rub') or 0)}"
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🏠 Меню статистики", callback_data="ui:go:admin_stats:menu"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "minigames":
                mines = db.admin_stats_mines(since_ts=since_ts)
                wheel = db.admin_stats_wheel()
                duels = db.admin_stats_duels(since_iso=since_iso)

                mines_profit = int(mines.get("profit_sum") or 0)
                mines_profit_txt = ("+" + _fmt_money(mines_profit)) if mines_profit >= 0 else _fmt_money(mines_profit)

                text = (
                    "🎮 Мини-игры\n\n"
                    "💣 Mines:\n"
                    f"  • Всего раундов: {int(mines.get('total') or 0)}\n"
                    f"  • Активных: {int(mines.get('active') or 0)}\n"
                    f"  • Cashout: {int(mines.get('cashed_out') or 0)}\n"
                    f"  • Lost: {int(mines.get('lost') or 0)}\n"
                    f"  • Timeout: {int(mines.get('timeout') or 0)}\n"
                    f"  • Ставок (сумма): {_fmt_money(int(mines.get('bet_sum') or 0))}\n"
                    f"  • Выплат (сумма): {_fmt_money(int(mines.get('payout_sum') or 0))}\n"
                    f"  • Профит (≈): {mines_profit_txt}\n"
                    f"  • За 24ч (стартов): {int(mines.get('started_since') or 0)}\n"
                    f"  • Режимы: nobet={int(mines.get('nobet_total') or 0)}, stake={int(mines.get('stake_total') or 0)}\n\n"
                    "🎡 Колесо:\n"
                    f"  • Игроков: {int(wheel.get('players') or 0)}\n"
                    f"  • Прокрутов: {int(wheel.get('rolls') or 0)}\n"
                    f"  • Выигрыш (сумма): {_fmt_money(int(wheel.get('win_sum') or 0))}\n"
                    f"  • Лучший выигрыш: {_fmt_money(int(wheel.get('best_win') or 0))}\n\n"
                    "⚔ Дуэли:\n"
                    f"  • Всего: {int(duels.get('total') or 0)} (24ч: {int(duels.get('created_since') or 0)})\n"
                    f"  • Waiting/Active/Resolved: {int(duels.get('waiting') or 0)}/{int(duels.get('active') or 0)}/{int(duels.get('resolved') or 0)}\n"
                    f"  • Ставки (сумма): {_fmt_money(int(duels.get('stake_sum') or 0))}\n"
                    f"  • Счётчики users: игр={_fmt_money(int(duels.get('user_games') or 0))}, W={_fmt_money(int(duels.get('user_wins') or 0))}, L={_fmt_money(int(duels.get('user_losses') or 0))}, best MMR={int(duels.get('best_mmr') or 0)}\n\n"
                    "🎲 Кости с ботом: (нет сохранения статистики)\n"
                    "🪜 Лесенка: (нет сохранения статистики)\n"
                    "✊✌️🖐 КНБ с ботом: (нет сохранения статистики)"
                )

                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🏠 Меню статистики", callback_data="ui:go:admin_stats:menu"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "farm":
                st = db.admin_stats_farm(now_ts=now_ts, since_ts=since_ts)
                total_btc = Decimal(str(st.get("total_btc") or 0.0))
                cur_btc = Decimal(str(st.get("current_btc") or 0.0))
                text = (
                    "⛏ CryptoMine (ферма)\n\n"
                    f"Ферм создано: {int(st.get('farms') or 0)}\n"
                    f"Ферм активных (mining_active): {int(st.get('active') or 0)}\n"
                    f"Заблокировано (locked_until): {int(st.get('locked') or 0)}\n"
                    f"Активность за 24ч (mining_last_ts): {int(st.get('active_since') or 0)}\n\n"
                    f"BTC (накоплено всего): {_cm_fmt_btc(total_btc)}\n"
                    f"BTC (на руках сейчас): {_cm_fmt_btc(cur_btc)}"
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🏠 Меню статистики", callback_data="ui:go:admin_stats:menu"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if view == "activity":
                st = db.admin_stats_activity(since_ts=since_ts, since_iso=since_iso)
                text = (
                    "⚡ Активность за 24 часа\n\n"
                    f"Новых пользователей: {int(st.get('new_users') or 0)}\n"
                    f"Фарм-клики (last_farm_time): {int(st.get('farm_active') or 0)}\n"
                    f"Майнинг активность (mining_last_ts): {int(st.get('mining_active') or 0)}\n"
                    f"Mines раунды (started_at): {int(st.get('mines_rounds') or 0)}\n"
                    f"Сообщений в диалогах: {int(st.get('dialog_msgs') or 0)}\n"
                    f"Заявок на вывод: {int(st.get('withdrawals') or 0)}"
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🏠 Меню статистики", callback_data="ui:go:admin_stats:menu"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            kb = InlineKeyboardMarkup()
            kb.row(InlineKeyboardButton("🏠 Меню статистики", callback_data="ui:go:admin_stats:menu"))
            kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
            panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="Экран не найден.", kb=kb, screen=screen, push_history=push_history)
            return

        if screen.startswith("weekly_event:"):
            parts = screen.split(":")
            view = parts[1] if len(parts) > 1 else "home"

            now_ts = int(time.time())
            try:
                st = db.get_weekly_event_state(int(user_id), now_ts=now_ts)
            except Exception:
                st = {"week_index": 0, "event_id": 1, "claimed": 0}

            week_index = int(st.get("week_index") or 0)
            event_id = int(st.get("event_id") or 1)
            claimed = bool(int(st.get("claimed") or 0))

            def _kb_back_only() -> InlineKeyboardMarkup:
                kb0 = InlineKeyboardMarkup()
                kb0.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                return kb0

            if view not in {"home", "show"}:
                panel_send_or_edit(
                    chat_id=chat_id,
                    user_id=user_id,
                    text="Экран не найден.",
                    kb=_kb_back_only(),
                    screen=screen,
                    push_history=push_history,
                )
                return

            if claimed:
                text = "🎁 Событие недели\n\nПодарок на этой неделе уже получен. Возвращайся через неделю!"
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            # Event texts (no smiley-faces in events 1-3; only event 4 has lots of emojis)
            if event_id == 1:
                text = (
                    "🌤 Сегодня чудный день, не так ли?\n\n"
                    "Иногда удача приходит просто так —\n"
                    "без причин и объяснений.\n\n"
                    "Мы решили немного поднять тебе настроение."
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🎁 Забрать подарок", callback_data=f"we:claim:{week_index}:1"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if event_id == 2:
                text = (
                    "🌙 Этот день чувствуется по-особенному…\n\n"
                    "Будто сегодня всё идёт чуть иначе.\n"
                    "Иногда это хороший знак ✨"
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🎁 Забрать подарок", callback_data=f"we:claim:{week_index}:2"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            if event_id == 3:
                text = (
                    "🎁 Что-то для тебя сегодня есть.\n\n"
                    "Без условий.\n"
                    "Без ожиданий.\n"
                    "Просто подарок."
                )
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🎁 Забрать подарок", callback_data=f"we:claim:{week_index}:3"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
                panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
                return

            # Event 4 (mood)
            text = (
                "✨ Сегодня особенный день.\n\n"
                "Мир будто стал внимательнее,\n"
                "а удача — чуть ближе.\n\n"
                "Какое у тебя сегодня настроение?\n"
                "Выбери смайлик 🎭"
            )

            emojis = ["🥳", "😋", "😊", "🙂", "😐", "😶", "😒", "😟", "😣", "😡"]
            kb = InlineKeyboardMarkup()
            kb.row(
                InlineKeyboardButton(emojis[0], callback_data=f"we:mood:{week_index}:4:0"),
                InlineKeyboardButton(emojis[1], callback_data=f"we:mood:{week_index}:4:1"),
                InlineKeyboardButton(emojis[2], callback_data=f"we:mood:{week_index}:4:2"),
                InlineKeyboardButton(emojis[3], callback_data=f"we:mood:{week_index}:4:3"),
                InlineKeyboardButton(emojis[4], callback_data=f"we:mood:{week_index}:4:4"),
            )
            kb.row(
                InlineKeyboardButton(emojis[5], callback_data=f"we:mood:{week_index}:4:5"),
                InlineKeyboardButton(emojis[6], callback_data=f"we:mood:{week_index}:4:6"),
                InlineKeyboardButton(emojis[7], callback_data=f"we:mood:{week_index}:4:7"),
                InlineKeyboardButton(emojis[8], callback_data=f"we:mood:{week_index}:4:8"),
                InlineKeyboardButton(emojis[9], callback_data=f"we:mood:{week_index}:4:9"),
            )
            kb.row(InlineKeyboardButton("⬅ Назад", callback_data="ui:back"))
            panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen=screen, push_history=push_history)
            return

        if screen == "main":
            text = "Главное меню. Выберите раздел:"
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💼 Профиль", callback_data="ui:go:profile"))
            kb.add(InlineKeyboardButton("🎮 Мини игры", callback_data="ui:go:minigames"))
            panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen="main", push_history=push_history)
            return

        if screen == "profile":
            text = _profile_build_text(user_id)
            kb = profile_kb()
            panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen="profile", push_history=push_history)
            return

        if screen == "shop":
            text = _shop_main_text(user_id)
            kb = shop_main_kb()
            panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen="shop", push_history=push_history)
            return

        if screen == "minigames":
            text = "Выберите игру:"
            kb = minigames_menu_kb(show_back=False)
            panel_send_or_edit(chat_id=chat_id, user_id=user_id, text=text, kb=kb, screen="minigames", push_history=push_history)
            return

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back"))
        panel_send_or_edit(chat_id=chat_id, user_id=user_id, text="Экран не найден.", kb=kb, screen="unknown", push_history=push_history)

    def reset_panel_state(user_id: int) -> None:
        s = session(int(user_id))
        s.panel_chat_id = None
        s.panel_message_id = None
        s.panel_screen = "main"
        try:
            s.panel_history.clear()
        except Exception:
            s.panel_history = []

    def reset_user_flow(user_id: int) -> None:
        s = session(user_id)
        s.awaiting_proof_task_id = None
        s.awaiting_proof_task_code = None
        s.withdraw_amount_rub = None
        s.withdraw_bank = None
        s.withdraw_requisites = None
        s.cmf_chat_id = None
        s.cmf_message_id = None
        s.cmf_kb_message_id = None
        s.cmf_mode = False
        s.temp_notice_chat_id = None
        s.temp_notice_message_id = None

    def _set_reply_keyboard_silent(chat_id: int, kb: ReplyKeyboardMarkup) -> None:
        """Apply a reply keyboard without leaving a visible chat message."""
        try:
            m = bot.send_message(int(chat_id), "\u200b", reply_markup=kb)
            try:
                _safe_delete_message(bot, int(chat_id), int(m.message_id))
            except Exception:
                pass
        except Exception:
            # As a last resort (should be rare), fall back to a minimal visible message.
            try:
                bot.send_message(int(chat_id), ".", reply_markup=kb)
            except Exception:
                pass
        # IMPORTANT: do NOT reset panel state here.
        # Panel mode should keep a stable message id across navigation.

    def _maybe_auto_send_weekly_event(chat_id: int, user_id: int) -> bool:
        """Auto-send weekly event message once per week (no menu button).

        Triggered by the weekly-event scheduler. Persisted via DB `notified_at_ts`.
        """
        try:
            now_ts = int(time.time())
            st = db.get_weekly_event_state(int(user_id), now_ts=now_ts)
            if bool(int(st.get("claimed") or 0)):
                return False
            if st.get("notified_at_ts") is not None:
                return False

            week_index = int(st.get("week_index") or 0)
            event_id = int(st.get("event_id") or 1)

            kb = InlineKeyboardMarkup()

            if event_id == 1:
                text = (
                    "🌤 Сегодня чудный день, не так ли?\n\n"
                    "Иногда удача приходит просто так —\n"
                    "без причин и объяснений.\n\n"
                    "Мы решили немного поднять тебе настроение."
                )
                kb.row(InlineKeyboardButton("🎁 Забрать подарок", callback_data=f"we:claim:{week_index}:1"))

            elif event_id == 2:
                text = (
                    "🌙 Этот день чувствуется по-особенному…\n\n"
                    "Будто сегодня всё идёт чуть иначе.\n"
                    "Иногда это хороший знак ✨"
                )
                kb.row(InlineKeyboardButton("🎁 Забрать подарок", callback_data=f"we:claim:{week_index}:2"))

            elif event_id == 3:
                text = (
                    "🎁 Что-то для тебя сегодня есть.\n\n"
                    "Без условий.\n"
                    "Без ожиданий.\n"
                    "Просто подарок."
                )
                kb.row(InlineKeyboardButton("🎁 Забрать подарок", callback_data=f"we:claim:{week_index}:3"))

            else:
                text = (
                    "✨ Сегодня особенный день.\n\n"
                    "Мир будто стал внимательнее,\n"
                    "а удача — чуть ближе.\n\n"
                    "Какое у тебя сегодня настроение?\n"
                    "Выбери смайлик 🎭"
                )
                emojis = ["🥳", "😋", "😊", "🙂", "😐", "😶", "😒", "😟", "😣", "😡"]
                kb.row(
                    InlineKeyboardButton(emojis[0], callback_data=f"we:mood:{week_index}:4:0"),
                    InlineKeyboardButton(emojis[1], callback_data=f"we:mood:{week_index}:4:1"),
                    InlineKeyboardButton(emojis[2], callback_data=f"we:mood:{week_index}:4:2"),
                    InlineKeyboardButton(emojis[3], callback_data=f"we:mood:{week_index}:4:3"),
                    InlineKeyboardButton(emojis[4], callback_data=f"we:mood:{week_index}:4:4"),
                )
                kb.row(
                    InlineKeyboardButton(emojis[5], callback_data=f"we:mood:{week_index}:4:5"),
                    InlineKeyboardButton(emojis[6], callback_data=f"we:mood:{week_index}:4:6"),
                    InlineKeyboardButton(emojis[7], callback_data=f"we:mood:{week_index}:4:7"),
                    InlineKeyboardButton(emojis[8], callback_data=f"we:mood:{week_index}:4:8"),
                    InlineKeyboardButton(emojis[9], callback_data=f"we:mood:{week_index}:4:9"),
                )

            sent = bot.send_message(int(chat_id), text, reply_markup=kb)
            if sent:
                try:
                    db.mark_weekly_event_notified(int(user_id), week_index=week_index, now_ts=now_ts)
                except Exception:
                    pass
            return True
        except Exception:
            return False

    @bot.message_handler(func=lambda m: (not _is_admin(m.from_user.id, settings)) and db.is_blocked(m.from_user.id))
    def blocked_user_guard(message: Message) -> None:
        try:
            bot.send_message(message.chat.id, "Вы заблокированы.")
        except Exception:
            pass
        return

    @bot.message_handler(func=lambda m: m.text == "⚔️ Дуэль")
    def legacy_duel_entry(message: Message) -> None:
        """Обработка старой команды "⚔️ Дуэль": мягко перекидываем в мини-игры.

        Пользователь мог набрать текст вручную или использовать закэшированную клавиатуру,
        поэтому вместо мёртвого кода подсказываем новый путь.
        """
        uid = int(message.from_user.id)
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        bot.send_message(
            message.chat.id,
            "⚔️ Дуэли теперь находятся в разделе «🎮 Мини игры»",
            reply_markup=minigames_menu_kb(),
        )

    def reset_admin_flow(user_id: int) -> None:
        s = session(user_id)
        s.admin_expect_user_lookup = False
        s.admin_add_task_step = None
        s.admin_add_task_code = None
        s.admin_add_task_title = None
        s.admin_add_task_desc = None
        s.admin_add_task_reward = None
        s.admin_add_task_limits = None
        s.admin_add_task_comment_text = None
        s.admin_duel_server_step = None
        s.admin_duel_server_game_type = None
        s.admin_duel_server_stake = None

        s.admin_target_user_id = None
        s.admin_flow = None
        s.admin_gift_amount = None
        s.admin_gift_text = None
        s.admin_gift_notify = True

        s.admin_tourn_step = None
        s.admin_tourn_max_players = None
        s.admin_tourn_start_in_min = None
        s.admin_tourn_entry_fee = None
        s.admin_tourn_prize1 = None
        s.admin_tourn_prize2 = None
        s.admin_tourn_prize3 = None

        # admin users panel
        s.admin_users_expect = None
        s.admin_users_query = None
        s.admin_users_page = 0
        s.admin_users_blocked_only = False
        s.admin_users_notify = True
        s.admin_users_allow_negative = False
        s.admin_users_target_user_id = None
        s.admin_users_pending_action = None
        s.admin_users_points_sign = 1
        s.admin_users_pending_value = None
        s.admin_users_pending_text = None
        s.admin_users_error = None

    def _parse_points_amount(text: str) -> int | None:
        raw = (text or "").strip()
        if not raw:
            return None
        raw = raw.replace(" ", "").replace("_", "")
        raw = raw.replace(".", "").replace(",", "")
        if raw.startswith("+"):
            raw = raw[1:]
        if not raw.isdigit():
            return None
        try:
            val = int(raw)
        except Exception:
            return None
        return val if val >= 0 else None

    def _admin_users_short_name(u: dict) -> str:
        uname = (u.get("username") or "").strip()
        if uname:
            if len(uname) > 14:
                uname = uname[:14] + "…"
            return f"@{uname}"
        return str(int(u.get("user_id") or 0))

    def _admin_users_card_text(target_id: int) -> str:
        target_id = int(target_id)
        u_fallback = db.find_user(target_id) or {}
        info = db.get_user_level_info(target_id)
        if info:
            blocked = bool(int(info.get("blocked") or 0))
            vip_active = bool(info.get("vip_active"))
            uname = (info.get("username") or u_fallback.get("username") or "").strip()
            uname_txt = f"@{uname}" if uname else "без_ника"
            lines = [
                "👤 Пользователь",
                "",
                f"{uname_txt} (ID {int(info.get('user_id') or target_id)})",
                f"Баланс: {_fmt_money(int(info.get('balance_points') or 0))} баллов",
                f"Уровень: {info.get('title')}",
                f"XP: {_fmt_int(info.get('xp'))}",
                f"VIP: {'ДА' if vip_active else 'НЕТ'}",
                f"Статус: {'⛔ Заблокирован' if blocked else '✅ Активен'}",
                f"Заданий: {int(info.get('completed_tasks') or 0)}",
                f"Рефералов: {int(info.get('referrals_count') or 0)}",
            ]
            return "\n".join(lines)

        u = u_fallback
        if not u:
            return "❌ Пользователь не найден."
        status = "⛔ Заблокирован" if int(u.get("blocked") or 0) else "✅ Активен"
        uname = (u.get("username") or "").strip()
        uname_txt = f"@{uname}" if uname else "без_ника"
        return (
            "👤 Пользователь\n\n"
            f"{uname_txt} (ID {u['user_id']})\n"
            + f"Баланс: {_fmt_money(int(u.get('balance_points') or 0))} баллов\n"
            + f"Статус: {status}"
        )

    def _admin_users_send_notify(target_id: int, text: str) -> None:
        try:
            bot.send_message(int(target_id), str(text))
        except Exception:
            pass

    # --- helpers ---

    FARM_REWARD = 10
    FARM_COOLDOWN_SECONDS = 90
    FARM_DAILY_LIMIT = 300
    # В новой спецификации реферальный бонус не используется напрямую во фарме
    FARM_REFERRAL_BONUS_PER_ACTIVE = 0
    # Бонусы за серию дней фарма (выдаются один раз при достижении дня)
    FARM_STREAK_BONUSES = {3: 5, 7: 20, 14: 50, 30: 150}
    FARM_BOOSTER_COST = 50
    FARM_BOOSTER_MULTIPLIER = 2
    FARM_BOOSTER_DURATION_SECONDS = 24 * 60 * 60
    WHEEL_PAID_SPIN_COST = 1000

    WHEEL_REWARDS = {
        100: {
            1: ("❌ Ничего", None),
            2: ("💰 +125 баллов", {"points": 125}),
            3: ("❌ Ничего", None),
            4: ("🎁 x2 фарм на 10 минут", {"farm": (2, 10)}),
            5: ("❌ Ничего", None),
            6: ("🎉 x2 фарм на 20 минут", {"farm": (2, 20)}),
        },
        500: {
            1: ("❌ Ничего", None),
            2: ("💰 +600 баллов", {"points": 600}),
            3: ("❌ Ничего", None),
            4: ("🎁 x2 фарм на 15 минут", {"farm": (2, 15)}),
            5: ("❌ Ничего", None),
            6: ("🎉 x2 фарм на 30 минут", {"farm": (2, 30)}),
        },
        1000: {
            1: ("❌ Ничего", None),
            2: ("💰 +1200 баллов", {"points": 1200}),
            3: ("❌ Ничего", None),
            4: ("🎁 x2 фарм на 30 минут", {"farm": (2, 30)}),
            5: ("❌ Ничего", None),
            6: ("🎉 x3 фарм на 15 минут", {"farm": (3, 15)}),
        },
    }

    WHEEL_BETS = tuple(WHEEL_REWARDS.keys())

    DICE_BETS = (100, 500, 1000)
    DICE_MAX_GAMES_PER_HOUR = 20
    DUEL_COMMISSION_PCT = 10  # комиссия 10% от общего банка

    def _fmt_mmss(seconds: int) -> str:
        seconds = max(0, int(seconds))
        mm = seconds // 60
        ss = seconds % 60
        return f"{mm:02d}:{ss:02d}"

    def _fmt_mss(seconds: int) -> str:
        seconds = max(0, int(seconds))
        mm = seconds // 60
        ss = seconds % 60
        return f"{mm}:{ss:02d}"

    def _fmt_int(n: int | None) -> str:
        try:
            # Use a narrow no-break space so Telegram doesn't collapse/wrap groups.
            return f"{int(n or 0):,}".replace(",", "\u202f")
        except Exception:
            return "0"

    def _fmt_points_ui(n: int | None) -> str:
        try:
            # Use a narrow no-break space so Telegram doesn't collapse/wrap groups.
            return f"{int(n or 0):,}".replace(",", "\u202f")
        except Exception:
            return "0"

    def _insurance_pick_pct() -> tuple[int, bool]:
        """Return (pct, is_bonus)."""
        try:
            if random.random() < (float(INSURANCE_BONUS_CHANCE_PCT) / 100.0):
                return int(INSURANCE_BONUS_REFUND_PCT), True
        except Exception:
            pass
        return int(INSURANCE_BASE_REFUND_PCT), False

    def _insurance_reserve_for_game(uid: int) -> bool:
        """Reserve insurance for the current game if it was armed.

        Insurance toggle should stay enabled until the user turns it off.
        """
        try:
            st = db.get_insurance_state(int(uid))
            if int(st.get("next") or 0) != 1:
                return False
            if int(st.get("block") or 0) == 1:
                return False
            if int(st.get("balance") or 0) <= 0:
                return False
            return True
        except Exception:
            return False

    def _insurance_apply_on_loss(*, uid: int, stake: int, chat_id: int, game_label: str, reserved: bool) -> tuple[bool, int, int]:
        """Attempt insurance refund for a game that reserved insurance. Returns (used, refund_points, pct)."""
        stake = int(stake)
        if (not bool(reserved)) or stake <= 0:
            return False, 0, 0
        pct, is_bonus = _insurance_pick_pct()
        res = db.insurance_try_refund_on_loss_reserved(uid, stake=stake, refund_pct=pct, source=str(game_label or ""))
        if not bool(res.get("ok")):
            return False, 0, 0

        refund = int(res.get("refund") or 0)
        pct_used = int(res.get("pct") or pct)
        left = int(res.get("balance_left") or 0)

        try:
            msg = f"🛡 Страховка сработала! Возвращено {_fmt_points_ui(refund)} ({pct_used}%)"
            if is_bonus and pct_used >= int(INSURANCE_BONUS_REFUND_PCT):
                msg += "\n🎉 Повезло! Сработал повышенный возврат."
            bot.send_message(int(chat_id), msg)
        except Exception:
            pass

        if left <= int(INSURANCE_LOW_STOCK_WARN_AT):
            try:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(text="🛡 Пополнить страховки", callback_data="shop:insurance"))
                bot.send_message(int(chat_id), f"⚠️ Осталось страховок: {max(0, left)}. Пополни запас.", reply_markup=kb)
            except Exception:
                pass

        return True, refund, pct_used

    def _insurance_after_game(*, uid: int, insured_used: bool) -> None:
        if not bool(insured_used):
            try:
                db.insurance_clear_block_if_needed(uid)
            except Exception:
                pass
    def _fmt_date_ddmmyyyy(ts: int) -> str:
        try:
            d = dt.datetime.utcfromtimestamp(int(ts))
            return d.strftime("%d.%m.%Y")
        except Exception:
            return "-"

    def _fmt_hhmmss(seconds: int) -> str:
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _shop_main_text(user_id: int | None = None) -> str:
        vip_line = ""
        ins_line = ""
        if user_id is not None:
            try:
                uid_local = int(user_id)
                now_ts = int(time.time())
                vip_active = bool(db.is_vip_active(uid_local, now_ts=now_ts))
                if vip_active:
                    vip_until = int(db.get_vip_until(uid_local) or 0)
                    if vip_until >= now_ts + 100 * 365 * 24 * 3600:
                        vip_line = "\n\n👑 VIP активен: навсегда"
                    else:
                        vip_line = f"\n\n👑 VIP активен до: {_fmt_date_ddmmyyyy(vip_until)}"
                else:
                    vip_line = "\n\n👑 VIP не активен"
            except Exception:
                vip_line = ""

            try:
                ins_bal = int(db.get_insurance_balance(uid_local) or 0)
                ins_line = f"\n\n🛡 Страховок: {max(0, ins_bal)}"
            except Exception:
                ins_line = ""
        return (
            "🛒 МАГАЗИН\n\n"
            "Доступно:\n\n"
            "👑 VIP-статус\n"
            "🛡 Страховки"
            + vip_line
            + ins_line
        )

    _CM_ITEMS: dict[str, dict[str, dict]] = {
        "gpu": {
            "gtx1060": {"name": "GTX 1060", "hash": 20, "w": 120, "t": 10, "rel": 95, "btc": Decimal("0.1"), "price_points": 50, "desc": "Подходит для старта.", "badge": None},
            "rtx2060": {"name": "RTX 2060", "hash": 35, "w": 160, "t": 15, "rel": 92, "btc": Decimal("0.25"), "price_points": 120, "desc": "", "badge": None},
            "rtx3060": {"name": "RTX 3060", "hash": 50, "w": 170, "t": 18, "rel": 90, "btc": Decimal("0.5"), "price_points": 200, "desc": "", "badge": None},
            "rtx3080": {"name": "RTX 3080", "hash": 80, "w": 320, "t": 30, "rel": 85, "btc": Decimal("0.9"), "price_points": 450, "desc": "", "badge": None},
            "rtx4090": {"name": "RTX 4090", "hash": 120, "w": 450, "t": 35, "rel": 80, "btc": Decimal("1.5"), "price_points": 900, "desc": "⚠ Высокий риск перегрева!", "badge": None},

            # 50-я серия: бейджи только иконками (без текста)
            "rtx5060": {"name": "RTX 5060", "hash": 95, "w": 380, "t": 28, "rel": 88, "btc": Decimal("1.2"), "price_points": 1200, "desc": "Новое поколение — баланс мощности и эффективности", "badge": None},
            "rtx5070": {"name": "RTX 5070", "hash": 140, "w": 450, "t": 32, "rel": 85, "btc": Decimal("1.8"), "price_points": 1650, "desc": "Продвинутая архитектура для серьёзного майнинга", "badge": None},
            "rtx5080": {"name": "RTX 5080", "hash": 190, "w": 520, "t": 38, "rel": 82, "btc": Decimal("2.4"), "price_points": 2400, "desc": "Топовая производительность для профессионалов", "badge": None},
            "rtx5090": {"name": "RTX 5090", "hash": 250, "w": 650, "t": 45, "rel": 78, "btc": Decimal("3.2"), "price_points": 3500, "desc": "Абсолютная вершина — для тех, кто не знает компромиссов!", "badge": None},
            "rtx5090ti": {"name": "RTX 5090 Ti", "hash": 320, "w": 750, "t": 50, "rel": 75, "btc": Decimal("4.0"), "price_points": 5000, "desc": "Карта для настоящих майнеров. Требует профессионального охлаждения!", "badge": None},
        },
        "cool": {
            # Temperature model (2026 spec): each cooler contributes the same cooling value.
            "fan": {"name": "🌀 Обычный кулер", "cool_min": 5, "cool_max": 5, "w": +10, "rel_bonus": 0, "price_points": 80, "desc": "🛠 Эффект: базовый", "badge": None},
            "water": {"name": "💧 Водяное охлаждение", "cool_min": 15, "cool_max": 15, "w": +25, "rel_bonus": 5, "price_points": 250, "desc": "🛠 Надёжность карт: +5%", "badge": "🔥 Рекомендуется"},
            "server": {"name": "🧊 Серверное охлаждение", "cool_min": 20, "cool_max": 20, "w": +50, "rel_bonus": 10, "price_points": 500, "desc": "🛠 Надёжность карт: +10%", "badge": "👑 Топ"},
            "immersion": {
                "name": "Иммерсионное охлаждение",
                "cool_min": 50,
                "cool_max": 50,
                "w": +120,
                "rel_bonus": 25,
                "price_points": 1500,
                "desc": "Иммерсия: -50C, +25% надёжности. Требует много энергии.",
                "badge": "🧊",
            },
        },
        "psu": {
            "600": {"name": "🔌 Блок питания 600W", "maxw": 600, "stab": 90, "price_points": 150, "desc": "", "badge": None},
            "1000": {"name": "🔌 Блок питания 1000W", "maxw": 1000, "stab": 95, "price_points": 350, "desc": "", "badge": "🔥 Оптимально"},
            "1600": {"name": "🔌 Блок питания 1600W", "maxw": 1600, "stab": 99, "price_points": 700, "desc": "", "badge": "👑 Лучший"},
        },
        "slots": {
            "rack4": {"name": "📦 Стойка", "add": 4, "bonus_temp": 0, "price_points": 250, "desc": "", "badge": None},
            "cont16": {"name": "🏭 Контейнер", "add": 16, "bonus_temp": -5, "price_points": 1200, "desc": "❄ Бонус охлаждения: -5°C", "badge": None},
            "dc64": {"name": "🏢 Дата-центр", "add": 64, "bonus_temp": -15, "price_points": 4500, "desc": "❄ Бонус охлаждения: -15°C\n⚡ Бонус стабильности", "badge": "👑 Элитно"},
        },
        "upg": {
            # Upgrades: prices converted to points (POINTS_PER_RUB = 100)
            # Requested: soft = 250 ₽, shield = 150 ₽, eff = 250 ₽
            "soft": {"name": "🧠 Оптимизация ПО", "price_points": 250 * POINTS_PER_RUB, "desc": "Ускорение цикла майнинга.", "badge": None},
            "shield": {"name": "🛡 Защита от сбоев", "price_points": 150 * POINTS_PER_RUB, "desc": "Меньше шанс поломки при перегреве.", "badge": None},
            "eff": {"name": "📈 Эффективность", "price_points": 250 * POINTS_PER_RUB, "desc": "+10% дохода постоянно.", "badge": None},
        },
        "boost": {
            "x2_10": {"name": "⚡ x2 доход (10 мин)", "price_points": 120, "desc": "Временное усиление.", "badge": None},
            "x3_5": {"name": "⚡ x3 доход (5 мин)", "price_points": 180, "desc": "Временное усиление.", "badge": None},
            "cool": {"name": "❄ Мгновенное охлаждение", "price_points": 90, "desc": "Сбрасывает перегрев.", "badge": None},
        },
    }

    def _cm_get_decimal_field(uid_local: int, field: str, default: Decimal = Decimal("0")) -> Decimal:
        raw = db.get_user_field(uid_local, field)
        if raw is None:
            return default
        try:
            return Decimal(str(raw))
        except Exception:
            return default

    def _cm_set_decimal_field(uid_local: int, field: str, val: Decimal) -> None:
        try:
            db.set_user_field(uid_local, field, str(val))
        except Exception:
            pass

    def _cm_get_cards(uid_local: int) -> list[str]:
        raw = db.get_user_field(uid_local, "mining_cards_json")
        if not raw:
            return []
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        return []

    def _cm_set_cards(uid_local: int, cards: list[str]) -> None:
        try:
            db.set_user_field(uid_local, "mining_cards_json", json.dumps(list(cards), ensure_ascii=False))
        except Exception:
            pass

    def _cm_slots_total(uid_local: int) -> int:
        try:
            return max(4, int(db.get_user_field(uid_local, "mining_slots") or 4))
        except Exception:
            return 4

    def _cm_slots_free(uid_local: int) -> int:
        total = _cm_slots_total(uid_local)
        used = len(_cm_get_cards(uid_local))
        return max(0, total - used)

    def _cm_fmt_btc(val: Decimal) -> str:
        try:
            q = val.quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)
            return f"{q:.6f}"
        except Exception:
            return "0.000000"

    def _cm_fmt_btc3(val: Decimal) -> str:
        try:
            q = val.quantize(Decimal("0.001"), rounding=ROUND_FLOOR)
            return f"{q:.3f}"
        except Exception:
            return "0.000"

    def _cm_gpu_btc_hour_suffix(uid_local: int) -> dict[str, str]:
        try:
            _cmf_ensure_initialized(int(uid_local))
        except Exception:
            pass
        cycle_s = max(15, _cmf_get_int(int(uid_local), "mining_cycle_seconds", 60))

        # Apply permanent income upgrade (+10%) and current PSU efficiency.
        income_mult = Decimal("1")
        try:
            raw = db.get_user_field(int(uid_local), "mining_upgrades_json")
            if raw:
                parsed = json.loads(str(raw))
                if isinstance(parsed, list) and "eff" in {str(x) for x in parsed}:
                    income_mult *= Decimal("1.10")
        except Exception:
            pass
        try:
            stats = _cmf_installed_stats(int(uid_local))
            psu_eff = Decimal(str(stats.get("psu_eff") or 1.0))
        except Exception:
            psu_eff = Decimal("1")

        mult = income_mult * psu_eff
        suffix: dict[str, str] = {}
        order = [
            "gtx1060",
            "rtx2060",
            "rtx3060",
            "rtx3080",
            "rtx4090",
            "rtx5060",
            "rtx5070",
            "rtx5080",
            "rtx5090",
            "rtx5090ti",
        ]
        for code in order:
            it = _CM_ITEMS.get("gpu", {}).get(str(code)) or {}
            try:
                btc_cycle = Decimal(str(it.get("btc") or "0"))
            except Exception:
                btc_cycle = Decimal("0")
            btc_hour = (btc_cycle * mult * Decimal("3600") / Decimal(str(cycle_s)))
            suffix[str(code)] = f"{_cm_fmt_btc3(btc_hour)} BTC/ч"
        return suffix

    def _cm_cool_suffix_by_code() -> dict[str, str]:
        suffix: dict[str, str] = {}
        order = ["fan", "water", "server", "immersion"]
        for code in order:
            it = _CM_ITEMS.get("cool", {}).get(str(code)) or {}
            suffix[str(code)] = f"-{int(it.get('cool_min') or 0)}°C"
        return suffix

    def _cm_shop_home_text(uid_local: int) -> str:
        points = int(db.get_balance(uid_local) or 0)
        return (
            "🛒 Магазин\n\n"
            f"⭐ Баллы: {points}\n"
            "Выбери, что купить:"
        )

    def _cm_category_text(cat: str, uid_local: int | None = None) -> str:
        if cat == "gpu":
            return "🎮 Видеокарты\n\nКупи видеокарту которая будет приносить BTC в час:"
        if cat == "cool":
            return "❄ Охлаждение\n\nСнижает температуру и риск поломки."
        if cat == "psu":
            return "⚡ Блоки питания\n\nЕсли не хватает мощности — ферма работает хуже."
        if cat == "slots":
            return "📦 Ячейки / Стойки\n\nОпределяют, сколько видеокарт можно установить."
        if cat == "upg":
            return "🧠 Апгрейды\n\nПостоянные улучшения аккаунта."
        if cat == "boost":
            return "🚀 Бустеры\n\nВременные усиления."
        return "Категория"

    def _cm_item_text(cat: str, code: str, *, uid: int, detailed: bool) -> str:
        item = _CM_ITEMS.get(cat, {}).get(code) or {}
        title = str(item.get("name") or "")
        price_points = int(item.get("price_points") or 0)

        if cat == "gpu":
            # Temperature increase on install (predictable values).
            gpu_code = str(code)
            install_delta = {
                "gtx1060": 6,
                "rtx2060": 12,
                "rtx3060": 18,
                "rtx3080": 26,
                "rtx4090": 35,

                # 50-я серия
                "rtx5060": 28,
                "rtx5070": 32,
                "rtx5080": 38,
                "rtx5090": 45,
                "rtx5090ti": 50,
            }.get(gpu_code)
            if install_delta is None:
                try:
                    t_val = float(item.get("t") or 0)
                    install_delta = int(max(1, min(50, round(t_val * 0.75))))
                except Exception:
                    install_delta = 10
            lines = [
                title,
                "",
                f"⚡ Потребление: {int(item.get('w') or 0)}W",
                f"🌡 При установке: +{int(install_delta)}°C к текущей температуре",
                f"🛠 Надёжность: {int(item.get('rel') or 0)}%",
                f"🪙 Добыча: {str(item.get('btc') or '0')} BTC/цикл",
                f"⭐ Цена: {price_points} баллов",
            ]
            desc = str(item.get("desc") or "").strip()
            if desc:
                lines.extend(["", desc])
            if detailed:
                free = _cm_slots_free(uid)
                lines.extend(["", f"📦 Свободные ячейки: {free}"])
            return "\n".join(lines)

        if cat == "cool":
            cur_cool = str(db.get_user_field(uid, "mining_cooling") or "fan")
            inv_raw = db.get_user_field(uid, "mining_cooling_inv_json")
            inv = _cm_get_cooling_inventory(uid)
            if inv:
                installed_qty = int(inv.get(cur_cool, 0) or 0)
            elif inv_raw:
                installed_qty = 0
            else:
                installed_qty = max(1, int(_cmf_get_int(uid, "mining_cooling_qty", 1)))
            installed = f"✅ Установлено: {int(installed_qty)} шт" if (cur_cool == str(code) and int(installed_qty) > 0) else ""
            lines = [
                title,
                "",
                f"❄ Охлаждение: -{int(item.get('cool_min') or 0)}°C",
                f"⚡ Потребление: +{int(item.get('w') or 0)}W",
                str(item.get("desc") or ""),
                installed,
                f"⭐ Цена: {price_points} баллов",
            ]
            return "\n".join([x for x in lines if str(x).strip()])

        if cat == "psu":
            cur_psu = str(db.get_user_field(uid, "mining_psu") or "600")
            inv = _cm_get_psu_inventory(uid)
            installed_qty = inv.get(cur_psu)
            if installed_qty is None:
                installed_qty = _cmf_get_int(uid, "mining_psu_qty", 1)
            installed = f"✅ Установлено: {max(1, int(installed_qty))} шт" if cur_psu == str(code) else ""
            lines = [
                title,
                "",
                f"⚡ Максимум: {int(item.get('maxw') or 0)}W",
                f"🛠 Стабильность: {int(item.get('stab') or 0)}%",
                installed,
                f"⭐ Цена: {price_points} баллов",
            ]
            return "\n".join(lines)

        if cat == "slots":
            lines = [
                title,
                "",
                f"➕ Вместимость: +{int(item.get('add') or 0)} карты",
                f"⭐ Цена: {price_points} баллов",
            ]
            desc = str(item.get("desc") or "").strip()
            if desc:
                lines.extend(["", desc])
            return "\n".join(lines)

        # upgrades / boosters
        lines = [
            title,
            "",
            str(item.get("desc") or ""),
            f"⭐ Цена: {price_points} баллов",
        ]
        return "\n".join([x for x in lines if str(x).strip()])

    def _cm_get_gpu_inventory(uid_local: int) -> dict[str, int]:
        raw = db.get_user_field(uid_local, "mining_gpu_inventory_json")
        if not raw:
            return {}
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                out: dict[str, int] = {}
                for k, v in parsed.items():
                    out[str(k)] = max(0, int(v))
                return out
        except Exception:
            pass
        return {}

    def _cm_set_gpu_inventory(uid_local: int, inv: dict[str, int]) -> None:
        try:
            cleaned = {str(k): int(v) for k, v in inv.items() if int(v) > 0}
            db.set_user_field(uid_local, "mining_gpu_inventory_json", json.dumps(cleaned, ensure_ascii=False))
        except Exception:
            pass

    def _cm_get_cooling_inventory(uid_local: int) -> dict[str, int]:
        raw = db.get_user_field(uid_local, "mining_cooling_inv_json")
        if not raw:
            return {}
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                out: dict[str, int] = {}
                for k, v in parsed.items():
                    out[str(k)] = max(0, int(v))
                return out
        except Exception:
            pass
        return {}

    def _cm_set_cooling_inventory(uid_local: int, inv: dict[str, int]) -> None:
        try:
            cleaned = {str(k): int(v) for k, v in inv.items() if int(v) > 0}
            db.set_user_field(uid_local, "mining_cooling_inv_json", json.dumps(cleaned, ensure_ascii=False))
        except Exception:
            pass

    def _cm_get_psu_inventory(uid_local: int) -> dict[str, int]:
        raw = db.get_user_field(uid_local, "mining_psu_inv_json")
        if not raw:
            return {}
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                out: dict[str, int] = {}
                for k, v in parsed.items():
                    out[str(k)] = max(0, int(v))
                return out
        except Exception:
            pass
        return {}

    def _cm_set_psu_inventory(uid_local: int, inv: dict[str, int]) -> None:
        try:
            cleaned = {str(k): int(v) for k, v in inv.items() if int(v) > 0}
            db.set_user_field(uid_local, "mining_psu_inv_json", json.dumps(cleaned, ensure_ascii=False))
        except Exception:
            pass

    def _cm_gpu_temp_per_card(code: str) -> int:
        gpu_code = str(code)
        per_card = {
            "gtx1060": 6,
            "rtx2060": 12,
            "rtx3060": 18,
            "rtx3080": 26,
            "rtx4090": 35,

            # 50-я серия
            "rtx5060": 28,
            "rtx5070": 32,
            "rtx5080": 38,
            "rtx5090": 45,
            "rtx5090ti": 50,
        }.get(gpu_code)
        if per_card is None:
            it = _CM_ITEMS.get("gpu", {}).get(gpu_code) or {}
            t_val = float(it.get("t") or 0)
            per_card = int(max(1, min(50, round(t_val * 0.75))))
        return int(max(0, int(per_card)))

    def _cmf_installed_cool_qty(uid_local: int) -> int:
        code = str(db.get_user_field(uid_local, "mining_cooling") or "fan")
        inv_raw = db.get_user_field(uid_local, "mining_cooling_inv_json")
        inv = _cm_get_cooling_inventory(uid_local)
        if inv:
            return max(0, int(inv.get(code, 0) or 0))
        # If JSON inventory exists but is empty, user has no cooling installed.
        if inv_raw:
            return 0
        qty = _cmf_get_int(uid_local, "mining_cooling_qty", 1)
        return max(1, int(qty))

    def _cmf_installed_psu_qty(uid_local: int) -> int:
        code = str(db.get_user_field(uid_local, "mining_psu") or "600")
        inv_raw = db.get_user_field(uid_local, "mining_psu_inv_json")
        inv = _cm_get_psu_inventory(uid_local)
        if inv:
            return max(0, int(inv.get(code, 0) or 0))
        # If JSON inventory exists but is empty, user has no PSU installed.
        if inv_raw:
            return 0
        qty = _cmf_get_int(uid_local, "mining_psu_qty", 1)
        return max(1, int(qty))

    def _cm_get_boosters(uid_local: int) -> dict[str, int]:
        raw = db.get_user_field(uid_local, "mining_boosters_json")
        if not raw:
            return {}
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                out: dict[str, int] = {}
                for k, v in parsed.items():
                    # old format used timestamps; treat as 1
                    if isinstance(v, (int, float)) and int(v) > 0:
                        out[str(k)] = max(0, int(v))
                    else:
                        out[str(k)] = 1
                return out
        except Exception:
            pass
        return {}

    def _cm_set_boosters(uid_local: int, boosters: dict[str, int]) -> None:
        try:
            cleaned = {str(k): int(v) for k, v in boosters.items() if int(v) > 0}
            db.set_user_field(uid_local, "mining_boosters_json", json.dumps(cleaned, ensure_ascii=False))
        except Exception:
            pass

    def _cm_try_buy(uid_local: int, cat: str, code: str, *, qty: int = 1) -> tuple[bool, str]:
        item = _CM_ITEMS.get(cat, {}).get(code)
        if not item:
            return (False, "❌ Товар не найден")

        try:
            qty_i = int(qty)
        except Exception:
            qty_i = 0
        if qty_i <= 0:
            return (False, "❌ Количество должно быть больше 0")

        # These items are not stackable in quantity.
        if cat in {"upg", "slots"} and qty_i != 1:
            return (False, "ℹ️ Для этого товара количество всегда 1")

        # Prevent paying for no effect
        if cat == "upg":
            raw = db.get_user_field(uid_local, "mining_upgrades_json")
            try:
                if raw:
                    parsed = json.loads(str(raw))
                    if isinstance(parsed, list) and str(code) in {str(x) for x in parsed}:
                        return (False, "ℹ️ Этот апгрейд уже куплен")
            except Exception:
                pass

        price_points = int(item.get("price_points") or 0)
        total_cost = int(price_points) * int(qty_i)
        bal_points = int(db.get_balance(uid_local) or 0)
        if bal_points < total_cost:
            return (False, "❌ Недостаточно баллов")

        # If mining is active, catch up before applying equipment changes.
        # Otherwise user may see "no change" because next screen applies overdue cycles after the purchase.
        if cat in {"cool", "psu", "gpu", "slots", "upg", "boost"}:
            try:
                _cmf_ensure_initialized(uid_local)
                _cmf_apply_mining(uid_local)
            except Exception:
                pass

        did_debit = False

        # For categories where we don't use `try_buy_cm_inventory_item`, pre-charge atomically
        # BEFORE mutating any inventory fields to prevent negative balances.
        if str(cat) in {"slots", "upg", "boost"}:
            try:
                spent = db.try_spend_points(int(uid_local), int(total_cost))
            except Exception:
                spent = {"ok": False, "balance": int(bal_points)}
            if not bool(spent.get("ok")):
                return (False, "❌ Недостаточно баллов")
            did_debit = True

        # validate capacity for GPUs
        if cat == "gpu":
            try:
                res = db.try_buy_cm_inventory_item(
                    int(uid_local),
                    inventory_field="mining_gpu_inventory_json",
                    code=str(code),
                    qty=int(qty_i),
                    unit_price_points=int(price_points),
                )
            except Exception:
                res = {"ok": False, "reason": "error"}
            if not bool(res.get("ok")):
                return (False, "❌ Недостаточно баллов")
            did_debit = True
            new_qty_for_code = int(res.get("new_qty") or 0)

        elif cat == "slots":
            add = int(item.get("add") or 0)
            total = _cm_slots_total(uid_local)
            db.set_user_field(uid_local, "mining_slots", int(total + max(0, add)))

        elif cat == "cool":
            try:
                res = db.try_buy_cm_inventory_item(
                    int(uid_local),
                    inventory_field="mining_cooling_inv_json",
                    code=str(code),
                    qty=int(qty_i),
                    unit_price_points=int(price_points),
                )
            except Exception:
                res = {"ok": False, "reason": "error"}
            if not bool(res.get("ok")):
                return (False, "❌ Недостаточно баллов")
            did_debit = True
            new_qty = int(res.get("new_qty") or 0)

            # Buying installs this type.
            db.set_user_field(uid_local, "mining_cooling", str(code))
            # Keep legacy field in sync for older codepaths.
            db.set_user_field(uid_local, "mining_cooling_qty", int(new_qty))

            # New temp model: no instant jumps; temperature changes only via gradual drift.
            try:
                _cmf_push_event(uid_local, f"🛒 Куплено охлаждение: {str(item.get('name') or '')}")
            except Exception:
                pass
            try:
                _cmf_update_temp_gradually(uid_local)
            except Exception:
                pass

        elif cat == "psu":
            try:
                res = db.try_buy_cm_inventory_item(
                    int(uid_local),
                    inventory_field="mining_psu_inv_json",
                    code=str(code),
                    qty=int(qty_i),
                    unit_price_points=int(price_points),
                )
            except Exception:
                res = {"ok": False, "reason": "error"}
            if not bool(res.get("ok")):
                return (False, "❌ Недостаточно баллов")
            did_debit = True
            new_qty = int(res.get("new_qty") or 0)

            # Buying installs this type.
            db.set_user_field(uid_local, "mining_psu", str(code))
            # Keep legacy field in sync for older codepaths.
            db.set_user_field(uid_local, "mining_psu_qty", int(new_qty))

            # Add a clear event about the new total PSU capacity.
            try:
                psu_code = str(db.get_user_field(uid_local, "mining_psu") or str(code))
                qty = max(1, int(new_qty))
                psu_it = _CM_ITEMS.get("psu", {}).get(psu_code) or {}
                max_w = int(psu_it.get("maxw") or 600) * int(qty)
                _cmf_push_event(uid_local, f"🛒 Куплен БП (x{qty}): {max_w}W")
            except Exception:
                pass

        elif cat == "upg":
            raw = db.get_user_field(uid_local, "mining_upgrades_json")
            cur: set[str] = set()
            try:
                if raw:
                    parsed = json.loads(str(raw))
                    if isinstance(parsed, list):
                        cur = {str(x) for x in parsed}
            except Exception:
                pass
            cur.add(str(code))
            db.set_user_field(uid_local, "mining_upgrades_json", json.dumps(sorted(cur), ensure_ascii=False))

        elif cat == "boost":
            boosters = _cm_get_boosters(uid_local)
            boosters[str(code)] = int(boosters.get(str(code), 0)) + int(qty_i)
            _cm_set_boosters(uid_local, boosters)

        # debit ⭐ points (shared with profile)
        if not did_debit:
            try:
                spent = db.try_spend_points(int(uid_local), int(total_cost))
            except Exception:
                spent = {"ok": False}
            if not bool(spent.get("ok")):
                return (False, "❌ Недостаточно баллов")

        # Friendly success message with stacked effects for cooling/PSU
        name = str(item.get("name") or "")
        if cat == "cool":
            qty = _cmf_installed_cool_qty(uid_local)
            try:
                _cmf_update_temp_gradually(uid_local)
            except Exception:
                pass
            t = int(round(_cmf_get_float(uid_local, "mining_temp", 0.0)))
            target = int(round(_cmf_get_float(uid_local, "mining_temp_target", 0.0)))
            bought = int(qty_i)
            return (True, f"✅ Куплено: {name} (x{qty})\n➕ Куплено: x{bought}\n⭐ Списано: {total_cost} баллов\n🌡 Температура: {t}°C → {target}°C")
        if cat == "psu":
            psu_code = str(db.get_user_field(uid_local, "mining_psu") or str(code))
            qty = _cmf_installed_psu_qty(uid_local)
            psu_it = _CM_ITEMS.get("psu", {}).get(psu_code) or {}
            max_w = int(psu_it.get("maxw") or 600) * int(qty)
            bought = int(qty_i)
            return (True, f"✅ Куплено: {name} (x{qty})\n➕ Куплено: x{bought}\n⭐ Списано: {total_cost} баллов\n⚡ Максимум: {max_w}W")
        if cat == "gpu":
            try:
                total_now = int(locals().get("new_qty_for_code", 0) or 0)
            except Exception:
                total_now = 0
            return (True, f"✅ Куплено: {name} (x{int(qty_i)})\n⭐ Списано: {total_cost} баллов\n📦 В инвентаре: {total_now} шт")
        return (True, f"✅ Куплено: {name} (x{int(qty_i)})\n⭐ Списано: {total_cost} баллов")

    def _cm_is_qty_purchase_category(cat: str) -> bool:
        return str(cat) in {"gpu", "cool", "psu", "boost"}

    def _cm_start_buy_qty_prompt(
        *,
        uid_local: int,
        cat: str,
        code: str,
        prefix: str,
        panel_chat_id: int,
        panel_message_id: int,
    ) -> tuple[bool, str]:
        """Start 'enter quantity' step. Returns (handled, error_message)."""
        cat = str(cat)
        code = str(code)
        prefix = str(prefix)
        item = _CM_ITEMS.get(cat, {}).get(code)
        if not item:
            return (True, "❌ Товар не найден")
        if not _cm_is_qty_purchase_category(cat):
            return (False, "")

        price_points = int(item.get("price_points") or 0)
        if price_points <= 0:
            return (True, "❌ Некорректная цена")

        bal = int(db.get_balance(int(uid_local)) or 0)
        max_aff = int(bal // price_points)
        max_qty = min(1000, max_aff)
        if max_qty <= 0:
            return (True, "❌ Недостаточно баллов")

        s = session(int(uid_local))
        # If there is an older pending prompt, clean it up.
        try:
            old_cid = int(getattr(s, "cm_buy_prompt_chat_id", 0) or 0)
            old_mid = int(getattr(s, "cm_buy_prompt_message_id", 0) or 0)
            if old_cid and old_mid:
                _safe_delete_message(bot, old_cid, old_mid)
        except Exception:
            pass

        s.cm_buy_pending = True
        s.cm_buy_category = cat
        s.cm_buy_code = code
        s.cm_buy_prefix = prefix
        s.cm_buy_panel_chat_id = int(panel_chat_id)
        s.cm_buy_panel_message_id = int(panel_message_id)
        s.cm_buy_max_qty = int(max_qty)

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cm:buy_cancel"))
        name = str(item.get("name") or "")
        txt = (
            "🛒 Покупка\n\n"
            f"Товар: {name}\n"
            f"Цена: {price_points} баллов / шт\n"
            f"Доступно по балансу: до {max_aff} шт\n"
            f"Лимит ввода: до {max_qty} шт\n\n"
            "✍ Введите количество (число):"
        )
        try:
            sent = bot.send_message(int(panel_chat_id), txt, reply_markup=kb)
            s.cm_buy_prompt_chat_id = int(sent.chat.id)
            s.cm_buy_prompt_message_id = int(sent.message_id)
        except Exception:
            pass
        return (True, "")

    def _cmf_now_ts() -> int:
        return int(time.time())

    def _cmf_get_int(uid_local: int, field: str, default: int = 0) -> int:
        try:
            return int(db.get_user_field(uid_local, field) or default)
        except Exception:
            return default

    def _cmf_get_float(uid_local: int, field: str, default: float = 0.0) -> float:
        try:
            return float(db.get_user_field(uid_local, field) or default)
        except Exception:
            return default

    def _cmf_get_event_log(uid_local: int) -> list[str]:
        raw = db.get_user_field(uid_local, "mining_event_log_json")
        if not raw:
            return []
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, list):
                return [str(x) for x in parsed][-8:]
        except Exception:
            pass
        return []

    def _cmf_push_event(uid_local: int, text: str) -> None:
        text = str(text).strip()
        if not text:
            return
        cur = _cmf_get_event_log(uid_local)
        cur.append(text)
        cur = cur[-8:]
        try:
            db.set_user_field(uid_local, "mining_event_log_json", json.dumps(cur, ensure_ascii=False))
        except Exception:
            pass

    def _cmf_normalize_temp_if_no_gpus(uid_local: int) -> None:
        """Compatibility helper (older codepaths call this).

        In the 2026 temperature spec, baseline is +25°C and temperature always drifts
        toward a target, even with no GPUs installed. So we no longer reset to 0°C.
        """
        try:
            if db.get_user_field(uid_local, "mining_temp") is None:
                db.set_user_field(uid_local, "mining_temp", 0.0)
        except Exception:
            pass

    def _cmf_calculate_target_temp(uid_local: int) -> float:
        """Calculate the target temperature for the farm.

        Spec:
        target = (sum GPU heat) - (sum cooler cooling) + 25°C base

        - GPU heat is taken from the GPU item's `t` value.
        - Cooling stacks by quantity for all owned coolers (inventory JSON).
        """
        base = 0.0

        # GPUs
        total_heat = 0.0
        try:
            cards = _cm_get_cards(uid_local)
        except Exception:
            cards = []
        for code in cards:
            it = _CM_ITEMS.get("gpu", {}).get(str(code)) or {}
            try:
                total_heat += float(it.get("t") or 0.0)
            except Exception:
                pass

        # Cooling (stack by quantity)
        total_cooling = 0.0
        try:
            cool_inv_raw = db.get_user_field(uid_local, "mining_cooling_inv_json")
            cool_inv = _cm_get_cooling_inventory(uid_local)
            if not cool_inv and not cool_inv_raw:
                cool_code_fallback = str(db.get_user_field(uid_local, "mining_cooling") or "fan")
                cool_inv = {cool_code_fallback: int(_cmf_get_int(uid_local, "mining_cooling_qty", 0))}
        except Exception:
            cool_inv = {}

        for code, qty in dict(cool_inv).items():
            q = max(0, int(qty or 0))
            if q <= 0:
                continue
            it = _CM_ITEMS.get("cool", {}).get(str(code)) or {}
            try:
                cool = float(it.get("cool_min") or 0.0)
            except Exception:
                cool = 0.0
            if cool > 0:
                total_cooling += cool * float(q)

        # If there are no GPUs installed at all, treat baseline as 0°C
        if not cards:
            base = 0.0

        target = float(total_heat - total_cooling + base)
        try:
            db.set_user_field(uid_local, "mining_temp_target", float(target))
        except Exception:
            pass

        # If target changed, reset animation so heating starts with +5/+4/+3/+2.
        try:
            prev_anim_target = float(db.get_user_field(uid_local, "mining_temp_animation_target") or 0.0)
        except Exception:
            prev_anim_target = 0.0
        try:
            if float(prev_anim_target) != float(target):
                try:
                    cur_temp = float(db.get_user_field(uid_local, "mining_temp") or 0.0)
                except Exception:
                    cur_temp = 0.0
                db.set_user_field(uid_local, "mining_temp_animation_start", int(round(cur_temp)))
                db.set_user_field(uid_local, "mining_temp_animation_target", float(target))
                db.set_user_field(uid_local, "mining_temp_animation_step", 0)
        except Exception:
            pass
        return float(target)

    def _cmf_get_animation_step(step_number: int) -> int:
        """Return the heating delta for a given animation step (2-second tick)."""
        s = int(step_number)
        if s <= 1:
            return 5
        if s <= 3:
            return 4
        if s <= 6:
            return 3
        return 2

    def _cmf_make_progress_bar(start_temp: float, current_temp: float, target_temp: float) -> str:
        """10-segment progress bar for reaching target temperature."""
        try:
            denom = float(target_temp - start_temp)
            if abs(denom) < 1e-9:
                progress = 1.0
            else:
                progress = float((current_temp - start_temp) / denom)
        except Exception:
            progress = 0.0
        progress = max(0.0, min(1.0, float(progress)))
        filled = int(round(progress * 10.0))
        filled = max(0, min(10, int(filled)))
        empty = 10 - filled
        return ("🟩" * filled) + ("⬜" * empty) + f" {int(round(progress * 100))}%"

    # Back-compat alias (older code calls this)
    def _cmf_temp_target(uid_local: int, *, stats: dict | None = None) -> float:
        return _cmf_calculate_target_temp(uid_local)

    def _cmf_update_temp_gradually(uid_local: int) -> None:
        """Gradually update mining_temp toward mining_temp_target.

        Every 2 seconds:
        - If current < target: +2°C per 2 sec
        - If current > target: -2°C per 2 sec, but last 20°C use -1°C per 2 sec
        """
        now = _cmf_now_ts()
        last_ts = _cmf_get_int(uid_local, "mining_temp_ts", 0)
        if last_ts <= 0:
            # Initialize the drift timestamp on first use.
            db.set_user_field(uid_local, "mining_temp_ts", int(now))
            # Ensure target is stored too.
            try:
                _cmf_calculate_target_temp(uid_local)
            except Exception:
                pass
            return

        elapsed = max(0, int(now - last_ts))
        cycles = int(elapsed // 2)
        if cycles <= 0:
            # Still update stored target for UI/debug.
            try:
                _cmf_calculate_target_temp(uid_local)
            except Exception:
                pass
            return

        try:
            current = float(_cmf_get_float(uid_local, "mining_temp", 0.0))
        except Exception:
            current = 0.0

        target = _cmf_calculate_target_temp(uid_local)
        new_temp = float(current)

        if current < target:
            # Heating with animation steps: +5,+5,+4,+4,+3,+3,+3,+2...
            step_no = 0
            try:
                step_no = int(db.get_user_field(uid_local, "mining_temp_animation_step") or 0)
            except Exception:
                step_no = 0

            temp = float(current)
            used = 0
            for _ in range(int(cycles)):
                if temp >= target:
                    break
                delta = float(_cmf_get_animation_step(step_no))
                step_no += 1
                temp = float(temp + delta)
                if temp > target:
                    temp = float(target)
                used += 1
            new_temp = float(temp)
            try:
                db.set_user_field(uid_local, "mining_temp_animation_step", int(step_no))
            except Exception:
                pass
        elif current > target:
            # Cooling
            diff = float(current - target)
            if diff <= 20.0:
                new_temp = float(current - float(cycles) * 1.0)
            else:
                # Fast cool until within 20°C of target, then slow.
                need_fast = int(math.ceil((diff - 20.0) / 2.0))
                fast_cycles = min(int(cycles), int(max(0, need_fast)))
                tmp = float(current - float(fast_cycles) * 2.0)
                remaining = int(cycles - fast_cycles)
                if remaining > 0 and tmp > target:
                    tmp = float(tmp - float(remaining) * 1.0)
                new_temp = float(tmp)
            if new_temp < target:
                new_temp = float(target)

        db.set_user_field(uid_local, "mining_temp", float(new_temp))
        db.set_user_field(uid_local, "mining_temp_ts", int(now))

    def _cmf_stop_temp_auto_refresh(uid_local: int) -> None:
        s = session(int(uid_local))
        s.cmf_animation_active = False

    def _cmf_start_temp_auto_refresh(uid_local: int, *, chat_id: int, message_id: int, view: str) -> None:
        """Auto-refresh the mining screen message every 2 seconds.

        We keep it per-user; if another view/message is opened, we stop the old one.
        """
        s = session(int(uid_local))

        # If already refreshing this exact message/view, keep running.
        if (
            s.cmf_animation_thread
            and s.cmf_animation_thread.is_alive()
            and s.cmf_animation_active
            and int(s.cmf_animation_chat_id or 0) == int(chat_id)
            and int(s.cmf_animation_message_id or 0) == int(message_id)
            and str(s.cmf_animation_view or "") == str(view)
        ):
            return

        # Stop previous refresh loop.
        s.cmf_animation_active = False
        s.cmf_animation_chat_id = int(chat_id)
        s.cmf_animation_message_id = int(message_id)
        s.cmf_animation_last_sig = None
        s.cmf_animation_active = True

        def _worker() -> None:
            while True:
                try:
                    ss = session(int(uid_local))
                    if not ss.cmf_animation_active:
                        return
                    if int(ss.cmf_animation_chat_id or 0) != int(chat_id) or int(ss.cmf_animation_message_id or 0) != int(message_id):
                        return
                    if str(ss.cmf_animation_view or "") != str(view):
                        return

                    # Keep temperature up to date (BTC accrual happens inside screen rendering).
                    try:
                        _cmf_update_temp_gradually(int(uid_local))
                    except Exception:
                        pass

                    # Render and update
                    try:
                        if str(view) == "mine":
                            active = bool(_cmf_get_int(int(uid_local), "mining_active", 0))
                            txt = _cmf_mining_screen_text(int(uid_local))
                            sig = f"mine|{int(active)}|{txt}"
                            if str(ss.cmf_animation_last_sig or "") != str(sig):
                                bot.edit_message_text(
                                    txt,
                                    chat_id=int(chat_id),
                                    message_id=int(message_id),
                                    reply_markup=cryptomine_mining_kb(is_active=active),
                                )
                                ss.cmf_animation_last_sig = str(sig)
                        elif str(view) == "farm":
                            txt = _cmf_farm_text(int(uid_local))
                            sig = f"farm|{txt}"
                            if str(ss.cmf_animation_last_sig or "") != str(sig):
                                bot.edit_message_text(
                                    txt,
                                    chat_id=int(chat_id),
                                    message_id=int(message_id),
                                    reply_markup=cryptomine_farm_kb(),
                                )
                                ss.cmf_animation_last_sig = str(sig)
                    except Exception as e:
                        # Ignore "message is not modified" errors; stop on other edit failures.
                        msg = str(e)
                        if "message is not modified" in msg:
                            pass
                        else:
                            ss.cmf_animation_active = False
                            return

                    time.sleep(12)
                except Exception:
                    return

        th = threading.Thread(target=_worker, daemon=True)
        s.cmf_animation_thread = th
        try:
            th.start()
        except Exception:
            s.cmf_animation_active = False

    # Back-compat alias
    def _cmf_update_temp(uid_local: int) -> None:
        _cmf_update_temp_gradually(uid_local)

    def _cmf_display_temp(uid_local: int, *, stats: dict | None = None) -> int:
        """Temperature shown to the user.

        Rules:
        - If there are no GPUs: baseline is 0°C (negative values from cooling can stay).
        - If there is NO PSU at all: cooling does not work => never show below 0°C.
        - No upper clamp: temperature may exceed 120°C.
        """
        try:
            _cmf_update_temp_gradually(uid_local)
        except Exception:
            pass
        # If user has no GPUs installed, force baseline to 0°C so UI shows 0 immediately.
        try:
            cards = _cm_get_cards(uid_local)
            if not cards:
                try:
                    db.set_user_field(uid_local, "mining_temp", 0.0)
                    db.set_user_field(uid_local, "mining_temp_target", 0.0)
                except Exception:
                    pass
                return 0
        except Exception:
            pass
        try:
            return int(round(float(_cmf_get_float(uid_local, "mining_temp", 0.0))))
        except Exception:
            return 0

    def _cmf_ensure_initialized(uid_local: int) -> None:
        inited = _cmf_get_int(uid_local, "mining_initialized", 0)
        if inited:
            # Existing users: keep inventories in sync (so xN persists when switching types).
            try:
                cool_code = str(db.get_user_field(uid_local, "mining_cooling") or "fan")
                cool_inv_raw = db.get_user_field(uid_local, "mining_cooling_inv_json")
                cool_inv = _cm_get_cooling_inventory(uid_local)
                # Only migrate from legacy qty if JSON inventory is missing/uninitialized.
                if not cool_inv_raw:
                    cool_qty_legacy = max(1, _cmf_get_int(uid_local, "mining_cooling_qty", 1))
                    if int(cool_inv.get(cool_code, 0) or 0) <= 0:
                        cool_inv[cool_code] = int(cool_qty_legacy)
                        _cm_set_cooling_inventory(uid_local, cool_inv)
                    db.set_user_field(uid_local, "mining_cooling_qty", max(1, int(cool_inv.get(cool_code, 1))))
                else:
                    # JSON inventory exists: allow empty / 0 quantities.
                    db.set_user_field(uid_local, "mining_cooling_qty", max(0, int(cool_inv.get(cool_code, 0) or 0)))
            except Exception:
                pass

            try:
                psu_code = str(db.get_user_field(uid_local, "mining_psu") or "600")
                psu_inv_raw = db.get_user_field(uid_local, "mining_psu_inv_json")
                psu_inv = _cm_get_psu_inventory(uid_local)
                # Only migrate from legacy qty if JSON inventory is missing/uninitialized.
                if not psu_inv_raw:
                    psu_qty_legacy = max(1, _cmf_get_int(uid_local, "mining_psu_qty", 1))
                    if int(psu_inv.get(psu_code, 0) or 0) <= 0:
                        psu_inv[psu_code] = int(psu_qty_legacy)
                        _cm_set_psu_inventory(uid_local, psu_inv)
                    db.set_user_field(uid_local, "mining_psu_qty", max(1, int(psu_inv.get(psu_code, 1))))
                else:
                    # JSON inventory exists: allow empty / 0 quantities.
                    db.set_user_field(uid_local, "mining_psu_qty", max(0, int(psu_inv.get(psu_code, 0) or 0)))
            except Exception:
                pass
            _cmf_normalize_temp_if_no_gpus(uid_local)
            return

        # Starter kit: 1x GTX 1060 installed, 4 slots, PSU 600W, basic cooler.
        try:
            db.set_user_field(uid_local, "mining_slots", max(4, int(db.get_user_field(uid_local, "mining_slots") or 4)))
        except Exception:
            pass
        if not db.get_user_field(uid_local, "mining_psu"):
            db.set_user_field(uid_local, "mining_psu", "600")
        if not db.get_user_field(uid_local, "mining_cooling"):
            db.set_user_field(uid_local, "mining_cooling", "fan")

        # Migrate legacy single-qty fields into per-type inventories (so switching types keeps counts).
        try:
            cool_code = str(db.get_user_field(uid_local, "mining_cooling") or "fan")
            cool_qty_legacy = max(1, _cmf_get_int(uid_local, "mining_cooling_qty", 1))
            cool_inv = _cm_get_cooling_inventory(uid_local)
            if int(cool_inv.get(cool_code, 0) or 0) <= 0:
                cool_inv[cool_code] = int(cool_qty_legacy)
                _cm_set_cooling_inventory(uid_local, cool_inv)
            db.set_user_field(uid_local, "mining_cooling_qty", max(1, int(cool_inv.get(cool_code, 1))))
        except Exception:
            db.set_user_field(uid_local, "mining_cooling_qty", 1)

        try:
            psu_code = str(db.get_user_field(uid_local, "mining_psu") or "600")
            psu_qty_legacy = max(1, _cmf_get_int(uid_local, "mining_psu_qty", 1))
            psu_inv = _cm_get_psu_inventory(uid_local)
            if int(psu_inv.get(psu_code, 0) or 0) <= 0:
                psu_inv[psu_code] = int(psu_qty_legacy)
                _cm_set_psu_inventory(uid_local, psu_inv)
            db.set_user_field(uid_local, "mining_psu_qty", max(1, int(psu_inv.get(psu_code, 1))))
        except Exception:
            db.set_user_field(uid_local, "mining_psu_qty", 1)
        # If legacy installed list exists, keep it. New users start with no GPUs installed.
        # Starter gift is granted on the first mining start.
        # Baseline temperature is 25°C.
        if db.get_user_field(uid_local, "mining_temp") is None:
            db.set_user_field(uid_local, "mining_temp", 25.0)
        if db.get_user_field(uid_local, "mining_temp_target") is None:
            db.set_user_field(uid_local, "mining_temp_target", 25.0)
        if int(_cmf_get_int(uid_local, "mining_temp_ts", 0)) <= 0:
            db.set_user_field(uid_local, "mining_temp_ts", int(_cmf_now_ts()))
        db.set_user_field(uid_local, "mining_active", 0)
        db.set_user_field(uid_local, "mining_last_ts", 0)
        db.set_user_field(uid_local, "mining_cycle_seconds", 60)
        db.set_user_field(uid_local, "mining_boost_until", 0)
        db.set_user_field(uid_local, "mining_boost_mult", 1.0)
        db.set_user_field(uid_local, "mining_initialized", 1)

    def _cmf_installed_stats(uid_local: int) -> dict:
        cards = _cm_get_cards(uid_local)
        hashrate = 0
        watts = 0
        heat = 0
        income = Decimal("0")
        for code in cards:
            it = _CM_ITEMS.get("gpu", {}).get(str(code)) or {}
            hashrate += int(it.get("hash") or 0)
            watts += int(it.get("w") or 0)
            heat += int(it.get("t") or 0)
            try:
                income += Decimal(str(it.get("btc") or "0"))
            except Exception:
                pass
        # Cooling: all owned cooling types stack.
        cool_inv_raw = db.get_user_field(uid_local, "mining_cooling_inv_json")
        cool_inv = _cm_get_cooling_inventory(uid_local)
        # Legacy fallback only if JSON inventory is missing/uninitialized.
        if not cool_inv and not cool_inv_raw:
            cool_code_fallback = str(db.get_user_field(uid_local, "mining_cooling") or "fan")
            cool_inv = {cool_code_fallback: _cmf_installed_cool_qty(uid_local)}

        cool_rel_bonus = 0
        cool_passive = 0.0
        for code, qty in cool_inv.items():
            q = max(0, int(qty))
            if q <= 0:
                continue
            cool = _CM_ITEMS.get("cool", {}).get(str(code)) or {}
            mn = float(cool.get("cool_min") or 5)
            mx = float(cool.get("cool_max") or mn)
            cool_rel_bonus += int(cool.get("rel_bonus") or 0) * q
            watts += int(cool.get("w") or 0) * q
            # Passive cooling applied each mining cycle (even if temp drift is disabled for now).
            cool_passive += (((mn + mx) / 2.0) / 3.0) * float(q)

        # PSU: all owned PSU types stack (capacity sums, stability weighted).
        psu_inv_raw = db.get_user_field(uid_local, "mining_psu_inv_json")
        psu_inv = _cm_get_psu_inventory(uid_local)
        # Legacy fallback only if JSON inventory is missing/uninitialized.
        if not psu_inv and not psu_inv_raw:
            psu_code_fallback = str(db.get_user_field(uid_local, "mining_psu") or "600")
            psu_inv = {psu_code_fallback: _cmf_installed_psu_qty(uid_local)}

        maxw = 0
        stab_weight_sum = 0.0
        stab_sum = 0.0
        for code, qty in psu_inv.items():
            q = max(0, int(qty))
            if q <= 0:
                continue
            psu = _CM_ITEMS.get("psu", {}).get(str(code)) or {}
            cap = int(psu.get("maxw") or 0)
            stab = int(psu.get("stab") or 70)
            maxw += cap * q
            w = float(max(1, cap * q))
            stab_weight_sum += w
            stab_sum += float(stab) * w
        psu_stab = int(round(stab_sum / stab_weight_sum)) if stab_weight_sum > 0 else 70
        psu_stab = int(max(0, min(99, psu_stab)))

        # PSU throttling
        eff = 1.0
        if watts > maxw and watts > 0 and maxw > 0:
            eff = max(0.25, min(1.0, float(maxw) / float(watts)))

        # Permanent upgrade: +10% income
        upg_raw = db.get_user_field(uid_local, "mining_upgrades_json")
        upgs: set[str] = set()
        try:
            if upg_raw:
                parsed = json.loads(str(upg_raw))
                if isinstance(parsed, list):
                    upgs = {str(x) for x in parsed}
        except Exception:
            pass
        income_mult = Decimal("1")
        if "eff" in upgs:
            income_mult *= Decimal("1.10")

        # Final income (with global multipliers)
        base_cycle_income = (income * income_mult).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)

        # Special rule: if there is NO PSU at all, farm still works but is capped to 5 BTC/час.
        # Cooling is considered inactive too (handled at display level).
        if maxw <= 0 and watts > 0 and cards:
            cycle_s = max(15, _cmf_get_int(uid_local, "mining_cycle_seconds", 60))
            cap_hour = Decimal("5")
            try:
                base_hour = (base_cycle_income * Decimal("3600") / Decimal(str(cycle_s)))
            except Exception:
                base_hour = Decimal("0")
            if base_hour > 0:
                scale = min(Decimal("1"), (cap_hour / base_hour))
            else:
                scale = Decimal("1")
            eff = float(scale)
            final_income = (base_cycle_income * scale).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)
        else:
            final_income = (base_cycle_income * Decimal(str(eff))).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)

        return {
            "cards": cards,
            "hashrate": int(hashrate),
            "watts": int(watts),
            "heat": int(heat),
            "income": final_income,
            "psu_max": int(maxw),
            "psu_eff": float(eff),
            "cool_inv": {str(k): int(v) for k, v in cool_inv.items() if int(v) > 0},
            "cool_rel_bonus": int(cool_rel_bonus),
            "psu_inv": {str(k): int(v) for k, v in psu_inv.items() if int(v) > 0},
            "psu_stab": int(psu_stab),
            "cool_passive": float(cool_passive),
        }

    def _cmf_apply_mining(uid_local: int) -> None:
        _cmf_ensure_initialized(uid_local)
        # Update temperature drift before applying income / random events
        try:
            _cmf_update_temp(uid_local)
        except Exception:
            pass
        active = bool(_cmf_get_int(uid_local, "mining_active", 0))
        if not active:
            return

        now = _cmf_now_ts()
        last_ts = _cmf_get_int(uid_local, "mining_last_ts", 0)
        cycle_s = max(15, _cmf_get_int(uid_local, "mining_cycle_seconds", 60))
        if last_ts <= 0:
            db.set_user_field(uid_local, "mining_last_ts", now)
            return

        cycles = (now - last_ts) // cycle_s
        if cycles <= 0:
            return
        cycles_total = int(cycles)
        cycles_sim = min(cycles_total, 120)

        stats = _cmf_installed_stats(uid_local)
        base_income = Decimal(str(stats.get("income") or "0"))
        temp = float(_cmf_get_float(uid_local, "mining_temp", 0.0))

        boost_until = _cmf_get_int(uid_local, "mining_boost_until", 0)
        boost_mult = Decimal(str(_cmf_get_float(uid_local, "mining_boost_mult", 1.0)))
        if boost_until and now > boost_until:
            db.set_user_field(uid_local, "mining_boost_until", 0)
            db.set_user_field(uid_local, "mining_boost_mult", 1.0)
            boost_mult = Decimal("1")

        # Protection modifiers: upgrade shield + stacked cooling reliability
        upg_raw = db.get_user_field(uid_local, "mining_upgrades_json")
        upgs: set[str] = set()
        try:
            if upg_raw:
                parsed = json.loads(str(upg_raw))
                if isinstance(parsed, list):
                    upgs = {str(x) for x in parsed}
        except Exception:
            pass
        break_protect = 0.6 if "shield" in upgs else 1.0
        try:
            cool_rel = float(stats.get("cool_rel_bonus") or 0)
            break_protect *= max(0.40, 1.0 - min(0.60, cool_rel / 100.0))
        except Exception:
            pass

        try:
            psu_stab = int(stats.get("psu_stab") or 70)
        except Exception:
            psu_stab = 70
        overload_chance = max(0.02, 0.10 * (1.0 - max(0.0, float(psu_stab - 70)) / 100.0))

        total_add = Decimal("0")
        cards = list(stats.get("cards") or [])
        broken_this_apply = False
        stopped_early = False
        for _ in range(cycles_sim):
            if not cards:
                break
            income = base_income * boost_mult

            # Random events
            r = random.random()
            # NOTE: previously this was very aggressive (could wipe many cards during catch-up).
            # We cap breakage to max 1 per apply and use a much smaller per-cycle probability.
            if (not broken_this_apply) and temp >= 95 and r < 0.010 * break_protect:
                broken_this_apply = True
                broken = random.choice(cards)
                it = _CM_ITEMS.get("gpu", {}).get(str(broken)) or {}
                label = str(it.get("name") or broken).replace("🎮 ", "")
                try:
                    cards.remove(broken)
                    _cm_set_cards(uid_local, cards)
                except Exception:
                    pass
                _cmf_push_event(uid_local, f"🔥 Перегрев! Карта {label} сломалась.")
                _cmf_push_event(uid_local, "⛔ Майнинг остановлен из-за перегрева")
                db.set_user_field(uid_local, "mining_active", 0)
                income = Decimal("0")
                temp = max(25.0, temp - 25.0)
                stopped_early = True
                break
            if (not broken_this_apply) and temp >= 85 and r < 0.003 * break_protect:
                broken_this_apply = True
                broken = random.choice(cards)
                it = _CM_ITEMS.get("gpu", {}).get(str(broken)) or {}
                label = str(it.get("name") or broken).replace("🎮 ", "")
                try:
                    cards.remove(broken)
                    _cm_set_cards(uid_local, cards)
                except Exception:
                    pass
                _cmf_push_event(uid_local, f"🔥 Перегрев! Карта {label} сломалась.")
                _cmf_push_event(uid_local, "⛔ Майнинг остановлен из-за перегрева")
                db.set_user_field(uid_local, "mining_active", 0)
                income = Decimal("0")
                temp = max(25.0, temp - 25.0)
                stopped_early = True
                break
            elif r < overload_chance:
                income = (income * Decimal("0.5"))
                _cmf_push_event(uid_local, "⚠ Перегрузка фермы: доход -50% на 1 цикл")
            elif r > 0.94:
                mult = Decimal(str(random.uniform(1.5, 2.0)))
                income = (income * mult)
                _cmf_push_event(uid_local, "✨ Бонусный час майнинга: доход повышен на 1 цикл")

            total_add += income

            # temperature is fixed (changes only on GPU install / cooling actions)
            # allow temperature to exceed 120°C (no upper clamp)
            temp = temp

        # If the user was offline for a long time, credit the remaining cycles instantly.
        # Random events are intentionally skipped for the remainder to avoid spam and slow loops.
        if (not stopped_early) and cards and base_income > 0 and cycles_total > cycles_sim:
            total_add += (base_income * boost_mult * Decimal(cycles_total - cycles_sim))

        if total_add > 0:
            bal_btc = _cm_get_decimal_field(uid_local, "mining_btc", default=Decimal("0"))
            _cm_set_decimal_field(uid_local, "mining_btc", (bal_btc + total_add))
            # Also record lifetime mined BTC so leaderboard is not reset on sell.
            try:
                total_lifetime = _cm_get_decimal_field(uid_local, "mining_total_btc", default=Decimal("0"))
                _cm_set_decimal_field(uid_local, "mining_total_btc", (total_lifetime + total_add))
            except Exception:
                pass

        db.set_user_field(uid_local, "mining_temp", float(temp))
        db.set_user_field(uid_local, "mining_last_ts", int(last_ts + cycles_total * cycle_s))

    def _cmf_home_text(uid_local: int) -> str:
        _cmf_ensure_initialized(uid_local)
        _cmf_apply_mining(uid_local)

        btc = _cm_get_decimal_field(uid_local, "mining_btc", default=Decimal("0"))
        stats = _cmf_installed_stats(uid_local)
        temp = float(_cmf_display_temp(uid_local, stats=stats))

        cycle_s = max(15, _cmf_get_int(uid_local, "mining_cycle_seconds", 60))
        income_cycle = Decimal(str(stats.get("income") or "0"))
        income_hour = (income_cycle * Decimal("3600") / Decimal(str(cycle_s))).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)

        watts = int(stats.get("watts") or 0)
        max_w = int(stats.get("psu_max") or 0)
        active = bool(_cmf_get_int(uid_local, "mining_active", 0))

        # 10-segment temperature bar (visual only)
        try:
            filled = int(round(float(temp) / 13.0))
        except Exception:
            filled = 0
        filled = max(0, min(10, filled))
        bar = ("■" * filled) + ("□" * (10 - filled))

        text = (
            "⛏️ МАЙНИНГ ФЕРМА\n"
            "━━━━━━━━━━━━━━━\n"
            f"💰 Баланс: {_cm_fmt_btc(btc)} BTC\n"
            f"📊 Доход: +{_cm_fmt_btc(income_hour)} BTC/час\n"
            f"🔥 Температура: {int(round(temp))}°C [{bar}]\n"
            f"⚡ Мощность: {watts}W / {max_w}W"
        )

        if not active:
            # Show the first-start hint only for truly new users.
            try:
                rewarded = int(db.get_user_field(uid_local, "mining_first_start_rewarded") or 0)
            except Exception:
                rewarded = 0
            last_ts = _cmf_get_int(uid_local, "mining_last_ts", 0)
            if rewarded != 1 and int(last_ts) <= 0 and btc <= 0:
                try:
                    intro_seen = int(db.get_user_field(uid_local, "mining_intro_seen") or 0)
                except Exception:
                    intro_seen = 0
                if intro_seen != 1:
                    text += "\n\n👇 Нажми на кнопке ниже ⛏ Майнить и запусти свою 1 ферму"
                    try:
                        db.set_user_field(uid_local, "mining_intro_seen", 1)
                    except Exception:
                        pass

        return text

    def _cmf_mining_screen_text(uid_local: int) -> str:
        _cmf_ensure_initialized(uid_local)
        _cmf_apply_mining(uid_local)
        active = bool(_cmf_get_int(uid_local, "mining_active", 0))
        stats = _cmf_installed_stats(uid_local)
        temp = float(_cmf_display_temp(uid_local, stats=stats))
        try:
            target = float(db.get_user_field(uid_local, "mining_temp_target") or temp)
        except Exception:
            target = float(temp)
        try:
            anim_start = float(db.get_user_field(uid_local, "mining_temp_animation_start") or int(round(temp)))
        except Exception:
            anim_start = float(temp)
        if anim_start < -100 or anim_start > 500:
            anim_start = float(temp)
        cycle_s = max(15, _cmf_get_int(uid_local, "mining_cycle_seconds", 60))
        last_ts = _cmf_get_int(uid_local, "mining_last_ts", 0)
        now = _cmf_now_ts()
        next_in = cycle_s
        if active and last_ts > 0:
            elapsed = max(0, now - last_ts)
            next_in = max(1, cycle_s - (elapsed % cycle_s))

        income = Decimal(str(stats.get("income") or "0"))
        try:
            btc_bal = _cm_get_decimal_field(uid_local, "mining_btc", default=Decimal("0"))
        except Exception:
            btc_bal = Decimal("0")
        try:
            income_per_hour = (income * Decimal("3600") / Decimal(str(cycle_s))) if cycle_s > 0 else Decimal("0")
        except Exception:
            income_per_hour = Decimal("0")
        bal_s = _cm_fmt_btc(btc_bal)
        cycle_s_s = str(cycle_s)
        temp_line = f"🌡 Температура: {int(round(temp))}°C"
        anim_lines = ""
        if abs(float(temp) - float(target)) >= 0.5:
            direction = "🔥 Нагрев" if float(temp) < float(target) else "❄️ Охлаждение"
            bar = _cmf_make_progress_bar(anim_start, float(temp), float(target))
            anim_lines = f"\n{direction}: {bar}\n🎯 Цель: {int(round(target))}°C"

        return (
            "⛏ Майнинг запущен...\n\n" if active else "⛏ Майнинг остановлен.\n\n"
        ) + (
            f"💰 Баланс: {bal_s} BTC\n"
            f"{temp_line}{anim_lines}\n"
            f"🪙 Доход: +{_cm_fmt_btc(income)} BTC / цикл ({cycle_s_s} сек) — { _cm_fmt_btc3(income_per_hour) } BTC/ч\n\n"
            f"Следующее начисление через {next_in} секунд ⏱"
        )

    def _cmf_farm_text(uid_local: int) -> str:
        _cmf_ensure_initialized(uid_local)
        _cmf_apply_mining(uid_local)
        stats = _cmf_installed_stats(uid_local)
        temp = float(_cmf_display_temp(uid_local, stats=stats))
        btc = _cm_get_decimal_field(uid_local, "mining_btc", default=Decimal("0"))
        cycle_s = max(15, _cmf_get_int(uid_local, "mining_cycle_seconds", 60))

        def _fmt_short(dec: Decimal) -> str:
            try:
                s = f"{dec:.6f}"
            except Exception:
                s = str(dec)
            if "." in s:
                s = s.rstrip("0").rstrip(".")
            return s

        # GPUs installed
        cards = [str(x) for x in (stats.get("cards") or [])]

        # Global income multipliers (so per-card BTC/час matches the real total).
        try:
            psu_eff = Decimal(str(stats.get("psu_eff") or 1.0))
        except Exception:
            psu_eff = Decimal("1")
        income_mult = Decimal("1")
        try:
            upg_raw = db.get_user_field(uid_local, "mining_upgrades_json")
            if upg_raw:
                parsed = json.loads(str(upg_raw))
                if isinstance(parsed, list) and "eff" in {str(x) for x in parsed}:
                    income_mult *= Decimal("1.10")
        except Exception:
            pass
        global_mult = income_mult * psu_eff

        counts: dict[str, int] = {}
        for c in cards:
            counts[c] = counts.get(c, 0) + 1
        gpu_lines: list[str] = []
        for code, qty in sorted(counts.items(), key=lambda kv: (-int(kv[1]), kv[0])):
            it = _CM_ITEMS.get("gpu", {}).get(str(code)) or {}
            name = str(it.get("name") or str(code)).replace("🎮 ", "")
            w = int(it.get("w") or 0)
            try:
                btc_cycle = Decimal(str(it.get("btc") or "0"))
            except Exception:
                btc_cycle = Decimal("0")
            btc_hour = (btc_cycle * global_mult * Decimal(int(qty)) * Decimal("3600") / Decimal(str(cycle_s))).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)
            gpu_lines.append(f"• {name} — {int(qty)} шт ({_fmt_short(btc_hour)} BTC/час, {int(w) * int(qty)}W)")
        if not gpu_lines:
            gpu_lines.append("• Нет установленных видеокарт")

        used_slots = len(cards)
        total_slots = _cm_slots_total(uid_local)
        slots_line = f"📦 Ячейки: {used_slots}/{total_slots}"

        # Cooling (all owned types)
        cool_inv_raw = db.get_user_field(uid_local, "mining_cooling_inv_json")
        cool_inv = _cm_get_cooling_inventory(uid_local)
        # Legacy fallback only if JSON inventory is missing/uninitialized.
        if not cool_inv and not cool_inv_raw:
            cool_code_fallback = str(db.get_user_field(uid_local, "mining_cooling") or "fan")
            cool_inv = {cool_code_fallback: _cmf_installed_cool_qty(uid_local)}

        # If there is NO PSU at all, cooling is considered inactive (no effect).
        cooling_active = True
        try:
            if int(stats.get("psu_max") or 0) <= 0 and int(stats.get("watts") or 0) > 0:
                cooling_active = False
        except Exception:
            cooling_active = True

        cool_lines: list[str] = []
        total_cool = 0
        for code, qty in sorted(cool_inv.items()):
            q = max(0, int(qty))
            if q <= 0:
                continue
            it = _CM_ITEMS.get("cool", {}).get(str(code)) or {}
            name = str(it.get("name") or str(code))
            name = name.replace("🌀 ", "").replace("💧 ", "").replace("🧊 ", "")
            mn_unit = float(it.get("cool_min") or 0)
            mx_unit = float(it.get("cool_max") or mn_unit)
            total_cool += int(round(((mn_unit + mx_unit) / 2.0) * float(q)))
            cool_lines.append(f"• {name} x{q}")
        if not cool_lines:
            cool_lines.append("• Нет охлаждения")
        else:
            if not cooling_active:
                cool_lines.extend(["", "Охлаждение не работает без питания", "Общее охлаждение: 0"])
            else:
                cool_lines.extend(["", f"Общее охлаждение -{int(total_cool)}"])

        # PSU (all owned types)
        psu_inv_raw = db.get_user_field(uid_local, "mining_psu_inv_json")
        psu_inv = _cm_get_psu_inventory(uid_local)
        # Legacy fallback only if JSON inventory is missing/uninitialized.
        if not psu_inv and not psu_inv_raw:
            psu_code_fallback = str(db.get_user_field(uid_local, "mining_psu") or "600")
            psu_inv = {psu_code_fallback: _cmf_installed_psu_qty(uid_local)}

        psu_lines: list[str] = []
        for code, qty in sorted(psu_inv.items(), key=lambda kv: int(kv[0])):
            q = max(0, int(qty))
            if q <= 0:
                continue
            psu_lines.append(f"• БП {int(code)}W x{q}")
        if not psu_lines:
            psu_lines.append("• Нет блоков питания")

        total_power = int(stats.get("psu_max") or 0)
        required = int(stats.get("watts") or 0)
        ok = "✅" if required <= total_power else "❌"

        income_cycle = Decimal(str(stats.get("income") or "0"))
        income_hour_total = (income_cycle * Decimal("3600") / Decimal(str(cycle_s))).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)

        return (
            "🖥 Моя ферма\n\n"
            "🎮 Видеокарты:\n"
            + "\n".join(gpu_lines)
            + "\n\n" + slots_line
            + "\n\n"
            "❄ Охлаждение:\n"
            + "\n".join(cool_lines)
            + "\n\n"
            "⚡ Питание:\n"
            + "\n".join(psu_lines)
            + "\n\n"
            f"➡ Всего мощность: {total_power}W\n"
            f"⚡ Требуется: {required}W {ok}\n\n"
            f"🌡 Общая температура фермы: {int(round(temp))}°C\n\n"
            f"💰 Итоговый доход фермы: {_fmt_short(income_hour_total)} BTC/час\n\n"
            f"🪙 Баланс BTC: {_cm_fmt_btc(btc)}"
        )

    def _cmf_market_text(uid_local: int) -> str:
        _cmf_ensure_initialized(uid_local)
        _cmf_apply_mining(uid_local)
        btc = _cm_get_decimal_field(uid_local, "mining_btc", default=Decimal("0"))
        points = int(db.get_balance(uid_local) or 0)
        coins = int(db.get_coins_balance(uid_local) or 0)
        return (
            "🔄 Рынок\n\n"
            "Продай BTC и получи награду:\n"
            "• 75% получаешь баллами\n"
            "• 15% получаешь коинами\n\n"
            f"🪙 BTC: {_cm_fmt_btc(btc)}\n"
            f"⭐ Баллы: {points}\n"
            f"🪙 Коины: {coins}\n\n"
            "Курс: 1 BTC = 100 (база)\n"
            "Обмен: 1 коин = 1.15 балла\n"
            "Обмен: 1000 коинов = 1 ₽"
        )

    def _cmf_market_confirm_text(uid_local: int, amt_btc: Decimal) -> str:
        _cmf_ensure_initialized(uid_local)
        _cmf_apply_mining(uid_local)
        base = int((amt_btc * Decimal("100")).to_integral_value(rounding=ROUND_FLOOR))
        pts = int((Decimal(base) * Decimal("0.75")).to_integral_value(rounding=ROUND_FLOOR))
        coins = int((Decimal(base) * Decimal("0.15")).to_integral_value(rounding=ROUND_FLOOR))
        return (
            "💱 Продажа BTC\n\n"
            f"Ты выбрал продать {str(amt_btc)} BTC\n"
            "Получишь:\n"
            f"• {pts} ⭐\n"
            f"• {coins} 🪙\n\n"
            "Подтвердить продажу?"
        )

    def _cmf_parse_decimal(s: str) -> Decimal | None:
        try:
            d = Decimal(str(s).strip())
        except Exception:
            return None
        if d <= 0:
            return None
        return d

    def _cmf_rating_text(uid_local: int) -> str:
        _cmf_ensure_initialized(uid_local)
        _cmf_apply_mining(uid_local)
        leaders = []
        try:
            leaders = db.get_mining_leaderboard(limit=10)
        except Exception:
            leaders = []
        lines = ["🏆 Рейтинг майнеров\n"]
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(leaders[:3]):
            uname = str(row.get("username") or "-")
            btc = row.get("mining_btc")
            try:
                btc_txt = _cm_fmt_btc(Decimal(str(btc or 0)))
            except Exception:
                btc_txt = "0.000000"
            lines.append(f"{medals[i]} @{uname} — {btc_txt} BTC")

        try:
            me = db.get_mining_rank_position(uid_local)
        except Exception:
            me = None
        if me:
            try:
                btc_txt = _cm_fmt_btc(Decimal(str(me.get("mining_btc") or 0)))
            except Exception:
                btc_txt = "0.000000"
            lines.append("")
            lines.append(f"Ты: #{me.get('position')} — {btc_txt} BTC")
        return "\n".join(lines)

    def _balance_rating_text(uid_local: int, *, limit: int = 10) -> str:
        limit = max(1, int(limit))
        try:
            leaders = db.get_leaderboard_by_balance(limit=limit)
        except Exception:
            leaders = []

        lines = ["🏆 Рейтинг по балансу\n"]
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(leaders[:limit]):
            try:
                uname = str(row.get("username") or "")
            except Exception:
                uname = ""
            try:
                bal = int(row.get("balance_points") or 0)
            except Exception:
                bal = 0
            tag = f"@{uname}" if uname else f"id{int(row.get('user_id') or 0)}"
            prefix = medals[i] if i < len(medals) else f"{i + 1}."
            lines.append(f"{prefix} {tag} — {_fmt_money(bal)}")

        try:
            me = db.get_user_rank_position_by_balance(uid_local)
        except Exception:
            me = None
        if me:
            try:
                pos = int(me.get("position") or 0)
            except Exception:
                pos = 0
            try:
                bal_me = int(me.get("balance_points") or 0)
            except Exception:
                bal_me = 0
            lines.append("")
            lines.append(f"Ты: #{pos} — {_fmt_money(bal_me)}")
        return "\n".join(lines)

    def _cmf_settings_text(uid_local: int) -> str:
        _cmf_ensure_initialized(uid_local)
        _cmf_apply_mining(uid_local)
        cycle_s = max(15, _cmf_get_int(uid_local, "mining_cycle_seconds", 60))
        boost_until = _cmf_get_int(uid_local, "mining_boost_until", 0)
        boost_mult = _cmf_get_float(uid_local, "mining_boost_mult", 1.0)
        now = _cmf_now_ts()
        boost_left = max(0, int(boost_until - now)) if boost_until else 0
        boosters = _cm_get_boosters(uid_local)

        lines = [
            "⚙ Настройки\n",
            f"⏱ Цикл: {cycle_s} сек",
            f"🚀 Активный буст: x{boost_mult:.2f} (осталось {boost_left} сек)" if boost_left else "🚀 Активный буст: нет",
            "",
            "🎒 Бустеры в инвентаре:",
            f"• x2 (10 мин): {int(boosters.get('x2_10', 0))}",
            f"• x3 (5 мин): {int(boosters.get('x3_5', 0))}",
            f"• Мгновенное охлаждение: {int(boosters.get('cool', 0))}",
            "",
            "Использование бустеров — через покупку в магазине (применится автоматически при запуске майнинга в этой версии).",
        ]
        return "\n".join(lines)

    def _shop_vip_text() -> str:
        return (
            "👑 VIP-СТАТУС\n\n"
            "VIP даёт максимальные бонусы в боте:\n\n"
            "💰 +20% к наградам за задания\n"
            "🎮 +0.10 — +0.50 к коэффициенту в игре Мины\n"
            "⏱ Быстрый вывод средств\n"
            "⭐ VIP-иконка в профиле\n\n"
            "Статус активируется сразу после покупки."
        )

    def _vip_cost_rub(plan: str) -> int:
        if plan == "7":
            return 299
        if plan == "30":
            return 999
        if plan == "forever":
            return 2499
        return 0

    def _vip_add_seconds(plan: str) -> int:
        if plan == "7":
            return 7 * 24 * 3600
        if plan == "30":
            return 30 * 24 * 3600
        if plan == "forever":
            # Year 3000-ish
            return 365 * 24 * 3600 * 1000
        return 0

    def _farm_plan_meta(plan: str) -> tuple[int, int, int]:
        # (price_rub, duration_seconds, multiplier)
        if plan == "x2_24":
            return (99, 24 * 3600, 2)
        if plan == "x3_24":
            return (199, 24 * 3600, 3)
        return (0, 0, 1)

    def _rub_to_points(rub: int) -> int:
        return int(max(0, int(rub))) * int(POINTS_PER_RUB)

    def _send_profile(chat_id: int, uid: int) -> None:
        info = db.get_user_level_info(uid)
        if not info:
            prof = db.get_profile(uid)
            level = "Активный" if prof["blocked"] == 0 else "Заблокирован"
            bot.send_message(
                chat_id,
                f"ID: {prof['user_id']}\n"
                f"Уровень: {level}\n"
                f"Выполнено заданий: {prof['completed_tasks']}\n"
                f"Приглашено друзей: {prof['referrals_count']}",
                reply_markup=main_menu_kb(is_admin=_is_admin(uid, settings)),
            )
            return

        lines = [
            "💼 ПРОФИЛЬ\n",
            f"👤 ID: {info['user_id']}",
            f"💰 Баланс: {_fmt_int(info.get('balance_points'))} баллов",
            f"🪙 Коины: {_fmt_int(db.get_coins_balance(uid))}",
            f"⭐ Уровень: {info['title']}",
            f"📈 XP: {_fmt_int(info.get('xp'))}",
        ]

        try:
            ins = db.get_insurance_state(uid) or {}
            insurance_balance = int(ins.get("balance") or 0)
            insurance_next = bool(int(ins.get("next") or 0))
            insurance_blocked = bool(int(ins.get("block") or 0))
            lines.append(
                "🛡 Страховки: "
                f"{max(0, insurance_balance)} "
                f"(включены: {'ВКЛ' if insurance_next else 'ВЫКЛ'}, блок: {'ДА' if insurance_blocked else 'НЕТ'})"
            )
        except Exception:
            pass

        # Rank and position in top by level
        try:
            rank = db.rank_for_level(int(info.get("level") or 0))
            lines.append(f"💎 Ранг: {rank}")
            pos = db.get_user_rank_position_by_level(uid)
            if pos:
                lines.append(f"🏆 Место в топе по уровню: {pos['position']}")
        except Exception:
            pass

        ct = info.get("custom_title")
        if ct:
            lines.append(f"🏷 Титул: {ct}")

        if bool(info.get("vip_active")):
            lines.append("👑 Статус: VIP")
            now_ts = int(time.time())
            vip_until = int(info.get("vip_until") or 0)
            if vip_until >= now_ts + 100 * 365 * 24 * 3600:
                lines.append("⏳ VIP: навсегда")
            else:
                lines.append(f"⏳ VIP до: {_fmt_date_ddmmyyyy(vip_until)}")
        else:
            lines.append("👑 Статус: Обычный")

        lines.append(f"👥 Рефералов: {info.get('referrals_count')}")

        # Блок по дуэлям: ранг, MMR и серия побед
        try:
            mmr = int(db.get_user_field(uid, "duel_mmr") or 1000)
        except Exception:
            mmr = 1000

        def _gf_duel(field: str, default: int = 0) -> int:
            try:
                return int(db.get_user_field(uid, field) or default)
            except Exception:
                return default

        try:
            duel_games = _gf_duel("duel_games")
            duel_wins = _gf_duel("duel_wins")
            duel_losses = _gf_duel("duel_losses")
            duel_streak = _gf_duel("duel_streak")
            duel_best = _gf_duel("duel_best_streak")
            stored_rank = db.get_user_field(uid, "duel_rank")
            duel_rank = stored_rank or _duel_rank_from_mmr(mmr)
        except Exception:
            duel_games = duel_wins = duel_losses = duel_streak = duel_best = 0
            duel_rank = _duel_rank_from_mmr(mmr)

        lines.append("")
        lines.append("⚔ Дуэли:")
        lines.append(f"🏅 Ранг: {duel_rank}")
        lines.append(f"📈 MMR: {mmr}")
        lines.append(f"🔥 Серия побед: {duel_streak} (лучшее: {duel_best})")
        lines.append(f"🎮 Игр: {duel_games} · Побед: {duel_wins} · Поражений: {duel_losses}")

        bot.send_message(chat_id, "\n".join(lines), reply_markup=profile_kb())


    def _weekly_next_reset_ts(now_ts: int) -> int:
        now_dt = dt.datetime.utcfromtimestamp(int(now_ts))
        monday = now_dt.date() - dt.timedelta(days=int(now_dt.weekday()))
        next_monday = monday + dt.timedelta(days=7)
        return int(dt.datetime(next_monday.year, next_monday.month, next_monday.day, tzinfo=dt.timezone.utc).timestamp())


    def _weekly_build_screen(
        uid: int,
        *,
        now_ts: int,
        refresh_cb: str = "profile:weekly",
        back_cb: str = "profile",
    ) -> tuple[str, list[dict], InlineKeyboardMarkup]:
        week_key = db.week_key_utc(now_ts)
        tasks = db.get_weekly_tasks_for_user(uid, week_key=week_key, now_ts=now_ts)
        next_reset_ts = _weekly_next_reset_ts(now_ts)
        left = max(0, int(next_reset_ts) - int(now_ts))

        lines: list[str] = []
        lines.append("📅 НЕДЕЛЬНЫЕ ЗАДАНИЯ\n")
        lines.append(f"Неделя (UTC): с {week_key}")
        lines.append(f"До обновления: {_fmt_mmss(left) if left < 3600 else _fmt_hhmmss(left)}")
        lines.append("")

        for t in tasks or []:
            slot = int(t.get("slot") or 0)
            title = str(t.get("title") or "")
            progress = int(t.get("progress") or 0)
            target = int(t.get("target") or 0)
            reward = int(t.get("reward_points") or 0)
            claimed = int(t.get("claimed") or 0)

            if claimed:
                status = "✅ Получено"
            elif target > 0 and progress >= target:
                status = "🎁 Готово"
            else:
                status = "⏳ В процессе"

            lines.append(f"{slot}) {title}")
            lines.append(f"   Прогресс: {min(progress, target)}/{target}")
            lines.append(f"   Награда: +{_fmt_money(reward)}")
            lines.append(f"   Статус: {status}")
            lines.append("")

        text = "\n".join(lines).strip()
        km = kb_module.weekly_tasks_kb(tasks, refresh_cb=str(refresh_cb), back_cb=str(back_cb))
        return text, tasks, km


    def _weekly_show(call: CallbackQuery, uid: int) -> None:
        now_ts = int(time.time())
        text, _tasks, km = _weekly_build_screen(uid, now_ts=now_ts, refresh_cb="profile:weekly", back_cb="profile")
        try:
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
            )
        except Exception:
            bot.send_message(call.message.chat.id, text, reply_markup=km)


    WHEEL_HOURLY_LIMIT = 20


    def _bet_limits_for(uid_local: int) -> tuple[int, int]:
        min_bet = 10
        max_bet = 100_000_000 if _is_admin(int(uid_local), settings) else 250_000
        return min_bet, max_bet


    def _bet_out_of_range_text(*, bet: int, min_bet: int, max_bet: int) -> str:
        if int(bet) < int(min_bet):
            return f"Ставка должна быть не меньше {_fmt_money(int(min_bet))} 💰"
        return f"Ставка должна быть не больше {_fmt_money(int(max_bet))} 💰"


    def _wheel_rewards_for_bet(bet: int) -> dict[int, tuple[str, dict | None]]:
        # New UX: rewards are always x2 of the chosen bet (no farm rewards).
        win_points = int(max(0, int(bet) * 2))
        return {
            1: ("❌ Ничего", None),
            2: (f"💰 +{win_points} баллов", {"points": win_points}),
            3: ("❌ Ничего", None),
            4: (f"💰 +{win_points} баллов", {"points": win_points}),
            5: ("❌ Ничего", None),
            6: (f"💰 +{win_points} баллов", {"points": win_points}),
        }


    def _build_wheel_screen(uid: int, *, show_top: bool = True) -> tuple[str, telebot.types.InlineKeyboardMarkup]:
        now_ts = int(time.time())
        hour_start = (now_ts // 3600) * 3600
        win_meta = db.get_wheel_window(uid) or {"hour_ts": 0, "games_in_hour": 0}
        if int(win_meta.get("hour_ts") or 0) != hour_start:
            games_in_hour = 0
        else:
            games_in_hour = int(win_meta.get("games_in_hour") or 0)
        left = max(0, int(WHEEL_HOURLY_LIMIT) - int(games_in_hour))

        last_bets = db.get_last_bets(uid, "wheel", limit=5)
        try:
            bal = int(db.get_balance(uid) or 0)
        except Exception:
            bal = 0
        lines = [
            "🎡 КОЛЕСО ФОРТУНЫ (🎲)",
            f"Баланс: {_fmt_points_ui(bal)} 💠",
            "",
            f"Ограничение: максимум {WHEEL_HOURLY_LIMIT} игр в час.",
            f"Осталось в этом часу: {left}.",
            "",
            "Выбери ставку:",
            "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
            "Или отправь сумму числом — игра начнётся сразу. Пример: 750",
        ]
        km = game_bet_kb(game="wheel", last_bets=last_bets)
        return "\n".join(lines), km


    def _apply_wheel_spin(uid: int, use_free: bool) -> tuple[str, telebot.types.InlineKeyboardMarkup]:
        now_ts = int(time.time())
        today = dt.datetime.utcfromtimestamp(now_ts).date()
        st = db.get_wheel_state(uid) or {"last_spin_date": None, "free_spins_used": 0, "streak_days": 0, "vip_until": 0}
        last_raw = st.get("last_spin_date")
        last_date = dt.date.fromisoformat(last_raw) if last_raw else None
        streak_days = int(st.get("streak_days") or 0)
        free_used = int(st.get("free_spins_used") or 0)
        vip_until = int(st.get("vip_until") or 0)
        vip_active = vip_until > now_ts

        # recompute daily context
        if last_date is None or last_date != today:
            free_used = 0
            if last_date is None:
                streak_days = 0
            else:
                if last_date == today - dt.timedelta(days=1):
                    streak_days = max(1, streak_days + 1)
                else:
                    streak_days = 1

        base_free = 1 + (1 if vip_active else 0)
        has_free = free_used < base_free
        if use_free and not has_free:
            msg, km = _build_wheel_screen(uid)
            return "❌ Бесплатные спины на сегодня закончились.\n\n" + msg, km

        # probabilities
        super_mode = streak_days >= 7
        if use_free:
            # Бесплатный спин всегда даёт пустой результат
            reward_type = "nothing"
        else:
            r = random.random()
            if not super_mode:
                # normal spin
                if r < 0.4:
                    reward_type = "points"
                elif r < 0.6:
                    reward_type = "booster"
                elif r < 0.8:
                    reward_type = "respins"
                elif r < 0.85:
                    reward_type = "vip7"
                else:
                    reward_type = "nothing"
            else:
                # super spin: выше шанс редких наград
                if r < 0.3:
                    reward_type = "points"
                elif r < 0.55:
                    reward_type = "booster"
                elif r < 0.75:
                    reward_type = "respins"
                elif r < 0.9:
                    reward_type = "vip7"
                else:
                    reward_type = "nothing"

        text_lines: list[str] = ["🎡 Результат спина:\n"]
        # consume cost unless reward is respin
        if use_free:
            if reward_type != "respins":
                free_used += 1
        else:
            if reward_type != "respins":
                spent = db.try_spend_points(uid, WHEEL_PAID_SPIN_COST)
                if not spent.get("ok"):
                    msg, km = _build_wheel_screen(uid)
                    return "❌ Недостаточно баллов для платного спина.\n\n" + msg, km

        # apply reward
        if reward_type == "points":
            amount = random.randint(50, 500)
            db.add_balance(uid, amount)
            text_lines.append(f"💰 Вы выиграли {_fmt_points_ui(int(amount))} баллов!")
        elif reward_type == "booster":
            res = db.try_buy_farm_booster(
                uid,
                now_ts=now_ts,
                cost_points=0,
                duration_seconds=FARM_BOOSTER_DURATION_SECONDS,
                multiplier=2,
            )
            if res.get("ok"):
                text_lines.append("⚡ Вы получили x2 фарм на 24 часа!")
            else:
                db.add_balance(uid, 100)
                text_lines.append("⚡ У вас уже есть буст, вместо этого: +100 баллов!")
        elif reward_type == "respins":
            text_lines.append("🎟 Повторный спин! Эта попытка не потрачена — крутите ещё раз.")
        elif reward_type == "vip7":
            new_until = db.extend_vip_until(uid, now_ts=now_ts, add_seconds=7 * 24 * 3600)
            text_lines.append(
                "👑 Вам выпал VIP на 7 дней!\n" f"Действует до: {_fmt_date_ddmmyyyy(new_until)}"
            )
        else:
            text_lines.append("❌ Ничего не выпало в этот раз.")

        new_streak = 0 if super_mode else streak_days
        db.update_wheel_state(uid, last_spin_date=today.isoformat(), free_spins_used=free_used, streak_days=new_streak)

        msg, km = _build_wheel_screen(uid)
        text_lines.append("")
        text_lines.append(msg)
        return "\n".join(text_lines), km


    def _build_dice_screen(uid: int) -> tuple[str, telebot.types.InlineKeyboardMarkup]:
        try:
            bal = int(db.get_balance(uid) or 0)
        except Exception:
            bal = 0
        text = (
            "🎲 КОСТИ С БОТОМ\n\n"
            f"Баланс: {_fmt_points_ui(bal)} 💠\n\n"
            "Выбери ставку:\n"
            "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)\n"
            "Или отправь сумму числом — игра начнётся сразу. Пример: 750"
        )
        last_bets = db.get_last_bets(uid, "dice", limit=5)
        return text, game_bet_kb(game="dice", last_bets=last_bets)


    def _dice_start_auto_game(*, chat_id: int, uid: int, bet: int, edit_message_id: int | None = None) -> None:
        if db.is_blocked(uid):
            bot.send_message(chat_id, "Ваш аккаунт заблокирован.")
            return

        try:
            bet = int(bet)
        except Exception:
            return
        min_bet, max_bet = _bet_limits_for(uid)
        if bet < min_bet or bet > max_bet:
            bot.send_message(chat_id, "❌ " + _bet_out_of_range_text(bet=bet, min_bet=min_bet, max_bet=max_bet))
            return

        s = session(uid)
        if s.dice_active:
            bot.send_message(chat_id, "🎲 Игра уже идёт. Подождите результат.")
            return

        try:
            db.push_last_bet(uid, "dice", bet, limit=5)
        except Exception:
            pass

        now_ts = int(time.time())
        win = db.get_dice_window(uid) or {"hour_ts": 0, "games_in_hour": 0}
        hour_start = (now_ts // 3600) * 3600
        if int(win.get("hour_ts") or 0) != hour_start:
            games_in_hour = 0
        else:
            games_in_hour = int(win.get("games_in_hour") or 0)
        if games_in_hour >= DICE_MAX_GAMES_PER_HOUR:
            bot.send_message(chat_id, "⏳ Лимит 20 игр в час. Попробуйте позже.")
            return

        # списываем ставку и запускаем автоматический раунд
        spent = db.try_spend_points(uid, bet)
        if not spent.get("ok"):
            bot.send_message(
                chat_id,
                f"Недостаточно баллов. Баланс: {_fmt_points_ui(int(spent.get('balance') or 0))}. Выбери ставку ниже.\n"
                "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
            )
            return
        s.dice_active = True
        s.dice_bet = bet
        s.dice_bot_value = None
        s.dice_insurance = bool(_insurance_reserve_for_game(uid))

        # Weekly tasks progress
        try:
            wk = db.week_key_utc(now_ts)
            db.add_weekly_progress(uid, week_key=wk, code="dice_games", delta=1, now_ts=now_ts)
        except Exception:
            pass

        if edit_message_id is not None:
            try:
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=edit_message_id, reply_markup=None)
            except Exception:
                pass

        def _worker() -> None:
            try:
                try:
                    bot.send_message(chat_id, "🤖 Бот кинул кубик 🎲")
                except Exception:
                    pass
                bot_dice = bot.send_dice(chat_id, emoji="🎲")
                bot_val = int(bot_dice.dice.value if bot_dice.dice else 0)

                time.sleep(1)
                try:
                    bot.send_message(chat_id, "🙂 Ты кинул кубик 🎲")
                except Exception:
                    pass
                user_dice = bot.send_dice(chat_id, emoji="🎲")
                user_val = int(user_dice.dice.value if user_dice.dice else 0)

                time.sleep(3)
                end_ts = int(time.time())
                vip_active = False
                try:
                    vip_active = db.is_vip_active(uid, now_ts=end_ts)
                except Exception:
                    vip_active = False

                if user_val > bot_val:
                    mult = 1.9
                    if vip_active:
                        mult = 1.95
                    win_amount = int(bet * mult)
                    db.add_balance(uid, win_amount)
                    result_text = (
                        f"🎲 Ты бросил: {user_val}\n"
                        f"🤖 Бот бросил: {bot_val}\n\n"
                        f"🎉 Победа! Ты выиграл {_fmt_points_ui(int(win_amount))} баллов."
                    )
                    _insurance_after_game(uid=uid, insured_used=False)
                elif user_val < bot_val:
                    used_ins, _refund, _pct = _insurance_apply_on_loss(
                        uid=uid,
                        stake=bet,
                        chat_id=int(chat_id),
                        game_label="Кости",
                        reserved=bool(getattr(s, "dice_insurance", False)),
                    )
                    _insurance_after_game(uid=uid, insured_used=bool(used_ins))
                    result_text = (
                        f"🎲 Ты бросил: {user_val}\n"
                        f"🤖 Бот бросил: {bot_val}\n\n"
                        f"😢 Ты проиграл ставку {_fmt_points_ui(int(bet))} баллов."
                    )
                else:
                    db.add_balance(uid, bet)
                    result_text = (
                        f"🎲 Ты бросил: {user_val}\n"
                        f"🤖 Бот бросил: {bot_val}\n\n"
                        "🤝 Ничья! Ставка возвращена."
                    )
                    _insurance_after_game(uid=uid, insured_used=False)

                win_meta = db.get_dice_window(uid) or {"hour_ts": 0, "games_in_hour": 0}
                hour_start2 = (end_ts // 3600) * 3600
                if int(win_meta.get("hour_ts") or 0) != hour_start2:
                    games_in_hour2 = 0
                else:
                    games_in_hour2 = int(win_meta.get("games_in_hour") or 0)
                games_in_hour2 += 1
                db.update_dice_window(uid, hour_ts=hour_start2, games_in_hour=games_in_hour2)

                bot.send_message(chat_id, result_text, reply_markup=dice_again_kb(bet))
            except Exception:
                # если упало до результата — возвращаем ставку
                try:
                    db.add_balance(uid, bet)
                except Exception:
                    pass
                try:
                    bot.send_message(chat_id, "❌ Ошибка в игре. Ставка возвращена.")
                except Exception:
                    pass
                try:
                    _insurance_after_game(uid=uid, insured_used=False)
                except Exception:
                    pass
            finally:
                s.dice_active = False
                s.dice_bet = None
                s.dice_bot_value = None
                s.dice_insurance = False

        threading.Thread(target=_worker, daemon=True).start()


    def _duels_menu_text(user_id: int) -> str:
        """Главное меню дуэлей: без рангов/статистики, только баланс."""
        uid = int(user_id)
        try:
            bal = int(db.get_balance(uid) or 0)
        except Exception:
            bal = 0

        lines: list[str] = [
            "⚔️ Дуэли",
            "",
            f"💰 Баланс: {_fmt_points_ui(bal)} 💠",
            "",
            "Сыграй с другом на баллы",
        ]
        return "\n".join(lines)


    def _server_duels_menu_text(duels: list[dict], user_id: int) -> str:
        uid = int(user_id)
        try:
            bal = int(db.get_balance(uid) or 0)
        except Exception:
            bal = 0

        lines: list[str] = [
            "⚔ СЕРВЕР ДУЭЛЕЙ",
            "",
            "Выберите дуэль, чтобы играть на баллы",
            f"💰 Баланс: {_fmt_points_ui(int(bal))}",
            "",
        ]
        if not duels:
            lines.append("Нет результатов по выбранным фильтрам.")
        else:
            lines.append("Доступные дуэли:")
        return "\n".join(lines)


    def _server_duels_get_filtered_page(uid: int) -> tuple[list[dict], int, int]:
        s = session(int(uid))
        games = {str(g) for g in (s.server_duels_games or set())}
        games = {g for g in games if g in {"dice", "rps", "ttt"}}
        stakes = {int(x) for x in (s.server_duels_stakes or set()) if int(x) > 0}

        all_duels = _decorate_server_duels_for_view(db.list_open_public_duels(limit=200))
        filtered: list[dict] = []
        for d in all_duels:
            gt = str(d.get("game_type") or "")
            stake = int(d.get("stake") or 0)
            if games and gt not in games:
                continue
            if stakes and stake not in stakes:
                continue
            filtered.append(d)

        page_size = 10
        total = len(filtered)
        pages = max(1, (total + page_size - 1) // page_size)
        page = int(getattr(s, "server_duels_page", 0) or 0)
        if page < 0:
            page = 0
        if page >= pages:
            page = pages - 1
        s.server_duels_page = int(page)

        start = page * page_size
        return filtered[start : start + page_size], int(pages), int(page)


    def _render_server_duels_panel(*, chat_id: int, message_id: int, uid: int) -> None:
        s = session(int(uid))
        if not getattr(s, "server_duels_games", None):
            s.server_duels_games = {"dice", "rps", "ttt"}
        if not getattr(s, "server_duels_stakes", None):
            s.server_duels_stakes = {10, 100, 1000, 2500, 5000, 10000}
        duels, pages, page = _server_duels_get_filtered_page(int(uid))
        _safe_edit_message_text(
            bot,
            _server_duels_menu_text(duels, int(uid)),
            chat_id=int(chat_id),
            message_id=int(message_id),
            reply_markup=server_duels_list_kb(
                duels,
                current_user_id=int(uid),
                enabled_games=set(getattr(s, "server_duels_games", {"dice", "rps", "ttt"})),
                enabled_stakes=set(int(x) for x in getattr(s, "server_duels_stakes", {10, 100, 1000, 2500, 5000, 10000})),
                page=int(page),
                pages=int(pages),
            ),
        )


    def _find_own_open_duel(duels: list[dict], user_id: int) -> dict | None:
        try:
            uid_int = int(user_id)
        except Exception:
            return None
        for d in duels:
            try:
                creator_id = int(d.get("creator_id") or 0)
                is_bot = int(d.get("is_bot") or 0)
                status = str(d.get("status") or "waiting")
            except Exception:
                continue
            if creator_id == uid_int and is_bot == 0 and status == "waiting":
                return d
        return None


    def _decorate_server_duels_for_view(duels: list[dict]) -> list[dict]:
        """Добавляет к дуэлям человекочитаемый label без ранга/MMR."""
        out: list[dict] = []
        for d in duels:
            d_local = dict(d)
            try:
                creator_id = int(d_local.get("creator_id") or 0)
            except Exception:
                creator_id = 0
            try:
                is_bot = int(d_local.get("is_bot") or 0)
            except Exception:
                is_bot = 0
            try:
                stake = int(d_local.get("stake") or 0)
            except Exception:
                stake = 0
            gt = str(d_local.get("game_type") or "")
            if gt == "dice":
                type_txt = "🎲 Кубики"
            elif gt == "rps":
                type_txt = "✊✋✌ КНБ"
            else:
                type_txt = "❌⭕ Крестики-нолики"

            label = f"{type_txt} · {stake} · Ожидает соперника"

            d_local["label"] = label
            out.append(d_local)
        return out


    def _ttt_kb(
        duel_id: int,
        board: str,
        *,
        viewer_id: int | None = None,
        turn_id: int | None = None,
        finished: bool = False,
        disabled: bool = False,
    ) -> InlineKeyboardMarkup:
        """3×3 inline board.

        If viewer_id/turn_id are provided, only the current player gets clickable empty cells.
        """
        b = str(board or ".........")
        if len(b) != 9:
            b = "........."
        if finished:
            disabled = True
        if viewer_id is not None and turn_id is not None and int(viewer_id) != int(turn_id):
            disabled = True
        kb = InlineKeyboardMarkup()
        for r in range(3):
            row_btns: list[InlineKeyboardButton] = []
            for c in range(3):
                i = r * 3 + c
                ch = b[i]
                if ch == ".":
                    txt = "·"
                    cb = "noop" if disabled else f"duel:ttt:move:{int(duel_id)}:{int(i)}"
                else:
                    txt = ch
                    cb = "noop"
                row_btns.append(InlineKeyboardButton(text=txt, callback_data=cb))
            kb.row(row_btns[0], row_btns[1], row_btns[2])
        return kb


    def _ttt_text(*, duel_id: int, stake: int, state: dict, viewer_id: int, creator_id: int, opponent_id: int) -> str:
        board = str(state.get("board") or ".........")
        turn = int(state.get("turn") or creator_id)
        sym = state.get("sym") if isinstance(state.get("sym"), dict) else {}
        my_sym = str(sym.get(str(int(viewer_id))) or ("❌" if int(viewer_id) == int(creator_id) else "⭕"))
        enemy_id = opponent_id if int(viewer_id) == int(creator_id) else creator_id
        enemy_sym = str(sym.get(str(int(enemy_id))) or ("⭕" if my_sym == "❌" else "❌"))
        turn_line = "Ваш ход." if int(turn) == int(viewer_id) else "Ход соперника."
        return (
            "Крестики-нолики\n\n"
            f"💰 Ставка: {_fmt_points_ui(int(stake))} баллов\n"
            f"Вы: {my_sym}\nСоперник: {enemy_sym}\n\n"
            f"{turn_line}"
        )


    def _ttt_start_duel(duel_id: int, *, creator_id: int, opponent_id: int, stake: int) -> None:
        # Send initial board messages and persist message ids in DB.
        state = {"board": ".........", "turn": int(creator_id), "sym": {str(int(creator_id)): "❌", str(int(opponent_id)): "⭕"}}

        c_msg_id = 0
        o_msg_id = 0
        try:
            kb_c = _ttt_kb(int(duel_id), state["board"], viewer_id=int(creator_id), turn_id=int(creator_id), finished=False)
            m1 = bot.send_message(
                int(creator_id),
                _ttt_text(duel_id=int(duel_id), stake=int(stake), state=state, viewer_id=int(creator_id), creator_id=int(creator_id), opponent_id=int(opponent_id)),
                reply_markup=kb_c,
            )
            c_msg_id = int(getattr(m1, "message_id", 0) or 0)
        except Exception:
            c_msg_id = 0
        try:
            kb_o = _ttt_kb(int(duel_id), state["board"], viewer_id=int(opponent_id), turn_id=int(creator_id), finished=False)
            m2 = bot.send_message(
                int(opponent_id),
                _ttt_text(duel_id=int(duel_id), stake=int(stake), state=state, viewer_id=int(opponent_id), creator_id=int(creator_id), opponent_id=int(opponent_id)),
                reply_markup=kb_o,
            )
            o_msg_id = int(getattr(m2, "message_id", 0) or 0)
        except Exception:
            o_msg_id = 0

        try:
            db.duel_ttt_init(
                int(duel_id),
                creator_id=int(creator_id),
                opponent_id=int(opponent_id),
                creator_msg_id=int(c_msg_id),
                opponent_msg_id=int(o_msg_id),
            )
        except Exception:
            pass

    def _ttt_result_kb(base_duel_id: int) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data=f"duel:ttt:again:{int(base_duel_id)}"))
        kb.add(InlineKeyboardButton(text="⚔ Дуэль", callback_data="duel:menu"))
        return kb

    def _ttt_try_update_board_message(*, duel_id: int, stake: int, state: dict, viewer_id: int, creator_id: int, opponent_id: int) -> None:
        # Update last board message for a specific player (edit if possible, else send a new one).
        turn_id = int(state.get("turn") or creator_id)
        finished = False
        try:
            duel_row = db.get_duel_by_id(int(duel_id)) or {}
            finished = str(duel_row.get("status") or "") == "finished"
        except Exception:
            finished = False

        msg_map = state.get("msg") if isinstance(state.get("msg"), dict) else {}
        msg_id = 0
        try:
            msg_id = int(msg_map.get(str(int(viewer_id))) or 0)
        except Exception:
            msg_id = 0

        text = _ttt_text(
            duel_id=int(duel_id),
            stake=int(stake),
            state=state,
            viewer_id=int(viewer_id),
            creator_id=int(creator_id),
            opponent_id=int(opponent_id),
        )
        kb = _ttt_kb(int(duel_id), str(state.get("board") or "........."), viewer_id=int(viewer_id), turn_id=int(turn_id), finished=bool(finished))

        if msg_id > 0:
            try:
                bot.edit_message_text(text, chat_id=int(viewer_id), message_id=int(msg_id), reply_markup=kb)
                return
            except Exception:
                pass

        try:
            msg = bot.send_message(int(viewer_id), text, reply_markup=kb)
            try:
                db.duel_ttt_set_msg(int(duel_id), user_id=int(viewer_id), message_id=int(getattr(msg, "message_id", 0) or 0))
            except Exception:
                pass
        except Exception:
            pass

    def _duel2_stake_text(game_type: str) -> str:
        if game_type == "dice":
            return "🎲 Дуэль — Кости\n\nВыберите ставку:"
        return "✊✋✌ Дуэль — КНБ\n\nВыберите ставку:"


    def _duel_commission_payout(stake: int) -> int:
        # Два игрока по stake, комиссия DUEL_COMMISSION_PCT% от банка
        bank = 2 * int(stake)
        payout = int(bank * (100 - DUEL_COMMISSION_PCT) / 100)
        return max(0, payout)

    def _duel_commission_payout_with_vip(stake: int, creator_id: int, opponent_id: int | None) -> int:
        # Halve commission if any player has VIP active
        bank = 2 * int(stake)
        now_ts = int(time.time())
        try:
            c_vip_until = int(db.get_user_field(creator_id, "vip_until") or 0)
        except Exception:
            c_vip_until = 0
        try:
            o_vip_until = int(db.get_user_field(opponent_id, "vip_until") or 0) if opponent_id is not None else 0
        except Exception:
            o_vip_until = 0
        vip_active = (c_vip_until > now_ts) or (o_vip_until > now_ts)
        commission_pct = DUEL_COMMISSION_PCT // 2 if vip_active else DUEL_COMMISSION_PCT
        payout = int(bank * (100 - commission_pct) / 100)
        return max(0, payout)


    def _duel_rank_from_mmr(mmr: int) -> str:
        mmr = int(mmr)
        if mmr < 1200:
            return "BRONZE"
        if mmr < 1600:
            return "SILVER"
        if mmr < 2100:
            return "GOLD"
        return "LEGEND"


    def _duel_mmr_delta(win: bool, self_mmr: int, enemy_mmr: int, streak: int) -> int:
        # Базовая формула из спека
        if win:
            base = 25
            streak_bonus = min(10, int(streak) * 2)
        else:
            base = -20
            streak_bonus = 0

        diff = int(enemy_mmr) - int(self_mmr)
        skill_bonus = max(-10, min(10, diff // 100))

        return int(base + skill_bonus + streak_bonus)


    def _send_duel_summary_feedback(duel_id: int) -> None:
        """Полный feedback после дуэли: результат, MMR, серия, ранг, финансы.

        Работает только для дуэлей между двумя игроками (creator/opponent).
        """
        duel = db.get_duel_by_id(int(duel_id))
        if not duel:
            return
        creator_id = int(duel.get("creator_id") or 0)
        opponent_id = duel.get("opponent_id")
        if not opponent_id:
            return
        opponent_id = int(opponent_id)
        stake = int(duel.get("stake") or 0)
        if stake <= 0:
            return

        winner_id = duel.get("winner_id")
        game_type = str(duel.get("game_type") or "")
        if game_type == "dice":
            game_label = "🎲 Кости"
        elif game_type == "rps":
            game_label = "✊✋✌ КНБ"
        else:
            game_label = "❌⭕ Крестики-нолики"

        # Только дуэли с двумя реальными участниками
        if creator_id <= 0 or opponent_id <= 0:
            return

        user_ids = (creator_id, opponent_id)

        # Базовые статы до матча
        base: dict[int, dict] = {}
        for uid_local in user_ids:
            try:
                mmr = int(db.get_user_field(uid_local, "duel_mmr") or 1000)
            except Exception:
                mmr = 1000
            def _gf(field: str, default: int = 0) -> int:
                try:
                    return int(db.get_user_field(uid_local, field) or default)
                except Exception:
                    return default

            games = _gf("duel_games")
            wins = _gf("duel_wins")
            losses = _gf("duel_losses")
            streak = _gf("duel_streak")
            best_streak = _gf("duel_best_streak")
            try:
                rank_val = db.get_user_field(uid_local, "duel_rank") or _duel_rank_from_mmr(mmr)
            except Exception:
                rank_val = _duel_rank_from_mmr(mmr)
            try:
                vip_until = int(db.get_user_field(uid_local, "vip_until") or 0)
            except Exception:
                vip_until = 0

            base[uid_local] = {
                "mmr": mmr,
                "games": games,
                "wins": wins,
                "losses": losses,
                "streak": streak,
                "best_streak": best_streak,
                "rank": str(rank_val),
                "vip_until": vip_until,
            }

        is_rematch = int(duel.get("is_rematch") or 0) == 1

        # Анти-абуз: слишком частые дуэли с одним соперником
        try:
            recent_count = db.count_recent_duels_between(creator_id, opponent_id, window_seconds=3600)
        except Exception:
            recent_count = 0
        mmr_allowed = winner_id is not None and stake >= 100 and recent_count < 3

        # Для серии: не растёт на минимальной ставке и в реваншах
        GLOBAL_MIN_STAKE_FOR_STREAK = 50

        # Финансы: банк, комиссия, VIP
        bank = 2 * stake
        base_payout = _duel_commission_payout(stake)
        vip_payout = _duel_commission_payout_with_vip(stake, creator_id, opponent_id)
        commission_base = max(0, bank - base_payout)
        commission_actual = max(0, bank - vip_payout)

        updates: dict[int, dict] = {}
        for uid_local in user_ids:
            st = base[uid_local]
            other_id = opponent_id if uid_local == creator_id else creator_id
            enemy = base[other_id]
            win = winner_id is not None and int(winner_id) == int(uid_local)
            lose = winner_id is not None and not win
            tie = winner_id is None

            delta = 0
            new_mmr = st["mmr"]
            if mmr_allowed and (win or lose):
                delta = _duel_mmr_delta(win, st["mmr"], enemy["mmr"], st["streak"] if win else 0)
                new_mmr = max(0, st["mmr"] + delta)

            # Серия побед
            new_streak = st["streak"]
            if tie:
                pass
            elif win:
                if not is_rematch and stake > GLOBAL_MIN_STAKE_FOR_STREAK:
                    new_streak = st["streak"] + 1
            else:
                new_streak = 0

            new_best = max(st["best_streak"], new_streak)
            new_games = st["games"] + 1
            new_wins = st["wins"] + (1 if win else 0)
            new_losses = st["losses"] + (1 if lose else 0)
            new_rank = _duel_rank_from_mmr(new_mmr)

            updates[uid_local] = {
                "mmr_old": st["mmr"],
                "mmr_new": new_mmr,
                "mmr_delta": delta if mmr_allowed else 0,
                "games": new_games,
                "wins": new_wins,
                "losses": new_losses,
                "streak": new_streak,
                "best_streak": new_best,
                "rank_old": st["rank"],
                "rank_new": new_rank,
            }

        # Применяем обновления
        for uid_local, up in updates.items():
            try:
                db.set_user_field(uid_local, "duel_mmr", up["mmr_new"])
                db.set_user_field(uid_local, "duel_games", up["games"])
                db.set_user_field(uid_local, "duel_wins", up["wins"])
                db.set_user_field(uid_local, "duel_losses", up["losses"])
                db.set_user_field(uid_local, "duel_streak", up["streak"])
                db.set_user_field(uid_local, "duel_best_streak", up["best_streak"])
                db.set_user_field(uid_local, "duel_rank", up["rank_new"])
            except Exception:
                pass

        # Отправляем сообщения каждому игроку (без текста про рейтинг/ранг)
        now_ts = int(time.time())
        for uid_local in user_ids:
            up = updates[uid_local]
            st = base[uid_local]
            other_id = opponent_id if uid_local == creator_id else creator_id
            win = winner_id is not None and int(winner_id) == int(uid_local)
            lose = winner_id is not None and not win
            tie = winner_id is None

            title = "🤝 НИЧЬЯ В ДУЭЛИ" if tie else ("🎉 ПОБЕДА В ДУЭЛИ!" if win else "❌ ПОРАЖЕНИЕ В ДУЭЛИ")

            # Детали результата (броски/ходы) с точки зрения конкретного игрока
            result_line = ""
            if game_type == "dice":
                c_roll = duel.get("creator_roll")
                o_roll = duel.get("opponent_roll")
                if c_roll is not None and o_roll is not None:
                    if uid_local == creator_id:
                        my_roll = int(c_roll)
                        enemy_roll = int(o_roll)
                    else:
                        my_roll = int(o_roll)
                        enemy_roll = int(c_roll)
                    result_line = f"🎲 Броски: вы {my_roll} — противник {enemy_roll}"
            elif game_type == "rps":
                c_choice = duel.get("creator_choice")
                o_choice = duel.get("opponent_choice")
                if c_choice and o_choice:
                    choice_map = {"rock": "✊ Камень", "paper": "✋ Бумага", "scissors": "✌ Ножницы"}
                    if uid_local == creator_id:
                        my_txt = choice_map.get(c_choice, str(c_choice))
                        enemy_txt = choice_map.get(o_choice, str(o_choice))
                    else:
                        my_txt = choice_map.get(o_choice, str(o_choice))
                        enemy_txt = choice_map.get(c_choice, str(c_choice))
                    result_line = f"✊✋✌ Ходы: вы — {my_txt}, противник — {enemy_txt}"

            # Финансы
            if tie:
                finance = "💸 Финансы:\nСтавка возвращена обоим игрокам."
            else:
                # Проверяем VIP для уменьшенной комиссии
                vip_until = int(st.get("vip_until") or 0)
                vip_active = vip_until > now_ts
                base_comm = commission_base
                actual_comm = commission_actual
                commission_line = f"🧾 Комиссия: -{actual_comm}"
                if actual_comm < base_comm and vip_active:
                    commission_line += " (VIP)"

                if win:
                    gain = vip_payout
                    finance = (
                        "💸 Финансы:\n"
                        f"🏦 Банк: {bank}\n"
                        f"{commission_line}\n"
                        f"💰 Получено: +{gain} баллов"
                    )
                else:
                    finance = (
                        "💸 Потеря:\n"
                        f"💰 Потеря: -{stake} баллов"
                    )

            if win:
                tail = "\n\n🔁 Хотите реванш?"
            elif lose:
                tail = "\n\n💢 Возьмёте реванш?"
            else:
                tail = "\n\n🔁 Сыграем ещё раз?"

            header_parts: list[str] = [f"{title}", "", f"⚔ Игра: {game_label}"]
            if result_line:
                header_parts.append(result_line)
            header_parts.append(f"💰 Ставка: {stake} баллов")
            header_text = "\n".join(header_parts) + "\n\n"

            text = header_text + f"{finance}" + f"{tail}"

            try:
                bot.send_message(uid_local, text, reply_markup=duel_rematch_offer_kb(int(duel["duel_id"])))
            except Exception:
                pass


    def _format_level_leaderboard(uid: int) -> tuple[str, telebot.types.InlineKeyboardMarkup]:
        top = db.get_leaderboard_by_level(limit=5)
        me = db.get_user_rank_position_by_level(uid)

        def _badges_for(user_id: int) -> str:
            info = db.get_user_level_info(int(user_id)) or {}
            badges: list[str] = []
            if info.get("vip_active"):
                badges.append("👑")
            if info.get("custom_title"):
                badges.append("🏷")
            if info.get("emoji_pack"):
                badges.append("😎")
            return (" " + " ".join(badges)) if badges else ""

        km = InlineKeyboardMarkup()
        for row in top:
            user_id = int(row["user_id"])
            uname = ("@" + row["username"]) if row.get("username") else f"ID{user_id}"
            txt = f"#{int(row['pos'])} {uname}{_badges_for(user_id)} ⭐{int(row.get('level') or 0)}"
            km.add(InlineKeyboardButton(text=txt, callback_data=f"rating:user:level:{user_id}"))

        km.row(
            InlineKeyboardButton(text="◀️ Категории", callback_data="rating:menu"),
            InlineKeyboardButton(text="⬅ Профиль", callback_data="rating:back"),
        )

        lines: list[str] = ["🏆 <b>ТОП-5 по уровню</b>"]
        if me:
            lines.append("")
            lines.append(f"📍 <b>Твоё место:</b> #{me['position']}")
            lines.append(f"⭐ Уровень: {me['level']} ({me['rank']}) · {me['experience']} XP")
        return "\n".join(lines), km


    def _format_balance_leaderboard(uid: int) -> tuple[str, telebot.types.InlineKeyboardMarkup]:
        top = db.get_leaderboard_by_balance(limit=5)
        me = db.get_user_rank_position_by_balance(uid)

        def _badges_for(user_id: int) -> str:
            info = db.get_user_level_info(int(user_id)) or {}
            badges: list[str] = []
            if info.get("vip_active"):
                badges.append("👑")
            if info.get("custom_title"):
                badges.append("🏷")
            if info.get("emoji_pack"):
                badges.append("😎")
            return (" " + " ".join(badges)) if badges else ""

        km = InlineKeyboardMarkup()
        for row in top:
            user_id = int(row["user_id"])
            uname = ("@" + row["username"]) if row.get("username") else f"ID{user_id}"
            bal = int(row.get("balance_points") or 0)
            txt = f"#{int(row['pos'])} {uname}{_badges_for(user_id)} 💰{_fmt_int(bal)}"
            km.add(InlineKeyboardButton(text=txt, callback_data=f"rating:user:balance:{user_id}"))

        km.row(
            InlineKeyboardButton(text="◀️ Категории", callback_data="rating:menu"),
            InlineKeyboardButton(text="⬅ Профиль", callback_data="rating:back"),
        )

        lines: list[str] = ["💰 <b>ТОП-5 по балансу</b>"]
        if me:
            lines.append("")
            lines.append(f"📍 <b>Твоё место:</b> #{me['position']}")
            lines.append(f"💰 Баланс: {_fmt_int(int(me.get('balance_points') or 0))} баллов")
        return "\n".join(lines), km


    def _format_duel_leaderboard(uid: int) -> tuple[str, telebot.types.InlineKeyboardMarkup]:
        top = db.get_leaderboard_by_duel_mmr(limit=5)
        me = db.get_user_rank_position_by_duel_mmr(uid)

        def _badges_for(user_id: int) -> str:
            info = db.get_user_level_info(int(user_id)) or {}
            badges: list[str] = []
            if info.get("vip_active"):
                badges.append("👑")
            if info.get("custom_title"):
                badges.append("🏷")
            if info.get("emoji_pack"):
                badges.append("😎")
            return (" " + " ".join(badges)) if badges else ""

        km = InlineKeyboardMarkup()
        for row in top:
            user_id = int(row["user_id"])
            uname = ("@" + row["username"]) if row.get("username") else f"ID{user_id}"
            mmr = int(row.get("mmr") or 1000)
            txt = f"#{int(row['pos'])} {uname}{_badges_for(user_id)} ⚔{mmr}"
            km.add(InlineKeyboardButton(text=txt, callback_data=f"rating:user:duels:{user_id}"))

        km.row(
            InlineKeyboardButton(text="◀️ Категории", callback_data="rating:menu"),
            InlineKeyboardButton(text="⬅ Профиль", callback_data="rating:back"),
        )

        lines: list[str] = ["⚔️ <b>ТОП-5 по дуэлям (MMR)</b>"]
        if me:
            lines.append("")
            lines.append(f"📍 <b>Твоё место:</b> #{me['position']}")
            lines.append(f"⚔️ MMR: {int(me.get('mmr') or 1000)}")
        return "\n".join(lines), km


    def _format_referrals_leaderboard(uid: int) -> tuple[str, telebot.types.InlineKeyboardMarkup]:
        top = db.get_leaderboard_by_referrals(limit=5)
        me = db.get_user_rank_position_by_referrals(uid)

        def _badges_for(user_id: int) -> str:
            info = db.get_user_level_info(int(user_id)) or {}
            badges: list[str] = []
            if info.get("vip_active"):
                badges.append("👑")
            if info.get("custom_title"):
                badges.append("🏷")
            if info.get("emoji_pack"):
                badges.append("😎")
            return (" " + " ".join(badges)) if badges else ""

        km = InlineKeyboardMarkup()
        for row in top:
            user_id = int(row["user_id"])
            uname = ("@" + row["username"]) if row.get("username") else f"ID{user_id}"
            refs = int(row.get("referrals_count") or 0)
            txt = f"#{int(row['pos'])} {uname}{_badges_for(user_id)} 👥{refs}"
            km.add(InlineKeyboardButton(text=txt, callback_data=f"rating:user:referrals:{user_id}"))

        km.row(
            InlineKeyboardButton(text="◀️ Категории", callback_data="rating:menu"),
            InlineKeyboardButton(text="⬅ Профиль", callback_data="rating:back"),
        )

        lines: list[str] = ["👥 <b>ТОП-5 по рефералам</b>"]
        if me:
            lines.append("")
            lines.append(f"📍 <b>Твоё место:</b> #{me['position']}")
            lines.append(f"👥 Приглашено: {int(me.get('referrals_count') or 0)}")
        return "\n".join(lines), km


    def _ru_days(n: int) -> str:
        n = int(n)
        n10 = n % 10
        n100 = n % 100
        if n10 == 1 and n100 != 11:
            return "день"
        if 2 <= n10 <= 4 and not (12 <= n100 <= 14):
            return "дня"
        return "дней"


    def _faq_kb() -> InlineKeyboardMarkup:
        km = InlineKeyboardMarkup()
        km.add(InlineKeyboardButton("💰 Как заработать?", callback_data="faq:earn"))
        km.add(InlineKeyboardButton("💸 Как вывести деньги?", callback_data="faq:withdraw"))
        km.add(InlineKeyboardButton("⏰ Сколько ждать проверки?", callback_data="faq:review"))
        km.add(InlineKeyboardButton("🎮 Как работают игры?", callback_data="faq:games"))
        km.add(InlineKeyboardButton("👥 Реферальная система", callback_data="faq:referral"))
        km.add(InlineKeyboardButton("🎁 Что даёт VIP?", callback_data="faq:vip"))
        km.add(InlineKeyboardButton("❓ Поддержка", callback_data="faq:support"))
        return km


    def _faq_main_text() -> str:
        return "❓ <b>Часто задаваемые вопросы</b>\n\nВыбери интересующую тему:"


    def _faq_answer(topic: str) -> str:
        topic = str(topic)
        referral_bonus = int(REFERRAL_BONUS_POINTS)
        farm_cooldown = 90
        farm_limit = 300

        answers: dict[str, str] = {
            "earn": (
                "💰 <b>Как заработать баллы?</b>\n\n"
                "<b>1. Выполняй задания</b> (разные награды)\n"
                "→ Меню: \"📋 Задания\"\n\n"
                "<b>2. Фарм баллов</b> (бесплатно)\n"
                f"• Кнопка доступна примерно каждые {farm_cooldown} сек\n"
                f"• Дневной лимит: {farm_limit} баллов\n"
                "• Есть бустеры x2/x3 и бонусы за серии\n"
                "→ Меню: \"✨ Фарм баллов\"\n\n"
                "<b>3. Приглашай друзей</b>\n"
                f"• Бонус пригласившему: +{_fmt_int(int(referral_bonus))} баллов\n"
                "→ Меню: \"👥 Пригласить друга\"\n\n"
                "<b>4. Играй в мини-игры</b>\n"
                "→ Меню: \"🎮 Мини игры\"\n\n"
                "<b>5. Достижения</b>\n"
                "→ Команда: /achievements"
            ),
            "withdraw": (
                "💸 <b>Как вывести деньги?</b>\n\n"
                "<b>Минимум:</b> 3000 баллов = 30₽\n\n"
                "<b>Как вывести:</b>\n"
                "1️⃣ Меню → \"💼 Профиль\"\n"
                "2️⃣ Нажми \"Вывести\"\n"
                "3️⃣ Выбери сумму и банк\n"
                "4️⃣ Введи реквизиты и подтверди\n\n"
                "⚠️ <b>Важно:</b> Проверяй реквизиты перед подтверждением."
            ),
            "review": (
                "⏰ <b>Сколько ждать проверки?</b>\n\n"
                "• Обычно: до 24 часов\n"
                "• Иногда быстрее (несколько часов)\n\n"
                "❌ Частые причины отказа:\n"
                "• Скрин нечёткий\n"
                "• Не видно выполнения условий\n"
                "• Задание выполнено не полностью"
            ),
            "games": (
                "🎮 <b>Как работают мини-игры?</b>\n\n"
                "<b>💣 Mines:</b> открывай клетки, избегая мин, забирай выигрыш вовремя.\n\n"
                "<b>🎡 Wheel:</b> ставка → множитель → выигрыш/проигрыш.\n\n"
                "<b>🎲 Dice:</b> бросок кубика против бота.\n\n"
                "<b>⚔️ Дуэли:</b> PvP (КНБ или кости) со ставками и MMR."
            ),
            "referral": (
                "👥 <b>Реферальная система</b>\n\n"
                "1️⃣ Получи ссылку: Меню → \"👥 Пригласить друга\"\n"
                "2️⃣ Отправь другу\n"
                "3️⃣ Друг нажимает ссылку и запускает бота\n\n"
                f"🎁 Бонус: +{_fmt_int(int(referral_bonus))} баллов пригласившему (если правилами разрешено)."
            ),
            "vip": (
                "🎁 <b>VIP-статус</b>\n\n"
                "• Приоритетная проверка заданий\n"
                "• Приоритетная обработка выводов\n"
                "• Дополнительные косметические возможности\n\n"
                "VIP покупается в магазине: \"🛒 Магазин\" → VIP"
            ),
            "support": (
                "❓ <b>Поддержка</b>\n\n"
                "Меню → \"❓ Поддержка\"\n"
                "Опиши проблему и приложи скрин (если нужно).\n\n"
                "Полезные команды:\n"
                "/start — перезапуск\n"
                "/stats — статистика\n"
                "/help — FAQ"
            ),
        }
        return answers.get(topic, "Информация не найдена.")

    @bot.inline_handler(func=lambda q: str(q.query or "").startswith("duel_"))
    def inline_duel_invite(query: InlineQuery) -> None:
        q = str(query.query or "")
        code = q[len("duel_") :]
        duel = db.get_duel_by_code(code)
        if not duel:
            try:
                bot.answer_inline_query(query.id, results=[], cache_time=1, is_personal=True)
            except Exception:
                pass
            return
        # Build invite card
        stake = int(duel.get("stake") or 0)
        gt = str(duel.get("game_type") or "")
        inviter_uname = ("@" + str(query.from_user.username)) if query.from_user.username else f"ID {int(query.from_user.id)}"
        title = "⚔️ Вызов на дуэль"
        if gt == "dice":
            game_txt = "🎲 Кости"
        elif gt == "ttt":
            game_txt = "❌⭕ Крестики-нолики"
        else:
            game_txt = "✊✋✌ КНБ"
        desc = f"Игрок: {inviter_uname}\nИгра: {game_txt}\nСтавка: {stake} баллов\nПринять вызов?"
        btns = InlineKeyboardMarkup()
        btns.row(
            InlineKeyboardButton(text="✅ Принять", callback_data=f"duel2:accept:{int(duel['duel_id'])}"),
            InlineKeyboardButton(text="❌ Отказаться", callback_data=f"duel2:decline:{int(duel['duel_id'])}"),
        )
        content = InputTextMessageContent(f"⚔️ Вас вызывают на дуэль!\n\n{desc}")
        res = InlineQueryResultArticle(id=str(int(duel["duel_id"])), title=title, description=desc, input_message_content=content, reply_markup=btns)
        try:
            bot.answer_inline_query(query.id, results=[res], cache_time=1, is_personal=True)
        except Exception:
            pass

    def _send_withdraw_menu(chat_id: int, uid: int) -> None:
        reset_user_flow(uid)
        balance = db.get_balance(uid)
        can_30 = balance >= WITHDRAW_OPTIONS_RUB[0] * POINTS_PER_RUB
        can_50 = balance >= WITHDRAW_OPTIONS_RUB[1] * POINTS_PER_RUB
        bot.send_message(
            chat_id,
            "Минимум для вывода: 3000 баллов (30₽)",
            reply_markup=withdraw_menu_kb(can_30, can_50),
        )

    def _farm_build_screen_text(uid: int) -> tuple[str, dict]:
        st = db.get_farm_state(uid) or {}
        now_ts = int(time.time())
        last_farm = int(st.get("last_farm_time") or 0)
        elapsed = now_ts - last_farm
        wait = max(0, FARM_COOLDOWN_SECONDS - elapsed) if last_farm else 0
        can_claim = (last_farm == 0) or (elapsed >= FARM_COOLDOWN_SECONDS)

        booster_until = int(st.get("farm_booster_until") or 0)
        booster_mult = int(st.get("farm_booster_mult") or 1)
        booster_active = booster_until > now_ts

        daily_used = int(st.get("farm_daily_points") or 0)
        daily_date = st.get("farm_daily_date")
        today = str(dt.datetime.utcfromtimestamp(now_ts).date())
        if not daily_date or str(daily_date) != today:
            daily_used = 0
        limit_reached = daily_used >= FARM_DAILY_LIMIT

        streak_days = int(st.get("farm_streak_days") or 0)
        click_streak = int(st.get("farm_click_streak") or 0)

        # Прогноз награды (без учёта рандомной «Удачи»)
        effective_mult = booster_mult if booster_active else 1
        next_click_streak = (click_streak + 1) if not limit_reached else click_streak
        click_bonus_preview = min(6, (next_click_streak // 3) * 2)
        reward_preview = (FARM_REWARD + click_bonus_preview) * max(1, int(effective_mult))

        # Бонус за серию дней «завтра» (если завтра будет фарм)
        bonus_tomorrow = int(FARM_STREAK_BONUSES.get(int(streak_days) + 1, 0) or 0)

        # Прогресс-бар по дневному лимиту (10 сегментов)
        if FARM_DAILY_LIMIT > 0:
            filled = int(min(FARM_DAILY_LIMIT, daily_used) * 10 / FARM_DAILY_LIMIT)
        else:
            filled = 0
        bar = "▓" * filled + "░" * (10 - filled)

        if limit_reached:
            txt = (
                "✨ Фарм баллов\n\n"
                "Нажимай кнопку и получай баллы бесплатно.\n\n"
                "🏁 Лимит на сегодня исчерпан\n"
                "🔥 Серия сохранена\n"
                f"🎁 Завтра лимит: {FARM_DAILY_LIMIT}\n\n"
                "⬇ Используй кнопку ниже"
            )
            reward_preview = 0
        else:
            txt = (
                "✨ Фарм баллов\n\n"
                "Нажимай кнопку и получай баллы бесплатно.\n\n"
                f"💰 Награда: +{reward_preview}\n"
                f"🔥 Серия дней: {max(0, streak_days)}\n"
                f"🏁 Сегодня: {daily_used} / {FARM_DAILY_LIMIT}\n"
                f"До лимита осталось: {max(0, FARM_DAILY_LIMIT - daily_used)}\n"
                f"{bar}\n\n"
                f"🎁 Завтра бонус: +{bonus_tomorrow}\n\n"
                "⬇ Используй кнопку ниже"
            )
        meta = {
            "can_claim": bool(can_claim) and (not limit_reached),
            "wait_seconds": int(wait),
            "limit_reached": bool(limit_reached),
            "booster_active": bool(booster_active),
            "daily_used": int(daily_used),
            "reward_preview": int(reward_preview),
        }
        return txt, meta

    def _farm_send_or_edit(call: CallbackQuery | None, chat_id: int, message_id: int | None, uid: int) -> None:
        text, meta = _farm_build_screen_text(uid)
        kb = farm_points_kb(
            can_claim=bool(meta["can_claim"]),
            wait_seconds=int(meta["wait_seconds"]),
            limit_reached=bool(meta["limit_reached"]),
            booster_active=bool(meta["booster_active"]),
            reward_preview=int(meta.get("reward_preview") or 0),
        )
        if call is not None and message_id is not None:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=kb)
        else:
            bot.send_message(chat_id, text, reply_markup=kb)

    def _notify_admin_once(text: str) -> None:
        nonlocal warned_admin_channel_access
        if warned_admin_channel_access:
            return
        warned_admin_channel_access = True
        try:
            bot.send_message(settings.admin_id, text)
        except Exception:
            pass

    # --- mini games: mines ---

    MINES_TIMEOUT_SECONDS = 5 * 60
    MINES_REVEAL_DELAY_SECONDS = 1.5
    MINES_CLEANUP_DELAY_SECONDS = 7.0
    MINES_MAX_WIN_MULTIPLIER = 10.0

    MINES_MODES = ("classic", "hardcore", "nobet")
    MINES_MAX_ROUNDS_PER_MINUTE = 4
    MINES_ACTION_COOLDOWN_SECONDS = 0.75

    # Profit caps (net profit = win - bet) for stake modes
    # NOTE: was very low and made large wins look like "no balance increase" (only bet returned).
    # Set high to effectively disable capping.
    MINES_CLASSIC_DAILY_PROFIT_CAP = 1_000_000_000
    MINES_HARDCORE_DAILY_PROFIT_CAP = 1_000_000_000

    # No-bet mode (XP/quests) is implemented as small point rewards (XP == earned points in this bot)
    MINES_NOBET_ATTEMPTS_PER_DAY = 3
    MINES_NOBET_ATTEMPTS_PER_DAY_VIP = 5
    MINES_NOBET_POINTS_PER_SAFE = 10
    MINES_NOBET_CASHOUT_BONUS = 10
    MINES_NOBET_DAILY_POINTS_CAP = 50
    MINES_NOBET_DAILY_XP_CAP = 300

    _mines_last_action_ts: dict[int, float] = {}

    def _mines_action_allowed(user_id: int) -> bool:
        now = time.time()
        last = float(_mines_last_action_ts.get(int(user_id), 0.0) or 0.0)
        if (now - last) < MINES_ACTION_COOLDOWN_SECONDS:
            return False
        _mines_last_action_ts[int(user_id)] = float(now)
        return True

    def _audit_mines(event: str, *, user_id: int, round_id: int | None = None, **details: object) -> None:
        try:
            payload = {
                "ts": int(time.time()),
                "event": str(event),
                "user_id": int(user_id),
                "round_id": (int(round_id) if round_id is not None else None),
                "details": details,
            }
            with open("bot_audit.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    MINES_MAX_DIAMONDS_BY_SIZE = {3: 5, 6: 8}

    MINES_MULTIPLIERS: dict[tuple[int, int], dict[int, float]] = {
        # recommended tables (RTP-style):
        # 3×3 (9), mines 1–2, up to 5 diamonds
        (3, 1): {1: 1.35, 2: 1.85, 3: 2.50, 4: 3.40, 5: 4.80},
        (3, 2): {1: 1.35, 2: 1.85, 3: 2.50, 4: 3.40, 5: 4.80},
        # 6×6 (36), mines 5, up to 8 diamonds
        (6, 5): {1: 1.15, 2: 1.35, 3: 1.60, 4: 1.95, 5: 2.40, 6: 3.00, 7: 3.80, 8: 5.00},
    }

    def _mines_reset(user_id: int, *, preserve_params: bool = False) -> None:
        s = session(user_id)
        s.mines_state = "none"
        s.mines_round_id = None
        if not preserve_params:
            s.mines_size = None
            s.mines_mines = None
            s.mines_bet = None
        s.mines_started_at = None
        s.mines_insurance = False
        s.mines_luck_boost_active = False
        s.mines_opened.clear()
        s.mines_mine_cells.clear()

    def _mines_start_round_from_call(call, uid: int) -> None:
        if db.is_blocked(uid):
            bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
            return
        if not _mines_action_allowed(uid):
            return
        s = session(uid)
        if s.mines_state == "active":
            bot.send_message(call.message.chat.id, "⏳ У вас уже есть активная игра в 💣 Мины.")
            return

        mode = str(getattr(s, "mines_mode", "classic") or "classic")
        if mode in ("hardcore", "nobet"):
            s.mines_size = 3
        if mode == "nobet":
            if not (s.mines_size and s.mines_mines):
                bot.send_message(call.message.chat.id, "Сначала выберите параметры.")
                return
        else:
            if not (s.mines_size and s.mines_mines and s.mines_bet):
                bot.send_message(call.message.chat.id, "Сначала выберите параметры.")
                return

        now_ts = int(time.time())
        if not db.mines_check_and_inc_rate_limit(uid, now_ts=now_ts, max_rounds_per_minute=MINES_MAX_ROUNDS_PER_MINUTE):
            bot.send_message(call.message.chat.id, "⏳ Слишком часто. Подождите немного.")
            return

        size = int(s.mines_size)
        mines_cnt = int(s.mines_mines)
        bet = int(s.mines_bet or 0)

        if not _mines_allowed_size(size):
            bot.send_message(call.message.chat.id, "Параметры некорректны.")
            return
        if mode == "classic" and not _mines_allowed_mines(size, mines_cnt):
            bot.send_message(call.message.chat.id, "Параметры некорректны.")
            return
        if mode == "hardcore" and mines_cnt not in (4, 5):
            bot.send_message(call.message.chat.id, "Параметры некорректны.")
            return
        if mode == "nobet" and mines_cnt not in (2, 3):
            bot.send_message(call.message.chat.id, "Параметры некорректны.")
            return
        if mode == "classic":
            min_bet, max_bet = _bet_limits_for(int(uid))
            if bet < int(min_bet) or bet > int(max_bet):
                bot.send_message(call.message.chat.id, "❌ " + _bet_out_of_range_text(bet=bet, min_bet=min_bet, max_bet=max_bet))
                return
        if mode == "hardcore" and bet not in (100, 250, 500, 1000):
            bot.send_message(call.message.chat.id, "Параметры некорректны.")
            return

        # no-bet: consume energy/attempt
        energy_spent = 0
        if mode == "nobet":
            today = str(dt.datetime.utcfromtimestamp(now_ts).date())
            try:
                vip_active = db.is_vip_active(uid, now_ts=now_ts)
            except Exception:
                vip_active = False
            limit = MINES_NOBET_ATTEMPTS_PER_DAY_VIP if vip_active else MINES_NOBET_ATTEMPTS_PER_DAY
            er = db.mines_consume_energy(uid, today=today, attempts_per_day=limit)
            if not er.get("ok"):
                bot.send_message(call.message.chat.id, "⚡ Попытки на сегодня закончились.")
                return
            energy_spent = int(er.get("spent") or 1)

        # stake modes: luck boost (+ optional global insurance reservation)
        if mode != "nobet":
            total_cost = int(bet)

            # Luck boost: auto-consume one for this game if available
            s.mines_luck_boost_active = bool(db.consume_mines_luck_boost(uid))

            # Insurance is reserved after the round is successfully created.
            s.mines_insurance = False
        else:
            total_cost = 0
            s.mines_luck_boost_active = False
            s.mines_insurance = False

        # Create persistent round (also deducts bet_points atomically for stake modes)
        client_seed = f"tg:{uid}:{call.message.message_id}:{now_ts}"
        tourn_id = getattr(s, "tourn_active_tournament_id", None)
        tourn_match_id = getattr(s, "tourn_active_match_id", None)
        tourn_game_idx = getattr(s, "tourn_active_game_index", None)
        cr = db.create_mines_round(
            uid,
            mode=mode,
            size=size,
            mines=mines_cnt,
            bet_points=(bet if mode != "nobet" else 0),
            extra_cost_points=0,
            energy_spent=energy_spent,
            now_ts=now_ts,
            client_seed=client_seed,
            tournament_id=(int(tourn_id) if tourn_id else None),
            tournament_match_id=(int(tourn_match_id) if tourn_match_id else None),
            tournament_game_index=(int(tourn_game_idx) if tourn_game_idx is not None else None),
        )
        if not cr.get("ok"):
            reason = str(cr.get("reason") or "")
            if reason == "insufficient":
                try:
                    bal_now = int(db.get_balance(uid) or 0)
                except Exception:
                    bal_now = 0
                bot.send_message(
                    call.message.chat.id,
                    f"❌ Недостаточно баллов. Нужно: {_fmt_points_ui(int(total_cost))}. Баланс: {_fmt_points_ui(int(bal_now))}.",
                )
            else:
                bot.send_message(call.message.chat.id, "❌ Не удалось начать раунд. Попробуйте позже.")
            return

        # Prevent accidental linkage of future rounds
        s.tourn_active_tournament_id = None
        s.tourn_active_match_id = None
        s.tourn_active_game_index = None

        round_id = int(cr.get("round_id") or 0)
        rnd = db.get_mines_round(round_id)
        if not rnd:
            bot.send_message(call.message.chat.id, "❌ Не удалось загрузить раунд.")
            return

        mine_cells = set(json.loads(str(rnd.get("mine_cells") or "[]")))
        s.mines_mode = mode
        s.mines_round_id = round_id
        s.mines_mine_cells = set(int(x) for x in mine_cells)
        s.mines_opened.clear()
        s.mines_started_at = float(now_ts)
        s.mines_state = "active"

        # Reserve insurance for this mines round (stake modes only).
        if mode != "nobet":
            s.mines_insurance = bool(_insurance_reserve_for_game(uid))
        else:
            s.mines_insurance = False

        # Weekly tasks progress
        try:
            wk = db.week_key_utc(now_ts)
            db.add_weekly_progress(uid, week_key=wk, code="mines_games", delta=1, now_ts=now_ts)
        except Exception:
            pass

        if mode == "nobet":
            start_text = "💎 Открыто алмазов: 0"
        else:
            start_text = (
                f"💣 МИНЫ {size}x{size}\n"
                f"Открыто: 0\n"
                f"Твоя ставка: {_fmt_points_ui(int(bet))}\n"
                f"👉 Ты можешь забрать {_fmt_points_ui(0)} 💰"
            )
        _safe_edit_message_text(
            bot,
            start_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=mines_field_kb(size=size, opened_cells=set(), show_cashout=True),
        )

        _schedule_game_inactivity(uid, game="mines", chat_id=call.message.chat.id, message_id=call.message.message_id)

        _audit_mines(
            "round_start",
            user_id=uid,
            round_id=round_id,
            mode=mode,
            size=size,
            mines=mines_cnt,
            bet=bet,
            energy_spent=energy_spent,
            insurance=bool(s.mines_insurance),
            luck_boost=bool(s.mines_luck_boost_active),
            fair_hash=str(cr.get("server_seed_hash") or ""),
        )
        return

    def _mines_max_diamonds_mode(size: int, mines: int, *, mode: str) -> int:
        mode = str(mode)
        if mode == "hardcore":
            return 3 if int(size) == 3 else 5
        if mode == "nobet":
            return 3
        return _mines_max_diamonds(int(size), int(mines))

    def _mines_total_cells(size: int) -> int:
        size = int(size)
        return size * size

    def _mines_allowed_size(size: int) -> bool:
        return int(size) in (3, 6)

    def _mines_allowed_mines(size: int, mines: int) -> bool:
        size = int(size)
        mines = int(mines)
        total = _mines_total_cells(size)
        if mines <= 0 or mines >= total:
            return False
        if size == 3:
            return mines in {1, 2, 3, 4, 5}
        if size == 6:
            return mines in {5, 8, 12, 16, 20}
        return False

    def _fmt_money(n: int) -> str:
        try:
            n = int(n)
        except Exception:
            n = 0
        return f"{n:,}".replace(",", " ")

    def _mines_survival_probability(total: int, mines: int, opened_safe: int) -> float:
        remaining_cells = int(total) - int(opened_safe)
        remaining_mines = int(mines)
        if remaining_cells <= 0:
            return 0.0
        safe_remaining = remaining_cells - remaining_mines
        if safe_remaining <= 0:
            return 0.0
        return safe_remaining / remaining_cells

    def _mines_fair_multiplier(total: int, mines: int, opened_safe: int) -> float:
        """Fair multiplier for cashing out after opened_safe safe cells."""
        total = int(total)
        mines = int(mines)
        opened_safe = int(opened_safe)
        safe_total = total - mines
        if opened_safe <= 0:
            return 1.0
        if opened_safe > safe_total:
            opened_safe = safe_total
        p = math.comb(safe_total, opened_safe) / math.comb(total, opened_safe)
        if p <= 0:
            return 0.0
        return 1.0 / p

    def _mines_base_multiplier(size: int, mines: int, opened_safe: int) -> float:
        """Return the base multiplier (from tables or fair calculation) before any adjustments."""
        size = int(size)
        mines = int(mines)
        opened_safe = int(opened_safe)
        if opened_safe <= 0:
            return 1.0

        table = MINES_MULTIPLIERS.get((size, mines))
        if table and opened_safe in table:
            base = float(table[opened_safe])
        else:
            base = float(_mines_fair_multiplier(_mines_total_cells(size), mines, opened_safe))

        if base > MINES_MAX_WIN_MULTIPLIER:
            base = MINES_MAX_WIN_MULTIPLIER
        return base

    def _mines_cashout_amount(bet: int, multiplier: float) -> int:
        bet = int(bet)
        if multiplier <= 0:
            return 0
        try:
            # use Decimal for deterministic arithmetic and floor to avoid float inaccuracy
            raw = Decimal(int(bet)) * Decimal(str(multiplier))
        except Exception:
            try:
                raw = Decimal(int(bet)) * Decimal(float(multiplier))
            except Exception:
                return 0
        if raw <= 0:
            return 0
        # floor to integer (deterministic)
        try:
            return int(raw // 1)
        except Exception:
            return int(raw)

    def _mines_vip_bonus(size: int, mines: int) -> float:
        size = int(size)
        mines = int(mines)
        if size == 6:
            # 6×6: configured bonuses per mine count
            return float({5: 0.30, 8: 0.35, 12: 0.40, 16: 0.45, 20: 0.50}.get(mines, 0.50))
        # 3×3: +0.10 .. +0.50 by mine count
        return float(min(0.50, 0.10 * max(0, mines)))

    def _mines_multiplier(size: int, mines: int, opened_safe: int, vip_active: bool = False) -> float:
        size = int(size)
        mines = int(mines)
        opened_safe = int(opened_safe)
        if opened_safe <= 0:
            return 1.0

        table = MINES_MULTIPLIERS.get((size, mines))
        if table and opened_safe in table:
            base_mult = float(table[opened_safe])
        else:
            # fallback: fair multiplier
            base_mult = float(_mines_fair_multiplier(_mines_total_cells(size), mines, opened_safe))

        # Apply VIP bonus directly to the base multiplier (full multiplier semantics)
        if vip_active:
            try:
                base_mult = float(base_mult) + float(_mines_vip_bonus(size, mines))
            except Exception:
                base_mult = float(base_mult)

        if base_mult > MINES_MAX_WIN_MULTIPLIER:
            base_mult = MINES_MAX_WIN_MULTIPLIER

        return float(base_mult)

    def _mines_max_diamonds(size: int, mines: int) -> int:
        # Allow opening up to all safe cells (total - mines) by default.
        size = int(size)
        mines = int(mines)
        total = _mines_total_cells(size)
        # If a configured cap exists for this size, prefer it only if it's larger than 0,
        # otherwise allow opening all safe cells.
        configured = int(MINES_MAX_DIAMONDS_BY_SIZE.get(int(size), 0) or 0)
        default_allowed = max(0, total - mines)
        return max(configured, default_allowed)

    def _mines_reveal_then_cleanup(
        *,
        chat_id: int,
        message_id: int,
        size: int,
        opened: set[int],
        mine_cells: set[int],
        final_text: str,
    ) -> None:
        def _worker() -> None:
            try:
                time.sleep(MINES_REVEAL_DELAY_SECONDS)
                bot.edit_message_text(
                    final_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=mines_field_kb(
                        size=size,
                        opened_cells=set(opened),
                        mine_cells=set(mine_cells),
                        reveal=True,
                        disabled=True,
                        show_restart=True,
                    ),
                )
            except Exception:
                return

        threading.Thread(target=_worker, daemon=True).start()

    def _mines_masked_grid(size: int, opened: set[int], bomb_cell: int) -> str:
        size = int(size)
        total = _mines_total_cells(size)
        bomb_cell = int(bomb_cell)
        opened = set(int(x) for x in opened)
        lines: list[str] = []
        for r in range(size):
            row: list[str] = []
            for c in range(size):
                idx = r * size + c + 1
                if idx > total:
                    continue
                if idx == bomb_cell:
                    row.append("💣")
                elif idx in opened:
                    row.append("💎")
                else:
                    row.append("⬛")
            lines.append(" ".join(row))
        return "\n".join(lines)

    def _mines_timeout_loop() -> None:
        while True:
            time.sleep(5)
            now = time.time()
            timed_out: list[tuple[int, int]] = []
            with sessions_lock:
                snapshot = list(sessions.items())
            for uid, s in snapshot:
                if s.mines_state != "active":
                    continue
                if not s.mines_started_at or not s.mines_bet:
                    continue
                if (now - float(s.mines_started_at)) >= MINES_TIMEOUT_SECONDS:
                    timed_out.append((uid, int(s.mines_bet)))

            for uid, bet in timed_out:
                # auto-loss; do not reveal the field
                _mines_reset(uid, preserve_params=True)
                try:
                    bot.send_message(uid, f"⏳ Время вышло (5 минут). Ставка {bet} проиграна.")
                except Exception:
                    pass

    threading.Thread(target=_mines_timeout_loop, daemon=True).start()

    def _handle_channel_unsub(user_id: int, task, st: dict) -> None:
        ok, reward_credited, repeat_used, new_status = db.try_transition_channel_unsub(user_id, task.id)
        if not ok:
            return
        deducted = int(reward_credited or task.reward_points)
        try:
            db.spend_points_clamped(int(user_id), int(deducted))
        except Exception:
            # Fallback: never create negative balances
            try:
                bal_now = int(db.get_balance(int(user_id)) or 0)
                db.add_balance(int(user_id), -int(min(bal_now, int(deducted))))
            except Exception:
                pass

        if new_status == "repeat_offer" and repeat_used == 0:
            bot.send_message(
                user_id,
                f"⚠ Вы отписались от канала {settings.channel_display or 'канала'}\n"
                f"С вашего баланса списано {_fmt_points_ui(int(deducted))} баллов\n\n"
                "Хотите выполнить задание снова?\nНаграда будет уменьшена на 10%",
                reply_markup=repeat_offer_kb("channel"),
            )
        else:
            bot.send_message(
                user_id,
                f"⚠ Вы отписались от канала {settings.channel_display or 'канала'}\n"
                f"С вашего баланса списано {_fmt_points_ui(int(deducted))} баллов",
            )

    def _is_transient_network_error(e: BaseException) -> bool:
        # Typical transient failures on Windows / unstable networks
        if isinstance(e, (ConnectionResetError, TimeoutError)):
            return True
        if isinstance(e, OSError) and (getattr(e, "winerror", None) in (10054, 10053, 10060)):
            return True
        msg = str(e).lower()
        return any(
            s in msg
            for s in (
                "connection aborted",
                "connection reset",
                "remotedisconnected",
                "max retries exceeded",
                "read timed out",
                "timed out",
                "temporarily unavailable",
            )
        )

    def _is_non_retriable_chat_member_error(e: BaseException) -> bool:
        # These usually mean wrong chat id / no rights / bot not in channel.
        msg = str(e).lower()
        return any(
            s in msg
            for s in (
                "chat not found",
                "bot was kicked",
                "not enough rights",
                "have no rights",
                "forbidden",
                "chat_admin_required",
                "bad request: chat not found",
            )
        )

    def _get_chat_member_safe(
        channel_chat_id: int,
        user_id: int,
        *,
        purpose: str,
        attempts: int = 2,
        base_sleep: float = 0.6,
    ) -> tuple[object | None, Exception | None]:
        last_exc: Exception | None = None
        for i in range(max(1, int(attempts))):
            try:
                return bot.get_chat_member(int(channel_chat_id), int(user_id)), None
            except Exception as e:
                last_exc = e
                if _is_non_retriable_chat_member_error(e):
                    break
                if not _is_transient_network_error(e):
                    break
                if i < (int(attempts) - 1):
                    try:
                        time.sleep(float(base_sleep) * (2**i))
                    except Exception:
                        pass
        try:
            logging.getLogger(__name__).warning(
                "get_chat_member failed (purpose=%s chat_id=%s user_id=%s): %r",
                str(purpose),
                int(channel_chat_id),
                int(user_id),
                last_exc,
            )
        except Exception:
            pass
        return None, last_exc

    def _task_state(user_id: int, task) -> dict:
        if not task:
            return {"status": "new", "repeat_used": 0, "reward_credited": 0}
        db.ensure_user_task(user_id, task.id)
        st = db.get_user_task(user_id, task.id)
        return st or {"status": "new", "repeat_used": 0, "reward_credited": 0}

    def _next_reward_for_task(user_id: int, task) -> int:
        st = _task_state(user_id, task)
        base = int(task.reward_points)
        reward = base
        if st["status"] == "repeat_offer":
            reward = int(base * 0.9)
        elif st["repeat_used"]:
            reward = int(base * 0.9)

        # VIP bonus: +20% to task rewards
        try:
            if db.is_vip_active(user_id, now_ts=int(time.time())):
                reward = int(math.floor(float(reward) * 1.20))
        except Exception:
            pass

        return int(reward)

    def _offer_repeat_tiktok(user_id: int, task_id: int) -> None:
        st = db.get_user_task(user_id, task_id)
        if not st:
            db.ensure_user_task(user_id, task_id)
            st = db.get_user_task(user_id, task_id)
        if st and int(st["repeat_used"]) == 0:
            db.update_user_task(user_id, task_id, status="repeat_offer")
            bot.send_message(
                user_id,
                "❌ Админ отклонил ваше задание.\nВы можете выполнить его повторно, награда −10%",
                reply_markup=repeat_offer_kb("tiktok"),
            )
        else:
            db.update_user_task(user_id, task_id, status="rejected")
            bot.send_message(user_id, "❌ Задание отклонено.")

    def _accept_repeat(user_id: int, task_code: str) -> None:
        if task_code == "tiktok":
            task = db.get_task_by_code("tiktok_comment")
            if not task:
                return
            db.update_user_task(user_id, task.id, status="new", repeat_used=1)
            bot.send_message(user_id, "Ок. Повторное выполнение доступно (награда −10%).")
            return
        if task_code == "channel":
            task = db.get_task_by_code("channel_subscribe")
            if not task:
                return
            db.update_user_task(user_id, task.id, status="new", repeat_used=1)
            bot.send_message(user_id, "Ок. Повторное выполнение доступно (награда −10%).")

    def _decline_repeat(user_id: int, task_code: str) -> None:
        if task_code == "tiktok":
            task = db.get_task_by_code("tiktok_comment")
            if task:
                db.update_user_task(user_id, task.id, status="refused", repeat_used=1)
            return
        if task_code == "channel":
            task = db.get_task_by_code("channel_subscribe")
            if task:
                db.update_user_task(user_id, task.id, status="refused", repeat_used=1)

    def _channel_on_activity(user_id: int, *, chat_id: int | None = None, message_id: int | None = None) -> None:
        # Any user activity clears temporary notices (e.g., "игра не активна").
        try:
            _clear_temp_notice(int(user_id))
        except Exception:
            pass

        task = db.get_task_by_code("channel_subscribe")
        if not task or not settings.channel_chat_id:
            return

    def _weekly_event_scheduler_loop() -> None:
        """Send weekly events by schedule (not by button presses).

        Slots: morning/day/evening. Weekly uniqueness is guaranteed by DB `notified_at_ts`.
        """

        slots: list[tuple[int, int, str]] = [
            (9, 0, "morning"),
            (15, 0, "day"),
            (21, 0, "evening"),
        ]
        last_slot_key: str | None = None

        while True:
            try:
                now_local = dt.datetime.now()
                slot_name: str | None = None
                for hh, mm, name in slots:
                    if now_local.hour == hh and now_local.minute == mm and now_local.second < 45:
                        slot_name = name
                        break

                if slot_name:
                    slot_key = f"{now_local.date().isoformat()}:{slot_name}"
                    if slot_key != last_slot_key:
                        last_slot_key = slot_key

                        offset = 0
                        limit = 500
                        while True:
                            try:
                                user_ids = db.list_user_ids(active_only=True, limit=limit, offset=offset)
                            except Exception:
                                user_ids = []
                            if not user_ids:
                                break
                            for uid_local in user_ids:
                                try:
                                    # In private chats, chat_id == user_id.
                                    _maybe_auto_send_weekly_event(int(uid_local), int(uid_local))
                                except Exception:
                                    pass
                            offset += int(limit)
            except Exception:
                pass

            time.sleep(1)

        st = _task_state(user_id, task)

        # Store last task message if provided (so we can hide the button later).
        if chat_id is not None and message_id is not None:
            s = session(user_id)
            s.last_channel_task_chat_id = chat_id
            s.last_channel_task_message_id = message_id

        is_subbed = False
        try:
            member, e = _get_chat_member_safe(
                int(settings.channel_chat_id),
                int(user_id),
                purpose="channel_on_activity",
                attempts=2,
            )
            status = getattr(member, "status", None) if member is not None else None
            is_subbed = status in ("member", "administrator", "creator")
        except Exception as e:
            member = None
            # Common Telegram edge case for private channels: `user not found` may mean "user is not a participant".
            msg = str(e).lower()
            if "user not found" in msg or "user_id_invalid" in msg or "user not participant" in msg:
                is_subbed = False
            else:
                bot_tag = None
                try:
                    me = bot.get_me()
                    if me and getattr(me, "username", None):
                        bot_tag = f"@{me.username}"
                except Exception:
                    bot_tag = None

                extra = f"\n\nДобавьте в канал именно этого бота: {bot_tag}" if bot_tag else ""
                _notify_admin_once(
                    "⚠ Не могу проверить подписку через getChatMember.\n"
                    "Проверь, что бот добавлен админом в канал и что CHANNEL_CHAT_ID верный."
                    + extra
                    + "\n\n"
                    f"Ошибка: {e}"
                )
                if chat_id is not None:
                    s = session(user_id)
                    if not s.warned_channel_check_unavailable:
                        s.warned_channel_check_unavailable = True
                        bot.send_message(
                            chat_id,
                            "⚠ Сейчас не получается проверить подписку автоматически.\n"
                            "Если вы подписались — отправьте любое сообщение в бота позже.\n"
                            "Админ должен добавить бота в канал администратором.",
                        )
                return

        # If already completed, only track unsubscribe.
        if st["status"] == "completed":
            if not is_subbed:
                _handle_channel_unsub(user_id, task, st)
            return

        # If not completed and subscribed -> auto-complete (only from allowed states)
        if is_subbed and st["status"] in ("new", "repeat_offer"):
            reward = _next_reward_for_task(user_id, task)
            repeat_used = int(st["repeat_used"])
            if st["status"] == "repeat_offer":
                repeat_used = 1
            if not db.try_mark_task_completed(user_id, task.id, reward_credited=reward, repeat_used=repeat_used):
                return
            lvl_res = db.add_balance(user_id, reward)
            db.inc_completed_tasks(user_id)

            try:
                now_ts = int(time.time())
                wk = db.week_key_utc(now_ts)
                db.add_weekly_progress(user_id, week_key=wk, code="tasks_completed", delta=1, now_ts=now_ts)
            except Exception:
                pass

            target_chat = chat_id if chat_id is not None else user_id
            msg = (
                f"✅ Спасибо за подписку!\n"
                f"Вам начислено +{reward} баллов\n"
                f"🎖 Уровень: {lvl_res.get('new_title')}"
            )
            bot.send_message(target_chat, msg)

            if lvl_res.get("leveled_up"):
                bot.send_message(target_chat, "🎉 Поздравляем!\n" f"Вы достигли уровня: {lvl_res.get('new_title')}")

            # Hide the subscribe button if we know which message to edit
            s = session(user_id)
            if s.last_channel_task_chat_id and s.last_channel_task_message_id:
                try:
                    _show_channel_task(
                        s.last_channel_task_chat_id,
                        s.last_channel_task_message_id,
                        user_id,
                        edit=True,
                    )
                except Exception:
                    pass

    def _maybe_check_channel_unsub(user_id: int) -> None:
        task = db.get_task_by_code("channel_subscribe")
        if not task:
            return
        st = _task_state(user_id, task)
        if st["status"] != "completed":
            return
        if not settings.channel_chat_id:
            return
        try:
            member, e = _get_chat_member_safe(
                int(settings.channel_chat_id),
                int(user_id),
                purpose="maybe_check_unsub",
                attempts=2,
            )
            status = getattr(member, "status", None) if member is not None else None
            is_subbed = status in ("member", "administrator", "creator")
        except Exception as e:
            _notify_admin_once(
                "⚠ Не могу проверить подписку через getChatMember.\n"
                "Проверь, что бот добавлен админом в канал и что CHANNEL_CHAT_ID верный.\n\n"
                f"Ошибка: {e}"
            )
            return

        if is_subbed:
            return

        _handle_channel_unsub(user_id, task, st)

    def _show_channel_task(chat_id: int, message_id: int | None, user_id: int, *, edit: bool) -> None:
        task = db.get_task_by_code("channel_subscribe")
        if not task:
            bot.send_message(chat_id, "Задание не найдено")
            return
        st = _task_state(user_id, task)

        channel_text = settings.channel_display or "канал"
        reward = _next_reward_for_task(user_id, task)

        if st["status"] == "completed":
            got = int(st["reward_credited"] or reward)
            text = f"✅ Подписка на канал {channel_text} выполнена\nВам начислено +{got} баллов"
        else:
            text = (
                f"Подпишитесь на канал {channel_text}\n"
                f"Награда: +{reward} баллов\n\n"
                "После подписки просто вернитесь в бота — проверка произойдет автоматически."
            )

        show_subscribe = st["status"] != "completed"

        kb = channel_task_kb(settings.channel_url, show_subscribe=show_subscribe)
        if edit and message_id is not None:
            bot.edit_message_text(text, chat_id, message_id)
            bot.edit_message_reply_markup(chat_id, message_id, reply_markup=kb)
            _channel_on_activity(user_id, chat_id=chat_id, message_id=message_id)
        else:
            msg = bot.send_message(chat_id, text, reply_markup=kb)
            s = session(user_id)
            s.last_channel_task_chat_id = msg.chat.id
            s.last_channel_task_message_id = msg.message_id
            _channel_on_activity(user_id, chat_id=msg.chat.id, message_id=msg.message_id)

    def _show_tiktok_task(chat_id: int, message_id: int | None, user_id: int, *, edit: bool) -> None:
        task = db.get_task_by_code("tiktok_comment")
        if not task:
            bot.send_message(chat_id, "Задание не найдено")
            return
        st = _task_state(user_id, task)
        reward = _next_reward_for_task(user_id, task)

        if st["status"] == "repeat_offer":
            bot.send_message(
                chat_id,
                "❌ Админ отклонил ваше задание.\nВы можете выполнить его повторно, награда −10%",
                reply_markup=repeat_offer_kb("tiktok"),
            )
            return

        text = (
            "Задание: Напишите комментарий в TikTok\n\n"
            "1️⃣ Найдите любое видео с 100 000+ лайков\n"
            "2️⃣ Вставьте комментарий ниже под видео:\n\n"
            "@zadaniya_za_cashBot в этом боте реально можно получить деньги выполняя легкие задания\n\n"
            "3️⃣ Сделайте скрин с вашим комментарием, ником и лайками\n\n"
            f"Награда: +{reward} баллов"
        )

        kb_state = "available"
        if st["status"] == "pending":
            kb_state = "pending"
        if st["status"] == "completed":
            kb_state = "completed"

        kb = tiktok_task_kb(kb_state)
        if edit and message_id is not None:
            bot.edit_message_text(text, chat_id, message_id)
            bot.edit_message_reply_markup(chat_id, message_id, reply_markup=kb)
        else:
            bot.send_message(chat_id, text, reply_markup=kb)

    def _start_tiktok_proof(user_id: int, chat_id: int) -> None:
        task = db.get_task_by_code("tiktok_comment")
        if not task:
            bot.send_message(chat_id, "Задание не найдено")
            return
        st = _task_state(user_id, task)
        if st["status"] == "pending":
            bot.send_message(chat_id, "🕒 Уже в обработке. Дождитесь проверки.")
            return
        if st["status"] == "completed":
            bot.send_message(chat_id, "✅ Задание уже выполнено.")
            return
        s = session(user_id)
        s.awaiting_proof_task_id = task.id
        s.awaiting_proof_task_code = task.code
        bot.send_message(chat_id, "Отправь скриншот (фото) одним сообщением.")

    @bot.message_handler(commands=["start"])
    def handle_start(message: Message) -> None:
        # Deep-link payload (referrals or duels)
        payload = None
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            payload = parts[1].strip()

        # Duel join deep-link: /start duel_CODE
        if payload and payload.lower().startswith("duel_"):
            code = payload[len("duel_") :]
            duel = db.get_duel_by_code(code)
            if not duel:
                bot.send_message(message.chat.id, "❌ Дуэль не найдена или устарела.")
                return
            if duel["status"] != "waiting" or duel["creator_id"] == message.from_user.id:
                bot.send_message(message.chat.id, "❌ Нельзя присоединиться к этой дуэли.")
                return
            joined = db.join_waiting_duel_atomic(int(duel["duel_id"]), user_id=int(message.from_user.id))
            if not bool(joined.get("ok")):
                reason = str(joined.get("reason") or "")
                if reason == "no_balance":
                    try:
                        bal = int(joined.get("balance") or 0)
                    except Exception:
                        bal = 0
                    bot.send_message(message.chat.id, f"❌ Недостаточно баллов для участия. Баланс: {_fmt_points_ui(int(bal))}.")
                    return
                bot.send_message(message.chat.id, "❌ Дуэль уже заняли или она недоступна.")
                return

            duel = (joined.get("duel") or duel)
            stake = int(duel.get("stake") or 0)
            game_type = str(duel.get("game_type") or "")
            creator_id = int(duel.get("creator_id") or 0)
            payout = _duel_commission_payout_with_vip(int(stake), int(creator_id), duel.get("opponent_id"))

            # Bot-duel (server pool): set bot choice immediately for RPS
            if int(duel.get("is_bot") or 0) == 1 and int(creator_id) == 0 and game_type == "rps":
                try:
                    db.update_duel_rps_choice(duel["duel_id"], user_id=0, choice=random.choice(["rock", "paper", "scissors"]))
                except Exception:
                    pass

            if game_type == "dice":
                # Отправляем обоим кнопку "Кинуть кубик" сразу
                try:
                    kb = InlineKeyboardMarkup()
                    kb.add(InlineKeyboardButton(text="🎲 Кинуть кубик", callback_data=f"duel:dice:roll:{duel['duel_id']}"))
                    bot.send_message(
                        creator_id,
                        "⚔ Противник присоединился к вашей дуэли!\n\nНажмите кнопку, чтобы кинуть кубик.",
                        reply_markup=kb,
                    )
                except Exception:
                    pass
                try:
                    bot.send_message(
                        message.chat.id,
                        "⚔ Вы присоединились к дуэли!\n\nНажмите кнопку ниже, чтобы кинуть кубик.",
                        reply_markup=kb,
                    )
                except Exception:
                    pass
                return

            if game_type == "ttt":
                try:
                    bot.send_message(int(creator_id), "⚔ Противник присоединился к дуэли! Игра начинается.")
                except Exception:
                    pass
                try:
                    bot.send_message(int(message.chat.id), "⚔ Вы присоединились к дуэли! Игра начинается.")
                except Exception:
                    pass
                try:
                    _ttt_start_duel(int(duel["duel_id"]), creator_id=int(creator_id), opponent_id=int(message.from_user.id), stake=int(stake))
                except Exception:
                    pass
                return

            # RPS duel: отправляем обоим меню выбора
            try:
                bot.send_message(
                    creator_id,
                    "⚔ Дуэль КНБ началась!\nВыберите: камень, ножницы или бумага.",
                    reply_markup=duel_rps_kb(duel["duel_id"]),
                )
            except Exception:
                pass
            try:
                bot.send_message(
                    message.chat.id,
                    "⚔ Дуэль КНБ началась!\nВыберите: камень, ножницы или бумага.",
                    reply_markup=duel_rps_kb(duel["duel_id"]),
                )
            except Exception:
                pass
            return

        uid = int(message.from_user.id)
        username = message.from_user.username
        first_name = html_escape(getattr(message.from_user, "first_name", "") or "")

        is_new = not db.user_exists(uid)

        inviter = _parse_start_ref(message.text or "")
        inviter_rewarded = db.register_user_from_start(
            uid,
            username,
            inviter,
            bonus_points=REFERRAL_BONUS_POINTS,
        )

        # Starter bonus for brand-new users
        if is_new:
            try:
                db.add_balance(uid, 100)
            except Exception:
                pass

        if inviter_rewarded:
            inviter_id = int(inviter_rewarded.get("inviter_id"))
            try:
                bot.send_message(
                    inviter_id,
                    f"🎉 Новый реферал!\n\n"
                    f"Пользователь @{username or 'без_ника'} запустил бота по твоей ссылке.\n"
                    f"Начислено +{_fmt_int(int(REFERRAL_BONUS_POINTS))} баллов.",
                )
            except Exception:
                pass

            if inviter_rewarded.get("leveled_up"):
                try:
                    bot.send_message(inviter_id, f"🎉 Новый уровень: {inviter_rewarded.get('new_title')}")
                except Exception:
                    pass
            reset_panel_state(message.from_user.id)
            reset_user_flow(message.from_user.id)
        reset_admin_flow(message.from_user.id)
        # После регистрации пользователя можно безопасно трекать активность по заданию канала
        try:
            _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass
        if db.is_blocked(message.from_user.id):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        if is_new:
            welcome_text = (
                f"🎉 <b>Добро пожаловать, {first_name}!</b>\n\n"
                "<b>BotZD</b> — бот, где ты получаешь баллы за активность.\n\n"
                "<b>Как начать:</b>\n"
                "1) Нажми \"📋 Задания\" и выбери задание\n"
                "2) Выполни условия и отправь скриншот\n"
                "3) Получи баллы на баланс\n\n"
                "🎁 <b>Стартовый бонус: +100 баллов</b> уже начислен!\n\n"
                "Команды:\n"
                "/stats — статистика\n"
                "/help — FAQ"
            )
            bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=main_menu_kb(is_admin=_is_admin(uid, settings)))
        else:
            snap = db.get_user_stats_snapshot(uid) or {}
            bal = int(snap.get("balance_points", 0) or 0)
            lvl_title = db.get_level_title(int(snap.get("level", 1) or 1))
            text = (
                f"👋 <b>С возвращением, {first_name}!</b>\n\n"
                f"💰 Баланс: <b>{_fmt_int(int(bal))}</b> баллов\n"
                f"⭐ Уровень: <b>{lvl_title}</b>\n\n"
                "Выбирай раздел: задания, мини-игры или фарм."
            )
            bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=main_menu_kb(is_admin=_is_admin(uid, settings)))

    @bot.message_handler(commands=["menu"])
    def handle_menu(message: Message) -> None:
        # Safety: allow users to restore the keyboard/menu anytime
        try:
            db.ensure_user(message.from_user.id, message.from_user.username, None)
        except Exception:
            pass
        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        if db.is_blocked(message.from_user.id):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _safe_delete_message(bot, int(message.chat.id), int(message.message_id))
        _set_reply_keyboard_silent(message.chat.id, main_menu_kb(is_admin=_is_admin(message.from_user.id, settings)))

    @bot.message_handler(commands=["admin"])
    def handle_admin_cmd(message: Message) -> None:
        if not _is_admin(message.from_user.id, settings):
            return
        reset_admin_flow(message.from_user.id)
        bot.send_message(message.chat.id, "👑 АДМИН-ПАНЕЛЬ", reply_markup=admin_menu_kb())

    @bot.message_handler(commands=["check_channel"])
    def handle_check_channel_cmd(message: Message) -> None:
        if not _is_admin(message.from_user.id, settings):
            return
        if not settings.channel_chat_id:
            bot.send_message(message.chat.id, "CHANNEL_CHAT_ID не задан в .env")
            return
        try:
            # Use short timeouts for manual checks to avoid blocking the bot for ~1 minute
            # on broken networks / stalled Telegram responses.
            try:
                from telebot import apihelper  # type: ignore

                _old_ct = getattr(apihelper, "CONNECT_TIMEOUT", None)
                _old_rt = getattr(apihelper, "READ_TIMEOUT", None)
                apihelper.CONNECT_TIMEOUT = 5
                apihelper.READ_TIMEOUT = 8
                try:
                    chat = bot.get_chat(settings.channel_chat_id)
                finally:
                    if _old_ct is not None:
                        apihelper.CONNECT_TIMEOUT = _old_ct
                    if _old_rt is not None:
                        apihelper.READ_TIMEOUT = _old_rt
            except Exception:
                chat = bot.get_chat(settings.channel_chat_id)
            title = getattr(chat, "title", None) or getattr(chat, "username", None) or "(без названия)"
            bot.send_message(
                message.chat.id,
                f"✅ CHANNEL_CHAT_ID = {settings.channel_chat_id}\nДоступ к чату есть: {title}",
            )
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"❌ Не могу открыть чат по CHANNEL_CHAT_ID = {settings.channel_chat_id}\nОшибка: {e}",
            )

    # --- tournaments (MVP, mines no-bet only for now) ---

    TOURN_MATCH_DEADLINE_SECONDS = 10 * 60

    def _fmt_ts_short(ts: int) -> str:
        try:
            return dt.datetime.utcfromtimestamp(int(ts)).strftime("%d.%m %H:%M")
        except Exception:
            return str(ts)

    def _pick_primary_tournament(now_ts: int) -> dict | None:
        items = db.list_tournaments(states=("running", "registering"), limit=10)
        if not items:
            return None
        for t in items:
            if str(t.get("state") or "") == "running":
                return t
        return items[0]

    def _send_tournament_screen(chat_id: int, user_id: int, *, edit_message_id: int | None = None) -> None:
        now_ts = int(time.time())
        t = _pick_primary_tournament(now_ts)
        if not t:
            bot.send_message(chat_id, "🏆 Сейчас нет активных турниров. Загляни позже!", reply_markup=main_menu_kb(is_admin=_is_admin(user_id, settings)))
            return

        tid = int(t.get("id") or 0)
        s = session(user_id)
        s.tourn_selected_id = tid

        state = str(t.get("state") or "")
        max_players = int(t.get("max_players") or 0)
        entry_fee = int(t.get("entry_fee_points") or 0)
        start_at = int(t.get("start_at") or 0)
        prize = {}
        try:
            prize = json.loads(str(t.get("prize_json") or "{}"))
        except Exception:
            prize = {}

        count = db.get_tournament_players_count(tid)
        is_reg = db.is_user_registered_in_tournament(tid, user_id)
        can_unreg = state == "registering"

        lines: list[str] = ["🏆 ТУРНИР", "━━━━━━━━━━━━━━━━━━━━", ""]
        lines.append(f"ID: {tid}")
        lines.append(f"Статус: {('🟢 Регистрация' if state=='registering' else '🔴 Идёт' if state=='running' else state)}")
        if start_at:
            lines.append(f"Старт: {_fmt_ts_short(start_at)} UTC")
        lines.append(f"Участники: {count}/{max_players}")
        if entry_fee > 0:
            lines.append(f"Взнос: {entry_fee} баллов")
        p1 = int(prize.get("1", 0) or 0)
        p2 = int(prize.get("2", 0) or 0)
        p3 = int(prize.get("3", 0) or 0)
        if p1 or p2 or p3:
            lines.append(f"Призы: 🥇{p1} / 🥈{p2} / 🥉{p3}")

        if is_reg and state == "running":
            m = db.get_user_pending_match(tid, user_id)
            if m:
                opp = int(m.get("p2_user_id") or 0) if int(m.get("p1_user_id") or 0) == int(user_id) else int(m.get("p1_user_id") or 0)
                deadline = int(m.get("deadline_at") or 0)
                lines.append("")
                lines.append("🎮 Ваш матч:")
                lines.append(f"Матч #{int(m.get('id') or 0)} | Раунд {int(m.get('round') or 1)}")
                lines.append(f"Соперник: ID{opp}" if opp else "Соперник: BYE")
                if deadline:
                    lines.append(f"Дедлайн: {_fmt_ts_short(deadline)} UTC")
            else:
                lines.append("")
                lines.append("⏳ Сейчас нет активного матча. Ждите следующего раунда.")

        text = "\n".join(lines)
        kb = tournaments_menu_kb(is_registered=is_reg, can_unregister=can_unreg)
        if edit_message_id:
            bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=kb)
        else:
            bot.send_message(chat_id, text, reply_markup=kb)

    def _tourn_submit_from_mines_round(*, rnd: dict, user_id: int, score: int, now_ts: int) -> None:
        try:
            tid = int(rnd.get("tournament_id") or 0)
            mid = int(rnd.get("tournament_match_id") or 0)
        except Exception:
            return
        if tid <= 0 or mid <= 0:
            return

        started_at = int(rnd.get("started_at") or now_ts)
        time_ms = max(0, int((int(now_ts) - int(started_at)) * 1000))
        try:
            db.submit_match_result(
                tournament_id=tid,
                match_id=mid,
                user_id=int(user_id),
                score=int(score),
                time_ms=int(time_ms),
                now_ts=int(now_ts),
            )
        except Exception:
            return

        try:
            db.maybe_advance_tournament(tid, now_ts=int(now_ts), round_deadline_seconds=int(TOURN_MATCH_DEADLINE_SECONDS))
        except Exception:
            pass

    def _admin_tourn_panel_kb() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="➕ Создать турнир (Mines XP)", callback_data="admin:tourn:create"))
        kb.add(InlineKeyboardButton(text="📋 Показать пользователям", callback_data="tourn:list"))
        kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
        return kb

    @bot.message_handler(func=lambda m: _is_admin(m.from_user.id, settings) and m.text == "🏆 Турниры")
    def admin_tournaments_entry(message: Message) -> None:
        bot.send_message(
            message.chat.id,
            "🏆 ТУРНИРЫ (админ)\n\nMVP: пока только турнир по 💣 Мины → «Без ставок (XP)».",
            reply_markup=_admin_tourn_panel_kb(),
        )

    @bot.message_handler(func=lambda m: m.text == "🏆 Турниры")
    def handle_tournaments_entry(message: Message) -> None:
        if db.is_blocked(message.from_user.id):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        _send_tournament_screen(message.chat.id, message.from_user.id)

    @bot.message_handler(func=lambda m: m.text == "📋 Задания")
    def handle_tasks(message: Message) -> None:
        if db.is_blocked(message.from_user.id):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return

        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)

        sub_task = db.get_task_by_code("channel_subscribe")
        tt_task = db.get_task_by_code("tiktok_comment")
        if not sub_task or not tt_task:
            bot.send_message(message.chat.id, "Задания временно недоступны.")
            return

        sub_reward = _next_reward_for_task(message.from_user.id, sub_task)
        tt_reward = _next_reward_for_task(message.from_user.id, tt_task)

        bot.send_message(
            message.chat.id,
            "📋 Доступные задания:\n\nВыберите задание, чтобы увидеть условия и награду:",
            reply_markup=tasks_menu_kb(sub_reward=sub_reward, tiktok_reward=tt_reward),
        )

    @bot.message_handler(func=lambda m: m.text == "💸 Вывод")
    def handle_withdraw(message: Message) -> None:
        if db.is_blocked(message.from_user.id):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        _send_withdraw_menu(message.chat.id, message.from_user.id)

    @bot.message_handler(func=lambda m: m.text == "👥 Пригласить друга")
    def handle_invite(message: Message) -> None:
        if db.is_blocked(message.from_user.id):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        if not settings.bot_username:
            bot.send_message(message.chat.id, "Укажи BOT_USERNAME в .env")
            return
        link = f"https://t.me/{settings.bot_username}?start={message.from_user.id}"
        bot.send_message(
            message.chat.id,
            "👥 Пригласить друга\n\n"
            f"Приглашайте друзей и получайте +{REFERRAL_BONUS_POINTS} баллов за каждого!\n\n"
            "Ваша реферальная ссылка:\n\n"
            f"{link}",
            reply_markup=main_menu_kb(is_admin=_is_admin(message.from_user.id, settings)),
        )

    @bot.message_handler(func=lambda m: _norm_reply_text(getattr(m, "text", None)) == "🎮 Мини игры")
    def handle_minigames(message: Message) -> None:
        try:
            _clear_temp_notice(int(message.from_user.id))
        except Exception:
            pass
        if db.is_blocked(message.from_user.id):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        _safe_delete_message(bot, int(message.chat.id), int(message.message_id))
        # If the panel message is far above (after non-panel flows like duels server),
        # editing it looks like "nothing happened". Force a fresh panel message.
        try:
            s = session(int(message.from_user.id))
            if bool(getattr(s, "panel_mode", True)) and int(getattr(s, "panel_chat_id", 0) or 0) == int(message.chat.id):
                s.panel_message_id = None
        except Exception:
            pass
        show_screen(chat_id=int(message.chat.id), user_id=int(message.from_user.id), screen="minigames", push_history=True)

    @bot.message_handler(func=lambda m: m.text == "💼 Профиль")
    def handle_profile(message: Message) -> None:
        try:
            _clear_temp_notice(int(message.from_user.id))
        except Exception:
            pass
        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        _safe_delete_message(bot, int(message.chat.id), int(message.message_id))
        # If the panel message is far above, editing it looks like "nothing happened".
        # Force a fresh panel message.
        try:
            s = session(int(message.from_user.id))
            if bool(getattr(s, "panel_mode", True)) and int(getattr(s, "panel_chat_id", 0) or 0) == int(message.chat.id):
                s.panel_message_id = None
        except Exception:
            pass
        show_screen(chat_id=int(message.chat.id), user_id=int(message.from_user.id), screen="profile", push_history=True)

    @bot.message_handler(func=lambda m: m.text == "✨ Фарм баллов")
    def handle_farm_points(message: Message) -> None:
        uid = message.from_user.id
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(uid, chat_id=message.chat.id, message_id=message.message_id)
        _farm_send_or_edit(None, message.chat.id, None, uid)

    @bot.message_handler(func=lambda m: (m.text or "").strip() in {"🛒 Магазин", "Магазин"})
    def handle_shop(message: Message) -> None:
        uid = message.from_user.id
        try:
            _clear_temp_notice(int(uid))
        except Exception:
            pass
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(uid, chat_id=message.chat.id, message_id=message.message_id)

        # Global shop (main menu): use the main panel (no chat spam)
        _safe_delete_message(bot, int(message.chat.id), int(message.message_id))
        show_screen(chat_id=int(message.chat.id), user_id=int(uid), screen="shop", push_history=True)

    @bot.message_handler(func=lambda m: (m.text or "").strip() in {"🛒 МАГАЗИН"})
    def handle_global_shop(message: Message) -> None:
        uid = message.from_user.id
        try:
            _clear_temp_notice(int(uid))
        except Exception:
            pass
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(uid, chat_id=message.chat.id, message_id=message.message_id)
        show_screen(chat_id=int(message.chat.id), user_id=int(uid), screen="shop", push_history=True)

    @bot.message_handler(func=lambda m: m.text == "⛏️ Майнинг ферма")
    def handle_cryptomine_shop(message: Message) -> None:
        uid = int(message.from_user.id)
        try:
            _clear_temp_notice(int(uid))
        except Exception:
            pass
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(uid, chat_id=message.chat.id, message_id=message.message_id)
        db.ensure_user(uid, message.from_user.username, None)
        _cmf_ensure_initialized(uid)
        _cmf_apply_mining(uid)

        # Create / refresh the main "panel" message (we will keep editing this one).
        s = session(uid)
        s.cmf_mode = True
        try:
            # Attach the reply-keyboard to the panel message itself (no extra anchor messages).
            active = bool(_cmf_get_int(uid, "mining_active", 0))
            panel = bot.send_message(message.chat.id, _cmf_home_text(uid), reply_markup=cryptomine_farm_reply_kb(is_active=active))
            s.cmf_chat_id = message.chat.id
            s.cmf_message_id = panel.message_id
        except Exception:
            pass


    def _cmf_norm_reply_text(t: str | None) -> str:
        # Telegram clients may send emoji with a variation selector (\ufe0f),
        # which breaks strict equality checks for reply-keyboard button texts.
        return (t or "").replace("\ufe0f", "").strip()


    _CMF_REPLY_TEXTS = {
        "⛏ Майнить",
        "⛔ Остановить",
        "🛒 Магазин фермы",
        "🔄 Рынок",
        "🖥 Ферма",
        "🏆 Рейтинг",
        "⌨ Главное меню",
    }

    _CMF_REPLY_TEXTS_NORM = {_cmf_norm_reply_text(x) for x in _CMF_REPLY_TEXTS}

    def _cmf_reply_buttons_match(m: Message) -> bool:
        try:
            nt = _cmf_norm_reply_text(getattr(m, "text", None))
        except Exception:
            nt = ""
        if nt in _CMF_REPLY_TEXTS_NORM:
            return True

        # Fallback: accept keyword matches while user is inside CMF flow.
        try:
            s = session(int(m.from_user.id))
            if not bool(getattr(s, "cmf_mode", False)):
                return False
        except Exception:
            return False

        keywords = ("Майнить", "Остановить", "Магазин фермы", "Рынок", "Ферма", "Рейтинг", "Главное меню")
        return any(k in nt for k in keywords)


    @bot.message_handler(func=_cmf_reply_buttons_match)
    def handle_cryptomine_farm_reply_buttons(message: Message) -> None:
        uid = int(message.from_user.id)
        chat_id = int(message.chat.id)
        try:
            _clear_temp_notice(int(uid))
        except Exception:
            pass
        if db.is_blocked(uid):
            return

        _channel_on_activity(uid, chat_id=chat_id, message_id=message.message_id)
        db.ensure_user(uid, message.from_user.username, None)
        _cmf_ensure_initialized(uid)
        _cmf_apply_mining(uid)

        user_message_id = int(getattr(message, "message_id", 0) or 0)

        def _log_panel_err(context: str) -> None:
            try:
                ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                ts = str(time.time())
            try:
                with open(os.path.join(os.getcwd(), "bot_run.err"), "a", encoding="utf-8") as f:
                    f.write(f"\n[{ts}] CMF panel error: {context} uid={uid} chat_id={chat_id}\n")
                    f.write(traceback.format_exc())
                    f.write("\n")
            except Exception:
                pass

        s = session(uid)
        s.cmf_mode = True

        def _panel_send(text: str, km: InlineKeyboardMarkup | None = None) -> bool:
            try:
                msg = bot.send_message(chat_id, text, reply_markup=km)
                s.cmf_chat_id = chat_id
                s.cmf_message_id = msg.message_id
                return True
            except Exception:
                _log_panel_err("send_message")
                return False

        def _panel_edit(text: str, km: InlineKeyboardMarkup | None = None) -> bool:
            if s.cmf_chat_id != chat_id or not s.cmf_message_id:
                return _panel_send(text, km)
            try:
                bot.edit_message_text(text, chat_id=chat_id, message_id=int(s.cmf_message_id), reply_markup=km)
                return True
            except Exception:
                _log_panel_err("edit_message_text")
                return _panel_send(text, km)

        def _delete_user_button_message() -> None:
            # Reply buttons send text messages; we try to delete them to keep the chat clean.
            # Note: Telegram only allows deleting user messages in groups/supergroups when the bot has rights.
            if user_message_id:
                _safe_delete_message(bot, chat_id, user_message_id)

        def _start_panel_rating_updater(chat_id_local: int, message_id_local: int, user_id_local: int) -> None:
            def _updater() -> None:
                try:
                    while True:
                        time.sleep(120)
                        try:
                            bot.edit_message_text(_cmf_rating_text(user_id_local), chat_id=chat_id_local, message_id=message_id_local, reply_markup=None)
                        except Exception:
                            break
                except Exception:
                    pass

            try:
                threading.Thread(target=_updater, daemon=True).start()
            except Exception:
                pass

        txt = _cmf_norm_reply_text(message.text)
        if txt == "⌨ Главное меню":
            if s.cmf_kb_message_id and s.cmf_chat_id == chat_id:
                _safe_delete_message(bot, chat_id, int(s.cmf_kb_message_id))
            reset_user_flow(uid)
            reset_admin_flow(uid)
            _set_reply_keyboard_silent(chat_id, main_menu_kb(is_admin=_is_admin(uid, settings)))
            _delete_user_button_message()
            return

        if txt in {"⛏ Майнить", "⛔ Остановить"}:
            if txt == "⛔ Остановить":
                try:
                    db.set_user_field(uid, "mining_active", 0)
                except Exception:
                    pass
                try:
                    _cmf_stop_temp_auto_refresh(uid)
                except Exception:
                    pass
                try:
                    _cmf_apply_mining(uid)
                except Exception:
                    pass
            active = bool(_cmf_get_int(uid, "mining_active", 0))
            if _panel_edit(_cmf_mining_screen_text(uid), cryptomine_mining_kb(is_active=active)):
                _delete_user_button_message()
            return

        if txt == "🖥 Ферма":
            if _panel_edit(_cmf_farm_text(uid), cryptomine_farm_kb()):
                _delete_user_button_message()
            return

        if txt == "🔄 Рынок":
            if _panel_edit(_cmf_market_text(uid), cryptomine_market_kb()):
                _delete_user_button_message()
            return

        if txt == "🏆 Рейтинг":
            # Show rating text (do not send+delete dummy messages; it causes flicker in clients)
            if _panel_edit(_cmf_rating_text(uid), None):
                _delete_user_button_message()
            try:
                # start updater for the panel message
                s = session(uid)
                if s.cmf_chat_id == chat_id and s.cmf_message_id:
                    _start_panel_rating_updater(chat_id, int(s.cmf_message_id), uid)
            except Exception:
                pass
            return

        # Shop shortcuts
        if txt == "🛒 Магазин фермы":
            if _panel_edit(_cm_shop_home_text(uid), cryptomine_shop_main_kb(prefix="cms", exit_cb="cmf:home", show_back=False)):
                _delete_user_button_message()
            return

        # Fallback: show home panel
        if _panel_edit(_cmf_home_text(uid), None):
            _delete_user_button_message()

    @bot.message_handler(func=lambda m: session(m.from_user.id).shop_expect_custom_title)
    def handle_shop_custom_title_input(message: Message) -> None:
        uid = message.from_user.id
        s = session(uid)

        # Feature removed/disabled
        try:
            s.shop_expect_custom_title = False
            s.shop_custom_title_pending = None
        except Exception:
            pass
        try:
            bot.send_message(message.chat.id, "❌ Раздел титулов отключен.")
        except Exception:
            pass
        return

        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            s.shop_expect_custom_title = False
            s.shop_custom_title_pending = None
            s.duel_game_type = None
            s.duel_stake = None
            return

        txt = (message.text or "").strip()
        if not txt:
            bot.send_message(message.chat.id, "Введите текст титула (до 20 символов).")
            return
        if len(txt) > 20:
            bot.send_message(message.chat.id, "Слишком длинно. Максимум 20 символов.")
            return

        lowered = txt.lower()
        banned = ("http", "t.me", "www.", ".ru", ".com", "bit.ly")
        if any(b in lowered for b in banned):
            bot.send_message(message.chat.id, "Запрещены ссылки и реклама. Введите другой титул.")
            return

        s.shop_custom_title_pending = txt
        s.shop_expect_custom_title = False

        bot.send_message(
            message.chat.id,
            "✏️ СВОЙ ТИТУЛ\n\n"
            "Ваш титул:\n"
            f"\"{txt}\"\n\n"
            "Цена: 149 ₽\n\n"
            "Подтвердить?",
            reply_markup=shop_confirm_kb(buy_cb="shop:title:custom:buy", cancel_cb="shop:title"),
        )

    @bot.message_handler(func=lambda m: m.text == "🚀 Бусты")
    def handle_boosts(message: Message) -> None:
        uid = message.from_user.id
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        _channel_on_activity(uid, chat_id=message.chat.id, message_id=message.message_id)
        ins = db.get_insurance_state(uid)
        insurance_balance = int(ins.get("balance") or 0)
        insurance_next = bool(int(ins.get("next") or 0))
        insurance_blocked = bool(int(ins.get("block") or 0))

        bot.send_message(
            message.chat.id,
            "🚀 БУСТЫ\n\n"
            "🛡 Страховка: включается на следующую игру (Мины/Лесенка/КНБ/Кости/Колесо)\n"
            "   • при проигрыше вернём 30% ставки\n"
            "   • с шансом вернём 50%\n"
            "   • тратится только при проигрыше\n"
            "   • нельзя 2 игры подряд\n\n"
            f"Страховок 🛡: {insurance_balance}",
            reply_markup=boosts_kb(
                luck_available=0,
                insurance_balance=insurance_balance,
                insurance_next=insurance_next,
                insurance_blocked=insurance_blocked,
            ),
        )

    @bot.message_handler(commands=["profile", "level"])
    def handle_profile_cmd(message: Message) -> None:
        handle_profile(message)

    @bot.message_handler(commands=["stats"])
    def handle_stats_cmd(message: Message) -> None:
        uid = int(message.from_user.id)
        try:
            db.ensure_user(uid, message.from_user.username, None)
        except Exception:
            pass
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return

        snap = db.get_user_stats_snapshot(uid)
        if not snap:
            bot.send_message(message.chat.id, "Нет данных по аккаунту.")
            return

        total_earned = db.get_user_total_earned(uid)
        total_withdrawn = db.get_user_total_withdrawn_rub(uid)
        games_played = db.get_user_games_count(uid)

        duel_total = int(snap.get("duel_games", 0) or 0)
        duel_wins = int(snap.get("duel_wins", 0) or 0)
        duel_losses = int(snap.get("duel_losses", 0) or 0)
        winrate = (duel_wins / duel_total * 100.0) if duel_total > 0 else 0.0

        ach = db.get_user_achievements(uid)
        ach_unlocked = int(ach.get("unlocked_count", 0) or 0)
        ach_total = db.get_total_achievements_count()

        days_in_bot = 0
        try:
            created = dt.datetime.fromisoformat(str(snap.get("created_at") or ""))
            days_in_bot = max(0, (dt.datetime.utcnow() - created).days)
        except Exception:
            days_in_bot = 0

        first_name = html_escape(getattr(message.from_user, "first_name", "") or "")
        balance_points = int(snap.get("balance_points", 0) or 0)
        level = int(snap.get("level", 1) or 1)
        xp = int(snap.get("experience", 0) or 0)
        farm_streak = int(snap.get("farm_streak_days", 0) or 0)
        mmr = int(snap.get("duel_mmr", 1000) or 1000)
        best_streak = int(snap.get("duel_best_streak", 0) or 0)

        text = (
            f"📊 <b>Статистика {first_name}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "💰 <b>Финансы:</b>\n"
            f"   • Текущий баланс: {_fmt_int(int(balance_points))} баллов\n"
            f"   • Заработано всего: {_fmt_int(int(total_earned))} баллов\n"
            f"   • Выведено: {_fmt_int(int(total_withdrawn))} ₽\n\n"
            "🎮 <b>Активность:</b>\n"
            f"   • Уровень: {level} ({db.get_level_title(level)})\n"
            f"   • Опыт: {_fmt_int(int(xp))} XP\n"
            f"   • Выполнено заданий: {int(snap.get('completed_tasks', 0) or 0)}\n"
            f"   • Игр сыграно: {games_played}\n\n"
            "⚔️ <b>Дуэли:</b>\n"
            f"   • Всего: {duel_total} ({duel_wins} побед)\n"
            f"   • Винрейт: {winrate:.1f}%\n"
            f"   • MMR: {mmr}\n"
            f"   • Лучший страйк: {best_streak}\n\n"
            "🏆 <b>Достижения:</b>\n"
            f"   • Разблокировано: {ach_unlocked}/{ach_total}\n\n"
            "👥 <b>Социальное:</b>\n"
            f"   • Приглашено друзей: {int(snap.get('referrals_count', 0) or 0)}\n\n"
            "📅 <b>Активность:</b>\n"
            f"   • В боте: {days_in_bot} {_ru_days(days_in_bot)}\n"
            f"   • Фарм страйк: {farm_streak} {_ru_days(farm_streak)} 🔥\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 <i>Продолжай в том же духе!</i>"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML")

    @bot.message_handler(commands=["help", "faq"])
    def handle_help_cmd(message: Message) -> None:
        uid = int(message.from_user.id)
        try:
            db.ensure_user(uid, message.from_user.username, None)
        except Exception:
            pass
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return
        bot.send_message(message.chat.id, _faq_main_text(), parse_mode="HTML", reply_markup=_faq_kb())

    @bot.message_handler(commands=["id"])
    def handle_id_cmd(message: Message) -> None:
        bot.send_message(message.chat.id, f"Ваш ID: {message.from_user.id}")

    @bot.message_handler(commands=["admin_debug"])
    def handle_admin_debug_cmd(message: Message) -> None:
        try:
            ids = sorted(list(getattr(settings, "admin_ids", frozenset({settings.admin_id}))))
        except Exception:
            ids = [int(settings.admin_id)]
        bot.send_message(
            message.chat.id,
            "🛠 ADMIN DEBUG\n\n"
            f"Ваш user_id: {message.from_user.id}\n"
            f"ADMIN_ID: {settings.admin_id}\n"
            f"ADMIN_IDS: {', '.join(str(x) for x in ids)}\n\n"
            f"is_admin: {'ДА' if _is_admin(message.from_user.id, settings) else 'НЕТ'}",
        )

    @bot.message_handler(commands=["cancel"])
    def handle_cancel_cmd(message: Message) -> None:
        reset_user_flow(message.from_user.id)
        reset_admin_flow(message.from_user.id)
        _safe_delete_message(bot, int(message.chat.id), int(message.message_id))
        _set_reply_keyboard_silent(message.chat.id, main_menu_kb(is_admin=_is_admin(message.from_user.id, settings)))

    @bot.message_handler(func=lambda m: m.text == "🛠 Админка")
    def handle_admin_button(message: Message) -> None:
        if not _is_admin(message.from_user.id, settings):
            bot.send_message(message.chat.id, "⛔ Доступно только админу.")
            return
        reset_admin_flow(message.from_user.id)
        bot.send_message(message.chat.id, "👑 АДМИН-ПАНЕЛЬ", reply_markup=admin_menu_kb())

    @bot.message_handler(commands=["top", "rating"])
    def handle_top_cmd(message: Message) -> None:
        uid = int(message.from_user.id)
        try:
            db.ensure_user(uid, message.from_user.username, None)
        except Exception:
            pass
        if db.is_blocked(uid):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return

        top = db.get_leaderboard_by_balance(limit=10)
        me = db.get_user_rank_position_by_balance(uid)
        medals = ["👑", "🥈", "🥉"]

        lines: list[str] = ["🏆 <b>ТОП-10 игроков</b>", "━━━━━━━━━━━━━━━━━━━━", ""]
        for i, row in enumerate(top, 1):
            prefix = medals[i - 1] if i <= 3 else f"{i}."
            user_id = int(row.get("user_id") or 0)
            username = str(row.get("username") or "").strip()
            uname = f"@{username} (ID {user_id})" if username else f"ID {user_id}"
            lines.append(f"{prefix} {uname} — {_fmt_int(int(row.get('balance_points', 0) or 0))} баллов")

        if me:
            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"📍 <b>Твоё место: #{me['position']}</b>")
            lines.append(f"💰 Твой баланс: {_fmt_int(int(me.get('balance_points', 0) or 0))} баллов")

        bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=rating_main_kb())

    @bot.message_handler(commands=["leaderboard"])
    def handle_leaderboard_level_cmd(message: Message) -> None:
        leaders = db.get_leaderboard_by_level(limit=10)
        if not leaders:
            bot.send_message(message.chat.id, "Пока нет данных.")
            return
        lines = ["🏆 Топ по уровню:\n"]
        for u in leaders:
            uname = ("@" + u["username"]) if u.get("username") else f"ID {u['user_id']}"
            lines.append(f"{u['pos']}. {uname} — ур. {u['level']} ({u['rank']})")
        bot.send_message(message.chat.id, "\n".join(lines))

    @bot.message_handler(commands=["achievements"])
    def handle_achievements_cmd(message: Message) -> None:
        data = db.get_user_achievements(message.from_user.id)
        unlocked = data.get("unlocked", [])
        total = int(data.get("total", 0))
        lines = [f"🏆 Достижения: {len(unlocked)} из {total}\n"]
        if not unlocked:
            lines.append("Пока нет достижений. Выполняйте задания и играйте!")
            bot.send_message(message.chat.id, "\n".join(lines))
            return
        for a in unlocked[:20]:
            lines.append(f"{a['icon']} {a['title']} — {a['description']}")
        bot.send_message(message.chat.id, "\n".join(lines))

    @bot.message_handler(content_types=["dice"])
    def handle_user_dice(message: Message) -> None:
        uid = message.from_user.id
        s = session(uid)

        # Обрабатываем только если у пользователя активна игра в кости
        if not s.dice_active or s.dice_bet is None or s.dice_bot_value is None:
            return

        # Блокированных можно просто игнорировать в этой игре
        if db.is_blocked(uid):
            s.dice_active = False
            s.dice_bet = None
            s.dice_bot_value = None
            return

        user_val = message.dice.value if message.dice else 0
        bot_val = int(s.dice_bot_value or 0)
        bet = int(s.dice_bet or 0)

        # Делаем небольшую паузу, чтобы анимация кубика докрутилась
        try:
            bot.send_message(uid, "⏳ Кости крутятся...")
        except Exception:
            pass

        def _finish_round() -> None:
            now_ts = int(time.time())
            try:
                vip_active = bool(db.is_vip_active(uid, now_ts=now_ts))
            except Exception:
                vip_active = False

            if user_val > bot_val:
                mult = 1.9
                if vip_active:
                    mult = 1.95
                win_amount = int(bet * mult)
                db.add_balance(uid, win_amount)
                result_text = (
                    f"🎲 Ты бросил: {user_val}\n"
                    f"🤖 Бот бросил: {bot_val}\n\n"
                    f"🎉 Победа! Ты выиграл {_fmt_points_ui(int(win_amount))} баллов."
                )
            elif user_val < bot_val:
                result_text = (
                    f"🎲 Ты бросил: {user_val}\n"
                    f"🤖 Бот бросил: {bot_val}\n\n"
                    f"😢 Ты проиграл ставку {_fmt_points_ui(int(bet))} баллов."
                )
            else:
                db.add_balance(uid, bet)
                result_text = (
                    f"🎲 Ты бросил: {user_val}\n"
                    f"🤖 Бот бросил: {bot_val}\n\n"
                    "🤝 Ничья! Ставка возвращена."
                )

            # Обновляем лимит игр в час
            win_meta = db.get_dice_window(uid) or {"hour_ts": 0, "games_in_hour": 0}
            hour_start = (now_ts // 3600) * 3600
            if int(win_meta.get("hour_ts") or 0) != hour_start:
                games_in_hour = 0
            else:
                games_in_hour = int(win_meta.get("games_in_hour") or 0)
            games_in_hour += 1
            db.update_dice_window(uid, hour_ts=hour_start, games_in_hour=games_in_hour)

            # Сбрасываем состояние игры
            s.dice_active = False
            s.dice_bet = None
            s.dice_bot_value = None

            text, km = _build_dice_screen()
            bot.send_message(
                message.chat.id,
                result_text + "\n\n" + text,
                reply_markup=km,
            )

        threading.Timer(3.0, _finish_round).start()
        return

    @bot.message_handler(func=lambda m: m.text == "❓ Поддержка")
    def handle_support(message: Message) -> None:
        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        bot.send_message(message.chat.id, "Поддержка:", reply_markup=support_kb(settings.admin_id))

    @bot.message_handler(func=lambda m: _is_admin(m.from_user.id, settings) and m.text == "📸 Проверка заданий")
    def admin_review_tasks(message: Message) -> None:
        item = db.get_pending_submission()
        if not item:
            bot.send_message(message.chat.id, "Нет заданий на проверку.")
            return
        bot.send_photo(
            message.chat.id,
            photo=item["photo_file_id"],
            caption=(
                f"👤 @{item['username'] or 'без_ника'} (ID {item['user_id']})\n"
                f"🎯 {item['task_title']}\n"
                f"💰 {item['reward_points']} баллов\n\n"
                f"🆔 Submission: {item['submission_id']}"
            ),
            reply_markup=admin_review_submission_kb(item["submission_id"]),
        )

    @bot.message_handler(func=lambda m: _is_admin(m.from_user.id, settings) and m.text == "💸 Выводы")
    def admin_review_withdraw(message: Message) -> None:
        item = db.get_pending_withdrawal()
        if not item:
            bot.send_message(message.chat.id, "Нет заявок на вывод.")
            return
        bot.send_message(
            message.chat.id,
            (
                f"👤 @{item['username'] or 'без_ника'} (ID {item['user_id']})\n"
                f"💰 {item['amount_rub']}₽\n"
                f"🏦 {item['bank']}\n"
                f"📱 {item['requisites']}\n\n"
                f"🆔 Withdrawal: {item['withdrawal_id']}"
            ),
            reply_markup=admin_review_withdraw_kb(item["withdrawal_id"]),
        )

    @bot.message_handler(
        func=lambda m: _is_admin(m.from_user.id, settings) and (m.text in ("👥 Пользователи", "👤 Пользователи"))
    )
    def admin_users(message: Message) -> None:
        uid = int(message.from_user.id)
        chat_id = int(message.chat.id)
        try:
            _clear_temp_notice(uid)
        except Exception:
            pass

        reset_admin_flow(uid)

        # Force a fresh panel message so it appears at the bottom.
        try:
            s = session(uid)
            s.panel_chat_id = chat_id
            s.panel_message_id = None
        except Exception:
            s = None

        show_screen(chat_id=chat_id, user_id=uid, screen="admin_users:list:0", push_history=True)

        # If panel failed to send (Telegram rejected text / other error), show a visible fallback.
        try:
            s2 = session(uid)
            if not getattr(s2, "panel_message_id", None):
                bot.send_message(chat_id, "⚠️ Не удалось открыть список пользователей. Попробуй ещё раз (/menu → 🛠 Админка).")
        except Exception:
            pass

    @bot.message_handler(func=lambda m: _is_admin(m.from_user.id, settings) and m.text == "📊 Статистика")
    def admin_stats(message: Message) -> None:
        reset_admin_flow(message.from_user.id)
        _safe_delete_message(bot, int(message.chat.id), int(message.message_id))
        show_screen(chat_id=int(message.chat.id), user_id=int(message.from_user.id), screen="admin_stats:menu", push_history=True)

    @bot.message_handler(func=lambda m: _is_admin(m.from_user.id, settings) and m.text == "⚔ Сервер дуэлей")
    def admin_duel_server(message: Message) -> None:
        reset_admin_flow(message.from_user.id)
        _send_admin_duel_server_menu(message.chat.id)

    @bot.message_handler(func=lambda m: _is_admin(m.from_user.id, settings) and m.text == "⬅ Выйти из админки")
    def admin_exit_panel(message: Message) -> None:
        reset_admin_flow(message.from_user.id)
        _safe_delete_message(bot, int(message.chat.id), int(message.message_id))
        _set_reply_keyboard_silent(message.chat.id, main_menu_kb(is_admin=_is_admin(message.from_user.id, settings)))

    @bot.message_handler(func=lambda m: _is_admin(m.from_user.id, settings) and m.text == "➕ Добавить задание")
    def admin_add_task(message: Message) -> None:
        reset_admin_flow(message.from_user.id)
        s = session(message.from_user.id)
        s.admin_add_task_step = "type"
        bot.send_message(message.chat.id, "Выбери тип задания:", reply_markup=admin_add_task_type_kb())

    @bot.message_handler(func=lambda m: _is_admin(m.from_user.id, settings) and m.text == "🎁 Подарить баллы")
    def admin_gift_entry(message: Message) -> None:
        uid = int(message.from_user.id)
        reset_admin_flow(uid)
        s = session(uid)
        s.admin_flow = "gift_pick_user"
        s.admin_gift_notify = True
        bot.send_message(message.chat.id, "🎁 Подарить баллы\n\nВведи ID пользователя (число) или @username:")

    @bot.message_handler(content_types=["photo"])
    def handle_photo(message: Message) -> None:
        _channel_on_activity(message.from_user.id, chat_id=message.chat.id, message_id=message.message_id)
        s = session(message.from_user.id)
        if not s.awaiting_proof_task_id:
            return
        if db.is_blocked(message.from_user.id):
            bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
            return

        task_id = s.awaiting_proof_task_id
        task_code = s.awaiting_proof_task_code or ""
        file_id = message.photo[-1].file_id
        submission_id = db.create_submission(message.from_user.id, task_id, file_id)
        s.awaiting_proof_task_id = None
        s.awaiting_proof_task_code = None

        if task_code == "tiktok_comment":
            db.update_user_task(message.from_user.id, task_id, status="pending")

        bot.send_message(
            message.chat.id,
            "🕒 Ваш скрин отправлен на проверку.\nПроверка займет до 24 часов.\nПосле успешной проверки баллы будут зачислены.",
            reply_markup=main_menu_kb(is_admin=_is_admin(message.from_user.id, settings)),
        )

        task = db.get_task(task_id)
        title = task.title if task else f"Task {task_id}"
        reward = _next_reward_for_task(message.from_user.id, task) if task else 0

        bot.send_photo(
            settings.admin_id,
            photo=file_id,
            caption=(
                f"👤 @{message.from_user.username or 'без_ника'} (ID {message.from_user.id})\n"
                f"🎯 {title}\n"
                f"💰 {_fmt_points_ui(int(reward))} баллов\n\n"
                f"🆔 Submission: {submission_id}"
            ),
            reply_markup=admin_review_submission_kb(submission_id),
        )

    @bot.message_handler(func=lambda m: True, content_types=["text"])
    def handle_text_fallback(message: Message) -> None:
        uid = int(message.from_user.id)
        text_raw = (message.text or "").strip()

        # Any user action should clear temporary notices and may trigger weekly event auto-message.
        try:
            _channel_on_activity(uid, chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass

        # --- universal bet input ---
        try:
            s_bet = session(uid)
        except Exception:
            s_bet = None
        if s_bet is not None and getattr(s_bet, "awaiting_bet_for_game", None):
            game = str(getattr(s_bet, "awaiting_bet_for_game", "") or "")
            min_bet, max_bet = _bet_limits_for(uid)

            try:
                balance_now = int(db.get_balance(uid) or 0)
            except Exception:
                balance_now = 0

            # parse number
            raw = text_raw.replace(" ", "").replace("_", "")
            if len(raw) > 12:
                bot.send_message(message.chat.id, "Слишком большое число. Введите сумму короче (до 12 цифр).")
                return
            if not raw.isdigit():
                bot.send_message(message.chat.id, "Отправь число (например 750) или выбери кнопку.")
                return
            bet = int(raw)
            if bet <= 0:
                bot.send_message(message.chat.id, "Отправь число (например 750) или выбери кнопку.")
                return
            if bet < min_bet or bet > max_bet:
                bot.send_message(message.chat.id, _bet_out_of_range_text(bet=bet, min_bet=min_bet, max_bet=max_bet))
                return
            if bet > balance_now:
                bot.send_message(
                    message.chat.id,
                    f"Недостаточно баллов. Баланс: {_fmt_points_ui(balance_now)}. Выбери ставку ниже.\n"
                    "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                )
                return

            # Persist last bet (top-5)
            try:
                db.push_last_bet(uid, game, bet, limit=5)
            except Exception:
                pass

            edit_chat_id = getattr(s_bet, "awaiting_bet_chat_id", None)
            edit_message_id = getattr(s_bet, "awaiting_bet_message_id", None)

            # clear awaiting state
            s_bet.awaiting_bet_for_game = None
            s_bet.awaiting_bet_chat_id = None
            s_bet.awaiting_bet_message_id = None

            # Start game using existing entry points.
            if game == "dice":
                edit_mid: int | None = None
                try:
                    if edit_chat_id is not None and edit_message_id is not None and int(edit_chat_id) == int(message.chat.id):
                        edit_mid = int(edit_message_id)
                except Exception:
                    edit_mid = None

                _dice_start_auto_game(chat_id=int(message.chat.id), uid=uid, bet=bet, edit_message_id=edit_mid)
                return

            if game == "wheel":
                # Prepare the roll screen (same as selecting wheel bet).
                now_ts = int(time.time())
                hour_start = (now_ts // 3600) * 3600
                win_meta = db.get_wheel_window(uid) or {"hour_ts": 0, "games_in_hour": 0}
                if int(win_meta.get("hour_ts") or 0) != hour_start:
                    games_in_hour = 0
                else:
                    games_in_hour = int(win_meta.get("games_in_hour") or 0)
                if games_in_hour >= WHEEL_HOURLY_LIMIT:
                    text, km = _build_wheel_screen(uid)
                    bot.send_message(message.chat.id, "❌ Лимит игр на этот час исчерпан.\n\n" + text, reply_markup=km)
                    return
                if balance_now < bet:
                    bot.send_message(
                        message.chat.id,
                        f"Недостаточно баллов. Баланс: {_fmt_points_ui(balance_now)}. Выбери ставку ниже.\n"
                        "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                    )
                    return

                s = session(uid)
                s.wheel_active = True
                s.wheel_bet = bet

                rewards = _wheel_rewards_for_bet(int(bet))
                text = (
                    "🎡 <b>Колесо фортуны</b>\n\n"
                    f"💰 <b>Ставка {_fmt_points_ui(int(bet))} баллов принята</b>\n\n"
                    "🎁 <b>Награды за бросок 🎲</b>\n"
                )
                for dice_value, (desc, _) in rewards.items():
                    text += f"🎲 {dice_value} — {desc}\n"
                text += "\n⬇ Нажмите кнопку ниже, чтобы кинуть кубик"

                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("🎲 Кинуть кубик", callback_data="wheel:roll"))

                # Try to edit original message, else send new.
                if edit_chat_id and edit_message_id:
                    try:
                        bot.edit_message_text(text, int(edit_chat_id), int(edit_message_id), reply_markup=kb, parse_mode="HTML")
                        return
                    except Exception:
                        pass
                bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="HTML")
                return

            if game == "ladder":
                # Start ladder similarly to callback path (deduct bet, set state, edit if possible).
                if db.is_blocked(uid):
                    bot.send_message(message.chat.id, "Ваш аккаунт заблокирован.")
                    return
                now_ts = int(time.time())
                spent = db.try_spend_points(uid, int(bet))
                if not spent.get("ok"):
                    bot.send_message(message.chat.id, f"Недостаточно баллов. Баланс: {_fmt_points_ui(int(spent.get('balance') or 0))}.")
                    return
                s = session(uid)
                s.ladder_active = True
                s.ladder_bet = bet
                s.ladder_step = 0
                s.ladder_multiplier = 1.0
                s.ladder_chat_id = int(message.chat.id)
                s.ladder_message_id = int(edit_message_id) if edit_message_id else None
                s.ladder_rows = []
                s.ladder_mines = [random.randint(0, 2) for _ in range(6)]
                s.ladder_choices = [None for _ in range(6)]
                s.ladder_current_mine = int(s.ladder_mines[0])
                try:
                    wk = db.week_key_utc(now_ts)
                    db.add_weekly_progress(uid, week_key=wk, code="ladder_games", delta=1, now_ts=now_ts)
                except Exception:
                    pass
                txt = _ladder_screen_text_v3(bet=bet, step=s.ladder_step, mult=s.ladder_multiplier, mines=s.ladder_mines, choices=s.ladder_choices)
                km = ladder_field_kb(step=s.ladder_step, mines=s.ladder_mines, choices=s.ladder_choices, show_cashout=False)
                if edit_chat_id and edit_message_id:
                    try:
                        bot.edit_message_text(txt, chat_id=int(edit_chat_id), message_id=int(edit_message_id), reply_markup=km)
                        return
                    except Exception:
                        pass
                bot.send_message(message.chat.id, txt, reply_markup=km)
                return

            if game == "rps":
                spent = db.try_spend_points(uid, int(bet))
                if not spent.get("ok"):
                    bot.send_message(message.chat.id, f"Недостаточно баллов. Баланс: {_fmt_points_ui(int(spent.get('balance') or 0))}.")
                    return
                s = session(uid)
                s.rps_active = True
                s.rps_stake = bet
                s.rps_bot_choice = random.choice(("rock", "paper", "scissors"))
                txt = "🤖 Я сделал выбор. Теперь твой ход — выбери: камень, ножницы или бумага."
                if edit_chat_id and edit_message_id:
                    try:
                        bot.edit_message_text(txt, chat_id=int(edit_chat_id), message_id=int(edit_message_id), reply_markup=rps_kb())
                        return
                    except Exception:
                        pass
                bot.send_message(message.chat.id, txt, reply_markup=rps_kb())
                return

            if game == "mines":
                # Update mines bet inside setup flow (no-bet mode ignores stake).
                s = session(uid)
                mode = str(getattr(s, "mines_mode", "classic") or "classic")
                if mode == "nobet":
                    bot.send_message(message.chat.id, "В режиме «Без ставок» ставка не нужна.")
                    return
                s.mines_bet = int(bet)
                s.mines_state = "setup"
                if edit_chat_id and edit_message_id:
                    try:
                        bot.edit_message_text(
                            "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                            chat_id=int(edit_chat_id),
                            message_id=int(edit_message_id),
                            reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode=mode, attempts_text=None),
                        )
                        return
                    except Exception:
                        pass
                bot.send_message(message.chat.id, "✅ Ставка для Мины установлена. Вернитесь к параметрам игры.")
                return

            bot.send_message(message.chat.id, "❌ Неизвестная игра для ставки")
            return

        # --- CryptoMine buy quantity input ---
        try:
            s_cm = session(uid)
        except Exception:
            s_cm = None
        if s_cm is not None and bool(getattr(s_cm, "cm_buy_pending", False)):
            cat = str(getattr(s_cm, "cm_buy_category", "") or "")
            code = str(getattr(s_cm, "cm_buy_code", "") or "")
            prefix = str(getattr(s_cm, "cm_buy_prefix", "cm") or "cm")

            raw = text_raw.replace(" ", "")
            if not raw.isdigit():
                bot.send_message(message.chat.id, "❌ Введите количество числом (например 20)")
                return
            qty = int(raw)
            if qty <= 0:
                bot.send_message(message.chat.id, "❌ Количество должно быть больше 0")
                return

            try:
                max_qty = int(getattr(s_cm, "cm_buy_max_qty", 0) or 0)
            except Exception:
                max_qty = 0
            if max_qty > 0 and qty > max_qty:
                bot.send_message(message.chat.id, f"❌ Слишком много. Максимум: {max_qty}")
                return

            ok, msg = _cm_try_buy(uid, cat, code, qty=qty)
            if not ok:
                bot.send_message(message.chat.id, msg)
                return

            # cleanup prompt message
            try:
                cid = int(getattr(s_cm, "cm_buy_prompt_chat_id", 0) or 0)
                mid = int(getattr(s_cm, "cm_buy_prompt_message_id", 0) or 0)
                if cid and mid:
                    _safe_delete_message(bot, cid, mid)
            except Exception:
                pass

            # update panel (item screen by default; farm view if applicable)
            panel_chat_id = int(getattr(s_cm, "cm_buy_panel_chat_id", 0) or 0)
            panel_message_id = int(getattr(s_cm, "cm_buy_panel_message_id", 0) or 0)

            # clear pending state
            s_cm.cm_buy_pending = False
            s_cm.cm_buy_category = None
            s_cm.cm_buy_code = None
            s_cm.cm_buy_prefix = None
            s_cm.cm_buy_panel_chat_id = None
            s_cm.cm_buy_panel_message_id = None
            s_cm.cm_buy_prompt_chat_id = None
            s_cm.cm_buy_prompt_message_id = None
            s_cm.cm_buy_max_qty = None

            # If user is in farm panel and bought GPU, refresh farm view for quick install.
            try:
                if str(cat) == "gpu" and getattr(s_cm, "cmf_mode", False) and int(getattr(s_cm, "cmf_chat_id", 0) or 0) == int(panel_chat_id):
                    if getattr(s_cm, "cmf_message_id", None):
                        bot.edit_message_text(
                            _cmf_farm_text(uid),
                            chat_id=int(panel_chat_id),
                            message_id=int(s_cm.cmf_message_id),
                            reply_markup=cryptomine_farm_kb(),
                        )
                else:
                    if panel_chat_id and panel_message_id:
                        item = _CM_ITEMS.get(str(cat), {}).get(str(code)) or {}
                        bot.edit_message_text(
                            _cm_item_text(str(cat), str(code), uid=uid, detailed=False),
                            chat_id=int(panel_chat_id),
                            message_id=int(panel_message_id),
                            reply_markup=cryptomine_item_kb(
                                category=str(cat),
                                code=str(code),
                                show_badge=item.get("badge"),
                                prefix=str(prefix),
                                back_to_category_prefix=str(prefix),
                            ),
                        )
            except Exception:
                pass

            # show result (temp notice style for equipment)
            try:
                if str(cat) in {"gpu", "psu", "cool", "slots"}:
                    sent = bot.send_message(message.chat.id, msg)
                    _remember_temp_notice(uid, sent)
                else:
                    bot.send_message(message.chat.id, msg)
            except Exception:
                pass
            return

        # If user is in an active admin-chat, forward plain text to admin.
        # We do not intercept menu buttons/commands to avoid breaking normal bot navigation.
        try:
            s_dialog = session(int(uid))
        except Exception:
            s_dialog = None

        if s_dialog and str(getattr(s_dialog, "dialog_expect", "") or "") in {"user_reply", "admin_reply"}:
            did = int(getattr(s_dialog, "dialog_id", 0) or 0)
            role = str(getattr(s_dialog, "dialog_role", "") or "")
            msg_txt = (text_raw or "").strip()

            if did > 0 and msg_txt and not msg_txt.startswith("/"):
                d = None
                try:
                    d = db.get_dialog(int(did))
                except Exception:
                    d = None

                if d and str(d.get("status") or "") != "closed":
                    if role == "user" and int(d.get("user_id") or 0) == int(uid):
                        try:
                            db.add_dialog_message(
                                dialog_id=int(did),
                                sender_type="user",
                                sender_id=int(uid),
                                message_text=str(msg_txt),
                                sent_at=int(time.time()),
                            )
                        except Exception:
                            pass
                        try:
                            admin_id = int(d.get("admin_id") or 0)
                            if admin_id > 0:
                                uname = message.from_user.username
                                prefix = f"@{uname}" if uname else "без_ника"
                                bot.send_message(admin_id, f"💬 Сообщение (диалог #{did}) от пользователя {prefix} (ID {uid}):\n{msg_txt}")
                        except Exception:
                            pass
                        try:
                            bot.send_message(int(uid), "✅ Отправлено.", reply_markup=dialog_user_kb(int(did)))
                        except Exception:
                            pass

                        s_dialog.dialog_expect = None
                        s_dialog.dialog_id = None
                        s_dialog.dialog_role = None
                        return

                    if role == "admin" and int(d.get("admin_id") or 0) == int(uid):
                        try:
                            db.add_dialog_message(
                                dialog_id=int(did),
                                sender_type="admin",
                                sender_id=int(uid),
                                message_text=str(msg_txt),
                                sent_at=int(time.time()),
                            )
                        except Exception:
                            pass
                        try:
                            user_id = int(d.get("user_id") or 0)
                            if user_id > 0:
                                bot.send_message(user_id, f"💬 Сообщение от админа (диалог #{did}):\n{msg_txt}")
                        except Exception:
                            pass
                        try:
                            bot.send_message(int(uid), "✅ Отправлено.", reply_markup=dialog_admin_kb(int(did), history_count=5))
                        except Exception:
                            pass

                        s_dialog.dialog_expect = None
                        s_dialog.dialog_id = None
                        s_dialog.dialog_role = None
                        return

            # invalid state / empty text -> just clear
            try:
                s_dialog.dialog_expect = None
                s_dialog.dialog_id = None
                s_dialog.dialog_role = None
            except Exception:
                pass

        if not _is_admin(uid, settings):
            admin_id: int | None = None
            with admin_chat_lock:
                admin_id = admin_chat_map.get(int(uid))
            if admin_id and text_raw and not text_raw.startswith("/"):
                known_buttons = {
                    "✨ Фарм баллов",
                    "🎮 Мини игры",
                    "💼 Профиль",
                    "🛒 МАГАЗИН",
                    "⛏️ Майнинг ферма",
                    "❓ Поддержка",
                    "🛠 Админка",
                }
                try:
                    # CryptoMine reply-keyboard texts
                    known_buttons |= set(_CMF_REPLY_TEXTS)
                except Exception:
                    pass

                if text_raw not in known_buttons:
                    try:
                        uname = message.from_user.username
                        prefix = f"@{uname}" if uname else "без_ника"
                        bot.send_message(int(admin_id), f"💬 Сообщение от пользователя {prefix} (ID {uid}):\n{text_raw}")
                    except Exception:
                        pass
                    return

        # Admin chat mode: any admin text goes to the selected user.
        if _is_admin(uid, settings):
            s_admin = session(uid)
            if str(getattr(s_admin, "admin_flow", None) or "") == "chat" and getattr(s_admin, "admin_target_user_id", None):
                target_uid = int(s_admin.admin_target_user_id or 0)
                if target_uid > 0 and text_raw:
                    try:
                        bot.send_message(target_uid, f"💬 Сообщение от админа:\n{text_raw}")
                    except Exception:
                        bot.send_message(message.chat.id, "⚠️ Не удалось отправить сообщение пользователю.")
                    return

            # Admin gift flow text steps
            flow = str(getattr(s_admin, "admin_flow", None) or "")
            if flow == "gift_pick_user":
                raw = text_raw
                target_uid: int | None = None
                if raw.isdigit():
                    try:
                        target_uid = int(raw)
                    except Exception:
                        target_uid = None
                elif raw.startswith("@"):
                    try:
                        target_uid = db.find_user_id_by_username(raw)
                    except Exception:
                        target_uid = None

                if not target_uid:
                    bot.send_message(
                        message.chat.id,
                        "❌ Пользователь не найден.\n\n"
                        "Подсказка: по @username работает только если он уже есть в базе (пользователь писал боту).\n"
                        "Попробуй ввести числовой ID.",
                    )
                    return

                # Ensure user exists in DB even if they never wrote the bot.
                try:
                    db.ensure_user(int(target_uid), None, None)
                except Exception:
                    pass

                s_admin.admin_target_user_id = int(target_uid)
                s_admin.admin_flow = None
                s_admin.admin_gift_amount = None
                s_admin.admin_gift_text = None
                s_admin.admin_gift_notify = True

                u = db.find_user(int(target_uid))
                if not u:
                    bot.send_message(message.chat.id, f"✅ Пользователь выбран: ID {int(target_uid)}")
                else:
                    status = "Заблокирован" if int(u.get("blocked") or 0) else "Активный"
                    bot.send_message(
                        message.chat.id,
                        "👤 Пользователь выбран\n\n"
                        f"ID: {u['user_id']}\n"
                        f"@{u['username'] or 'без_ника'}\n"
                        f"Баланс: {int(u.get('balance_points') or 0)}\n"
                        f"Статус: {status}",
                        reply_markup=admin_gift_user_kb(),
                    )
                return

            if flow == "gift_amount":
                if not text_raw.isdigit() or int(text_raw) <= 0:
                    bot.send_message(message.chat.id, "Введите сумму (целое число > 0):")
                    return
                s_admin.admin_gift_amount = int(text_raw)
                s_admin.admin_flow = None
                amt = int(s_admin.admin_gift_amount or 0)
                tid = int(s_admin.admin_target_user_id or 0)
                preview = (s_admin.admin_gift_text or "").strip()
                notify = bool(s_admin.admin_gift_notify)
                bot.send_message(
                    message.chat.id,
                    "🎁 Подтверждение\n\n"
                    f"Кому: {tid}\n"
                    f"Сумма: +{amt} баллов\n"
                    f"Уведомление: {'ВКЛ' if notify else 'ВЫКЛ'}\n\n"
                    f"Текст: {preview if preview else '(по умолчанию)'}",
                    reply_markup=admin_gift_confirm_kb(notify_enabled=notify),
                )
                return

            if flow == "gift_text":
                txt = text_raw
                if txt == "-":
                    txt = ""
                s_admin.admin_gift_text = txt
                s_admin.admin_flow = None

                amt = int(s_admin.admin_gift_amount or 0)
                tid = int(s_admin.admin_target_user_id or 0)
                notify = bool(s_admin.admin_gift_notify)
                preview = (s_admin.admin_gift_text or "").strip()
                bot.send_message(
                    message.chat.id,
                    "🎁 Подтверждение\n\n"
                    f"Кому: {tid}\n"
                    f"Сумма: +{amt} баллов\n"
                    f"Уведомление: {'ВКЛ' if notify else 'ВЫКЛ'}\n\n"
                    f"Текст: {preview if preview else '(по умолчанию)'}",
                    reply_markup=admin_gift_confirm_kb(notify_enabled=notify),
                )
                return

        # admin user lookup
        if _is_admin(message.from_user.id, settings) and session(message.from_user.id).admin_expect_user_lookup:
            if (message.text or "").strip().isdigit():
                uid = int(message.text.strip())
                u = db.find_user(uid)
                if not u:
                    bot.send_message(message.chat.id, "Пользователь не найден")
                else:
                    status = "Заблокирован" if u["blocked"] else "Активный"
                    bot.send_message(
                        message.chat.id,
                        f"ID: {u['user_id']}\n@{u['username'] or 'без_ника'}\nБаланс: {u['balance_points']}\nСтатус: {status}",
                    )
                session(message.from_user.id).admin_expect_user_lookup = False
                return

        # admin users panel input (edit-in-place)
        if _is_admin(message.from_user.id, settings):
            s_admin = session(message.from_user.id)
            expect = str(getattr(s_admin, "admin_users_expect", "") or "")
            if expect in ("search", "block_reason", "points_amount", "points_message"):
                txt = (message.text or "").strip()

                # best-effort: remove admin's input message to reduce spam
                try:
                    _safe_delete_message(bot, int(message.chat.id), int(message.message_id))
                except Exception:
                    pass

                chat_id_local = int(message.chat.id)
                admin_id_local = int(message.from_user.id)

                if expect == "search":
                    if not txt:
                        s_admin.admin_users_error = "Пустой запрос"
                        show_screen(chat_id=chat_id_local, user_id=admin_id_local, screen="admin_users:search", push_history=False)
                        return

                    target_id: int | None = None
                    if txt.isdigit():
                        try:
                            target_id = int(txt)
                        except Exception:
                            target_id = None
                    else:
                        # Accept both @username and username
                        raw_u = txt
                        if not raw_u.startswith("@"):
                            raw_u = "@" + raw_u
                        try:
                            target_id = db.find_user_id_by_username(raw_u)
                        except Exception:
                            target_id = None

                    if not target_id:
                        s_admin.admin_users_error = "Пользователь не найден"
                        show_screen(chat_id=chat_id_local, user_id=admin_id_local, screen="admin_users:search", push_history=False)
                        return

                    # Ensure user exists in DB if admin enters a raw numeric ID.
                    try:
                        db.ensure_user(int(target_id), None, None)
                    except Exception:
                        pass

                    s_admin.admin_users_expect = None
                    s_admin.admin_users_error = None
                    show_screen(chat_id=chat_id_local, user_id=admin_id_local, screen=f"admin_users:card:{int(target_id)}", push_history=True)
                    return

                if expect == "block_reason":
                    target_id = int(getattr(s_admin, "admin_users_target_user_id", 0) or 0)
                    action = str(getattr(s_admin, "admin_users_pending_action", "") or "")
                    if not target_id or action not in ("block", "unblock"):
                        s_admin.admin_users_expect = None
                        s_admin.admin_users_pending_action = None
                        show_screen(chat_id=chat_id_local, user_id=admin_id_local, screen="admin_users:home", push_history=False)
                        return

                    reason = txt
                    do_block = action == "block"

                    # Admins cannot be blocked/unblocked via admin panel.
                    try:
                        admin_ids = set(getattr(settings, "admin_ids", frozenset({settings.admin_id})))
                    except Exception:
                        admin_ids = {int(settings.admin_id)}
                    if int(target_id) in admin_ids:
                        s_admin.admin_users_error = "❌ Нельзя блокировать/разблокировать администратора."
                        s_admin.admin_users_expect = None
                        s_admin.admin_users_pending_action = None
                        show_screen(chat_id=chat_id_local, user_id=admin_id_local, screen=f"admin_users:card:{target_id}", push_history=False)
                        return

                    db.set_blocked(int(target_id), bool(do_block))
                    if bool(s_admin.admin_users_notify):
                        if do_block:
                            _admin_users_send_notify(
                                int(target_id),
                                "⛔ Ваш аккаунт заблокирован." + (f"\nПричина: {reason}" if reason else ""),
                            )
                        else:
                            _admin_users_send_notify(
                                int(target_id),
                                "✅ Ваш аккаунт разблокирован." + (f"\nКомментарий: {reason}" if reason else ""),
                            )

                    s_admin.admin_users_expect = None
                    s_admin.admin_users_pending_action = None
                    s_admin.admin_users_error = None
                    show_screen(chat_id=chat_id_local, user_id=admin_id_local, screen=f"admin_users:card:{target_id}", push_history=False)
                    return

                if expect == "points_amount":
                    target_id = int(getattr(s_admin, "admin_users_target_user_id", 0) or 0)
                    sign = 1 if int(getattr(s_admin, "admin_users_points_sign", 1) or 1) >= 0 else -1
                    amt = _parse_points_amount(txt)
                    if amt is None or amt <= 0:
                        s_admin.admin_users_error = "Введите корректную сумму"
                        sign_chr = "+" if sign == 1 else "-"
                        show_screen(
                            chat_id=chat_id_local,
                            user_id=admin_id_local,
                            screen=f"admin_users:points_amount:{sign_chr}:{target_id}",
                            push_history=False,
                        )
                        return

                    s_admin.admin_users_pending_value = int(sign * int(amt))
                    s_admin.admin_users_expect = None
                    s_admin.admin_users_error = None
                    show_screen(chat_id=chat_id_local, user_id=admin_id_local, screen=f"admin_users:points_confirm:{target_id}", push_history=True)
                    return

                if expect == "points_message":
                    target_id = int(getattr(s_admin, "admin_users_target_user_id", 0) or 0)
                    if txt == "-":
                        txt = ""
                    s_admin.admin_users_pending_text = txt
                    s_admin.admin_users_expect = None
                    show_screen(chat_id=chat_id_local, user_id=admin_id_local, screen=f"admin_users:points_confirm:{target_id}", push_history=False)
                    return

        # admin tournament wizard (MVP)
        if _is_admin(message.from_user.id, settings):
            s_admin = session(message.from_user.id)
            if s_admin.admin_tourn_step:
                step = str(s_admin.admin_tourn_step)
                txt = (message.text or "").strip()
                now_ts = int(time.time())

                if step == "max_players":
                    if not txt.isdigit() or int(txt) not in (16, 32, 64):
                        bot.send_message(message.chat.id, "Введите 16 / 32 / 64:")
                        return
                    s_admin.admin_tourn_max_players = int(txt)
                    s_admin.admin_tourn_step = "start_in_min"
                    bot.send_message(message.chat.id, "Через сколько минут старт? (например 10)")
                    return

                if step == "start_in_min":
                    if not txt.isdigit() or int(txt) < 1 or int(txt) > 24 * 60:
                        bot.send_message(message.chat.id, "Введите число минут от 1 до 1440:")
                        return
                    s_admin.admin_tourn_start_in_min = int(txt)
                    s_admin.admin_tourn_step = "entry_fee"
                    bot.send_message(message.chat.id, "Взнос (баллы). 0 = бесплатно:")
                    return

                if step == "entry_fee":
                    if not txt.isdigit() or int(txt) < 0:
                        bot.send_message(message.chat.id, "Введите число (0 или больше):")
                        return
                    s_admin.admin_tourn_entry_fee = int(txt)
                    s_admin.admin_tourn_step = "prize1"
                    bot.send_message(message.chat.id, "Приз за 1 место (баллы):")
                    return

                if step == "prize1":
                    if not txt.isdigit() or int(txt) < 0:
                        bot.send_message(message.chat.id, "Введите число (0 или больше):")
                        return
                    s_admin.admin_tourn_prize1 = int(txt)
                    s_admin.admin_tourn_step = "prize2"
                    bot.send_message(message.chat.id, "Приз за 2 место (баллы):")
                    return

                if step == "prize2":
                    if not txt.isdigit() or int(txt) < 0:
                        bot.send_message(message.chat.id, "Введите число (0 или больше):")
                        return
                    s_admin.admin_tourn_prize2 = int(txt)
                    s_admin.admin_tourn_step = "prize3"
                    bot.send_message(message.chat.id, "Приз за 3 место (баллы):")
                    return

                if step == "prize3":
                    if not txt.isdigit() or int(txt) < 0:
                        bot.send_message(message.chat.id, "Введите число (0 или больше):")
                        return
                    s_admin.admin_tourn_prize3 = int(txt)
                    s_admin.admin_tourn_step = "confirm"

                    max_players = int(s_admin.admin_tourn_max_players or 0)
                    start_in_min = int(s_admin.admin_tourn_start_in_min or 0)
                    entry_fee = int(s_admin.admin_tourn_entry_fee or 0)
                    p1 = int(s_admin.admin_tourn_prize1 or 0)
                    p2 = int(s_admin.admin_tourn_prize2 or 0)
                    p3 = int(s_admin.admin_tourn_prize3 or 0)
                    start_at = now_ts + start_in_min * 60
                    bot.send_message(
                        message.chat.id,
                        "🏆 Турнир (MVP)\n\n"
                        f"Участники: {max_players}\n"
                        f"Старт: через {start_in_min} мин (UTC: {_fmt_ts_short(start_at)})\n"
                        f"Взнос: {entry_fee} баллов\n"
                        f"Призы: 🥇{p1} / 🥈{p2} / 🥉{p3}\n\n"
                        "Создать? (да/нет)",
                    )
                    return

                if step == "confirm":
                    ans = txt.lower()
                    if ans not in ("да", "нет"):
                        bot.send_message(message.chat.id, "Ответьте: да или нет")
                        return
                    if ans == "нет":
                        reset_admin_flow(message.from_user.id)
                        bot.send_message(message.chat.id, "Ок, отменено.")
                        return

                    max_players = int(s_admin.admin_tourn_max_players or 0)
                    start_in_min = int(s_admin.admin_tourn_start_in_min or 0)
                    entry_fee = int(s_admin.admin_tourn_entry_fee or 0)
                    p1 = int(s_admin.admin_tourn_prize1 or 0)
                    p2 = int(s_admin.admin_tourn_prize2 or 0)
                    p3 = int(s_admin.admin_tourn_prize3 or 0)
                    start_at = now_ts + start_in_min * 60

                    prize = {"1": p1, "2": p2, "3": p3}
                    prize_pool = int(p1 + p2 + p3)
                    rules = {
                        "game": "mines_nobet",
                        "score": "opened_safe",
                        "tiebreak": "time_ms",
                        "deadline_seconds": int(TOURN_MATCH_DEADLINE_SECONDS),
                    }
                    res = db.create_tournament(
                        created_by_admin_id=int(message.from_user.id),
                        games=["mines_nobet"],
                        max_players=int(max_players),
                        prize_pool_points=int(prize_pool),
                        entry_fee_points=int(entry_fee),
                        prize=prize,
                        start_at=int(start_at),
                        rules=rules,
                    )
                    reset_admin_flow(message.from_user.id)
                    if not res.get("ok"):
                        bot.send_message(message.chat.id, "❌ Не удалось создать турнир.")
                        return
                    bot.send_message(message.chat.id, f"✅ Турнир создан. ID: {int(res.get('tournament_id') or 0)}")
                    return

        # withdraw requisites
        s = session(message.from_user.id)
        if s.withdraw_amount_rub and s.withdraw_bank and not s.withdraw_requisites:
            s.withdraw_requisites = (message.text or "").strip()
            bot.send_message(
                message.chat.id,
                f"Подтверди заявку:\n\n💰 {s.withdraw_amount_rub}₽\n🏦 {s.withdraw_bank}\n📱 {s.withdraw_requisites}",
                reply_markup=confirm_withdraw_kb(),
            )
            return

        # admin add task wizard
        if _is_admin(message.from_user.id, settings):
            s = session(message.from_user.id)
            # duel server wizard (counts / min/max)
            if s.admin_duel_server_step in ("add_count", "random_setmin", "random_setmax"):
                raw = (message.text or "").strip()
                if not raw.isdigit():
                    bot.send_message(message.chat.id, "Нужно число.")
                    return
                val = int(raw)

                if s.admin_duel_server_step == "add_count":
                    gt = str(s.admin_duel_server_game_type or "")
                    stake = int(s.admin_duel_server_stake or 0)
                    if gt not in ("dice", "rps") or stake <= 0 or val <= 0:
                        s.admin_duel_server_step = None
                        s.admin_duel_server_game_type = None
                        s.admin_duel_server_stake = None
                        bot.send_message(message.chat.id, "❌ Неверные параметры. Откройте меню ещё раз.")
                        return
                    created = 0
                    for _ in range(val):
                        db.create_duel(0, stake=stake, game_type=gt, is_bot=True)
                        created += 1
                    s.admin_duel_server_step = None
                    s.admin_duel_server_game_type = None
                    s.admin_duel_server_stake = None
                    bot.send_message(message.chat.id, f"✅ Создано дуэлей: {created}")
                    _send_admin_duel_server_menu(message.chat.id, ensure_random=False)
                    return

                if s.admin_duel_server_step == "random_setmin":
                    db.set_setting(DUEL_SERVER_RANDOM_MIN_KEY, str(max(0, val)))
                    s.admin_duel_server_step = None
                    bot.send_message(message.chat.id, "✅ Минимум обновлён.")
                    _send_admin_duel_server_menu(message.chat.id)
                    return

                if s.admin_duel_server_step == "random_setmax":
                    db.set_setting(DUEL_SERVER_RANDOM_MAX_KEY, str(max(0, val)))
                    s.admin_duel_server_step = None
                    bot.send_message(message.chat.id, "✅ Максимум обновлён.")
                    _send_admin_duel_server_menu(message.chat.id)
                    return

            if s.admin_add_task_step == "title":
                s.admin_add_task_title = (message.text or "").strip()
                s.admin_add_task_step = "desc"
                bot.send_message(message.chat.id, "Введи текст задания:")
                return
            if s.admin_add_task_step == "desc":
                s.admin_add_task_desc = (message.text or "").strip()
                s.admin_add_task_step = "reward"
                bot.send_message(message.chat.id, "Введи награду (число баллов):")
                return
            if s.admin_add_task_step == "reward":
                raw = (message.text or "").strip()
                if not raw.isdigit():
                    bot.send_message(message.chat.id, "Нужно число. Введи награду (баллы):")
                    return
                s.admin_add_task_reward = int(raw)
                s.admin_add_task_step = "limits"
                bot.send_message(message.chat.id, "Ограничения (текст) или '-' если нет:")
                return
            if s.admin_add_task_step == "limits":
                s.admin_add_task_limits = (message.text or "").strip()
                if s.admin_add_task_code == "tiktok_comment":
                    s.admin_add_task_step = "comment_text"
                    bot.send_message(message.chat.id, "Текст комментария (или '-' если не нужен):")
                else:
                    # finalize
                    _finalize_add_task(message.chat.id, s)
                return
            if s.admin_add_task_step == "comment_text":
                s.admin_add_task_comment_text = (message.text or "").strip()
                _finalize_add_task(message.chat.id, s)
                return

    def _finalize_add_task(chat_id: int, s: Session) -> None:
        title = (s.admin_add_task_title or "").strip()
        desc = (s.admin_add_task_desc or "").strip()
        reward = int(s.admin_add_task_reward or 0)
        limits = (s.admin_add_task_limits or "").strip()
        code = (s.admin_add_task_code or "").strip()

        if limits and limits != "-":
            desc = f"{desc}\n\nОграничения: {limits}"

        comment_text = (s.admin_add_task_comment_text or "").strip()
        if comment_text == "-":
            comment_text = ""

        task_id = db.create_task(
            code=code,
            title=title,
            description=desc,
            reward_points=reward,
            comment_text=(comment_text if comment_text else None),
        )
        reset_admin_flow(settings.admin_id)
        bot.send_message(chat_id, f"✅ Задание добавлено. ID: {task_id}")

    # --- Admin Duel Server (pool of bot-duels) ---

    DUEL_SERVER_AUTO_RECREATE_KEY = "duel_server_auto_recreate"
    DUEL_SERVER_RANDOM_ENABLED_KEY = "duel_server_random_enabled"
    DUEL_SERVER_RANDOM_MIN_KEY = "duel_server_random_min"
    DUEL_SERVER_RANDOM_MAX_KEY = "duel_server_random_max"
    DUEL_SERVER_RANDOM_GAMES_KEY = "duel_server_random_games"
    DUEL_SERVER_RANDOM_STAKES_KEY = "duel_server_random_stakes"

    def _get_bool_setting(key: str, default: bool = False) -> bool:
        raw = db.get_setting(key)
        if raw is None:
            return bool(default)
        return str(raw).strip() in ("1", "true", "True", "yes", "on")

    def _get_int_setting(key: str, default: int) -> int:
        raw = db.get_setting(key)
        if raw is None:
            return int(default)
        try:
            return int(str(raw).strip())
        except Exception:
            return int(default)

    def _get_set_setting_str(key: str, default: set[str]) -> set[str]:
        raw = db.get_setting(key)
        if not raw:
            return set(default)
        parts = [p.strip() for p in str(raw).split(",")]
        return {p for p in parts if p}

    def _get_set_setting_int(key: str, default: set[int]) -> set[int]:
        raw = db.get_setting(key)
        if not raw:
            return set(default)
        out: set[int] = set()
        for p in str(raw).split(","):
            p = p.strip()
            if not p:
                continue
            if p.isdigit():
                out.add(int(p))
        return out if out else set(default)

    def _save_set_setting_str(key: str, values: set[str]) -> None:
        db.set_setting(key, ",".join(sorted(values)))

    def _save_set_setting_int(key: str, values: set[int]) -> None:
        db.set_setting(key, ",".join(str(v) for v in sorted(values)))

    def _ensure_random_duel_pool() -> int:
        enabled = _get_bool_setting(DUEL_SERVER_RANDOM_ENABLED_KEY, default=False)
        if not enabled:
            return 0
        min_pool = max(0, _get_int_setting(DUEL_SERVER_RANDOM_MIN_KEY, default=0))
        max_pool = max(0, _get_int_setting(DUEL_SERVER_RANDOM_MAX_KEY, default=min_pool))
        if max_pool < min_pool:
            max_pool = min_pool

        games = _get_set_setting_str(DUEL_SERVER_RANDOM_GAMES_KEY, default={"dice", "rps"})
        stakes = _get_set_setting_int(DUEL_SERVER_RANDOM_STAKES_KEY, default={200, 500, 1000})
        games = {g for g in games if g in {"dice", "rps"}}
        stakes = {s for s in stakes if s in {200, 500, 1000}}
        if not games or not stakes:
            return 0

        current = db.count_open_server_duels()
        if current >= min_pool:
            return 0

        target = max_pool
        to_create = max(0, target - current)
        created = 0
        for _ in range(to_create):
            gt = random.choice(sorted(list(games)))
            st = random.choice(sorted(list(stakes)))
            db.create_duel(0, stake=int(st), game_type=str(gt), is_bot=True)
            created += 1
        return created

    def _admin_duel_server_menu_text() -> str:
        open_cnt = db.count_open_server_duels()
        auto_recreate = _get_bool_setting(DUEL_SERVER_AUTO_RECREATE_KEY, default=False)
        random_enabled = _get_bool_setting(DUEL_SERVER_RANDOM_ENABLED_KEY, default=False)
        min_pool = _get_int_setting(DUEL_SERVER_RANDOM_MIN_KEY, default=0)
        max_pool = _get_int_setting(DUEL_SERVER_RANDOM_MAX_KEY, default=0)
        return (
            "⚔ СЕРВЕР ДУЭЛЕЙ\n\n"
            f"Открытых дуэлей в пуле: {open_cnt}\n"
            f"♻ Пересоздавать после входа: {'ВКЛ' if auto_recreate else 'ВЫКЛ'}\n"
            f"🎲 Рандом дуэлей: {'ВКЛ' if random_enabled else 'ВЫКЛ'}\n"
            f"Диапазон пула (min/max): {int(min_pool)}/{int(max_pool)}"
        )

    def _send_admin_duel_server_menu(
        chat_id: int,
        *,
        edit: bool = False,
        message_id: int | None = None,
        ensure_random: bool = True,
    ) -> None:
        created = 0
        if ensure_random:
            try:
                created = _ensure_random_duel_pool()
            except Exception:
                created = 0

        auto_recreate = _get_bool_setting(DUEL_SERVER_AUTO_RECREATE_KEY, default=False)
        random_enabled = _get_bool_setting(DUEL_SERVER_RANDOM_ENABLED_KEY, default=False)
        max_pool = _get_int_setting(DUEL_SERVER_RANDOM_MAX_KEY, default=0)
        text = _admin_duel_server_menu_text()
        if created:
            text += f"\n\n✅ Добавлено дуэлей рандомом: {created}"

        km = admin_duel_server_kb(auto_recreate=auto_recreate, random_enabled=random_enabled, max_pool=max_pool)
        if edit and message_id is not None:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=km)
        else:
            bot.send_message(chat_id, text, reply_markup=km)

    def _edit_admin_duel_server_delete_menu(chat_id: int, message_id: int, *, page: int = 0) -> None:
        page = max(0, int(page))
        per_page = 20
        offset = page * per_page
        total = int(db.count_open_server_duels() or 0)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages - 1)
        offset = page * per_page

        duels = db.list_open_server_duels_admin(limit=per_page, offset=offset)
        kb = InlineKeyboardMarkup()

        if not duels:
            kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:menu"))
            bot.edit_message_text(
                "🗑 Удаление дуэлей\n\nВ пуле нет открытых дуэлей.",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=kb,
            )
            return

        for d in duels:
            duel_id = int(d.get("duel_id") or 0)
            stake = int(d.get("stake") or 0)
            gt = str(d.get("game_type") or "")
            type_txt = "🎲" if gt == "dice" else "✊✋✌"
            kb.add(
                InlineKeyboardButton(
                    text=f"{type_txt} ID {duel_id} · {stake}",
                    callback_data=f"admin:duel_server:delete:{duel_id}",
                )
            )

        if total_pages > 1:
            prev_page = max(0, page - 1)
            next_page = min(total_pages - 1, page + 1)
            kb.row(
                InlineKeyboardButton(text="⬅", callback_data=f"admin:duel_server:delete_menu:{prev_page}"),
                InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"),
                InlineKeyboardButton(text="➡", callback_data=f"admin:duel_server:delete_menu:{next_page}"),
            )

        kb.row(
            InlineKeyboardButton(text="🧹 Удалить все", callback_data="admin:duel_server:delete_all:confirm"),
            InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:menu"),
        )

        bot.edit_message_text(
            "🗑 Удаление дуэлей\n\nВыберите дуэль для удаления:",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=kb,
        )

    def _edit_admin_duel_manage_menu(chat_id: int, message_id: int, *, page: int = 0) -> None:
        page = max(0, int(page))
        per_page = 20
        total = int(db.count_waiting_duels() or 0)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages - 1)
        offset = page * per_page

        duels = db.list_waiting_duels_admin(limit=per_page, offset=offset)
        kb = InlineKeyboardMarkup()

        if not duels:
            kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:menu"))
            _safe_edit_message_text(
                bot,
                "🛠 Управление дуэлями\n\nОткрытых дуэлей нет.",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=kb,
            )
            return

        for d in duels:
            duel_id = int(d.get("duel_id") or 0)
            stake = int(d.get("stake") or 0)
            gt = str(d.get("game_type") or "")
            is_bot = int(d.get("is_bot") or 0)
            creator_id = int(d.get("creator_id") or 0)
            type_txt = "🎲" if gt == "dice" else "✊✋✌"
            who = "🤖" if (is_bot == 1 or creator_id == 0) else f"👤{creator_id}"
            kb.add(
                InlineKeyboardButton(
                    text=f"{type_txt} ID {duel_id} · {stake} · {who}",
                    callback_data=f"admin:duel_manage:delete:{duel_id}",
                )
            )

        if total_pages > 1:
            prev_page = max(0, page - 1)
            next_page = min(total_pages - 1, page + 1)
            kb.row(
                InlineKeyboardButton(text="⬅", callback_data=f"admin:duel_manage:menu:{prev_page}"),
                InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"),
                InlineKeyboardButton(text="➡", callback_data=f"admin:duel_manage:menu:{next_page}"),
            )

        kb.row(
            InlineKeyboardButton(text="🧹 Очистить пул", callback_data="admin:duel_server:delete_all:confirm"),
            InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:menu"),
        )

        _safe_edit_message_text(
            bot,
            "🛠 Управление дуэлями\n\nВыберите дуэль для удаления/отмены:",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=kb,
        )

    def _edit_admin_duel_server_random_menu(chat_id: int, message_id: int) -> None:
        enabled = _get_bool_setting(DUEL_SERVER_RANDOM_ENABLED_KEY, default=False)
        min_pool = _get_int_setting(DUEL_SERVER_RANDOM_MIN_KEY, default=0)
        max_pool = _get_int_setting(DUEL_SERVER_RANDOM_MAX_KEY, default=0)
        games = _get_set_setting_str(DUEL_SERVER_RANDOM_GAMES_KEY, default={"dice", "rps"})
        stakes = _get_set_setting_int(DUEL_SERVER_RANDOM_STAKES_KEY, default={200, 500, 1000})
        games = {g for g in games if g in {"dice", "rps"}}
        stakes = {s for s in stakes if s in {200, 500, 1000}}
        bot.edit_message_text(
            "🎲 Рандом дуэлей\n\nНастройки генератора (минимум/максимум пула, типы игр и ставки):",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=admin_duel_server_random_kb(
                enabled=enabled,
                min_pool=min_pool,
                max_pool=max_pool,
                games=games,
                stakes=stakes,
            ),
        )

    @bot.callback_query_handler(func=lambda c: True)
    def on_callback(call: CallbackQuery) -> None:
        uid = call.from_user.id
        data = call.data or ""

        # Blocked users: nothing should work (global guard).
        try:
            if db.is_blocked(int(uid)):
                try:
                    bot.answer_callback_query(call.id, "Вы заблокированы.", show_alert=True)
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Any inline button press clears the last temporary notice.
        try:
            _clear_temp_notice(int(uid))
        except Exception:
            pass

        # Dialog callbacks must work for both users and admins (do not keep them inside admin-only branches).
        if str(data).startswith("dialog:"):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass

            parts2 = str(data).split(":")
            if len(parts2) < 3 or not str(parts2[2]).isdigit():
                return
            did = int(parts2[2])
            d = db.get_dialog(int(did))
            if not d:
                try:
                    bot.answer_callback_query(call.id, "Диалог не найден.", show_alert=True)
                except Exception:
                    pass
                return

            status = str(d.get("status") or "")
            if status == "closed":
                try:
                    bot.answer_callback_query(call.id, "Диалог закрыт.")
                except Exception:
                    pass
                return

            # User side
            if str(data).startswith("dialog:open:"):
                if int(d.get("user_id") or 0) != int(uid):
                    return
                text = (
                    "💬 Диалог открыт\n\n"
                    f"Диалог: #{did}\n\n"
                    "Нажмите «✍️ Ответить», чтобы отправить сообщение админу."
                )
                _safe_edit_message_text(
                    bot,
                    text,
                    chat_id=int(call.message.chat.id),
                    message_id=int(call.message.message_id),
                    reply_markup=dialog_user_kb(int(did)),
                    parse_mode=None,
                )
                return

            if str(data).startswith("dialog:user_reply:"):
                if int(d.get("user_id") or 0) != int(uid):
                    return
                s = session(int(uid))
                s.dialog_expect = "user_reply"
                s.dialog_id = int(did)
                s.dialog_role = "user"
                try:
                    bot.send_message(int(uid), "✍️ Напишите сообщение админу:")
                except Exception:
                    pass
                return

            if str(data).startswith("dialog:user_close:"):
                if int(d.get("user_id") or 0) != int(uid):
                    return
                try:
                    db.set_dialog_status(dialog_id=int(did), status="closed", now_ts=int(time.time()))
                except Exception:
                    pass
                try:
                    admin_id = int(d.get("admin_id") or 0)
                    if admin_id > 0:
                        bot.send_message(admin_id, f"💬 Диалог #{did} закрыт пользователем (ID {uid}).")
                except Exception:
                    pass
                try:
                    _safe_edit_message_text(
                        bot,
                        "✅ Диалог закрыт.",
                        chat_id=int(call.message.chat.id),
                        message_id=int(call.message.message_id),
                        reply_markup=None,
                        parse_mode=None,
                    )
                except Exception:
                    pass
                return

            # Admin side
            if str(data).startswith("dialog:admin_reply:"):
                if int(d.get("admin_id") or 0) != int(uid):
                    return
                s = session(int(uid))
                s.dialog_expect = "admin_reply"
                s.dialog_id = int(did)
                s.dialog_role = "admin"
                try:
                    bot.send_message(int(uid), f"✍️ Напишите сообщение пользователю (диалог #{did}):")
                except Exception:
                    pass
                return

            if str(data).startswith("dialog:admin_history:"):
                if int(d.get("admin_id") or 0) != int(uid):
                    return
                items: list[dict] = []
                try:
                    items = db.list_dialog_messages(dialog_id=int(did), limit=5)
                except Exception:
                    items = []

                lines = [f"📋 История диалога #{did} (последние 5):", ""]
                for it in reversed(items):
                    who = "👤" if str(it.get("sender_type") or "") == "user" else "🛠"
                    txt = str(it.get("message_text") or "").strip()
                    if len(txt) > 800:
                        txt = txt[:800] + "…"
                    lines.append(f"{who} {txt}")
                if len(lines) <= 2:
                    lines.append("(пусто)")
                try:
                    bot.send_message(int(uid), "\n".join(lines))
                except Exception:
                    pass
                return

            if str(data).startswith("dialog:admin_close:"):
                if int(d.get("admin_id") or 0) != int(uid):
                    return
                try:
                    db.set_dialog_status(dialog_id=int(did), status="closed", now_ts=int(time.time()))
                except Exception:
                    pass
                try:
                    user_id = int(d.get("user_id") or 0)
                    if user_id > 0:
                        bot.send_message(user_id, f"💬 Диалог #{did} завершён админом.")
                except Exception:
                    pass
                return

        try:
            _channel_on_activity(uid, chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass

        try:
            # --- global panel navigation ---
            if data.startswith("admusr:"):
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass

                s_admin = session(int(uid))
                chat_id_local = int(call.message.chat.id)

                if data == "admusr:home":
                    show_screen(chat_id=chat_id_local, user_id=int(uid), screen="admin_users:home", push_history=True)
                    return

                if data.startswith("admusr:list:"):
                    try:
                        page = int((data.split(":", 2)[2] or "0").strip())
                    except Exception:
                        page = 0
                    show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:list:{page}", push_history=True)
                    return

                if data == "admusr:search":
                    s_admin.admin_users_expect = "search"
                    s_admin.admin_users_error = None
                    show_screen(chat_id=chat_id_local, user_id=int(uid), screen="admin_users:search", push_history=True)
                    return

                if data == "admusr:toggle_blocked":
                    s_admin.admin_users_blocked_only = not bool(s_admin.admin_users_blocked_only)
                    show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:list:{int(s_admin.admin_users_page or 0)}", push_history=False)
                    return

                if data == "admusr:toggle_notify":
                    s_admin.admin_users_notify = not bool(s_admin.admin_users_notify)
                    current = str(getattr(s_admin, "panel_screen", "") or "")
                    show_screen(chat_id=chat_id_local, user_id=int(uid), screen=current or "admin_users:home", push_history=False)
                    return

                if data == "admusr:clear":
                    s_admin.admin_users_query = None
                    s_admin.admin_users_page = 0
                    show_screen(chat_id=chat_id_local, user_id=int(uid), screen="admin_users:list:0", push_history=False)
                    return

                if data.startswith("admusr:card:"):
                    try:
                        target_id = int((data.split(":", 2)[2] or "0").strip())
                    except Exception:
                        target_id = 0
                    show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:card:{target_id}", push_history=True)
                    return

                if data.startswith("admusr:points_menu:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 3 and str(parts2[2]).isdigit():
                        target_id = int(parts2[2])
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:points_menu:{target_id}", push_history=True)
                    return

                if data.startswith("admusr:chat:start:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 4 and str(parts2[3]).isdigit():
                        target_id = int(parts2[3])

                        did = 0
                        try:
                            did = int(db.get_or_create_dialog(user_id=int(target_id), admin_id=int(uid), now_ts=int(time.time())) or 0)
                        except Exception:
                            did = 0

                        try:
                            if did:
                                bot.send_message(
                                    int(target_id),
                                    "💬 Админ открыл диалог. Нажмите «📖 Открыть», чтобы ответить.",
                                    reply_markup=dialog_user_open_kb(int(did)),
                                )
                            else:
                                bot.send_message(int(target_id), "💬 Админ открыл диалог. Можете написать сообщение, оно будет доставлено админу.")
                        except Exception:
                            pass
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:chat:{target_id}", push_history=True)
                    return

                if data.startswith("admusr:chat:stop:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 4 and str(parts2[3]).isdigit():
                        target_id = int(parts2[3])
                        try:
                            did = db.get_open_dialog_id(user_id=int(target_id))
                            if did:
                                db.set_dialog_status(dialog_id=int(did), status="closed", now_ts=int(time.time()))
                        except Exception:
                            pass
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:card:{target_id}", push_history=False)
                    return

                if data.startswith("admusr:blkask:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 4 and parts2[2].isdigit() and parts2[3].isdigit():
                        do_block = int(parts2[2])
                        target_id = int(parts2[3])
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:blkask:{do_block}:{target_id}", push_history=True)
                    return

                if data.startswith("admusr:blkdo:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 4 and parts2[2].isdigit() and parts2[3].isdigit():
                        do_block = int(parts2[2])
                        target_id = int(parts2[3])
                        # Prevent admins from blocking/unblocking themselves or other admins
                        admin_ids = set(getattr(settings, "admin_ids", frozenset({settings.admin_id})))
                        if int(target_id) in admin_ids:
                            # show error in admin panel instead of performing the action
                            try:
                                s_admin.admin_users_error = "❌ Нельзя блокировать/разблокировать администратора."
                            except Exception:
                                pass
                            show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:card:{target_id}", push_history=False)
                            return

                        db.set_blocked(int(target_id), bool(do_block == 1))
                        if bool(s_admin.admin_users_notify):
                            if do_block == 1:
                                _admin_users_send_notify(int(target_id), "⛔ Ваш аккаунт заблокирован.")
                            else:
                                _admin_users_send_notify(int(target_id), "✅ Ваш аккаунт разблокирован.")
                        s_admin.admin_users_pending_action = None
                        s_admin.admin_users_expect = None
                        s_admin.admin_users_error = None
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:card:{target_id}", push_history=False)
                    return

                if data.startswith("admusr:blkreason:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 4 and parts2[2].isdigit() and parts2[3].isdigit():
                        do_block = int(parts2[2])
                        target_id = int(parts2[3])
                        s_admin.admin_users_target_user_id = int(target_id)
                        s_admin.admin_users_pending_action = "block" if do_block == 1 else "unblock"
                        s_admin.admin_users_expect = "block_reason"
                        s_admin.admin_users_error = None
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:block_reason:{do_block}:{target_id}", push_history=True)
                    return

                if data.startswith("admusr:points:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 4:
                        sign = str(parts2[2])
                        target_id = int(parts2[3]) if str(parts2[3]).isdigit() else 0
                        s_admin.admin_users_target_user_id = int(target_id)
                        s_admin.admin_users_pending_action = "points"
                        s_admin.admin_users_points_sign = 1 if sign == "+" else -1
                        s_admin.admin_users_pending_value = None
                        s_admin.admin_users_pending_text = None
                        s_admin.admin_users_error = None
                        s_admin.admin_users_allow_negative = False
                        s_admin.admin_users_expect = "points_amount"
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:points_amount:{sign}:{target_id}", push_history=True)
                    return

                if data.startswith("admusr:toggle_penalty:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 3 and parts2[2].isdigit():
                        target_id = int(parts2[2])
                        s_admin.admin_users_allow_negative = not bool(getattr(s_admin, "admin_users_allow_negative", False))
                        s_admin.admin_users_error = None
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:points_confirm:{target_id}", push_history=False)
                    return

                if data.startswith("admusr:points_confirm:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 3 and parts2[2].isdigit():
                        target_id = int(parts2[2])
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:points_confirm:{target_id}", push_history=False)
                    return

                if data.startswith("admusr:pointsmsg:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 3 and parts2[2].isdigit():
                        target_id = int(parts2[2])
                        s_admin.admin_users_target_user_id = int(target_id)
                        s_admin.admin_users_expect = "points_message"
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:points_message:{target_id}", push_history=True)
                    return

                if data.startswith("admusr:pointsclear:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 3 and parts2[2].isdigit():
                        target_id = int(parts2[2])
                        s_admin.admin_users_pending_text = None
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:points_confirm:{target_id}", push_history=False)
                    return

                if data.startswith("admusr:pointsdo:"):
                    parts2 = data.split(":")
                    if len(parts2) >= 3 and parts2[2].isdigit():
                        target_id = int(parts2[2])
                        delta = int(s_admin.admin_users_pending_value or 0)

                        db.add_balance(int(target_id), int(delta))
                        if bool(s_admin.admin_users_notify):
                            msg = (s_admin.admin_users_pending_text or "").strip()
                            delta_txt = ("+" + _fmt_money(delta)) if delta >= 0 else _fmt_money(delta)
                            base = f"💰 Баланс изменён: {delta_txt} баллов."
                            _admin_users_send_notify(int(target_id), base + ("\n\n" + msg if msg else ""))
                        s_admin.admin_users_pending_value = None
                        s_admin.admin_users_pending_text = None
                        s_admin.admin_users_expect = None
                        s_admin.admin_users_error = None
                        s_admin.admin_users_allow_negative = False
                        show_screen(chat_id=chat_id_local, user_id=int(uid), screen=f"admin_users:card:{target_id}", push_history=False)
                    return

            # --- weekly event callbacks ---
            if str(data).startswith("we:"):
                parts_we = str(data).split(":")
                action = str(parts_we[1] or "") if len(parts_we) > 1 else ""

                def _edit_weekly_event_result(text: str) -> None:
                    _safe_edit_message_text(
                        bot,
                        text,
                        chat_id=int(call.message.chat.id),
                        message_id=int(call.message.message_id),
                        reply_markup=None,
                        parse_mode=None,
                    )

                now_ts = int(time.time())

                if action == "close":
                    # Close button removed by UX request.
                    return

                if action == "claim":
                    # we:claim:<week_index>:<event_id>
                    if len(parts_we) != 4:
                        return
                    try:
                        week_index = int(parts_we[2])
                        event_id = int(parts_we[3])
                    except Exception:
                        return

                    res = db.claim_weekly_event(int(uid), week_index=week_index, event_id=event_id, now_ts=now_ts)
                    if not bool(res.get("ok")):
                        reason = str(res.get("reason") or "")
                        if reason == "already_claimed":
                            _edit_weekly_event_result("🎁 Событие недели\n\nПодарок на этой неделе уже получен. Возвращайся через неделю!")
                        else:
                            _edit_weekly_event_result("🎁 Событие недели\n\nНе удалось получить подарок. Попробуй позже.")
                        return

                    reward = int(res.get("reward_points") or 0)
                    reward_txt = f"{reward:,}".replace(",", " ")
                    _edit_weekly_event_result(f"🎁 Подарок получен!\n\nНачислено: {reward_txt} очков.")
                    return

                if action == "mood":
                    # we:mood:<week_index>:4:<emoji_index>
                    if len(parts_we) != 5:
                        return
                    try:
                        week_index = int(parts_we[2])
                        event_id = int(parts_we[3])
                        emoji_index = int(parts_we[4])
                    except Exception:
                        return
                    if event_id != 4:
                        return

                    emojis = ["🥳", "😋", "😊", "🙂", "😐", "😶", "😒", "😟", "😣", "😡"]
                    if emoji_index < 0 or emoji_index >= len(emojis):
                        return
                    mood = emojis[emoji_index]

                    good_set = {"🥳", "😋", "😊", "🙂"}
                    if mood in good_set:
                        mood_text = (
                            "💫 Отлично!\n\n"
                            "Такое настроение — лучший магнит для удачи.\n"
                            "Так держать!\n\n"
                            "Вот небольшой подарок\n"
                            "для хорошего дня."
                        )
                    else:
                        mood_text = (
                            "Хм... понимаю.\n"
                            "Иногда день не тот.\n\n"
                            "Но даже в такие моменты удача может улыбнуться.\n\n"
                            "Вот небольшой подарок\n"
                            "чтобы стало чуть легче."
                        )

                    res = db.claim_weekly_event(int(uid), week_index=week_index, event_id=4, now_ts=now_ts, mood_emoji=mood)
                    if not bool(res.get("ok")):
                        reason = str(res.get("reason") or "")
                        if reason == "already_claimed":
                            _edit_weekly_event_result("🎁 Событие недели\n\nПодарок на этой неделе уже получен. Возвращайся через неделю!")
                        else:
                            _edit_weekly_event_result("🎁 Событие недели\n\nНе удалось получить подарок. Попробуй позже.")
                        return

                    reward = int(res.get("reward_points") or 0)
                    reward_txt = f"{reward:,}".replace(",", " ")
                    _edit_weekly_event_result(mood_text + "\n\n" + f"🎁 Начислено: {reward_txt} очков.")
                    return

                return

            if data == "ui:back":
                s = session(int(uid))
                try:
                    chat_id = int(call.message.chat.id)
                except Exception:
                    chat_id = int(call.from_user.id)

                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass

                if not (s.panel_history or []):
                    show_screen(chat_id=chat_id, user_id=int(uid), screen="main", push_history=False)
                    return

                try:
                    prev = str(s.panel_history.pop())
                except Exception:
                    prev = "main"
                show_screen(chat_id=chat_id, user_id=int(uid), screen=prev, push_history=False)
                return

            if data.startswith("ui:go:"):
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass

                screen = (data.split("ui:go:", 1)[1] or "").strip() or "main"
                show_screen(chat_id=int(call.message.chat.id), user_id=int(uid), screen=screen, push_history=True)
                return

            if data == "back":
                # If the user is using the global panel message, treat this as a panel back.
                s = session(int(uid))
                try:
                    if (
                        getattr(s, "panel_mode", True)
                        and s.panel_chat_id == int(call.message.chat.id)
                        and s.panel_message_id == int(call.message.message_id)
                    ):
                        if not (s.panel_history or []):
                            show_screen(chat_id=int(call.message.chat.id), user_id=int(uid), screen="main", push_history=False)
                            try:
                                bot.answer_callback_query(call.id)
                            except Exception:
                                pass
                            return

                        try:
                            prev = str(s.panel_history.pop())
                        except Exception:
                            prev = "main"

                        show_screen(chat_id=int(call.message.chat.id), user_id=int(uid), screen=prev, push_history=False)
                        try:
                            bot.answer_callback_query(call.id)
                        except Exception:
                            pass
                        return
                except Exception:
                    pass

                reset_user_flow(uid)
                reset_admin_flow(uid)
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                try:
                    _safe_delete_message(bot, int(call.message.chat.id), int(call.message.message_id))
                except Exception:
                    pass
                _set_reply_keyboard_silent(call.message.chat.id, main_menu_kb(is_admin=_is_admin(uid, settings)))
                return

            # --- universal bet module ---
            if data.startswith("bet:back:"):
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                s = session(int(uid))
                s.awaiting_bet_for_game = None
                s.awaiting_bet_chat_id = None
                s.awaiting_bet_message_id = None

                game = (data.split(":", 2)[2] or "").strip()
                if game == "duel":
                    try:
                        bot.edit_message_text(
                            _duels_menu_text(int(uid)),
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=duels_main_kb(),
                        )
                    except Exception:
                        try:
                            bot.send_message(call.message.chat.id, _duels_menu_text(int(uid)), reply_markup=duels_main_kb())
                        except Exception:
                            pass
                    return
                if game == "mines":
                    try:
                        mode = str(getattr(s, "mines_mode", "classic") or "classic")
                        attempts_txt = None
                        if mode == "nobet":
                            today = str(dt.datetime.utcfromtimestamp(int(time.time())).date())
                            try:
                                vip_active = db.is_vip_active(int(uid), now_ts=int(time.time()))
                            except Exception:
                                vip_active = False
                            limit = MINES_NOBET_ATTEMPTS_PER_DAY_VIP if vip_active else MINES_NOBET_ATTEMPTS_PER_DAY
                            st = db.mines_get_energy(int(uid), today=today, attempts_per_day=limit) or {"remaining": 0, "limit": limit}
                            attempts_txt = f"{int(st.get('remaining') or 0)}/{int(st.get('limit') or limit)}"
                        bot.edit_message_text(
                            "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode=mode, attempts_text=attempts_txt),
                        )
                        return
                    except Exception:
                        pass
                try:
                    bot.edit_message_text(
                        "Выберите игру:",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=minigames_menu_kb(show_back=False),
                    )
                except Exception:
                    bot.send_message(call.message.chat.id, "Выберите игру:", reply_markup=minigames_menu_kb(show_back=False))
                return

            if data.startswith("bet:custom:"):
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                game = (data.split(":", 2)[2] or "").strip()
                s = session(int(uid))
                s.awaiting_bet_for_game = game
                try:
                    s.awaiting_bet_chat_id = int(call.message.chat.id)
                    s.awaiting_bet_message_id = int(call.message.message_id)
                except Exception:
                    s.awaiting_bet_chat_id = None
                    s.awaiting_bet_message_id = None
                bot.answer_callback_query(call.id, "Отправь сумму числом или выбери кнопку.", show_alert=False)
                return

            if data.startswith("bet:pick:"):
                parts = data.split(":")
                if len(parts) != 4:
                    return
                game = str(parts[2])
                token = str(parts[3] or "").strip()

                try:
                    balance_now = int(db.get_balance(int(uid)) or 0)
                except Exception:
                    balance_now = 0

                min_bet, max_bet = _bet_limits_for(int(uid))
                amount: int | None = None
                if token == "p25":
                    amount = int(math.floor(float(balance_now) * 0.25))
                elif token == "p50":
                    amount = int(math.floor(float(balance_now) * 0.50))
                elif token == "max":
                    amount = int(min(int(balance_now), int(max_bet)))
                else:
                    try:
                        amount = int(token)
                    except Exception:
                        amount = None
                if amount is None:
                    return
                if amount <= 0:
                    bot.send_message(call.message.chat.id, "Отправь число (например 750) или выбери кнопку.")
                    return
                if amount < min_bet:
                    amount = int(min_bet)
                if amount > max_bet:
                    amount = int(max_bet)
                if amount > balance_now:
                    bot.send_message(
                        call.message.chat.id,
                        f"Недостаточно баллов. Баланс: {_fmt_points_ui(balance_now)}. Выбери ставку ниже.\n"
                        "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                    )
                    return

                try:
                    s = session(int(uid))
                    s.awaiting_bet_for_game = None
                    s.awaiting_bet_chat_id = None
                    s.awaiting_bet_message_id = None
                except Exception:
                    pass

                try:
                    db.push_last_bet(int(uid), game, int(amount), limit=5)
                except Exception:
                    pass

                if game == "dice":
                    data = f"dice:bet:{int(amount)}"
                elif game == "wheel":
                    data = f"wheel:bet:{int(amount)}"
                elif game == "ladder":
                    data = f"ladder:bet:{int(amount)}"
                elif game == "rps":
                    data = f"rps:stake:{int(amount)}"
                elif game == "mines":
                    data = f"mines:bet:{int(amount)}"
                elif game == "duel":
                    data = f"duel:stake:{int(amount)}"
                else:
                    return

            if data == "noop":
                bot.answer_callback_query(call.id, "⛔ Недоступно", show_alert=False)
                return

            if data.startswith("cmf:"):
                bot.answer_callback_query(call.id)
                if db.is_blocked(uid):
                    bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                    return

                chat_id = call.message.chat.id
                message_id = call.message.message_id
                db.ensure_user(uid, call.from_user.username, None)
                _cmf_ensure_initialized(uid)

                def _edit(text: str, km: InlineKeyboardMarkup | None = None) -> None:
                    nonlocal message_id
                    try:
                        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=km)
                    except Exception:
                        try:
                            m = bot.send_message(chat_id, text, reply_markup=km)
                            message_id = int(m.message_id)
                        except Exception:
                            pass

                mine_views = {"cmf:mine", "cmf:start", "cmf:stop", "cmf:cool", "cmf:status"}
                if data not in mine_views:
                    try:
                        _cmf_stop_temp_auto_refresh(uid)
                    except Exception:
                        pass

                def _inv_install_kb() -> InlineKeyboardMarkup:
                    inv = _cm_get_gpu_inventory(uid)
                    kb = InlineKeyboardMarkup()
                    for code, qty in sorted(inv.items()):
                        if qty <= 0:
                            continue
                        it = _CM_ITEMS.get("gpu", {}).get(code) or {}
                        label = str(it.get("name") or code).replace("🎮 ", "")
                        kb.add(InlineKeyboardButton(text=f"➕ {label} (x{qty})", callback_data=f"cmf:install:{code}"))
                    kb.add(InlineKeyboardButton(text="🎮 Видеокарты", callback_data="cm:cat:gpu"))
                    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:farm"))
                    return kb

                def _installed_uninstall_kb() -> InlineKeyboardMarkup:
                    cards = _cm_get_cards(uid)
                    counts: dict[str, int] = {}
                    for c in cards:
                        counts[str(c)] = counts.get(str(c), 0) + 1
                    kb = InlineKeyboardMarkup()
                    for code, qty in sorted(counts.items()):
                        it = _CM_ITEMS.get("gpu", {}).get(code) or {}
                        label = str(it.get("name") or code).replace("🎮 ", "")
                        kb.add(InlineKeyboardButton(text=f"🔄 {label} (x{qty})", callback_data=f"cmf:uninstall:{code}"))
                    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:farm"))
                    return kb

                if data in {"cmf:home", "cmf:refresh"}:
                    try:
                        _cmf_update_temp_gradually(uid)
                    except Exception:
                        pass
                    _edit(_cmf_home_text(uid), None)
                    return

                if data == "cmf:exit":
                    s = session(uid)
                    if s.cmf_kb_message_id is not None:
                        _safe_delete_message(bot, int(chat_id), int(s.cmf_kb_message_id))
                    reset_user_flow(uid)
                    reset_admin_flow(uid)
                    try:
                        _safe_delete_message(bot, int(chat_id), int(message_id))
                    except Exception:
                        pass
                    _set_reply_keyboard_silent(chat_id, main_menu_kb(is_admin=_is_admin(uid, settings)))
                    return

                if data == "cmf:mine":
                    active = bool(_cmf_get_int(uid, "mining_active", 0))
                    _edit(_cmf_mining_screen_text(uid), cryptomine_mining_kb(is_active=active))
                    try:
                        _cmf_start_temp_auto_refresh(uid, chat_id=int(chat_id), message_id=int(message_id), view="mine")
                    except Exception:
                        pass
                    return

                if data == "cmf:start":
                    _cmf_apply_mining(uid)
                    now = _cmf_now_ts()
                    prev_last_ts = _cmf_get_int(uid, "mining_last_ts", 0)
                    if prev_last_ts <= 0:
                        db.set_user_field(uid, "mining_last_ts", now)
                    db.set_user_field(uid, "mining_active", 1)
                    # Update reply-keyboard state (best-effort)
                    try:
                        m_kb = bot.send_message(int(chat_id), " ", reply_markup=cryptomine_farm_reply_kb(is_active=True))
                        _safe_delete_message(bot, int(chat_id), int(m_kb.message_id))
                    except Exception:
                        pass
                    try:
                        _cmf_update_temp_gradually(uid)
                    except Exception:
                        pass

                    # One-time first start gift (new users only).
                    try:
                        rewarded = int(db.get_user_field(uid, "mining_first_start_rewarded") or 0)
                    except Exception:
                        rewarded = 0

                    cards_installed = _cm_get_cards(uid)
                    inv_gpu = _cm_get_gpu_inventory(uid)
                    btc_bal = _cm_get_decimal_field(uid, "mining_btc", default=Decimal("0"))

                    # Consider it a first start if the user never had mining_last_ts set.
                    # This is persisted, so it survives bot restarts.
                    if rewarded != 1 and prev_last_ts <= 0:
                        # Gift (one-time): 1x GTX 1060 (auto-install if there is a free slot), basic fan, and 600W PSU.
                        gifted_lines: list[str] = []
                        try:
                            total = _cm_slots_total(uid)
                            free = max(0, int(total) - len(cards_installed))
                        except Exception:
                            free = 0

                        if free > 0:
                            cards_installed.append("gtx1060")
                            _cm_set_cards(uid, cards_installed)
                            gifted_lines.append("• 🎮 GTX 1060 (установлена)")
                        else:
                            inv_gpu["gtx1060"] = int(inv_gpu.get("gtx1060", 0) or 0) + 1
                            _cm_set_gpu_inventory(uid, inv_gpu)
                            gifted_lines.append("• 🎮 GTX 1060 (в инвентаре)")

                        try:
                            cool_inv = _cm_get_cooling_inventory(uid)
                            if int(cool_inv.get("fan", 0) or 0) <= 0:
                                cool_inv["fan"] = 1
                                _cm_set_cooling_inventory(uid, cool_inv)
                            db.set_user_field(uid, "mining_cooling", "fan")
                            gifted_lines.append("• 🌀 Обычный кулер")
                        except Exception:
                            pass

                        try:
                            psu_inv = _cm_get_psu_inventory(uid)
                            if int(psu_inv.get("600", 0) or 0) <= 0:
                                psu_inv["600"] = 1
                                _cm_set_psu_inventory(uid, psu_inv)
                            db.set_user_field(uid, "mining_psu", "600")
                            gifted_lines.append("• 🔌 Блок питания 600W")
                        except Exception:
                            pass

                        try:
                            db.set_user_field(uid, "mining_first_start_rewarded", 1)
                        except Exception:
                            pass

                        kb = InlineKeyboardMarkup()
                        kb.add(InlineKeyboardButton(text="🖥 Ферма", callback_data="cmf:farm"))

                        gift_text = "\n".join(gifted_lines) if gifted_lines else "• 🎁 Подарок получен"
                        try:
                            _cmf_update_temp_gradually(uid)
                        except Exception:
                            pass
                        _edit(
                            "🎉 Поздравляю с первой запущенной фермой!\n\n"
                            "Мы дарим тебе подарок для старта:\n"
                            f"{gift_text}\n\n"
                            "Нажми «🖥 Ферма», чтобы посмотреть.",
                            kb,
                        )
                        return

                    _edit(_cmf_mining_screen_text(uid), cryptomine_mining_kb(is_active=True))
                    try:
                        _cmf_start_temp_auto_refresh(uid, chat_id=int(chat_id), message_id=int(message_id), view="mine")
                    except Exception:
                        pass
                    return

                if data == "cmf:stop":
                    _cmf_apply_mining(uid)
                    db.set_user_field(uid, "mining_active", 0)
                    # Update reply-keyboard state (best-effort)
                    try:
                        m_kb = bot.send_message(int(chat_id), " ", reply_markup=cryptomine_farm_reply_kb(is_active=False))
                        _safe_delete_message(bot, int(chat_id), int(m_kb.message_id))
                    except Exception:
                        pass
                    try:
                        _cmf_update_temp_gradually(uid)
                    except Exception:
                        pass
                    _edit(_cmf_mining_screen_text(uid), cryptomine_mining_kb(is_active=False))
                    try:
                        _cmf_start_temp_auto_refresh(uid, chat_id=int(chat_id), message_id=int(message_id), view="mine")
                    except Exception:
                        pass
                    return

                if data == "cmf:cool":
                    _cmf_apply_mining(uid)
                    # Legacy handler kept for safety: temperature no longer changes instantly.
                    try:
                        _cmf_update_temp_gradually(uid)
                    except Exception:
                        pass
                    active = bool(_cmf_get_int(uid, "mining_active", 0))
                    _edit(_cmf_mining_screen_text(uid), cryptomine_mining_kb(is_active=active))
                    try:
                        _cmf_start_temp_auto_refresh(uid, chat_id=int(chat_id), message_id=int(message_id), view="mine")
                    except Exception:
                        pass
                    return

                if data == "cmf:status":
                    _cmf_apply_mining(uid)
                    text = _cmf_mining_screen_text(uid)
                    events = _cmf_get_event_log(uid)
                    if events:
                        text += "\n\n🔥 События:\n" + "\n".join(f"• {e}" for e in events[-5:])
                    active = bool(_cmf_get_int(uid, "mining_active", 0))
                    _edit(text, cryptomine_mining_kb(is_active=active))
                    try:
                        _cmf_start_temp_auto_refresh(uid, chat_id=int(chat_id), message_id=int(message_id), view="mine")
                    except Exception:
                        pass
                    return

                if data == "cmf:farm":
                    _edit(_cmf_farm_text(uid), cryptomine_farm_kb())
                    try:
                        _cmf_start_temp_auto_refresh(uid, chat_id=int(chat_id), message_id=int(message_id), view="farm")
                    except Exception:
                        pass
                    return

                if data == "cmf:add_card":
                    total = _cm_slots_total(uid)
                    used = len(_cm_get_cards(uid))
                    free = max(0, total - used)
                    inv = _cm_get_gpu_inventory(uid)
                    if free <= 0:
                        _edit("❌ Нет свободных ячеек.\n\nСними карту или купи ячейки.", cryptomine_farm_kb())
                        return
                    if not inv:
                        kb = InlineKeyboardMarkup()
                        kb.add(InlineKeyboardButton(text="🎮 Видеокарты", callback_data="cm:cat:gpu"))
                        kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:farm"))
                        _edit("🎒 Инвентарь пуст.\n\nКупи видеокарту в магазине.", kb)
                        return
                    _edit(f"➕ Добавить карту\n\nСвободные ячейки: {free}\nВыбери карту из инвентаря:", _inv_install_kb())
                    return

                if data.startswith("cmf:install:"):
                    code = data.split(":", 2)[2]
                    inv = _cm_get_gpu_inventory(uid)
                    available = int(inv.get(code, 0) or 0)
                    if available <= 0:
                        _edit("❌ Нет такой карты в инвентаре.", cryptomine_farm_kb())
                        return
                    total = _cm_slots_total(uid)
                    cards = _cm_get_cards(uid)
                    free = max(0, int(total) - len(cards))
                    if free <= 0:
                        _edit("❌ Нет свободных ячеек.", cryptomine_farm_kb())
                        return
                    to_install = min(available, free)
                    inv[code] = available - to_install
                    _cm_set_gpu_inventory(uid, inv)
                    if to_install > 0:
                        cards.extend([str(code)] * int(to_install))
                    _cm_set_cards(uid, cards)

                    try:
                        _cmf_update_temp_gradually(uid)
                    except Exception:
                        pass

                    if to_install == 1:
                        _edit("✅ Карта установлена!\n\n" + _cmf_farm_text(uid), cryptomine_farm_kb())
                    else:
                        _edit(f"✅ Установлено карт: {to_install}\n\n" + _cmf_farm_text(uid), cryptomine_farm_kb())
                    return

                if data == "cmf:sell_card":
                    cards = _cm_get_cards(uid)
                    if not cards:
                        _edit("❌ На ферме нет установленных карт.", cryptomine_farm_kb())
                        return
                    _edit("🔄 Продать карту\n\nВыбери карту, чтобы снять с фермы (вернётся в инвентарь):", _installed_uninstall_kb())
                    return

                # Delete (remove permanently) menu
                if data == "cmf:delete_menu":
                    s = session(uid)
                    s.cmf_delete_cat = None
                    s.cmf_delete_selected.clear()
                    kb = InlineKeyboardMarkup()
                    kb.row(
                        InlineKeyboardButton(text="🎮 Видеокарты", callback_data="cmf:del:cat:gpu"),
                        InlineKeyboardButton(text="❄ Охлаждение", callback_data="cmf:del:cat:cool"),
                    )
                    kb.add(InlineKeyboardButton(text="⚡ Питание", callback_data="cmf:del:cat:psu"))
                    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:farm"))
                    _edit("🗑 Удалить\n\nВыбери что удалить:", kb)
                    return

                def _cmf_del_items(cat: str) -> list[str]:
                    cat = str(cat)
                    if cat == "gpu":
                        cards = [str(x) for x in _cm_get_cards(uid)]

                        def _rank_gpu(code: str) -> tuple:
                            it = _CM_ITEMS.get("gpu", {}).get(str(code)) or {}
                            try:
                                btc = Decimal(str(it.get("btc") or "0"))
                            except Exception:
                                btc = Decimal("0")
                            # weaker -> smaller btc
                            return (btc, str(code))

                        cards.sort(key=_rank_gpu)
                        return cards
                    if cat == "cool":
                        inv = _cm_get_cooling_inventory(uid)
                        items: list[str] = []
                        for code in sorted(inv.keys()):
                            items.extend([str(code)] * int(inv.get(code, 0) or 0))
                        return items
                    if cat == "psu":
                        inv = _cm_get_psu_inventory(uid)
                        items: list[str] = []
                        for code in sorted(inv.keys()):
                            items.extend([str(code)] * int(inv.get(code, 0) or 0))
                        return items
                    return []

                def _cmf_del_label(cat: str, code: str) -> str:
                    if cat == "gpu":
                        it = _CM_ITEMS.get("gpu", {}).get(str(code)) or {}
                        return str(it.get("name") or code).replace("🎮 ", "")
                    if cat == "cool":
                        it = _CM_ITEMS.get("cool", {}).get(str(code)) or {}
                        return str(it.get("name") or code).replace("❄ ", "")
                    if cat == "psu":
                        it = _CM_ITEMS.get("psu", {}).get(str(code)) or {}
                        return str(it.get("name") or code).replace("🔌 ", "")
                    return str(code)

                def _cmf_del_kb(cat: str) -> InlineKeyboardMarkup:
                    s = session(uid)
                    cat = str(cat)
                    items = _cmf_del_items(cat)
                    kb = InlineKeyboardMarkup()
                    # Two columns
                    if cat == "gpu":
                        # Left column: weaker half (top->bottom). Right column: stronger half (top->bottom).
                        mid = (len(items) + 1) // 2
                        for i in range(0, mid):
                            row_btns: list[InlineKeyboardButton] = []
                            for j in (i, i + mid):
                                if j >= len(items):
                                    continue
                                code = items[j]
                                selected = j in s.cmf_delete_selected
                                mark = "✅" if selected else "❌"
                                label = _cmf_del_label(cat, code)
                                row_btns.append(
                                    InlineKeyboardButton(
                                        text=f"{mark} {label}",
                                        callback_data=f"cmf:del:toggle:{cat}:{j}",
                                    )
                                )
                            if row_btns:
                                kb.row(*row_btns)
                    else:
                        for i in range(0, len(items), 2):
                            row_btns: list[InlineKeyboardButton] = []
                            for j in (i, i + 1):
                                if j >= len(items):
                                    continue
                                code = items[j]
                                selected = j in s.cmf_delete_selected
                                mark = "✅" if selected else "❌"
                                label = _cmf_del_label(cat, code)
                                row_btns.append(
                                    InlineKeyboardButton(
                                        text=f"{mark} {label}",
                                        callback_data=f"cmf:del:toggle:{cat}:{j}",
                                    )
                                )
                            if row_btns:
                                kb.row(*row_btns)

                    sel_n = len(s.cmf_delete_selected)
                    kb.add(InlineKeyboardButton(text=f"🗑 Удалить ({sel_n})", callback_data=f"cmf:del:confirm:{cat}"))
                    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:delete_menu"))
                    return kb

                if data.startswith("cmf:del:cat:"):
                    cat = data.split(":", 3)[3]
                    s = session(uid)
                    s.cmf_delete_cat = str(cat)
                    s.cmf_delete_selected.clear()
                    items = _cmf_del_items(cat)
                    if not items:
                        _edit("ℹ️ Нечего удалять.", InlineKeyboardMarkup().add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:delete_menu")))
                        return
                    title = "Выбери карту которую хотите удалить:" if str(cat) == "gpu" else "Выбери что хотите удалить:"
                    _edit(f"{title}\n\n❌ — не выбрано\n✅ — выбрано", _cmf_del_kb(cat))
                    return

                if data.startswith("cmf:del:toggle:"):
                    # cmf:del:toggle:<cat>:<idx>
                    parts = data.split(":")
                    if len(parts) >= 5:
                        cat = parts[3]
                        try:
                            idx = int(parts[4])
                        except Exception:
                            idx = -1
                        s = session(uid)
                        s.cmf_delete_cat = str(cat)
                        items = _cmf_del_items(cat)
                        if idx < 0 or idx >= len(items):
                            _edit("⚠️ Список изменился. Открой заново.", InlineKeyboardMarkup().add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:delete_menu")))
                            return
                        if idx in s.cmf_delete_selected:
                            s.cmf_delete_selected.remove(idx)
                        else:
                            s.cmf_delete_selected.add(idx)
                        title = "Выбери карту которую хотите удалить:" if str(cat) == "gpu" else "Выбери что хотите удалить:"
                        _edit(f"{title}\n\n❌ — не выбрано\n✅ — выбрано", _cmf_del_kb(cat))
                        return

                if data.startswith("cmf:del:confirm:"):
                    cat = data.split(":", 3)[3]
                    s = session(uid)
                    items = _cmf_del_items(cat)
                    selected = sorted([i for i in s.cmf_delete_selected if 0 <= i < len(items)])
                    if not selected:
                        _edit("ℹ️ Ничего не выбрано.", _cmf_del_kb(cat))
                        return

                    if str(cat) == "gpu":
                        # The delete list is sorted independently, so remove by code occurrences
                        # rather than by indices in the original installed list.
                        cards = [str(x) for x in _cm_get_cards(uid)]
                        to_remove: dict[str, int] = {}
                        for idx in selected:
                            code = str(items[idx])
                            to_remove[code] = int(to_remove.get(code, 0)) + 1

                        total_delta = 0
                        for code, qty in to_remove.items():
                            q = max(0, int(qty))
                            if q <= 0:
                                continue
                            total_delta += int(_cm_gpu_temp_per_card(code)) * q
                            for _ in range(q):
                                try:
                                    cards.remove(str(code))
                                except ValueError:
                                    break

                        _cm_set_cards(uid, cards)

                        try:
                            _cmf_update_temp_gradually(uid)
                        except Exception:
                            pass

                        s.cmf_delete_selected.clear()
                        _edit("✅ Удалено.\n\n" + _cmf_farm_text(uid), cryptomine_farm_kb())
                        return

                    if str(cat) in {"cool", "psu"}:
                        if str(cat) == "cool":
                            inv = _cm_get_cooling_inventory(uid)
                            default_code = "fan"
                            field_sel = "mining_cooling"
                            set_inv = _cm_set_cooling_inventory
                        else:
                            inv = _cm_get_psu_inventory(uid)
                            default_code = "600"
                            field_sel = "mining_psu"
                            set_inv = _cm_set_psu_inventory

                        was_cooling = (str(cat) == "cool")
                        old_total_cool_qty = 0
                        if was_cooling:
                            try:
                                old_total_cool_qty = sum(int(v or 0) for v in inv.values())
                            except Exception:
                                old_total_cool_qty = 0

                        # decrement selected units
                        for idx in selected:
                            code = str(items[idx])
                            cur = int(inv.get(code, 0) or 0)
                            if cur > 0:
                                inv[code] = cur - 1
                        # cleanup
                        inv = {k: int(v) for k, v in inv.items() if int(v) > 0}
                        set_inv(uid, inv)

                        # ensure selected equipment points to an existing code
                        if inv:
                            cur_sel = str(db.get_user_field(uid, field_sel) or default_code)
                            if cur_sel not in inv:
                                db.set_user_field(uid, field_sel, next(iter(inv.keys()), default_code))
                        else:
                            # Empty inventory: keep the selector set, but it won't have any effect.
                            db.set_user_field(uid, field_sel, str(db.get_user_field(uid, field_sel) or default_code))

                        # Keep legacy qty in sync for selected type (0 allowed when inventory empty).
                        try:
                            if was_cooling:
                                cur_sel = str(db.get_user_field(uid, "mining_cooling") or default_code)
                                db.set_user_field(uid, "mining_cooling_qty", int(inv.get(cur_sel, 0) or 0))
                            else:
                                cur_sel = str(db.get_user_field(uid, "mining_psu") or default_code)
                                db.set_user_field(uid, "mining_psu_qty", int(inv.get(cur_sel, 0) or 0))
                        except Exception:
                            pass

                        # If we just removed the last unit of the installed cooling type, auto-switch.
                        warn_heat = False
                        if was_cooling:
                            try:
                                cur_cool = str(db.get_user_field(uid, "mining_cooling") or default_code)
                                if int(inv.get(cur_cool, 0) or 0) <= 0:
                                    # pick any remaining type or keep selector but with 0 qty
                                    next_code = next(iter(inv.keys()), cur_cool)
                                    db.set_user_field(uid, "mining_cooling", str(next_code))
                                    db.set_user_field(uid, "mining_cooling_qty", int(inv.get(str(next_code), 0) or 0))
                                new_total = sum(int(v or 0) for v in inv.values())
                                if new_total < int(old_total_cool_qty):
                                    warn_heat = True
                            except Exception:
                                pass

                        try:
                            _cmf_update_temp_gradually(uid)
                        except Exception:
                            pass

                        s.cmf_delete_selected.clear()
                        if was_cooling and warn_heat:
                            _edit("🔥 Охлаждение снижено! Температура начинает расти...\n\n" + _cmf_farm_text(uid), cryptomine_farm_kb())
                        else:
                            _edit("✅ Удалено.\n\n" + _cmf_farm_text(uid), cryptomine_farm_kb())
                        return

                if data.startswith("cmf:uninstall:"):
                    code = data.split(":", 2)[2]
                    cards = _cm_get_cards(uid)
                    if code not in cards:
                        _edit("❌ Карта не найдена на ферме.", cryptomine_farm_kb())
                        return
                    try:
                        cards.remove(code)
                        _cm_set_cards(uid, cards)
                    except Exception:
                        pass
                    inv = _cm_get_gpu_inventory(uid)
                    inv[code] = int(inv.get(code, 0)) + 1
                    _cm_set_gpu_inventory(uid, inv)
                    try:
                        _cmf_update_temp_gradually(uid)
                    except Exception:
                        pass
                    _edit("✅ Карта снята и возвращена в инвентарь.\n\n" + _cmf_farm_text(uid), cryptomine_farm_kb())
                    return

                if data == "cmf:upgrade":
                    _edit(
                        "🛒 Магазин\n\nВыберите раздел магазина для улучшений:",
                        cryptomine_shop_main_kb(prefix="cms", exit_cb="cmf:farm", show_back=False),
                    )
                    return

                if data == "cmf:shop":
                    _edit(_cm_shop_home_text(uid), cryptomine_shop_main_kb(prefix="cms", exit_cb="cmf:home", show_back=False))
                    return

                if data == "cmf:market":
                    _edit(_cmf_market_text(uid), cryptomine_market_kb())
                    return

                if data == "cmf:market:sell_all":
                    _cmf_ensure_initialized(uid)
                    _cmf_apply_mining(uid)
                    btc = _cm_get_decimal_field(uid, "mining_btc", default=Decimal("0"))
                    if btc <= 0:
                        _edit("ℹ️ Нечего продавать.\n\n" + _cmf_market_text(uid), cryptomine_market_kb())
                        return
                    pts = int((btc * Decimal("100")).to_integral_value(rounding=ROUND_FLOOR))
                    if pts <= 0:
                        _edit("ℹ️ Сумма слишком маленькая для продажи.\n\n" + _cmf_market_text(uid), cryptomine_market_kb())
                        return
                    _cm_set_decimal_field(uid, "mining_btc", Decimal("0"))
                    try:
                        db.add_balance(uid, int(pts))
                    except Exception:
                        pass
                    _edit(f"✅ Продано всё BTC!\n\n+{pts} ⭐", None)
                    return

                if data.startswith("cmf:market:sell:"):
                    # Legacy buttons support: redirect to the new "sell all" flow.
                    _edit(_cmf_market_text(uid), cryptomine_market_kb())
                    return

                if data.startswith("cmf:market:confirm:"):
                    # Legacy buttons support: redirect to the new market screen.
                    _edit(_cmf_market_text(uid), cryptomine_market_kb())
                    return

                if data == "cmf:market:cancel":
                    _edit(_cmf_market_text(uid), cryptomine_market_kb())
                    return

                if data == "cmf:rating":
                    # Show rating (avoid send+delete dummy messages; it causes flicker in clients)
                    _edit(_cmf_rating_text(uid), None)
                    try:
                        def _updater() -> None:
                            try:
                                while True:
                                    time.sleep(120)
                                    try:
                                        bot.edit_message_text(
                                            _cmf_rating_text(uid),
                                            chat_id=chat_id,
                                            message_id=message_id,
                                            reply_markup=None,
                                        )
                                    except Exception:
                                        break
                            except Exception:
                                pass

                        threading.Thread(target=_updater, daemon=True).start()
                    except Exception:
                        pass
                    return

                if data == "cmf:settings":
                    kb2 = InlineKeyboardMarkup()
                    kb2.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:home"))
                    _edit(_cmf_settings_text(uid), kb2)
                    return

                _edit(_cmf_home_text(uid), None)
                return

            if data.startswith("cms:"):
                bot.answer_callback_query(call.id)
                if db.is_blocked(uid):
                    bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                    return

                chat_id = call.message.chat.id
                message_id = call.message.message_id
                db.ensure_user(uid, call.from_user.username, None)
                _cmf_ensure_initialized(uid)

                if data == "cms:exit":
                    bot.edit_message_text(_cmf_home_text(uid), chat_id=chat_id, message_id=message_id)
                    return

                if data == "cms:home":
                    bot.edit_message_text(
                        _cm_shop_home_text(uid),
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=cryptomine_shop_main_kb(prefix="cms", exit_cb="cmf:home", show_back=False),
                    )
                    return

                if data == "cms:noop":
                    return

                if data.startswith("cms:cat:"):
                    cat = data.split(":", 2)[2]
                    bot.edit_message_text(
                        _cm_category_text(cat, uid),
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=cryptomine_category_kb(
                            cat,
                            prefix="cms",
                            home_cb="cms:home",
                            gpu_suffix_by_code=_cm_gpu_btc_hour_suffix(uid) if str(cat) == "gpu" else None,
                            cool_suffix_by_code=_cm_cool_suffix_by_code() if str(cat) == "cool" else None,
                        ),
                    )
                    return

                if data.startswith("cms:item:"):
                    parts = data.split(":")
                    if len(parts) != 4:
                        return
                    cat = parts[2]
                    code = parts[3]
                    item = _CM_ITEMS.get(cat, {}).get(code)
                    if not item:
                        bot.send_message(chat_id, "❌ Товар не найден")
                        return
                    bot.edit_message_text(
                        _cm_item_text(cat, code, uid=uid, detailed=False),
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=cryptomine_item_kb(category=cat, code=code, show_badge=item.get("badge"), prefix="cms", back_to_category_prefix="cms"),
                    )
                    return

                if data.startswith("cms:info:"):
                    parts = data.split(":")
                    if len(parts) != 4:
                        return
                    cat = parts[2]
                    code = parts[3]
                    if cat != "gpu":
                        return
                    item = _CM_ITEMS.get(cat, {}).get(code)
                    if not item:
                        bot.send_message(chat_id, "❌ Товар не найден")
                        return
                    bot.edit_message_text(
                        _cm_item_text(cat, code, uid=uid, detailed=True),
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=cryptomine_item_kb(category=cat, code=code, show_badge=item.get("badge"), prefix="cms", back_to_category_prefix="cms"),
                    )
                    return

                if data.startswith("cms:buy:"):
                    parts = data.split(":")
                    if len(parts) != 4:
                        return
                    cat = parts[2]
                    code = parts[3]
                    handled, err = _cm_start_buy_qty_prompt(
                        uid_local=uid,
                        cat=cat,
                        code=code,
                        prefix="cms",
                        panel_chat_id=int(chat_id),
                        panel_message_id=int(message_id),
                    )
                    if handled:
                        if err:
                            bot.send_message(chat_id, err)
                        return

                    ok, msg = _cm_try_buy(uid, cat, code, qty=1)
                    if not ok:
                        bot.send_message(chat_id, msg)
                        return
                    bot.edit_message_text(
                        _cm_shop_home_text(uid),
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=cryptomine_shop_main_kb(prefix="cms", exit_cb="cmf:home", show_back=False),
                    )
                    try:
                        sent = bot.send_message(chat_id, msg)
                        _remember_temp_notice(uid, sent)
                    except Exception:
                        pass
                    return

            if data.startswith("cm:"):
                bot.answer_callback_query(call.id)
                if db.is_blocked(uid):
                    bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                    return

                chat_id = call.message.chat.id
                message_id = call.message.message_id
                db.ensure_user(uid, call.from_user.username, None)

                if data == "cm:buy_cancel":
                    s = session(uid)
                    s.cm_buy_pending = False
                    s.cm_buy_category = None
                    s.cm_buy_code = None
                    s.cm_buy_prefix = None
                    s.cm_buy_panel_chat_id = None
                    s.cm_buy_panel_message_id = None
                    s.cm_buy_max_qty = None
                    try:
                        cid = int(getattr(s, "cm_buy_prompt_chat_id", 0) or 0)
                        mid = int(getattr(s, "cm_buy_prompt_message_id", 0) or 0)
                        if cid and mid:
                            _safe_delete_message(bot, cid, mid)
                    except Exception:
                        pass
                    s.cm_buy_prompt_chat_id = None
                    s.cm_buy_prompt_message_id = None
                    try:
                        bot.answer_callback_query(call.id, "Отменено", show_alert=False)
                    except Exception:
                        pass
                    return

                if data == "cm:exit":
                    reset_user_flow(uid)
                    reset_admin_flow(uid)
                    try:
                        _safe_delete_message(bot, int(chat_id), int(message_id))
                    except Exception:
                        pass
                    _set_reply_keyboard_silent(chat_id, main_menu_kb(is_admin=_is_admin(uid, settings)))
                    return

                if data == "cm:home":
                    bot.edit_message_text(_cm_shop_home_text(uid), chat_id=chat_id, message_id=message_id, reply_markup=cryptomine_shop_main_kb(prefix="cm"))
                    return

                if data == "cm:noop":
                    return

                if data.startswith("cm:cat:"):
                    cat = data.split(":", 2)[2]
                    bot.edit_message_text(
                        _cm_category_text(cat, uid),
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=cryptomine_category_kb(
                            cat,
                            prefix="cm",
                            home_cb="cm:home",
                            gpu_suffix_by_code=_cm_gpu_btc_hour_suffix(uid) if str(cat) == "gpu" else None,
                            cool_suffix_by_code=_cm_cool_suffix_by_code() if str(cat) == "cool" else None,
                        ),
                    )
                    return

                if data.startswith("cm:item:"):
                    parts = data.split(":")
                    if len(parts) != 4:
                        return
                    cat = parts[2]
                    code = parts[3]
                    item = _CM_ITEMS.get(cat, {}).get(code)
                    if not item:
                        bot.send_message(chat_id, "❌ Товар не найден")
                        return
                    bot.edit_message_text(
                        _cm_item_text(cat, code, uid=uid, detailed=False),
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=cryptomine_item_kb(category=cat, code=code, show_badge=item.get("badge"), prefix="cm", back_to_category_prefix="cm"),
                    )
                    return

                if data.startswith("cm:info:"):
                    parts = data.split(":")
                    if len(parts) != 4:
                        return
                    cat = parts[2]
                    code = parts[3]
                    if cat != "gpu":
                        return
                    item = _CM_ITEMS.get(cat, {}).get(code)
                    if not item:
                        bot.send_message(chat_id, "❌ Товар не найден")
                        return
                    bot.edit_message_text(
                        _cm_item_text(cat, code, uid=uid, detailed=True),
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=cryptomine_item_kb(category=cat, code=code, show_badge=item.get("badge"), prefix="cm", back_to_category_prefix="cm"),
                    )
                    return

                if data.startswith("cm:buy:"):
                    parts = data.split(":")
                    if len(parts) != 4:
                        return
                    cat = parts[2]
                    code = parts[3]
                    handled, err = _cm_start_buy_qty_prompt(
                        uid_local=uid,
                        cat=cat,
                        code=code,
                        prefix="cm",
                        panel_chat_id=int(chat_id),
                        panel_message_id=int(message_id),
                    )
                    if handled:
                        if err:
                            bot.send_message(chat_id, err)
                        return

                    ok, msg = _cm_try_buy(uid, cat, code, qty=1)
                    if not ok:
                        bot.send_message(chat_id, msg)
                        return
                    s = session(uid)
                    # If user is currently using the farm panel, and bought a GPU from the
                    # shop opened via "Добавить карту", return them to the farm view so
                    # they can install the purchased card immediately.
                    if str(cat) == "gpu" and getattr(s, "cmf_mode", False) and int(getattr(s, "cmf_chat_id", 0) or 0) == int(chat_id):
                        try:
                            if getattr(s, "cmf_message_id", None):
                                bot.edit_message_text(_cmf_farm_text(uid), chat_id=chat_id, message_id=int(s.cmf_message_id), reply_markup=cryptomine_farm_kb())
                        except Exception:
                            pass
                    else:
                        bot.edit_message_text(_cm_shop_home_text(uid), chat_id=chat_id, message_id=message_id, reply_markup=cryptomine_shop_main_kb(prefix="cm"))
                    try:
                        if str(cat) in {"gpu", "psu", "cool", "slots"}:
                            sent = bot.send_message(chat_id, msg)
                            _remember_temp_notice(uid, sent)
                        else:
                            bot.send_message(chat_id, msg)
                    except Exception:
                        pass
                    return

            if data == "history":
                bot.answer_callback_query(call.id)
                bot.send_message(call.message.chat.id, "История пока недоступна.", reply_markup=back_inline_kb())
                return

            if data.startswith("tourn:"):
                bot.answer_callback_query(call.id)
                if db.is_blocked(uid):
                    bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                    return
                now_ts = int(time.time())
                t = _pick_primary_tournament(now_ts)
                if not t:
                    bot.send_message(call.message.chat.id, "🏆 Сейчас нет активных турниров.")
                    return
                tid = int(t.get("id") or 0)
                state = str(t.get("state") or "")

                if data == "tourn:list":
                    _send_tournament_screen(call.message.chat.id, uid, edit_message_id=call.message.message_id)
                    return

                if data == "tourn:rules":
                    bot.send_message(
                        call.message.chat.id,
                        "🏆 Правила турнира (MVP)\n\n"
                        "Игра: 💣 Мины → режим «Без ставок (XP)»\n"
                        "Счёт: количество открытых 💎 (safe)\n"
                        "Тай-брейк: меньшая длительность попытки (ms)\n"
                        "Неявка до дедлайна: авто-поражение.",
                        reply_markup=back_inline_kb(),
                    )
                    return

                if data == "tourn:reg":
                    db.ensure_user(uid, call.from_user.username, None)
                    res = db.register_for_tournament(tid, user_id=uid, username=call.from_user.username, now_ts=now_ts)
                    if not res.get("ok"):
                        reason = str(res.get("reason") or "")
                        msg = "❌ Не удалось записаться."
                        if reason == "full":
                            msg = "❌ Турнир уже заполнен."
                        elif reason == "insufficient":
                            msg = "❌ Недостаточно баллов для взноса."
                        elif reason == "daily_limit":
                            msg = "❌ Лимит: 1 турнир в день."
                        elif reason in ("closed", "already_started"):
                            msg = "❌ Регистрация закрыта."
                        bot.send_message(call.message.chat.id, msg)
                    _send_tournament_screen(call.message.chat.id, uid, edit_message_id=call.message.message_id)
                    return

                if data == "tourn:unreg":
                    res = db.unregister_from_tournament(tid, user_id=uid, now_ts=now_ts)
                    if not res.get("ok"):
                        bot.send_message(call.message.chat.id, "❌ Не удалось отменить участие.")
                    _send_tournament_screen(call.message.chat.id, uid, edit_message_id=call.message.message_id)
                    return

                if data == "tourn:play":
                    if state != "running":
                        bot.send_message(call.message.chat.id, "⏳ Турнир ещё не начался.")
                        return
                    if not db.is_user_registered_in_tournament(tid, uid):
                        bot.send_message(call.message.chat.id, "Сначала нажмите «Участвовать».")
                        return

                    active = db.get_active_mines_round(uid)
                    if active:
                        bot.send_message(call.message.chat.id, "⏳ У вас уже есть активный раунд в 💣 Мины. Завершите его.")
                        return

                    m = db.get_user_pending_match(tid, uid)
                    if not m:
                        bot.send_message(call.message.chat.id, "⏳ Сейчас нет активного матча. Ждите следующий раунд.")
                        return

                    s = session(uid)
                    s.tourn_active_tournament_id = tid
                    s.tourn_active_match_id = int(m.get("id") or 0)
                    s.tourn_active_game_index = 0

                    # Force tournament params: mines no-bet on 3x3
                    _mines_reset(uid)
                    s.mines_mode = "nobet"
                    s.mines_size = 3
                    s.mines_mines = 3
                    s.mines_bet = None
                    s.mines_state = "confirm"

                    bot.send_message(
                        call.message.chat.id,
                        "🏆 Турнирный матч\n\n"
                        f"Матч #{int(m.get('id') or 0)} | Раунд {int(m.get('round') or 1)}\n"
                        "Игра: 💣 Мины (Без ставок)\n"
                        "Нажмите «Начать», чтобы сыграть попытку.",
                        reply_markup=mines_confirm_kb(),
                    )
                    return

            if data.startswith("admin:tourn:"):
                if not _is_admin(uid, settings):
                    bot.answer_callback_query(call.id)
                    return
                bot.answer_callback_query(call.id)
                action = data.split(":", 2)[2]
                if action == "create":
                    reset_admin_flow(uid)
                    s = session(uid)
                    s.admin_tourn_step = "max_players"
                    bot.send_message(call.message.chat.id, "🏆 Создание турнира (MVP)\n\nВведите число участников (16/32/64):")
                    return
                bot.send_message(call.message.chat.id, "Команда админа пока не реализована.")
                return

            if data == "faq:back":
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    _faq_main_text(),
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=_faq_kb(),
                )
                return

            if data.startswith("faq:"):
                topic = data.split(":", 1)[1]
                bot.answer_callback_query(call.id)
                km = InlineKeyboardMarkup()
                km.add(InlineKeyboardButton("◀️ Назад к вопросам", callback_data="faq:back"))
                bot.edit_message_text(
                    _faq_answer(topic),
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=km,
                )
                return

            # (остальная логика обработчика ниже остаётся без изменений)
        except Exception as e:
            try:
                bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=False)
            except Exception:
                pass
            try:
                bot.logger.error(f"Callback handler crashed: {e}")
            except Exception:
                pass
            try:
                traceback.print_exc()
            except Exception:
                pass
            return

        if data == "profile:withdraw":
            bot.answer_callback_query(call.id)
            _send_withdraw_menu(call.message.chat.id, uid)
            return

        if data == "profile:rating":
            bot.answer_callback_query(call.id)
            text, km = _format_balance_leaderboard(uid)
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
                parse_mode="HTML",
            )
            return

        if data == "profile:weekly":
            bot.answer_callback_query(call.id)
            _weekly_show(call, uid)
            return

        if data.startswith("weekly:claim:"):
            try:
                slot = int(data.split(":", 2)[2])
            except Exception:
                return
            now_ts = int(time.time())
            week_key = db.week_key_utc(now_ts)
            res = db.try_claim_weekly_task(uid, week_key=week_key, slot=slot, now_ts=now_ts)
            if not res.get("ok"):
                reason = str(res.get("reason") or "")
                if reason == "already_claimed":
                    bot.answer_callback_query(call.id, "✅ Уже получено", show_alert=False)
                elif reason == "not_completed":
                    bot.answer_callback_query(call.id, "⏳ Ещё не выполнено", show_alert=False)
                else:
                    bot.answer_callback_query(call.id, "❌ Не удалось", show_alert=False)
                _weekly_show(call, uid)
                return

            reward = int(res.get("reward_points") or 0)
            lvl_res = db.add_balance(uid, reward)
            bot.answer_callback_query(call.id, f"🎉 +{reward} баллов", show_alert=False)
            if lvl_res.get("leveled_up"):
                try:
                    bot.send_message(call.message.chat.id, "🎉 Поздравляем!\n" f"Вы достигли уровня: {lvl_res.get('new_title')}")
                except Exception:
                    pass
            _weekly_show(call, uid)
            return

        if data == "rating:menu":
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                "🏆 РЕЙТИНГ ИГРОКОВ\n\nВыберите категорию:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=rating_main_kb(),
            )
            return

        if data == "rating:back":
            bot.answer_callback_query(call.id)
            _send_profile(call.message.chat.id, uid)
            return

        if data == "rating:level":
            bot.answer_callback_query(call.id)
            text, km = _format_level_leaderboard(uid)
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
                parse_mode="HTML",
            )
            return

        if data == "rating:balance":
            bot.answer_callback_query(call.id)
            text, km = _format_balance_leaderboard(uid)
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
                parse_mode="HTML",
            )
            return

        if data == "rating:duels":
            bot.answer_callback_query(call.id)
            text, km = _format_duel_leaderboard(uid)
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
                parse_mode="HTML",
            )
            return

        if data == "rating:referrals":
            bot.answer_callback_query(call.id)
            text, km = _format_referrals_leaderboard(uid)
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
                parse_mode="HTML",
            )
            return

        if data.startswith("rating:user:"):
            bot.answer_callback_query(call.id)
            parts = data.split(":")
            if len(parts) != 4:
                return
            metric = str(parts[2])
            try:
                target_uid = int(parts[3])
            except Exception:
                return

            info = db.get_user_level_info(target_uid) or {}
            if not info:
                snap = db.get_user_stats_snapshot(target_uid) or {}
                try:
                    level_fallback = int(snap.get("level", 1) or 1)
                except Exception:
                    level_fallback = 1
                try:
                    xp_fallback = int(snap.get("xp", 0) or 0)
                except Exception:
                    xp_fallback = 0
                try:
                    bal_fallback = int(snap.get("balance_points", 0) or 0)
                except Exception:
                    bal_fallback = 0
                if bal_fallback <= 0:
                    try:
                        bal_fallback = int(db.get_balance(target_uid) or 0)
                    except Exception:
                        bal_fallback = 0
                vip_fallback = False
                try:
                    vip_fallback = bool(db.is_vip_active(target_uid, now_ts=int(time.time())))
                except Exception:
                    vip_fallback = False
                info = {
                    "level": level_fallback,
                    "title": db.get_level_title(level_fallback),
                    "xp": xp_fallback,
                    "balance_points": bal_fallback,
                    "vip_active": vip_fallback,
                }

            username = None
            try:
                username = db.get_user_field(target_uid, "username")
            except Exception:
                username = None
            uname = ("@" + str(username)) if username else None
            uname_disp = f"{uname} (ID {target_uid})" if uname else f"ID {target_uid}"

            vip_badge = " 👑 VIP" if info.get("vip_active") else ""
            custom_title = info.get("custom_title")
            emoji_pack = info.get("emoji_pack")

            # Duel stats
            def _gf(field: str, default: int = 0) -> int:
                try:
                    return int(db.get_user_field(target_uid, field) or default)
                except Exception:
                    return int(default)

            mmr = _gf("duel_mmr", 1000)
            wins = _gf("duel_wins", 0)
            losses = _gf("duel_losses", 0)
            games = _gf("duel_games", 0)
            rank_val = None
            try:
                rank_val = db.get_user_field(target_uid, "duel_rank")
            except Exception:
                rank_val = None
            duel_rank = str(rank_val) if rank_val else _duel_rank_from_mmr(mmr)
            wr = (float(wins) / float(games) * 100.0) if games > 0 else 0.0

            lines: list[str] = [
                f"━━━━━ <b>Карточка игрока</b> ━━━━━",
                "",
                f"👤 {uname_disp}{vip_badge}",
            ]
            if custom_title:
                lines.append(f"🏷 {html_escape(str(custom_title))}")

            lines.extend(
                [
                    "",
                    f"⭐ Уровень: <b>{int(info.get('level') or 1)}</b> ({html_escape(str(info.get('title') or ''))})",
                    f"✨ XP: <b>{_fmt_int(int(info.get('xp') or 0))}</b>",
                    f"💰 Баланс: <b>{_fmt_int(int(info.get('balance_points') or 0))}</b> баллов",
                    "",
                    f"📋 Выполнено заданий: <b>{int(info.get('completed_tasks') or 0)}</b>",
                    f"👥 Приглашено друзей: <b>{int(info.get('referrals_count') or 0)}</b>",
                    "",
                    "⚔️ <b>Дуэли</b>:",
                    f"├ Ранг: <b>{html_escape(duel_rank)}</b>",
                    f"├ MMR: <b>{mmr}</b>",
                    f"└ Побед: <b>{wins}</b> | Поражений: <b>{losses}</b> | Винрейт: <b>{wr:.1f}%</b>",
                ]
            )

            if emoji_pack:
                lines.append("")
                lines.append(f"😎 Эмодзи-пак: <b>{html_escape(str(emoji_pack))}</b>")

            back_cb = {
                "level": "rating:level",
                "balance": "rating:balance",
                "duels": "rating:duels",
                "referrals": "rating:referrals",
            }.get(metric, "rating:menu")

            km = InlineKeyboardMarkup()
            km.row(
                InlineKeyboardButton(text="◀️ Назад к ТОП", callback_data=str(back_cb)),
                InlineKeyboardButton(text="◀️ Категории", callback_data="rating:menu"),
            )
            km.add(InlineKeyboardButton(text="⬅ Профиль", callback_data="rating:back"))

            bot.edit_message_text(
                "\n".join(lines),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=km,
            )
            return

        if data == "support:rules":
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                "Правила:\n1) Скрин должен быть читаемым.\n2) Обман = блокировка.",
                reply_markup=back_inline_kb(),
            )
            return

        if data == "invite:link":
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "Используйте кнопку 👥 Пригласить друга")
            return

        # --- Admin duel server callbacks ---

        if data == "admin:panel":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            reset_admin_flow(uid)
            bot.send_message(call.message.chat.id, "👑 АДМИН-ПАНЕЛЬ", reply_markup=admin_menu_kb())
            return

        # --- Admin gift/chat flow ---

        if data.startswith("admin:gift:") or data.startswith("admin:chat:"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                return

            s = session(uid)
            chat_id = int(call.message.chat.id)

            def _ensure_target_selected() -> int | None:
                try:
                    tid = int(getattr(s, "admin_target_user_id", 0) or 0)
                except Exception:
                    tid = 0
                return tid if tid > 0 else None

            def _send_confirm() -> None:
                tid = int(s.admin_target_user_id or 0)
                amt = int(s.admin_gift_amount or 0)
                notify = bool(getattr(s, "admin_gift_notify", True))
                preview = (s.admin_gift_text or "").strip()
                bot.send_message(
                    chat_id,
                    "🎁 Подтверждение\n\n"
                    f"Кому: {tid}\n"
                    f"Сумма: +{amt} баллов\n"
                    f"Уведомление: {'ВКЛ' if notify else 'ВЫКЛ'}\n\n"
                    f"Текст: {preview if preview else '(по умолчанию)'}",
                    reply_markup=admin_gift_confirm_kb(notify_enabled=notify),
                )

            if data == "admin:gift:cancel":
                reset_admin_flow(uid)
                bot.send_message(chat_id, "👑 АДМИН-ПАНЕЛЬ", reply_markup=admin_menu_kb())
                return

            if data == "admin:gift:pick_user":
                reset_admin_flow(uid)
                s = session(uid)
                s.admin_flow = "gift_pick_user"
                s.admin_gift_notify = True
                bot.send_message(chat_id, "Введи ID пользователя (число) или @username:")
                return

            if data == "admin:gift:amount":
                tid = _ensure_target_selected()
                if not tid:
                    bot.send_message(chat_id, "Сначала выберите пользователя: нажмите «🎁 Подарить баллы» и введите ID/@username.")
                    return
                s.admin_flow = "gift_amount"
                bot.send_message(chat_id, f"Введите сумму подарка (баллы) для ID {tid}:")
                return

            if data == "admin:gift:text":
                tid = _ensure_target_selected()
                if not tid:
                    bot.send_message(chat_id, "Сначала выберите пользователя.")
                    return
                s.admin_flow = "gift_text"
                bot.send_message(chat_id, "Введите текст уведомления (или '-' чтобы оставить по умолчанию/очистить):")
                return

            if data == "admin:gift:notify:toggle":
                try:
                    s.admin_gift_notify = not bool(getattr(s, "admin_gift_notify", True))
                except Exception:
                    s.admin_gift_notify = True

                # Re-render current confirm message if possible
                try:
                    tid = int(s.admin_target_user_id or 0)
                    amt = int(s.admin_gift_amount or 0)
                    notify = bool(getattr(s, "admin_gift_notify", True))
                    preview = (s.admin_gift_text or "").strip()
                    bot.edit_message_text(
                        "🎁 Подтверждение\n\n"
                        f"Кому: {tid}\n"
                        f"Сумма: +{amt} баллов\n"
                        f"Уведомление: {'ВКЛ' if notify else 'ВЫКЛ'}\n\n"
                        f"Текст: {preview if preview else '(по умолчанию)'}",
                        chat_id=chat_id,
                        message_id=int(call.message.message_id),
                        reply_markup=admin_gift_confirm_kb(notify_enabled=notify),
                    )
                except Exception:
                    pass
                return

            if data == "admin:gift:send":
                tid = _ensure_target_selected()
                amt = int(getattr(s, "admin_gift_amount", 0) or 0)
                if not tid:
                    bot.send_message(chat_id, "Сначала выберите пользователя.")
                    return
                if amt <= 0:
                    bot.send_message(chat_id, "Сначала задайте сумму подарка.")
                    return

                # Ensure DB row exists
                try:
                    db.ensure_user(int(tid), None, None)
                except Exception:
                    pass

                lvl_res: dict | None = None
                try:
                    lvl_res = db.add_balance(int(tid), int(amt))
                except Exception:
                    lvl_res = None

                notify = bool(getattr(s, "admin_gift_notify", True))
                text_custom = (s.admin_gift_text or "").strip()
                notify_sent = False
                notify_error = False
                if notify:
                    notify_text = text_custom or f"🎁 Вам начислено +{amt} баллов!"
                    try:
                        bot.send_message(int(tid), notify_text)
                        notify_sent = True
                    except Exception:
                        notify_error = True

                # Keep selected user, reset gift params
                s.admin_gift_amount = None
                s.admin_gift_text = None
                s.admin_gift_notify = True
                s.admin_flow = None

                try:
                    bal = int(db.get_balance(int(tid)) or 0)
                except Exception:
                    bal = 0

                status_lines = [f"✅ Начислено пользователю ID {tid}: +{amt} баллов", f"Новый баланс: {bal}"]
                if notify:
                    if notify_sent:
                        status_lines.append("🔔 Уведомление: отправлено")
                    elif notify_error:
                        status_lines.append("⚠️ Уведомление: не удалось отправить (пользователь мог не писать боту)")
                else:
                    status_lines.append("🔕 Уведомление: выключено")

                if isinstance(lvl_res, dict) and lvl_res.get("leveled_up"):
                    status_lines.append(f"🎉 Уровень повышен: {lvl_res.get('new_title')}")

                bot.send_message(chat_id, "\n".join(status_lines))

                u = db.find_user(int(tid))
                if u:
                    st = "Заблокирован" if int(u.get("blocked") or 0) else "Активный"
                    bot.send_message(
                        chat_id,
                        "👤 Пользователь\n\n"
                        f"ID: {u['user_id']}\n"
                        f"@{u['username'] or 'без_ника'}\n"
                        f"Баланс: {int(u.get('balance_points') or 0)}\n"
                        f"Статус: {st}",
                        reply_markup=admin_gift_user_kb(),
                    )
                return

            if data == "admin:chat:start":
                tid = _ensure_target_selected()
                if not tid:
                    bot.send_message(chat_id, "Сначала выберите пользователя.")
                    return

                s.admin_flow = "chat"
                with admin_chat_lock:
                    admin_chat_map[int(tid)] = int(uid)

                bot.send_message(
                    chat_id,
                    f"💬 Диалог активен с пользователем ID {tid}.\n"
                    "Все ваши следующие сообщения будут отправляться ему.\n"
                    "Нажмите «⛔ Завершить диалог», чтобы выйти.",
                    reply_markup=admin_chat_stop_kb(),
                )

                # Optional: notify user
                try:
                    bot.send_message(int(tid), "💬 Админ начал диалог. Можете написать сообщение, оно будет доставлено админу.")
                except Exception:
                    pass
                return

            if data == "admin:chat:stop":
                tid = _ensure_target_selected()
                if tid:
                    with admin_chat_lock:
                        cur = admin_chat_map.get(int(tid))
                        if cur == int(uid):
                            admin_chat_map.pop(int(tid), None)
                s.admin_flow = None
                bot.send_message(chat_id, "⛔ Диалог завершён.")
                if tid:
                    u = db.find_user(int(tid))
                    if u:
                        st = "Заблокирован" if int(u.get("blocked") or 0) else "Активный"
                        bot.send_message(
                            chat_id,
                            "👤 Пользователь\n\n"
                            f"ID: {u['user_id']}\n"
                            f"@{u['username'] or 'без_ника'}\n"
                            f"Баланс: {int(u.get('balance_points') or 0)}\n"
                            f"Статус: {st}",
                            reply_markup=admin_gift_user_kb(),
                        )
                return

            # Unknown admin gift/chat command
            return

        if data == "admin:duel_server:menu":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            _send_admin_duel_server_menu(call.message.chat.id, edit=True, message_id=call.message.message_id)
            return

        if data == "admin:duel_server:quick":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            open_cnt = int(db.count_open_server_duels() or 0)
            max_pool = _get_int_setting(DUEL_SERVER_RANDOM_MAX_KEY, default=0)
            hint = "\n\n⚠ Лимит пула не задан." if int(max_pool) <= 0 else f"\n\nЛимит пула: {int(max_pool)}"
            bot.edit_message_text(
                "✅ Быстрый запуск\n\n"
                f"Сейчас в пуле: {open_cnt}\n"
                "Добавить +5 дуэлей в пул."
                + hint,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=admin_duel_server_quick_kb(),
            )
            return

        if data == "admin:duel_server:quick:do":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            max_pool = _get_int_setting(DUEL_SERVER_RANDOM_MAX_KEY, default=0)
            current = int(db.count_open_server_duels() or 0)
            want = 5
            if int(max_pool) > 0:
                want = max(0, min(int(want), int(max_pool) - int(current)))
            if want <= 0:
                bot.answer_callback_query(call.id, "Лимит пула достигнут")
                _send_admin_duel_server_menu(call.message.chat.id, edit=True, message_id=call.message.message_id)
                return

            games = _get_set_setting_str(DUEL_SERVER_RANDOM_GAMES_KEY, default={"dice", "rps"})
            stakes = _get_set_setting_int(DUEL_SERVER_RANDOM_STAKES_KEY, default={200, 500, 1000})
            games = {g for g in games if g in {"dice", "rps"}} or {"dice", "rps"}
            stakes = {s for s in stakes if s in {200, 500, 1000}} or {200, 500, 1000}

            created = 0
            for _ in range(int(want)):
                gt = random.choice(sorted(list(games)))
                st = random.choice(sorted(list(stakes)))
                db.create_duel(0, stake=int(st), game_type=str(gt), is_bot=True)
                created += 1
            bot.answer_callback_query(call.id, f"Добавлено: {created}")
            _send_admin_duel_server_menu(call.message.chat.id, edit=True, message_id=call.message.message_id, ensure_random=False)
            return

        if data == "admin:duel_server:manage":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            _edit_admin_duel_manage_menu(call.message.chat.id, call.message.message_id, page=0)
            return

        if data.startswith("admin:duel_manage:menu:"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            parts = data.split(":")
            page = 0
            if len(parts) >= 4 and str(parts[3]).isdigit():
                page = int(parts[3])
            _edit_admin_duel_manage_menu(call.message.chat.id, call.message.message_id, page=page)
            return

        if data.startswith("admin:duel_manage:delete:"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            parts = data.split(":")
            if len(parts) < 4 or not str(parts[3]).isdigit():
                return
            duel_id = int(parts[3])
            duel = db.get_duel_by_id(duel_id)
            if not duel or str(duel.get("status") or "") != "waiting":
                bot.answer_callback_query(call.id, "❌ Дуэль уже недоступна")
                _edit_admin_duel_manage_menu(call.message.chat.id, call.message.message_id, page=0)
                return

            try:
                is_bot = int(duel.get("is_bot") or 0)
            except Exception:
                is_bot = 0
            try:
                creator_id = int(duel.get("creator_id") or 0)
            except Exception:
                creator_id = 0

            ok = False
            try:
                if is_bot == 1 or creator_id == 0:
                    ok = bool(db.delete_open_server_duel(duel_id))
                else:
                    ok = bool(db.cancel_waiting_duel(duel_id))
            except Exception:
                ok = False
            bot.answer_callback_query(call.id, "✅ Готово" if ok else "❌ Не удалось")
            _edit_admin_duel_manage_menu(call.message.chat.id, call.message.message_id, page=0)
            return

        if data == "admin:duel_server:limit":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            max_pool = _get_int_setting(DUEL_SERVER_RANDOM_MAX_KEY, default=0)
            bot.edit_message_text(
                "⚙ Лимит пула\n\nВыберите максимальное количество дуэлей в пуле:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=admin_duel_server_limit_kb(max_pool=max_pool),
            )
            return

        if data == "admin:duel_server:limit:custom":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            s = session(uid)
            s.admin_duel_server_step = "random_setmax"
            bot.send_message(call.message.chat.id, "Введите максимальный размер пула (число):")
            return

        if data.startswith("admin:duel_server:limit:set:"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            parts = data.split(":")
            if len(parts) < 5 or not str(parts[4]).isdigit():
                return
            max_pool = int(parts[4])
            db.set_setting(DUEL_SERVER_RANDOM_MAX_KEY, str(max(0, max_pool)))
            try:
                _ensure_random_duel_pool()
            except Exception:
                pass
            _send_admin_duel_server_menu(call.message.chat.id, edit=True, message_id=call.message.message_id)
            return

        if data.startswith("admin:duel_server:delete_menu"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            page = 0
            parts = data.split(":")
            if len(parts) >= 4 and str(parts[3]).isdigit():
                page = int(parts[3])
            _edit_admin_duel_server_delete_menu(call.message.chat.id, call.message.message_id, page=page)
            return

        if data == "admin:duel_server:delete_all:confirm":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return

            try:
                open_cnt = int(db.count_open_server_duels() or 0)
            except Exception:
                open_cnt = 0
            kb = InlineKeyboardMarkup()
            kb.row(
                InlineKeyboardButton(text="✅ Удалить все", callback_data="admin:duel_server:delete_all:do"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin:duel_server:menu"),
            )
            bot.edit_message_text(
                "🧹 Очистить пул дуэлей\n\n"
                f"Сейчас в пуле: {open_cnt}\n\n"
                "Удалить ВСЕ открытые дуэли из пула (создатель=0 / бот)?",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=kb,
            )
            return

        if data == "admin:duel_server:delete_all:do":
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            deleted = 0
            try:
                deleted = int(db.delete_all_open_server_duels() or 0)
            except Exception:
                deleted = 0
            try:
                if deleted > 0:
                    bot.answer_callback_query(call.id, f"✅ Удалено: {deleted}")
                else:
                    bot.answer_callback_query(call.id, "ℹ️ Пул пуст — удалять нечего")
            except Exception:
                pass
            _send_admin_duel_server_menu(call.message.chat.id, edit=True, message_id=call.message.message_id, ensure_random=False)
            return

        if data.startswith("admin:duel_server:delete:"):
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            parts = data.split(":")
            if len(parts) < 4 or not str(parts[3]).isdigit():
                bot.answer_callback_query(call.id, "Некорректная дуэль")
                return
            duel_id = int(parts[3])
            ok = False
            try:
                ok = bool(db.delete_open_server_duel(int(duel_id)))
            except Exception:
                ok = False
            try:
                bot.answer_callback_query(call.id, "✅ Удалено" if ok else "❌ Не удалось")
            except Exception:
                pass
            _edit_admin_duel_server_delete_menu(call.message.chat.id, call.message.message_id, page=0)
            return

        if data == "admin:duel_server:auto_recreate":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            cur = _get_bool_setting(DUEL_SERVER_AUTO_RECREATE_KEY, default=False)
            db.set_setting(DUEL_SERVER_AUTO_RECREATE_KEY, "0" if cur else "1")
            _send_admin_duel_server_menu(call.message.chat.id, edit=True, message_id=call.message.message_id)
            return

        if data == "admin:duel_server:add":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            s = session(uid)
            s.admin_duel_server_step = None
            s.admin_duel_server_game_type = None
            s.admin_duel_server_stake = None
            s.admin_duel_server_add_one = False
            bot.edit_message_text(
                "⚔ Сервер дуэлей\n\nВыберите тип игры для создания дуэлей:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=admin_duel_server_add_game_kb(),
            )
            return

        if data == "admin:duel_server:add_one":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            s = session(uid)
            s.admin_duel_server_step = None
            s.admin_duel_server_game_type = None
            s.admin_duel_server_stake = None
            s.admin_duel_server_add_one = True
            bot.edit_message_text(
                "⚔ Сервер дуэлей\n\nВыберите тип игры для создания 1 дуэли:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=admin_duel_server_add_game_kb(),
            )
            return

        if data.startswith("admin:duel_server:add_game:"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            gt = data.split(":", 3)[3]
            if gt not in ("dice", "rps"):
                return
            s = session(uid)
            s.admin_duel_server_game_type = gt
            bot.edit_message_text(
                "Выберите ставку:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=admin_duel_server_add_stake_kb(game_type=gt),
            )
            return

        if data.startswith("admin:duel_server:add_stake:"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            parts = data.split(":")
            if len(parts) < 5:
                return
            gt = parts[3]
            if gt not in ("dice", "rps"):
                return
            try:
                stake = int(parts[4])
            except Exception:
                return
            if stake <= 0:
                return
            s = session(uid)
            s.admin_duel_server_game_type = gt
            s.admin_duel_server_stake = stake

            # "Add 1 duel" mode: create instantly without asking for count.
            if bool(getattr(s, "admin_duel_server_add_one", False)):
                try:
                    db.create_duel(0, stake=int(stake), game_type=str(gt), is_bot=True)
                    bot.answer_callback_query(call.id, "✅ Создано: 1")
                except Exception:
                    bot.answer_callback_query(call.id, "❌ Не удалось")
                s.admin_duel_server_step = None
                s.admin_duel_server_game_type = None
                s.admin_duel_server_stake = None
                s.admin_duel_server_add_one = False
                _send_admin_duel_server_menu(call.message.chat.id, edit=True, message_id=call.message.message_id, ensure_random=False)
                return

            s.admin_duel_server_step = "add_count"
            bot.send_message(call.message.chat.id, "Введите количество дуэлей (число):")
            return

        if data == "admin:duel_server:random":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return

            enabled = _get_bool_setting(DUEL_SERVER_RANDOM_ENABLED_KEY, default=False)
            min_pool = _get_int_setting(DUEL_SERVER_RANDOM_MIN_KEY, default=0)
            max_pool = _get_int_setting(DUEL_SERVER_RANDOM_MAX_KEY, default=0)
            games = _get_set_setting_str(DUEL_SERVER_RANDOM_GAMES_KEY, default={"dice", "rps"})
            stakes = _get_set_setting_int(DUEL_SERVER_RANDOM_STAKES_KEY, default={200, 500, 1000})
            games = {g for g in games if g in {"dice", "rps"}}
            stakes = {s for s in stakes if s in {200, 500, 1000}}

            bot.edit_message_text(
                "🎲 Рандом дуэлей\n\nНастройки генератора (минимум/максимум пула, типы игр и ставки):",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=admin_duel_server_random_kb(
                    enabled=enabled,
                    min_pool=min_pool,
                    max_pool=max_pool,
                    games=games,
                    stakes=stakes,
                ),
            )
            return

        if data == "admin:duel_server:random:toggle":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            cur = _get_bool_setting(DUEL_SERVER_RANDOM_ENABLED_KEY, default=False)
            db.set_setting(DUEL_SERVER_RANDOM_ENABLED_KEY, "0" if cur else "1")
            try:
                _ensure_random_duel_pool()
            except Exception:
                pass
            _edit_admin_duel_server_random_menu(call.message.chat.id, call.message.message_id)
            return

        if data == "admin:duel_server:random:setmin":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            s = session(uid)
            s.admin_duel_server_step = "random_setmin"
            bot.send_message(call.message.chat.id, "Введите минимальный размер пула (число):")
            return

        if data == "admin:duel_server:random:setmax":
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            s = session(uid)
            s.admin_duel_server_step = "random_setmax"
            bot.send_message(call.message.chat.id, "Введите максимальный размер пула (число):")
            return

        if data.startswith("admin:duel_server:random:game:"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            gt = data.split(":", 4)[4]
            if gt not in ("dice", "rps"):
                return
            games = _get_set_setting_str(DUEL_SERVER_RANDOM_GAMES_KEY, default={"dice", "rps"})
            games = {g for g in games if g in {"dice", "rps"}}
            if gt in games:
                games.discard(gt)
            else:
                games.add(gt)
            _save_set_setting_str(DUEL_SERVER_RANDOM_GAMES_KEY, games)
            _edit_admin_duel_server_random_menu(call.message.chat.id, call.message.message_id)
            return

        if data.startswith("admin:duel_server:random:stake:"):
            bot.answer_callback_query(call.id)
            if not _is_admin(uid, settings):
                bot.send_message(call.message.chat.id, "⛔ Доступно только админу.")
                return
            try:
                stake = int(data.split(":", 4)[4])
            except Exception:
                return
            if stake not in (200, 500, 1000):
                return
            stakes = _get_set_setting_int(DUEL_SERVER_RANDOM_STAKES_KEY, default={200, 500, 1000})
            stakes = {s for s in stakes if s in {200, 500, 1000}}
            if stake in stakes:
                stakes.discard(stake)
            else:
                stakes.add(stake)
            _save_set_setting_int(DUEL_SERVER_RANDOM_STAKES_KEY, stakes)
            _edit_admin_duel_server_random_menu(call.message.chat.id, call.message.message_id)
            return

        if data == "minigame:duels":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            bot.edit_message_text(
                _duels_menu_text(uid),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duels_main_kb(),
            )
            return

        if data == "duel:menu":
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                _duels_menu_text(uid),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duels_main_kb(),
            )
            return

        if data in ("duel:create", "duel:friend"):
            bot.answer_callback_query(call.id)
            s = session(uid)
            s.duel_stake = None
            s.duel_game_type = None
            # режим: публичная дуэль (создать) или игра с конкретным другом
            try:
                s.duel_mode = "public" if data == "duel:create" else "friend"
            except Exception:
                pass
            try:
                last = db.get_last_bets(int(uid), "duel", limit=5)
            except Exception:
                last = []
            bot.edit_message_text(
                "Выберите ставку для дуэли:\n⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=game_bet_kb(game="duel", last_bets=last),
            )
            return

        if data == "duel:find":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            s = session(uid)
            # Ensure defaults
            if not getattr(s, "server_duels_games", None):
                s.server_duels_games = {"dice", "rps", "ttt"}
            if not getattr(s, "server_duels_stakes", None):
                s.server_duels_stakes = {10, 100, 1000, 2500, 5000, 10000}

            duels, pages, page = _server_duels_get_filtered_page(uid)
            bot.edit_message_text(
                _server_duels_menu_text(duels, uid),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=server_duels_list_kb(
                    duels,
                    current_user_id=int(uid),
                    enabled_games=set(s.server_duels_games),
                    enabled_stakes=set(int(x) for x in s.server_duels_stakes),
                    page=int(page),
                    pages=int(pages),
                ),
            )
            return

        if data.startswith("duel:my:"):
            bot.answer_callback_query(call.id)
            try:
                duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(duel_id)
            if not duel:
                bot.send_message(call.message.chat.id, "❌ Дуэль не найдена.")
                return
            try:
                creator_id = int(duel.get("creator_id") or 0)
            except Exception:
                creator_id = 0
            try:
                is_bot = int(duel.get("is_bot") or 0)
            except Exception:
                is_bot = 0
            if creator_id != uid or is_bot != 0:
                bot.send_message(call.message.chat.id, "❌ Это не ваша дуэль.")
                return

            status = str(duel.get("status") or "")
            if status != "waiting":
                _render_server_duels_panel(chat_id=call.message.chat.id, message_id=call.message.message_id, uid=uid)
                return

            stake = int(duel.get("stake") or 0)
            gt = str(duel.get("game_type") or "")
            if gt == "dice":
                gt_txt = "🎲 Кости"
            elif gt == "rps":
                gt_txt = "✊✋✌ КНБ"
            else:
                gt_txt = "❌⭕ Крестики-нолики"
            text = f"🧾 Моя дуэль\n\n{gt_txt}\n💰 Ставка: {_fmt_money(stake)}\n⏳ Статус: ожидает соперника"
            km = InlineKeyboardMarkup()
            km.add(InlineKeyboardButton(text="❌ Отменить дуэль", callback_data=f"duel:cancel:{duel_id}"))
            km.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:refresh"))
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
            )
            return

        if data.startswith("duel:cancel:"):
            bot.answer_callback_query(call.id)
            try:
                duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(duel_id)
            if not duel:
                bot.send_message(call.message.chat.id, "❌ Дуэль не найдена.")
                return
            try:
                creator_id = int(duel.get("creator_id") or 0)
            except Exception:
                creator_id = 0
            try:
                is_bot = int(duel.get("is_bot") or 0)
            except Exception:
                is_bot = 0
            if creator_id != uid or is_bot != 0:
                bot.send_message(call.message.chat.id, "❌ Нельзя отменить эту дуэль.")
                return
            if str(duel.get("status") or "") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль уже недоступна.")
                return

            ok = db.cancel_waiting_duel(duel_id)
            if not ok:
                try:
                    bot.send_message(call.message.chat.id, "❌ Не удалось отменить дуэль (возможно, соперник уже присоединился).")
                except Exception:
                    pass
            _render_server_duels_panel(chat_id=call.message.chat.id, message_id=call.message.message_id, uid=uid)
            return

        # Список друзей для конкретной обычной дуэли (созданной через duel:type)
        if data.startswith("duel:friends_for_duel:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 3)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = 0
            if uid != creator_id:
                bot.send_message(call.message.chat.id, "❌ Только создатель дуэли может приглашать друзей.")
                return

            friends = db.list_recent_opponents(uid, limit=20)
            if not friends:
                text = (
                    "👥 Друзья\n\n"
                    "У вас пока нет друзей для дуэли.\n"
                    "Сыграйте хотя бы одну дуэль или пригласите друга по ссылке."
                )
                km = InlineKeyboardMarkup()
                km.add(InlineKeyboardButton(text="⬅ Назад", callback_data=f"duel:back_to_invite:{did}"))
                bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=km,
                )
                return

            text = "👥 Ваши друзья\n\nВыберите друга для дуэли:"
            km = InlineKeyboardMarkup()
            for fr in friends:
                uname = ("@" + fr["username"]) if fr.get("username") else f"ID {int(fr['user_id'])}"
                km.add(
                    InlineKeyboardButton(
                        text=uname,
                        callback_data=f"duel2:invite_user:{did}:{int(fr['user_id'])}",
                    )
                )
            km.add(InlineKeyboardButton(text="⬅ Назад", callback_data=f"duel:back_to_invite:{did}"))
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
            )
            return

        # Duel2: friends menu (global list of duel friends)
        if data == "duel2:friends":
            bot.answer_callback_query(call.id)
            friends = db.list_recent_opponents(uid, limit=20)
            if not friends:
                text = (
                    "👥 Друзья\n\n"
                    "У вас пока нет друзей для дуэли.\n"
                    "Сыграйте хотя бы одну дуэль или пригласите друга по ссылке."
                )
                km = InlineKeyboardMarkup()
                km.add(InlineKeyboardButton(text="➕ Пригласить друга", callback_data="duel2:friends_invite"))
                km.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel2:menu"))
                bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=km,
                )
                return

            text = "👥 Ваши друзья\n\nВыберите друга для дуэли:"
            km = InlineKeyboardMarkup()
            for fr in friends:
                uname = ("@" + fr["username"]) if fr.get("username") else f"ID {int(fr['user_id'])}"
                km.add(
                    InlineKeyboardButton(
                        text=uname,
                        callback_data=f"duel2:friends_select:{int(fr['user_id'])}",
                    )
                )
            km.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel2:menu"))
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
            )
            return

        if data == "duel:refresh":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            s = session(uid)
            duels, pages, page = _server_duels_get_filtered_page(uid)
            _safe_edit_message_text(
                bot,
                _server_duels_menu_text(duels, uid),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=server_duels_list_kb(
                    duels,
                    enabled_games=set(getattr(s, "server_duels_games", {"dice", "rps", "ttt"})),
                    enabled_stakes=set(int(x) for x in getattr(s, "server_duels_stakes", {10, 100, 1000, 2500, 5000, 10000})),
                    page=int(page),
                    pages=int(pages),
                ),
            )
            return

        if data.startswith("duel:filter:game:"):
            bot.answer_callback_query(call.id)
            gt = data.split(":", 3)[3]
            if gt not in ("dice", "rps", "ttt"):
                return
            s = session(uid)
            cur = set(getattr(s, "server_duels_games", {"dice", "rps", "ttt"}))
            if gt in cur:
                cur.discard(gt)
            else:
                cur.add(gt)
            s.server_duels_games = cur
            s.server_duels_page = 0
            duels, pages, page = _server_duels_get_filtered_page(uid)
            _safe_edit_message_text(
                bot,
                _server_duels_menu_text(duels, uid),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=server_duels_list_kb(
                    duels,
                    enabled_games=set(s.server_duels_games),
                    enabled_stakes=set(int(x) for x in getattr(s, "server_duels_stakes", set())),
                    page=int(page),
                    pages=int(pages),
                ),
            )
            return

        if data.startswith("duel:filter:stake:"):
            bot.answer_callback_query(call.id)
            try:
                amount = int(data.split(":", 3)[3])
            except Exception:
                return
            if amount not in (10, 100, 1000, 2500, 5000, 10000):
                return
            s = session(uid)
            cur = set(int(x) for x in getattr(s, "server_duels_stakes", {10, 100, 1000, 2500, 5000, 10000}))
            if amount in cur:
                cur.discard(amount)
            else:
                cur.add(amount)
            s.server_duels_stakes = cur
            s.server_duels_page = 0
            duels, pages, page = _server_duels_get_filtered_page(uid)
            _safe_edit_message_text(
                bot,
                _server_duels_menu_text(duels, uid),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=server_duels_list_kb(
                    duels,
                    enabled_games=set(getattr(s, "server_duels_games", {"dice", "rps", "ttt"})),
                    enabled_stakes=set(int(x) for x in s.server_duels_stakes),
                    page=int(page),
                    pages=int(pages),
                ),
            )
            return

        if data.startswith("duel:filter:page:"):
            bot.answer_callback_query(call.id)
            try:
                p = int(data.split(":", 3)[3])
            except Exception:
                return
            s = session(uid)
            s.server_duels_page = int(p)
            duels, pages, page = _server_duels_get_filtered_page(uid)
            _safe_edit_message_text(
                bot,
                _server_duels_menu_text(duels, uid),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=server_duels_list_kb(
                    duels,
                    enabled_games=set(getattr(s, "server_duels_games", {"dice", "rps", "ttt"})),
                    enabled_stakes=set(int(x) for x in getattr(s, "server_duels_stakes", {10, 100, 1000, 2500, 5000, 10000})),
                    page=int(page),
                    pages=int(pages),
                ),
            )
            return

        if data.startswith("duel:join:"):
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            try:
                duel_id = int(data.split(":", 2)[2])
            except Exception:
                return

            duel = db.get_duel_by_id(duel_id)
            if not duel or str(duel.get("status") or "") != "waiting":
                try:
                    bot.answer_callback_query(call.id, "❌ Дуэль недоступна.", show_alert=True)
                except Exception:
                    pass
                _render_server_duels_panel(chat_id=call.message.chat.id, message_id=call.message.message_id, uid=uid)
                return

            try:
                creator_id = int(duel.get("creator_id") or 0)
            except Exception:
                creator_id = 0
            try:
                is_bot_flag = int(duel.get("is_bot") or 0)
            except Exception:
                is_bot_flag = 0
            is_bot_duel = (is_bot_flag == 1 and creator_id == 0)

            # Clicking your own duel in the list should open "My duel" (so you can cancel).
            if not is_bot_duel and int(creator_id) == int(uid):
                stake = int(duel.get("stake") or 0)
                gt = str(duel.get("game_type") or "")
                if gt == "dice":
                    gt_txt = "🎲 Кости"
                elif gt == "rps":
                    gt_txt = "✊✋✌ КНБ"
                else:
                    gt_txt = "❌⭕ Крестики-нолики"
                text = f"🧾 Моя дуэль\n\n{gt_txt}\n💰 Ставка: {_fmt_money(stake)}\n⏳ Статус: ожидает соперника"
                km = InlineKeyboardMarkup()
                km.add(InlineKeyboardButton(text="❌ Отменить дуэль", callback_data=f"duel:cancel:{duel_id}"))
                km.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:refresh"))
                _safe_edit_message_text(
                    bot,
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=km,
                )
                return

            # Atomic join + stake deduction
            joined = db.join_waiting_duel_atomic(int(duel_id), user_id=int(uid))
            if not bool(joined.get("ok")):
                reason = str(joined.get("reason") or "")
                if reason == "no_balance":
                    bal = int(joined.get("balance") or 0)
                    bot.send_message(call.message.chat.id, f"❌ Недостаточно баллов. Баланс: {_fmt_points_ui(int(bal))}.")
                    return
                try:
                    bot.answer_callback_query(call.id, "⏳ Уже заняли или дуэль недоступна.", show_alert=True)
                except Exception:
                    pass
                _render_server_duels_panel(chat_id=call.message.chat.id, message_id=call.message.message_id, uid=uid)
                return

            # Refresh list immediately so duel disappears
            _render_server_duels_panel(chat_id=call.message.chat.id, message_id=call.message.message_id, uid=uid)

            stake = int((joined.get("duel") or {}).get("stake") or duel.get("stake") or 0)
            game_type = str((joined.get("duel") or {}).get("game_type") or duel.get("game_type") or "")
            creator_id = int((joined.get("duel") or {}).get("creator_id") or creator_id)

            # Auto-recreate bot pool
            if is_bot_duel:
                def _delayed_recreate(stake_val: int, game_type_val: str) -> None:
                    try:
                        time.sleep(random.randint(1, 10))
                    except Exception:
                        pass
                    try:
                        if _get_bool_setting(DUEL_SERVER_AUTO_RECREATE_KEY, default=False):
                            db.create_duel(0, stake=stake_val, game_type=game_type_val, is_bot=True)
                        try:
                            _ensure_random_duel_pool()
                        except Exception:
                            pass
                    except Exception:
                        pass

                try:
                    threading.Thread(target=_delayed_recreate, args=(int(stake), str(game_type or "dice")), daemon=True).start()
                except Exception:
                    pass

            if is_bot_duel:
                if game_type == "dice":
                    kb = InlineKeyboardMarkup()
                    kb.add(InlineKeyboardButton(text="🎲 Кинуть кубик", callback_data=f"duel:dice:roll:{duel_id}"))
                    bot.send_message(uid, "⚔ Дуэль (сервер) началась!\n\nНажмите кнопку, чтобы кинуть кубик.", reply_markup=kb)
                    return
                try:
                    db.update_duel_rps_choice(int(duel_id), user_id=0, choice=random.choice(["rock", "paper", "scissors"]))
                except Exception:
                    pass
                bot.send_message(uid, "⚔ Дуэль КНБ (сервер) началась!\nВыберите ход:", reply_markup=duel_rps_kb(duel_id))
                return

            # PvP duel
            if game_type == "dice":
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(text="🎲 Кинуть кубик", callback_data=f"duel:dice:roll:{duel_id}"))
                try:
                    bot.send_message(creator_id, "⚔ Противник присоединился к дуэли! Нажмите, чтобы кинуть кубик первым.", reply_markup=kb)
                except Exception:
                    pass
                try:
                    bot.send_message(uid, "⚔ Вы присоединились к дуэли! Ожидаем, пока соперник первым бросит кубик.")
                except Exception:
                    pass
                return

            if game_type == "ttt":
                try:
                    bot.send_message(int(creator_id), "⚔ Противник присоединился к дуэли! Игра начинается.")
                except Exception:
                    pass
                try:
                    bot.send_message(int(uid), "⚔ Вы присоединились к дуэли! Игра начинается.")
                except Exception:
                    pass
                try:
                    _ttt_start_duel(int(duel_id), creator_id=int(creator_id), opponent_id=int(uid), stake=int(stake))
                except Exception:
                    pass
                return

            try:
                bot.send_message(creator_id, "⚔ Противник присоединился к дуэли! Выберите ход:", reply_markup=duel_rps_kb(duel_id))
            except Exception:
                pass
            try:
                bot.send_message(uid, "⚔ Вы присоединились к дуэли! Выберите ход:", reply_markup=duel_rps_kb(duel_id))
            except Exception:
                pass
            return

        if data.startswith("duel:ttt:move:"):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            parts = data.split(":")
            if len(parts) < 5:
                return
            try:
                duel_id = int(parts[3])
                pos = int(parts[4])
            except Exception:
                return

            try:
                res = db.duel_ttt_make_move(int(duel_id), user_id=int(uid), pos=int(pos))
            except Exception:
                res = {"ok": False, "error": "Ошибка"}

            if not bool(res.get("ok")):
                try:
                    bot.answer_callback_query(call.id, str(res.get("error") or "Ошибка"), show_alert=False)
                except Exception:
                    pass
                return

            state = res.get("state") if isinstance(res.get("state"), dict) else {}
            creator_id = int(res.get("creator_id") or 0)
            opponent_id = int(res.get("opponent_id") or 0)
            stake = int(res.get("stake") or 0)

            # Update boards for both players
            try:
                _ttt_try_update_board_message(
                    duel_id=int(duel_id),
                    stake=int(stake),
                    state=state,
                    viewer_id=int(creator_id),
                    creator_id=int(creator_id),
                    opponent_id=int(opponent_id),
                )
            except Exception:
                pass
            try:
                _ttt_try_update_board_message(
                    duel_id=int(duel_id),
                    stake=int(stake),
                    state=state,
                    viewer_id=int(opponent_id),
                    creator_id=int(creator_id),
                    opponent_id=int(opponent_id),
                )
            except Exception:
                pass

            # Finalize payout/refund only once
            finished = bool(res.get("finished"))
            finalized_now = bool(res.get("finalized_now"))
            winner_id = res.get("winner_id")
            if finished and finalized_now:
                if winner_id is None:
                    try:
                        db.add_balance(int(creator_id), int(stake))
                    except Exception:
                        pass
                    try:
                        db.add_balance(int(opponent_id), int(stake))
                    except Exception:
                        pass
                else:
                    try:
                        payout = _duel_commission_payout_with_vip(int(stake), int(creator_id), int(opponent_id))
                    except Exception:
                        payout = 0
                    try:
                        db.add_balance(int(winner_id), int(payout))
                    except Exception:
                        pass

                # Result messages with replay button
                try:
                    if winner_id is None:
                        txt_creator = f"❌⭕ Крестики-нолики\n\n🤝 Ничья!\nСтавка возвращена: {_fmt_points_ui(int(stake))}"
                        txt_opponent = txt_creator
                    elif int(winner_id) == int(creator_id):
                        txt_creator = (
                            "❌⭕ Крестики-нолики\n\n"
                            f"🎉 Победа!\nПолучено: {_fmt_points_ui(int(_duel_commission_payout_with_vip(int(stake), int(creator_id), int(opponent_id))))}"
                        )
                        txt_opponent = f"❌⭕ Крестики-нолики\n\n😢 Поражение\nПотеря: {_fmt_points_ui(int(stake))}"
                    else:
                        txt_opponent = (
                            "❌⭕ Крестики-нолики\n\n"
                            f"🎉 Победа!\nПолучено: {_fmt_points_ui(int(_duel_commission_payout_with_vip(int(stake), int(creator_id), int(opponent_id))))}"
                        )
                        txt_creator = f"❌⭕ Крестики-нолики\n\n😢 Поражение\nПотеря: {_fmt_points_ui(int(stake))}"
                except Exception:
                    txt_creator = "❌⭕ Крестики-нолики\n\nИгра завершена."
                    txt_opponent = txt_creator

                try:
                    bot.send_message(int(creator_id), txt_creator, reply_markup=_ttt_result_kb(int(duel_id)))
                except Exception:
                    pass
                try:
                    bot.send_message(int(opponent_id), txt_opponent, reply_markup=_ttt_result_kb(int(duel_id)))
                except Exception:
                    pass

            return

        if data.startswith("duel:ttt:again:"):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            parts = data.split(":")
            if len(parts) < 4:
                return
            try:
                base_duel_id = int(parts[3])
            except Exception:
                return
            base = db.get_duel_by_id(int(base_duel_id))
            if not base:
                return
            if str(base.get("game_type") or "") != "ttt":
                return
            if str(base.get("status") or "") != "resolved":
                return

            creator_id = int(base.get("creator_id") or 0)
            opponent_id = int(base.get("opponent_id") or 0)
            stake = int(base.get("stake") or 0)
            if stake <= 0:
                return
            if int(uid) not in (creator_id, opponent_id):
                return
            other_id = opponent_id if int(uid) == creator_id else creator_id

            spent_me = db.try_spend_points(int(uid), int(stake))
            if not bool(spent_me.get("ok")):
                bot.send_message(call.message.chat.id, "❌ Недостаточно баллов для реванша.")
                return
            spent_other = db.try_spend_points(int(other_id), int(stake))
            if not bool(spent_other.get("ok")):
                try:
                    db.add_balance(int(uid), int(stake))
                except Exception:
                    pass
                bot.send_message(call.message.chat.id, "❌ У соперника недостаточно баллов для реванша.")
                return

            # Create new duel with same participants & stake
            new_duel = db.create_duel(int(creator_id), stake=int(stake), game_type="ttt", is_bot=False, is_rematch=True)
            db.set_duel_opponent(int(new_duel["duel_id"]), int(opponent_id))
            try:
                _ttt_start_duel(int(new_duel["duel_id"]), creator_id=int(creator_id), opponent_id=int(opponent_id), stake=int(stake))
            except Exception:
                pass
            return

        if data.startswith("duel:stake:"):
            bot.answer_callback_query(call.id)
            s = session(uid)
            try:
                stake = int(data.split(":", 2)[2])
            except Exception:
                return
            if stake <= 0:
                return
            s.duel_stake = stake
            bot.edit_message_text(
                f"Ставка выбрана: {_fmt_points_ui(int(stake))} баллов.\nТеперь выберите тип дуэли:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel_type_kb(),
            )
            return

        # Duel2: start random matching from invite options
        if data.startswith("duel2:random:start:"):
            bot.answer_callback_query(call.id)
            parts = data.split(":", 4)
            if len(parts) < 5:
                return
            gt = parts[3]
            try:
                stake = int(parts[4])
            except Exception:
                return
            if gt not in ("dice", "rps") or stake not in (50, 100, 250, 500):
                return
            # find a match
            balance = db.get_balance(uid)
            other = db.find_random_match(uid, stake=stake, game_type=gt, balance=balance)
            if other is None:
                # Enqueue and inform waiting
                db.enqueue_random(uid, stake=stake, game_type=gt, balance=balance)
                bot.edit_message_text(
                    "🎯 Ищем случайного соперника... Ожидание.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
                return
            # Found match: create duel and start
            # Ensure both have stake and are not in active duel
            if db.has_active_duel(uid) or db.has_active_duel(other):
                bot.edit_message_text(
                    "❌ Один из игроков уже в активной дуэли.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
                return
            # Deduct stake from both atomically (best-effort): if opponent fails, refund the creator.
            spent_self = db.try_spend_points(int(uid), int(stake))
            if not spent_self.get("ok"):
                bot.edit_message_text(
                    "❌ Недостаточно баллов для этой ставки.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
                return
            spent_other = db.try_spend_points(int(other), int(stake))
            if not spent_other.get("ok"):
                try:
                    db.add_balance(int(uid), int(stake))
                except Exception:
                    pass
                bot.edit_message_text(
                    "❌ Сопернику недостаточно баллов для этой ставки.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
                return
            db.dequeue_random_for_users(uid, other, stake=stake, game_type=gt)

            duel = db.create_duel(uid, stake=stake, game_type=gt)
            db.set_duel_opponent(int(duel["duel_id"]), int(other))

            # Start game: сначала ходит создатель дуэли (uid)
            if gt == "dice":
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(text="🎲 Кинуть кубик", callback_data=f"duel:dice:roll:{int(duel['duel_id'])}"))
                try:
                    bot.send_message(uid, "⚔ Дуэль (кубики) началась! Нажмите, чтобы кинуть кубик первым.", reply_markup=kb)
                except Exception:
                    pass
                try:
                    bot.send_message(int(other), "⚔ Дуэль (кубики) началась! Ожидаем, пока соперник первым бросит кубик.")
                except Exception:
                    pass
            else:
                try:
                    bot.send_message(uid, "⚔ Дуэль КНБ началась! Выберите ход:", reply_markup=duel_rps_kb(int(duel["duel_id"])))
                except Exception:
                    pass
                try:
                    bot.send_message(int(other), "⚔ Дуэль КНБ началась! Выберите ход:", reply_markup=duel_rps_kb(int(duel["duel_id"])))
                except Exception:
                    pass
            return

        if data.startswith("duel:type:"):
            bot.answer_callback_query(call.id)
            s = session(uid)
            game_type = data.split(":", 2)[2]
            if game_type not in ("dice", "rps", "ttt"):
                return
            if not s.duel_stake:
                bot.send_message(call.message.chat.id, "Сначала выберите ставку.")
                return
            stake = int(s.duel_stake)
            # списываем ставку с создателя и создаём запись дуэли
            spent = db.try_spend_points(uid, stake)
            if not spent.get("ok"):
                bot.send_message(call.message.chat.id, "❌ Недостаточно баллов для создания дуэли.")
                return
            duel = db.create_duel(uid, stake=stake, game_type=game_type)
            s.duel_game_type = game_type
            mode = getattr(s, "duel_mode", "friend")

            # Режим "играть с другом" — оставляем старое поведение с ссылкой и друзьями
            if mode == "friend":
                text = "⚔ Дуэль создана!"
                bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=duel_friend_actions_kb(int(duel["duel_id"])),
                )
                return

            # Режим "Создать дуэль" — публикуем дуэль в общем списке (сервер дуэлей)
            try:
                s.server_duels_page = 0
            except Exception:
                pass
            _render_server_duels_panel(chat_id=call.message.chat.id, message_id=call.message.message_id, uid=uid)
            return

        if data.startswith("duel:back_to_invite:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = 0
            if uid != creator_id:
                bot.send_message(call.message.chat.id, "❌ Только создатель дуэли может изменять приглашение.")
                return
            bot.edit_message_text(
                "⚔ Дуэль создана!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel_friend_actions_kb(did),
            )
            return

        if data.startswith("duel:invite_link:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = 0
            if uid != creator_id:
                bot.send_message(call.message.chat.id, "❌ Только создатель дуэли может получить ссылку.")
                return
            code = duel.get("code")
            payload = f"duel_{code}"
            if settings.bot_username:
                link = f"https://t.me/{settings.bot_username}?start={payload}"
            else:
                link = f"/start {payload}"
            text = f"🔗 Ссылка для друга:\n{link}"
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel_invite_link_back_kb(did),
            )
            return

        if data.startswith("duel:invite_menu:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = 0
            if uid != creator_id:
                bot.send_message(call.message.chat.id, "❌ Только создатель дуэли может изменять приглашение.")
                return
            bot.edit_message_text(
                "⚔ Дуэль создана!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel_friend_actions_kb(did),
            )
            return

        # Duel2: pick game
        if data.startswith("duel2:game:"):
            bot.answer_callback_query(call.id)
            gt = data.split(":", 2)[2]
            if gt not in ("dice", "rps"):
                return
            bot.edit_message_text(
                _duel2_stake_text(gt),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel2_stake_kb(gt),
            )
            return

        # Duel2: stake selection
        if data.startswith("duel2:stake:"):
            bot.answer_callback_query(call.id)
            parts = data.split(":", 3)
            if len(parts) < 4:
                return
            gt = parts[2]
            try:
                stake = int(parts[3])
            except Exception:
                return
            if gt not in ("dice", "rps") or stake not in (50, 100, 250, 500):
                return
            # Deduct creator stake atomically and create duel (waiting)
            spent = db.try_spend_points(int(uid), int(stake))
            if not spent.get("ok"):
                bot.edit_message_text(
                    "❌ Недостаточно баллов для этой ставки.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
                return
            duel = db.create_duel(uid, stake=stake, game_type=gt)

            bot.edit_message_text(
                "⚔ Дуэль создана!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel2_friend_actions_kb(int(duel["duel_id"])),
            )

            # Start expiry timer (2 minutes)
            def _expire_duel_later(did: int) -> None:
                try:
                    time.sleep(120)
                except Exception:
                    pass
                if db.duel_is_waiting(int(did)):
                    db.cancel_waiting_duel(int(did))
                    try:
                        bot.send_message(uid, "⏳ Вызов просрочен (2 минуты). Ставка возвращена.")
                    except Exception:
                        pass

            threading.Thread(target=_expire_duel_later, args=(int(duel["duel_id"]),), daemon=True).start()
            return

        # Duel2: friends invite entry from empty friends list
        if data == "duel2:friends_invite":
            bot.answer_callback_query(call.id)
            # Просто возвращаем в меню дуэлей, откуда можно выбрать игру и ставку,
            # затем пригласить друга по ссылке или из списка.
            bot.edit_message_text(
                _duels_menu_text(uid),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel2_menu_kb(),
            )
            return

        # Duel2: открыть список друзей для конкретной дуэли (после выбора игры и ставки)
        if data.startswith("duel2:friends_for_duel:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 3)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            # только создатель дуэли может вызывать друзей для неё
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = 0
            if uid != creator_id:
                bot.send_message(call.message.chat.id, "❌ Только создатель дуэли может приглашать друзей.")
                return

            friends = db.list_recent_opponents(uid, limit=20)
            if not friends:
                text = (
                    "👥 Друзья\n\n"
                    "У вас пока нет друзей для дуэли.\n"
                    "Сыграйте хотя бы одну дуэль или пригласите друга по ссылке."
                )
                km = InlineKeyboardMarkup()
                km.add(InlineKeyboardButton(text="⬅ Назад", callback_data=f"duel2:back_to_invite:{did}"))
                bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=km,
                )
                return

            text = "👥 Ваши друзья\n\nВыберите друга для дуэли:"
            km = InlineKeyboardMarkup()
            for fr in friends:
                uname = ("@" + fr["username"]) if fr.get("username") else f"ID {int(fr['user_id'])}"
                km.add(
                    InlineKeyboardButton(
                        text=uname,
                        callback_data=f"duel2:invite_user:{did}:{int(fr['user_id'])}",
                    )
                )
            km.add(InlineKeyboardButton(text="⬅ Назад", callback_data=f"duel2:back_to_invite:{did}"))
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
            )
            return

        # Duel2: вернуться с экрана "Друзья" к экрану со ссылкой/приглашением
        if data.startswith("duel2:back_to_invite:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = 0
            if uid != creator_id:
                bot.send_message(call.message.chat.id, "❌ Только создатель дуэли может изменять приглашение.")
                return

            bot.edit_message_text(
                "⚔ Дуэль создана!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel2_friend_actions_kb(did),
            )
            return

        if data.startswith("duel2:invite_link:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = 0
            if uid != creator_id:
                bot.send_message(call.message.chat.id, "❌ Только создатель дуэли может получить ссылку.")
                return
            code = duel.get("code")
            payload = f"duel_{code}"
            if settings.bot_username:
                link = f"https://t.me/{settings.bot_username}?start={payload}"
            else:
                link = f"/start {payload}"
            bot.edit_message_text(
                f"🔗 Ссылка для друга:\n{link}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel2_invite_link_back_kb(did),
            )
            return

        if data.startswith("duel2:invite_menu:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = 0
            if uid != creator_id:
                bot.send_message(call.message.chat.id, "❌ Только создатель дуэли может изменять приглашение.")
                return
            bot.edit_message_text(
                "⚔ Дуэль создана!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=duel2_friend_actions_kb(did),
            )
            return

        if data.startswith("duel2:invite_user:"):
            bot.answer_callback_query(call.id)
            parts = data.split(":", 3)
            if len(parts) < 4:
                return
            try:
                did = int(parts[2])
                friend_id = int(parts[3])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            if friend_id == uid:
                bot.send_message(call.message.chat.id, "❌ Нельзя играть с самим собой.")
                return
            # Compose friend invite
            stake = int(duel.get("stake") or 0)
            gt = str(duel.get("game_type") or "rps")

            # If friend has insufficient balance right now, don't send the invite.
            try:
                friend_balance = int(db.get_balance(friend_id) or 0)
            except Exception:
                friend_balance = 0
            if stake > 0 and friend_balance < stake:
                try:
                    bot.send_message(call.message.chat.id, f"❌ У соперника недостаточно баллов для ставки {stake}.")
                except Exception:
                    pass
                try:
                    bot.send_message(friend_id, f"❌ Вас пытались пригласить на дуэль со ставкой {stake}, но у вас недостаточно баллов.")
                except Exception:
                    pass
                return

            inviter_uname = ("@" + (call.from_user.username or "")) if getattr(call.from_user, "username", None) else f"ID {uid}"
            if gt == "dice":
                game_line = "🎲 Игра: Кости"
            elif gt == "ttt":
                game_line = "❌⭕ Игра: Крестики-нолики"
            else:
                game_line = "✊✋✌ Игра: КНБ"
            text = (
                "⚔️ Вас вызывают на дуэль!\n\n"
                f"👤 Игрок: {inviter_uname}\n"
                f"{game_line}\n"
                f"💰 Ставка: {stake} баллов\n\n"
                "Принять вызов?"
            )
            km = InlineKeyboardMarkup()
            km.row(
                InlineKeyboardButton(text="✅ Принять", callback_data=f"duel2:accept:{did}"),
                InlineKeyboardButton(text="❌ Отказаться", callback_data=f"duel2:decline:{did}"),
            )
            ok_send = True
            try:
                bot.send_message(friend_id, text, reply_markup=km)
            except Exception:
                ok_send = False
            if ok_send:
                try:
                    friend_label = f"@{call.from_user.username}" if getattr(call.from_user, "username", None) else f"ID {friend_id}"
                except Exception:
                    friend_label = f"ID {friend_id}"
                bot.edit_message_text(
                    f"📤 Приглашение отправлено сопернику ({friend_label}).",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
            else:
                bot.send_message(call.message.chat.id, "❌ Не удалось отправить приглашение этому пользователю.")
            return

        # Inline invite accept/decline
        if data.startswith("duel2:accept:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel:
                bot.send_message(call.message.chat.id, "❌ Дуэль не найдена.")
                return
            if duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль уже недоступна.")
                return
            creator_id = int(duel["creator_id"])
            if uid == creator_id:
                bot.send_message(call.message.chat.id, "❌ Нельзя играть с самим собой.")
                return
            joined = db.join_waiting_duel_atomic(int(did), user_id=int(uid))
            if not bool(joined.get("ok")):
                reason = str(joined.get("reason") or "")
                if reason == "no_balance":
                    bot.send_message(call.message.chat.id, "❌ Недостаточно баллов для участия.")
                    try:
                        decliner_name = f"@{call.from_user.username}" if getattr(call.from_user, "username", None) else f"ID {uid}"
                    except Exception:
                        decliner_name = f"ID {uid}"
                    try:
                        stake_need = int(duel.get("stake") or 0)
                    except Exception:
                        stake_need = 0
                    try:
                        bot.send_message(
                            creator_id,
                            f"❌ {decliner_name} не смог принять дуэль: недостаточно баллов для ставки {_fmt_points_ui(int(stake_need))}.",
                        )
                    except Exception:
                        pass
                    return
                bot.send_message(call.message.chat.id, "❌ Дуэль уже заняли или она недоступна.")
                try:
                    _safe_delete_message(bot, int(call.message.chat.id), int(call.message.message_id))
                except Exception:
                    pass
                return

            duel = (joined.get("duel") or duel)
            gt = str(duel.get("game_type") or "")
            stake = int(duel.get("stake") or 0)

            # Delete invite message after decision
            try:
                _safe_delete_message(bot, int(call.message.chat.id), int(call.message.message_id))
            except Exception:
                pass

            if gt == "dice":
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(text="🎲 Кинуть кубик", callback_data=f"duel:dice:roll:{did}"))
                try:
                    bot.send_message(creator_id, "⚔ Противник принял вызов! Нажмите, чтобы кинуть кубик первым.", reply_markup=kb)
                except Exception:
                    pass
                try:
                    bot.send_message(uid, "⚔ Вы приняли вызов! Ожидаем, пока соперник первым бросит кубик.")
                except Exception:
                    pass
            elif gt == "ttt":
                try:
                    bot.send_message(int(creator_id), "⚔ Противник принял вызов! Игра начинается.")
                except Exception:
                    pass
                try:
                    bot.send_message(int(uid), "⚔ Вы приняли вызов! Игра начинается.")
                except Exception:
                    pass
                try:
                    _ttt_start_duel(int(did), creator_id=int(creator_id), opponent_id=int(uid), stake=int(stake))
                except Exception:
                    pass
            else:
                try:
                    bot.send_message(creator_id, "⚔ Противник принял вызов! Выберите ход:", reply_markup=duel_rps_kb(did))
                except Exception:
                    pass
                try:
                    bot.send_message(uid, "⚔ Вы приняли вызов! Выберите ход:", reply_markup=duel_rps_kb(did))
                except Exception:
                    pass
            return

        if data.startswith("duel2:decline:"):
            bot.answer_callback_query(call.id)
            try:
                did = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(did)
            if not duel or duel.get("status") != "waiting":
                bot.send_message(call.message.chat.id, "❌ Дуэль не найдена.")
                return
            # Cancel duel and refund creator
            db.cancel_waiting_duel(did)
            # Сообщение инициатору с указанием, кто отказался
            try:
                creator_id = int(duel["creator_id"])
            except Exception:
                creator_id = None
            decliner_name = f"@{call.from_user.username}" if getattr(call.from_user, "username", None) else "Соперник"
            if creator_id:
                try:
                    bot.send_message(
                        creator_id,
                        f"❌ {decliner_name} отказался от дуэли. Ставка возвращена.",
                    )
                except Exception:
                    pass

            # Delete invite message after decision
            try:
                _safe_delete_message(bot, int(call.message.chat.id), int(call.message.message_id))
            except Exception:
                pass
            return

        if data.startswith("duel:rps:"):
            bot.answer_callback_query(call.id)
            parts = data.split(":", 3)
            if len(parts) < 4:
                return
            try:
                duel_id = int(parts[2])
            except Exception:
                return
            choice = parts[3]
            if choice not in ("rock", "paper", "scissors"):
                return
            duel = db.get_duel_by_id(duel_id)
            if not duel or duel["status"] != "active":
                bot.send_message(call.message.chat.id, "❌ Дуэль недоступна.")
                return
            if uid not in (duel["creator_id"], duel.get("opponent_id")):
                bot.send_message(call.message.chat.id, "❌ Эта дуэль не для вас.")
                return
            db.update_duel_rps_choice(duel_id, user_id=uid, choice=choice)
            duel = db.get_duel_by_id(duel_id) or duel
            c_choice = duel.get("creator_choice")
            o_choice = duel.get("opponent_choice")
            if not (c_choice and o_choice):
                bot.send_message(call.message.chat.id, "Вы выбрали ход. Ожидаем выбор соперника...")
                return

            # оба сделали выбор — определяем победителя
            stake = int(duel["stake"])
            payout = _duel_commission_payout_with_vip(stake, duel["creator_id"], duel.get("opponent_id"))
            def _beats(a: str, b: str) -> bool:
                return (a == "rock" and b == "scissors") or (a == "scissors" and b == "paper") or (a == "paper" and b == "rock")

            # Server-bot RPS duel: creator_id = 0, is_bot = 1
            if int(duel.get("is_bot") or 0) == 1 and int(duel.get("creator_id") or 0) == 0:
                # Determine outcome and notify the human opponent with bot rematch option
                if c_choice == o_choice:
                    winner = None
                else:
                    winner = duel["creator_id"] if _beats(c_choice, o_choice) else duel.get("opponent_id")

                if winner is None:
                    if duel.get("opponent_id"):
                        db.add_balance(int(duel.get("opponent_id")), stake)
                elif winner == duel.get("opponent_id"):
                    if duel.get("opponent_id"):
                        db.add_balance(int(duel.get("opponent_id")), payout)
                db.finalize_duel_result(duel_id, winner_id=winner)

                choice_map = {"rock": "✊ Камень", "paper": "✋ Бумага", "scissors": "✌ Ножницы"}
                human_id = duel.get("opponent_id")
                if human_id:
                    u_txt = choice_map.get(o_choice, str(o_choice))
                    b_txt = choice_map.get(c_choice, str(c_choice))
                    if winner is None:
                        msg = (
                            "⚔ Дуэль КНБ — ничья!\n\n"
                            f"Вы: {u_txt}\nБот: {b_txt}\nСтавка возвращена."
                        )
                    elif winner == human_id:
                        msg = (
                            "⚔ Дуэль КНБ завершена!\n\n"
                            f"Вы: {u_txt}\nБот: {b_txt}\n\n"
                            f"🎉 Вы победили и получили {payout} баллов!"
                        )
                    else:
                        msg = (
                            "⚔ Дуэль КНБ завершена!\n\n"
                            f"Вы: {u_txt}\nБот: {b_txt}\n\n"
                            "😢 Ты проиграл."
                        )
                    try:
                        bot.send_message(int(human_id), msg + "\n\n♻️ Сыграем ещё раз?", reply_markup=bot_rematch_kb(duel_id))
                    except Exception:
                        pass
                return

            if c_choice == o_choice:
                # ничья
                db.add_balance(duel["creator_id"], stake)
                if duel.get("opponent_id"):
                    db.add_balance(duel["opponent_id"], stake)
                db.finalize_duel_result(duel_id, winner_id=None)
                try:
                    _send_duel_summary_feedback(duel_id)
                except Exception:
                    pass
                return

            if _beats(c_choice, o_choice):
                winner = duel["creator_id"]
                loser = duel.get("opponent_id")
            else:
                winner = duel.get("opponent_id")
                loser = duel["creator_id"]

            if winner is not None:
                db.add_balance(winner, payout)
            db.finalize_duel_result(duel_id, winner_id=winner)

            try:
                _send_duel_summary_feedback(duel_id)
            except Exception:
                pass
            return

        if data.startswith("duel:rematch_offer:"):
            bot.answer_callback_query(call.id)
            try:
                base_duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(base_duel_id)
            if not duel:
                bot.send_message(call.message.chat.id, "❌ Дуэль не найдена.")
                return
            if duel.get("opponent_id") is None:
                bot.send_message(call.message.chat.id, "❌ Нельзя предложить реванш без соперника.")
                return
            if uid not in (duel["creator_id"], duel["opponent_id"]):
                bot.send_message(call.message.chat.id, "❌ Эта дуэль не ваша.")
                return

            # определяем соперника
            other_id = duel["opponent_id"] if uid == duel["creator_id"] else duel["creator_id"]

            s_initiator = session(uid)
            s_friend = session(other_id)
            s_initiator.rematch_with_user = other_id
            s_initiator.rematch_base_duel_id = base_duel_id
            s_initiator.rematch_pending_stake = None
            s_initiator.rematch_role = "initiator"

            s_friend.rematch_with_user = uid
            s_friend.rematch_base_duel_id = base_duel_id
            s_friend.rematch_pending_stake = None
            s_friend.rematch_role = "opponent"

            # Keep the result message intact: remove its buttons, then send a separate status message.
            try:
                bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except Exception:
                pass

            # cleanup any stale rematch service messages
            try:
                _rematch_clear_service_messages(user_id=int(uid))
            except Exception:
                pass
            try:
                _rematch_clear_service_messages(user_id=int(other_id))
            except Exception:
                pass

            try:
                _kb = InlineKeyboardMarkup()
                _kb.add(InlineKeyboardButton(text="❌ Отменить отправку", callback_data=f"duel:rematch_stop:{base_duel_id}"))
                m = bot.send_message(call.message.chat.id, "Запрос на реванш отправлен сопернику. Ждём его ответа.", reply_markup=_kb)
                try:
                    s_initiator.rematch_status_chat_id = int(call.message.chat.id)
                    s_initiator.rematch_status_message_id = int(getattr(m, "message_id", 0) or 0)
                except Exception:
                    pass
            except Exception:
                try:
                    bot.send_message(call.message.chat.id, "Запрос на реванш отправлен сопернику. Ждём его ответа.")
                except Exception:
                    pass

            # сопернику: предложение сыграть снова
            gt = str(duel.get("game_type") or "rps")
            if gt == "dice":
                gt_txt = "🎲 Кубики"
            elif gt == "ttt":
                gt_txt = "❌⭕ Крестики-нолики"
            else:
                gt_txt = "✊✋✌ КНБ"
            try:
                m2 = bot.send_message(
                    other_id,
                    f"Соперник предлагает сыграть ещё раз в {gt_txt}.",
                    reply_markup=duel_rematch_answer_kb(base_duel_id),
                )
                try:
                    s_friend.rematch_offer_chat_id = int(other_id)
                    s_friend.rematch_offer_message_id = int(getattr(m2, "message_id", 0) or 0)
                except Exception:
                    pass
            except Exception:
                pass
            return

        if data.startswith("duel:rematch_accept:"):
            bot.answer_callback_query(call.id)
            try:
                base_duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            duel = db.get_duel_by_id(base_duel_id)
            if not duel or duel.get("opponent_id") is None:
                bot.send_message(call.message.chat.id, "❌ Дуэль не найдена.")
                return
            s = session(uid)
            if s.rematch_with_user is None or s.rematch_base_duel_id != base_duel_id:
                bot.send_message(call.message.chat.id, "❌ Реванш уже недоступен.")
                return

            friend_id = s.rematch_with_user

            # remove initiator "Отменить отправку" status once the other side accepted
            try:
                _rematch_clear_service_messages(user_id=int(friend_id))
            except Exception:
                pass

            base_stake = int(duel.get("stake") or 0)

            # сопернику (инициатору) сообщаем, что вы согласились, и просим выбрать ставку
            try:
                bot.send_message(
                    friend_id,
                    "Соперник согласился на реванш! Выберите ставку.",
                    reply_markup=_build_rematch_stake_kb(int(base_duel_id), int(base_stake)),
                )
            except Exception:
                pass

            bot.edit_message_text(
                "Вы согласились на реванш. Соперник выбирает ставку...",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
            )

            # clear offer message reference for this user (we keep the edited text)
            try:
                _rematch_clear_service_messages(
                    user_id=int(uid),
                    skip_chat_id=int(call.message.chat.id),
                    skip_message_id=int(call.message.message_id),
                )
            except Exception:
                pass
            return

        if data.startswith("duel:rematch_decline:"):
            bot.answer_callback_query(call.id)
            try:
                base_duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            s = session(uid)
            friend_id = s.rematch_with_user
            # очищаем состояние у обоих, если есть
            if friend_id is not None:
                s_friend = session(friend_id)
                s_friend.rematch_with_user = None
                s_friend.rematch_base_duel_id = None
                s_friend.rematch_pending_stake = None
                s_friend.rematch_role = None

            s.rematch_with_user = None
            s.rematch_base_duel_id = None
            s.rematch_pending_stake = None
            s.rematch_role = None

            if friend_id is not None:
                # cleanup initiator status/other service messages
                try:
                    _rematch_clear_service_messages(user_id=int(friend_id))
                except Exception:
                    pass
                try:
                    bot.send_message(friend_id, "Соперник отказался от реванша.")
                except Exception:
                    pass
            bot.edit_message_text(
                "Вы отказались от реванша.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
            )

            try:
                _rematch_clear_service_messages(
                    user_id=int(uid),
                    skip_chat_id=int(call.message.chat.id),
                    skip_message_id=int(call.message.message_id),
                )
            except Exception:
                pass
            return

        if data.startswith("duel:rematch_stake:"):
            bot.answer_callback_query(call.id)
            parts = data.split(":", 3)
            if len(parts) < 4:
                return
            try:
                base_duel_id = int(parts[2])
                amount = int(parts[3])
            except Exception:
                return
            base_duel = db.get_duel_by_id(int(base_duel_id))
            base_stake = int((base_duel or {}).get("stake") or 0)
            allowed = set(_rematch_amount_options(int(base_stake)))
            if amount not in allowed:
                bot.send_message(call.message.chat.id, "❌ Неверная ставка.")
                return
            s = session(uid)
            if s.rematch_with_user is None or s.rematch_base_duel_id != base_duel_id:
                bot.send_message(call.message.chat.id, "❌ Реванш уже недоступен.")
                return
            friend_id = s.rematch_with_user
            s_friend = session(friend_id)

            # запоминаем выбранную ставку
            s.rematch_pending_stake = amount
            s_friend.rematch_pending_stake = amount

            if s.rematch_role == "initiator":
                # первый игрок выбрал ставку -> у него текст ожидания, у друга выбор согласия/изменения
                bot.edit_message_text(
                    f"Ставка выбрана: {amount} баллов. Ждём решение соперника.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
                try:
                    s.rematch_wait_chat_id = int(call.message.chat.id)
                    s.rematch_wait_message_id = int(call.message.message_id)
                except Exception:
                    pass
                try:
                    bot.send_message(
                        friend_id,
                        f"Соперник поставил ставку {amount} баллов.",
                        reply_markup=duel_rematch_opponent_choice_kb(base_duel_id),
                    )
                except Exception:
                    pass
            else:
                # друг изменяет ставку
                bot.edit_message_text(
                    f"Вы изменили ставку на {amount} баллов. Нажмите 'Согласен', чтобы начать игру.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=duel_rematch_opponent_choice_kb(base_duel_id),
                )
                try:
                    bot.send_message(
                        friend_id,
                        f"Сопернику не понравилась ставка, он изменил её. Новая ставка: {amount} баллов.",
                    )
                except Exception:
                    pass
            return

        if data.startswith("duel:rematch_change:"):
            bot.answer_callback_query(call.id)
            try:
                base_duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            # другу показываем выбор новой ставки
            base_duel = db.get_duel_by_id(int(base_duel_id))
            base_stake = int((base_duel or {}).get("stake") or 0)
            bot.edit_message_text(
                "Выберите новую ставку для реванша:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=_build_rematch_stake_kb(int(base_duel_id), int(base_stake)),
            )
            return

        if data.startswith("duel:rematch_confirm:"):
            bot.answer_callback_query(call.id)
            try:
                base_duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            s = session(uid)
            friend_id = s.rematch_with_user
            if friend_id is None or s.rematch_base_duel_id != base_duel_id or not s.rematch_pending_stake:
                bot.send_message(call.message.chat.id, "❌ Реванш уже недоступен.")
                return
            stake = int(s.rematch_pending_stake)
            other_id = friend_id

            # проверяем баланс обоих
            if db.get_balance(uid) < stake or db.get_balance(other_id) < stake:
                bot.send_message(call.message.chat.id, "❌ У одного из игроков недостаточно баллов для этой ставки.")
                return

            # списываем ставки и создаём новую дуэль того же типа сразу с двумя участниками
            spent_me = db.try_spend_points(int(uid), int(stake))
            if not spent_me.get("ok"):
                bot.send_message(call.message.chat.id, "❌ Недостаточно баллов для этой ставки.")
                return
            spent_other = db.try_spend_points(int(other_id), int(stake))
            if not spent_other.get("ok"):
                # rollback our debit
                try:
                    db.add_balance(int(uid), int(stake))
                except Exception:
                    pass
                bot.send_message(call.message.chat.id, "❌ У соперника недостаточно баллов для этой ставки.")
                return
            base_duel = db.get_duel_by_id(base_duel_id)
            new_game_type = base_duel.get("game_type") if base_duel else "rps"
            if new_game_type not in ("rps", "dice"):
                new_game_type = "rps"
            new_duel = db.create_duel(uid, stake=stake, game_type=new_game_type, is_bot=False, is_rematch=True)
            db.set_duel_opponent(new_duel["duel_id"], other_id)

            # чистим состояние реванша
            s.rematch_with_user = None
            s.rematch_base_duel_id = None
            s.rematch_pending_stake = None
            s.rematch_role = None
            s_friend = session(other_id)
            s_friend.rematch_with_user = None
            s_friend.rematch_base_duel_id = None
            s_friend.rematch_pending_stake = None
            s_friend.rematch_role = None

            # cleanup service messages for both sides (including "ставка выбрана..." and initial status)
            try:
                _rematch_clear_service_messages(
                    user_id=int(uid),
                    skip_chat_id=int(call.message.chat.id),
                    skip_message_id=int(call.message.message_id),
                )
            except Exception:
                pass
            try:
                _rematch_clear_service_messages(user_id=int(other_id))
            except Exception:
                pass

            # старт новой дуэли в зависимости от типа
            if new_game_type == "dice":
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(text="🎲 Кинуть кубик", callback_data=f"duel:dice:roll:{new_duel['duel_id']}"))
                try:
                    bot.send_message(uid, "⚔ Реванш (кубики)! Нажмите, чтобы кинуть кубик первым.", reply_markup=kb)
                except Exception:
                    pass
                try:
                    bot.send_message(other_id, "⚔ Реванш (кубики)! Ожидаем, пока соперник первым бросит кубик.")
                except Exception:
                    pass
            else:
                try:
                    bot.send_message(
                        uid,
                        f"⚔ Реванш КНБ! Ставка {_fmt_points_ui(int(stake))} баллов. Выберите ход:",
                        reply_markup=duel_rps_kb(new_duel["duel_id"]),
                    )
                except Exception:
                    pass
                try:
                    bot.send_message(
                        other_id,
                        f"⚔ Реванш КНБ! Ставка {_fmt_points_ui(int(stake))} баллов. Выберите ход:",
                        reply_markup=duel_rps_kb(new_duel["duel_id"]),
                    )
                except Exception:
                    pass
            return

        if data.startswith("duel:rematch_stop:"):
            bot.answer_callback_query(call.id)
            try:
                base_duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            s = session(uid)
            friend_id = s.rematch_with_user
            s.rematch_with_user = None
            s.rematch_base_duel_id = None
            s.rematch_pending_stake = None
            s.rematch_role = None
            if friend_id is not None:
                s_friend = session(friend_id)
                s_friend.rematch_with_user = None
                s_friend.rematch_base_duel_id = None
                s_friend.rematch_pending_stake = None
                s_friend.rematch_role = None
                try:
                    bot.send_message(friend_id, "Соперник прекратил попытку реванша.")
                except Exception:
                    pass

                try:
                    _rematch_clear_service_messages(user_id=int(friend_id))
                except Exception:
                    pass

            # cleanup our other service messages but keep current message so we can edit it
            try:
                _rematch_clear_service_messages(
                    user_id=int(uid),
                    skip_chat_id=int(call.message.chat.id),
                    skip_message_id=int(call.message.message_id),
                )
            except Exception:
                pass
            bot.edit_message_text(
                "Вы прекратили попытку реванша.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
            )
            return

        if data.startswith("duel:bot_rematch:"):
            bot.answer_callback_query(call.id)
            try:
                base_duel_id = int(data.split(":", 2)[2])
            except Exception:
                return
            base_duel = db.get_duel_by_id(base_duel_id)
            if not base_duel or int(base_duel.get("is_bot") or 0) != 1:
                bot.send_message(call.message.chat.id, "❌ Дуэль не найдена.")
                return
            stake = int(base_duel.get("stake") or 0)
            game_type = str(base_duel.get("game_type") or "rps")
            if db.get_balance(uid) < stake:
                bot.send_message(call.message.chat.id, "❌ Недостаточно баллов для реванша с ботом.")
                return
            # Show waiting state
            try:
                bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except Exception:
                pass
            try:
                bot.send_message(call.message.chat.id, "Запрос на реванш отправлен боту. Ждём ответа...")
            except Exception:
                pass

            def _bot_accept_rematch(user_id: int, base_duel_id: int, stake: int, game_type: str) -> None:
                try:
                    time.sleep(random.randint(2, 5))
                except Exception:
                    pass
                # Double-check balance then deduct
                spent = db.try_spend_points(int(user_id), int(stake))
                if not spent.get("ok"):
                    try:
                        bot.send_message(user_id, "❌ Недостаточно баллов для реванша.")
                    except Exception:
                        pass
                    return
                # Create bot duel: creator_id = 0, is_bot = 1
                new_duel = db.create_duel(0, stake=int(stake), game_type=game_type, is_bot=True)
                db.set_duel_opponent(int(new_duel["duel_id"]), int(user_id))
                if game_type == "rps":
                    try:
                        db.update_duel_rps_choice(int(new_duel["duel_id"]), user_id=0, choice=random.choice(["rock", "paper", "scissors"]))
                    except Exception:
                        pass
                    try:
                        bot.send_message(int(user_id), "⚔ Дуэль КНБ (бот) началась! Выберите ход:", reply_markup=duel_rps_kb(int(new_duel["duel_id"])))
                    except Exception:
                        pass
                else:
                    try:
                        kb = InlineKeyboardMarkup()
                        kb.add(InlineKeyboardButton(text="🎲 Кинуть кубик", callback_data=f"duel:dice:roll:{int(new_duel['duel_id'])}"))
                        bot.send_message(int(user_id), "⚔ Дуэль (кубики) с ботом! Нажмите, чтобы кинуть кубик.", reply_markup=kb)
                    except Exception:
                        pass

            th = threading.Thread(target=_bot_accept_rematch, args=(uid, base_duel_id, stake, game_type), daemon=True)
            try:
                th.start()
            except Exception:
                _bot_accept_rematch(uid, base_duel_id, stake, game_type)
            return

        if data.startswith("duel:dice:roll:"):
            parts = data.split(":", 3)
            if len(parts) < 4:
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                return
            try:
                duel_id = int(parts[3])
            except Exception:
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                return
            duel = db.get_duel_by_id(duel_id)
            if not duel or duel.get("status") != "active":
                try:
                    bot.answer_callback_query(call.id, "❌ Эта дуэль недоступна.", show_alert=True)
                except Exception:
                    pass
                return
            creator_id = duel["creator_id"]
            opponent_id = duel.get("opponent_id")
            if call.from_user.id not in (creator_id, opponent_id):
                try:
                    bot.answer_callback_query(call.id, "❌ Эта дуэль не для вас.", show_alert=True)
                except Exception:
                    pass
                return

            # Bot-duel (server pool): creator_id=0, is_bot=1. Only the human opponent plays.
            if int(duel.get("is_bot") or 0) == 1 and int(creator_id) == 0:
                player_id = opponent_id
                if not player_id or call.from_user.id != player_id:
                    try:
                        bot.answer_callback_query(call.id, "❌ Эта дуэль не для вас.", show_alert=True)
                    except Exception:
                        pass
                    return

                if duel.get("opponent_roll") is not None:
                    try:
                        bot.answer_callback_query(call.id, "Вы уже кидали кубик.", show_alert=True)
                    except Exception:
                        pass
                    return

                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass

                # сначала бросает игрок
                dice_msg_user = bot.send_dice(player_id, emoji="🎲")
                player_roll = dice_msg_user.dice.value if dice_msg_user.dice else 0
                db.update_duel_roll(duel_id, user_id=int(player_id), roll=int(player_roll))

                # через 2–3 секунды бросает бот
                try:
                    time.sleep(random.randint(2, 3))
                except Exception:
                    pass

                dice_msg_bot = bot.send_dice(player_id, emoji="🎲")
                bot_roll = dice_msg_bot.dice.value if dice_msg_bot.dice else 0
                db.update_duel_roll(duel_id, user_id=0, roll=int(bot_roll))

                try:
                    time.sleep(2)
                except Exception:
                    pass

                # Read back persisted rolls to avoid any mismatch in messaging
                duel_final = db.get_duel_by_id(duel_id) or duel
                stake = int(duel_final.get("stake") or 0)
                c_roll = duel_final.get("creator_roll")
                o_roll = duel_final.get("opponent_roll")
                br = int(c_roll or 0)  # bot (creator_id=0)
                pr = int(o_roll or 0)  # player (opponent_id)
                payout = _duel_commission_payout_with_vip(stake, creator_id, opponent_id)

                if pr > br:
                    winner = int(player_id)
                elif pr < br:
                    winner = 0
                else:
                    winner = None

                if winner is None:
                    db.add_balance(int(player_id), stake)
                    txt = f"⚔ Дуэль (кубики) — ничья!\n\nВы: {pr}\nБот: {br}\n\nСтавка возвращена."
                elif winner == int(player_id):
                    db.add_balance(int(player_id), payout)
                    txt = f"⚔ Дуэль (кубики) завершена!\n\nВы: {pr}\nБот: {br}\n\n🎉 Вы победили и получили {payout} баллов!"
                else:
                    txt = (
                        "⚔ Дуэль (кубики) завершена!\n\n"
                        f"Ты: {_fmt_points_ui(int(pr))}\n"
                        f"Бот: {_fmt_points_ui(int(br))}\n\n"
                        "😢 Ты проиграл."
                    )

                db.finalize_duel_result(duel_id, winner_id=winner, creator_roll=br, opponent_roll=pr)
                try:
                    bot.send_message(int(player_id), txt + "\n\n♻️ Сыграем ещё раз?", reply_markup=bot_rematch_kb(duel_id))
                except Exception:
                    pass
                return

            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass

            # determine role
            is_creator = call.from_user.id == creator_id

            # Enforce turn order for кубики: сначала бросает создатель дуэли
            # Если противник пытается бросить раньше создателя — ждём его ход.
            if (not is_creator) and duel.get("creator_roll") is None:
                try:
                    bot.answer_callback_query(call.id, "⏳ Сначала соперник должен кинуть кубик.", show_alert=True)
                except Exception:
                    pass
                return

            # prevent double-rolls
            if is_creator and duel.get("creator_roll") is not None:
                try:
                    bot.answer_callback_query(call.id, "Вы уже кидали кубик.", show_alert=True)
                except Exception:
                    pass
                return
            if (not is_creator) and duel.get("opponent_roll") is not None:
                try:
                    bot.answer_callback_query(call.id, "Вы уже кидали кубик.", show_alert=True)
                except Exception:
                    pass
                return

            # send animated dice on behalf of the user
            dice_msg = bot.send_dice(call.from_user.id, emoji="🎲")
            roll_val = dice_msg.dice.value if dice_msg.dice else 0

            # copy the same dice message to the opponent so both see identical roll (and animation)
            try:
                other_id = opponent_id if is_creator else creator_id
                if other_id:
                    try:
                        bot.copy_message(
                            chat_id=other_id,
                            from_chat_id=call.from_user.id,
                            message_id=dice_msg.message_id,
                        )
                    except Exception:
                        bot.forward_message(
                            chat_id=other_id,
                            from_chat_id=call.from_user.id,
                            message_id=dice_msg.message_id,
                        )
            except Exception:
                pass

            # record roll
            db.update_duel_roll(duel_id, user_id=call.from_user.id, roll=int(roll_val))

            # если первым бросил создатель — после его хода выдаём кнопку второму игроку
            try:
                if is_creator and opponent_id and (duel.get("opponent_roll") is None):
                    kb_next = InlineKeyboardMarkup()
                    kb_next.add(InlineKeyboardButton(text="🎲 Кинуть кубик", callback_data=f"duel:dice:roll:{duel_id}"))
                    bot.send_message(opponent_id, "Теперь ваша очередь кинуть кубик.", reply_markup=kb_next)
            except Exception:
                pass

            # No extra messages: only dice animations until both rolled.

            # reload duel to get both rolls
            duel = db.get_duel_by_id(duel_id) or duel
            creator_roll = duel.get("creator_roll")
            opponent_roll = duel.get("opponent_roll")

            # if both rolled — wait 3s and finalize
            if creator_roll is not None and opponent_roll is not None:
                try:
                    time.sleep(3)
                except Exception:
                    pass

                creator_roll_i = int(creator_roll)
                opponent_roll_i = int(opponent_roll)
                stake = int(duel.get("stake") or 0)
                payout = _duel_commission_payout_with_vip(stake, creator_id, opponent_id)

                if opponent_roll_i > creator_roll_i:
                    winner = opponent_id
                elif opponent_roll_i < creator_roll_i:
                    winner = creator_id
                else:
                    winner = None

                if winner is None:
                    # ничья — возвращаем ставки обоим
                    db.add_balance(int(creator_id), int(stake))
                    if opponent_id:
                        db.add_balance(int(opponent_id), int(stake))
                    db.finalize_duel_result(
                        duel_id,
                        winner_id=None,
                        creator_roll=int(creator_roll_i),
                        opponent_roll=int(opponent_roll_i),
                    )
                else:
                    db.add_balance(int(winner), int(payout))
                    db.finalize_duel_result(
                        duel_id,
                        winner_id=int(winner),
                        creator_roll=int(creator_roll_i),
                        opponent_roll=int(opponent_roll_i),
                    )

                try:
                    _send_duel_summary_feedback(duel_id)
                except Exception:
                    pass
                return

        if data == "minigames:open":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            # User asked: do not preserve Mines params after leaving.
            try:
                _mines_reset(uid, preserve_params=False)
            except Exception:
                pass
            try:
                bot.edit_message_text(
                    "Выберите игру:",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=minigames_menu_kb(show_back=False),
                )
            except Exception:
                # fallback to sending a new message
                bot.send_message(call.message.chat.id, "Выберите игру:", reply_markup=minigames_menu_kb(show_back=False))
            return

        if data == "wheel:again":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            # Show wheel bets again, but without the rating button.
            text, km = _build_wheel_screen(uid, show_top=False)
            try:
                m = bot.send_message(call.message.chat.id, text, reply_markup=km)
                try:
                    s = session(uid)
                    s.awaiting_bet_for_game = "wheel"
                    s.awaiting_bet_chat_id = int(call.message.chat.id)
                    s.awaiting_bet_message_id = int(m.message_id)
                except Exception:
                    pass
            except Exception:
                pass
            return

        if data.startswith("wheel:bet:"):
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            try:
                bet = int(data.split(":", 2)[2])
            except Exception:
                return
            min_bet, max_bet = _bet_limits_for(uid)
            if bet < min_bet or bet > max_bet:
                bot.send_message(call.message.chat.id, "❌ " + _bet_out_of_range_text(bet=bet, min_bet=min_bet, max_bet=max_bet))
                return
            now_ts = int(time.time())
            hour_start = (now_ts // 3600) * 3600
            win_meta = db.get_wheel_window(uid) or {"hour_ts": 0, "games_in_hour": 0}
            if int(win_meta.get("hour_ts") or 0) != hour_start:
                games_in_hour = 0
            else:
                games_in_hour = int(win_meta.get("games_in_hour") or 0)
            if games_in_hour >= WHEEL_HOURLY_LIMIT:
                text, km = _build_wheel_screen(uid)
                bot.send_message(call.message.chat.id, "❌ Лимит игр на этот час исчерпан.\n\n" + text, reply_markup=km)
                return

            try:
                balance_now = int(db.get_balance(uid) or 0)
            except Exception:
                balance_now = 0
            if balance_now < bet:
                bot.send_message(
                    call.message.chat.id,
                    f"Недостаточно баллов. Баланс: {_fmt_points_ui(balance_now)}. Выбери ставку ниже.\n"
                    "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                )
                return

            try:
                db.push_last_bet(uid, "wheel", bet, limit=5)
            except Exception:
                pass

            s = session(uid)
            s.wheel_active = True
            s.wheel_bet = bet
            s.awaiting_bet_for_game = None
            s.awaiting_bet_chat_id = None
            s.awaiting_bet_message_id = None

            _schedule_game_inactivity(uid, game="wheel", chat_id=call.message.chat.id, message_id=call.message.message_id)

            rewards = _wheel_rewards_for_bet(int(bet))

            text = (
                "🎡 <b>Колесо фортуны</b>\n\n"
                f"💰 <b>Ставка {_fmt_points_ui(bet)} баллов принята</b>\n\n"
                "🎁 <b>Награды за бросок 🎲</b>\n"
            )

            for dice_value, (desc, _) in rewards.items():
                text += f"🎲 {dice_value} — {desc}\n"

            text += "\n⬇ Нажмите кнопку ниже, чтобы кинуть кубик"

            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🎲 Кинуть кубик", callback_data="wheel:roll"))

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=kb,
                parse_mode="HTML",
            )
            return

        if data == "wheel:roll":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return

            # Remove the roll button immediately so it can't be pressed twice.
            try:
                bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except Exception:
                pass

            s = session(uid)
            if not s.wheel_active or not s.wheel_bet:
                bot.answer_callback_query(call.id, "❌ Ставка не выбрана")
                return

            _touch_game(uid, game="wheel", chat_id=call.message.chat.id, message_id=call.message.message_id)

            bet = int(s.wheel_bet)
            # сбрасываем состояние, чтобы не было повторных бросков
            s.wheel_active = False
            s.wheel_bet = None

            now_ts = int(time.time())
            hour_start = (now_ts // 3600) * 3600
            win_meta = db.get_wheel_window(uid) or {"hour_ts": 0, "games_in_hour": 0}
            if int(win_meta.get("hour_ts") or 0) != hour_start:
                games_in_hour = 0
            else:
                games_in_hour = int(win_meta.get("games_in_hour") or 0)
            if games_in_hour >= WHEEL_HOURLY_LIMIT:
                text, km = _build_wheel_screen(uid)
                bot.send_message(call.message.chat.id, "❌ Лимит игр на этот час исчерпан.\n\n" + text, reply_markup=km)
                return

            spent = db.try_spend_points(uid, bet)
            if not bool(spent.get("ok")):
                try:
                    bot.answer_callback_query(call.id, "❌ Недостаточно баллов")
                except Exception:
                    pass
                return

            wheel_insurance_reserved = _insurance_reserve_for_game(uid)

            # обновляем окно по колесо-играм
            games_in_hour += 1
            db.update_wheel_window(uid, hour_ts=hour_start, games_in_hour=games_in_hour)

            # бросаем кубик через Telegram 🎲
            dice_msg = bot.send_dice(call.message.chat.id, emoji="🎲")
            value = dice_msg.dice.value if dice_msg.dice else 0

            reward_desc, reward = _wheel_rewards_for_bet(int(bet)).get(value, ("❌ Ничего", None))

            points_won = 0
            if reward:
                if "points" in reward:
                    points_won = int(reward["points"]) or 0
                    db.add_balance(uid, points_won)
                elif "farm" in reward:
                    mult, minutes = reward["farm"]
                    db.grant_or_refresh_farm_booster(
                        uid,
                        now_ts=now_ts,
                        duration_seconds=int(minutes) * 60,
                        multiplier=int(mult),
                    )

            # Insurance: triggers only on a true loss (no reward).
            if reward is None:
                used_ins, _, _ = _insurance_apply_on_loss(
                    uid=uid,
                    stake=bet,
                    chat_id=call.message.chat.id,
                    game_label="wheel",
                    reserved=bool(wheel_insurance_reserved),
                )
                _insurance_after_game(uid=uid, insured_used=bool(used_ins))
            else:
                _insurance_after_game(uid=uid, insured_used=False)

            # обновляем статистику колеса (еженедельно + за всё время)
            db.update_wheel_stats(uid, now_ts=now_ts, add_roll=1, points_won=points_won)

            result_text = f"🎲 Выпало: <b>{value}</b>\n{reward_desc}"

            from .keyboards import wheel_result_kb
            def _send_wheel_result() -> None:
                try:
                    bot.send_message(call.message.chat.id, result_text, parse_mode="HTML", reply_markup=wheel_result_kb())
                except Exception:
                    pass

            try:
                threading.Timer(3.0, _send_wheel_result).start()
            except Exception:
                _send_wheel_result()
            return

        if data == "wheel:top":
            bot.answer_callback_query(call.id)
            # по умолчанию показываем топ по выигранным баллам (неделя)
            top = db.get_wheel_top_weekly_total(limit=10)
            lines = ["🏆 ТОП колеса — по выигранным баллам (неделя):\n"]
            if not top:
                lines.append("Пока пусто. Крути колесо и попади в топ!")
            else:
                for row in top:
                    uname = ("@" + row.get("username")) if row.get("username") else f"ID {row['user_id']}"
                    lines.append(f"{row['pos']}. {uname} — {row['value']} баллов")
            from .keyboards import wheel_top_kb
            bot.edit_message_text(
                "\n".join(lines),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=wheel_top_kb(),
            )
            return

        if data.startswith("wheel:top:"):
            bot.answer_callback_query(call.id)
            kind = data.split(":", 2)[2]
            if kind == "total":
                top = db.get_wheel_top_weekly_total(limit=10)
                title = "🏆 ТОП колеса — по выигранным баллам (неделя):\n"
            elif kind == "rolls":
                top = db.get_wheel_top_weekly_rolls(limit=10)
                title = "🎲 ТОП колеса — по числу спинов (неделя):\n"
            else:
                top = db.get_wheel_top_weekly_best(limit=10)
                title = "💎 ТОП колеса — крупнейший выигрыш (неделя):\n"
            lines = [title]
            if not top:
                lines.append("Пока пусто. Крути колесо и попади в топ!")
            else:
                for row in top:
                    uname = ("@" + row.get("username")) if row.get("username") else f"ID {row['user_id']}"
                    value = int(row.get("value") or 0)
                    suffix = " баллов" if kind in ("total", "best") else " спинов"
                    lines.append(f"{row['pos']}. {uname} — {value}{suffix}")
            from .keyboards import wheel_top_kb
            bot.edit_message_text(
                "\n".join(lines),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=wheel_top_kb(),
            )
            return

        if data == "minigame:dice":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            text, km = _build_dice_screen(uid)
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=km,
            )
            try:
                s = session(uid)
                s.awaiting_bet_for_game = "dice"
                s.awaiting_bet_chat_id = int(call.message.chat.id)
                s.awaiting_bet_message_id = int(call.message.message_id)
            except Exception:
                pass
            return

        if data == "minigame:wheel":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            text, km = _build_wheel_screen(uid)
            try:
                bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=km,
                )
                try:
                    s = session(uid)
                    s.awaiting_bet_for_game = "wheel"
                    s.awaiting_bet_chat_id = int(call.message.chat.id)
                    s.awaiting_bet_message_id = int(call.message.message_id)
                except Exception:
                    pass
            except Exception as e:
                if not _is_message_not_modified_error(e):
                    raise
            return

        if data == "minigame:ladder":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            try:
                bal = int(db.get_balance(uid) or 0)
            except Exception:
                bal = 0
            last_bets = db.get_last_bets(uid, "ladder", limit=5)
            try:
                bot.edit_message_text(
                    "🪜 ЛЕСЕНКА\n\n"
                    f"Баланс: {_fmt_points_ui(bal)} 💠\n\n"
                    "Выбери ставку:\n"
                    "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)\n"
                    "Или отправь сумму числом — игра начнётся сразу. Пример: 750",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=game_bet_kb(game="ladder", last_bets=last_bets),
                )
                try:
                    s = session(uid)
                    s.awaiting_bet_for_game = "ladder"
                    s.awaiting_bet_chat_id = int(call.message.chat.id)
                    s.awaiting_bet_message_id = int(call.message.message_id)
                except Exception:
                    pass
            except Exception as e:
                if not _is_message_not_modified_error(e):
                    raise
            return

        if data == "minigame:rps":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            try:
                bal = int(db.get_balance(uid) or 0)
            except Exception:
                bal = 0
            last_bets = db.get_last_bets(uid, "rps", limit=5)
            bot.edit_message_text(
                "✊✌️🖐 <b>Камень-Ножницы-Бумага (PvE)</b>\n\n"
                f"Баланс: <b>{_fmt_points_ui(bal)}</b> 💠\n\n"
                "Выбери ставку:\n"
                "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)\n"
                "Или отправь сумму числом — игра начнётся сразу. Пример: 750",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=game_bet_kb(game="rps", last_bets=last_bets),
                parse_mode="HTML",
            )
            try:
                s = session(uid)
                s.awaiting_bet_for_game = "rps"
                s.awaiting_bet_chat_id = int(call.message.chat.id)
                s.awaiting_bet_message_id = int(call.message.message_id)
            except Exception:
                pass
            return

        if data.startswith("rps:stake:"):
            bot.answer_callback_query(call.id)
            try:
                stake = int(data.split(":", 2)[2])
            except Exception:
                return
            min_bet, max_bet = _bet_limits_for(uid)
            if stake < min_bet or stake > max_bet:
                bot.send_message(call.message.chat.id, "❌ " + _bet_out_of_range_text(bet=stake, min_bet=min_bet, max_bet=max_bet))
                return

            spent = db.try_spend_points(uid, stake)
            if not bool(spent.get("ok")):
                bal_now = 0
                try:
                    bal_now = int(spent.get("balance") or 0)
                except Exception:
                    bal_now = 0
                bot.send_message(
                    call.message.chat.id,
                    f"Недостаточно баллов. Баланс: {_fmt_points_ui(bal_now)}. Выбери ставку ниже.\n"
                    "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                )
                return

            try:
                db.push_last_bet(uid, "rps", stake, limit=5)
            except Exception:
                pass
            # stake already spent atomically above
            s = session(uid)
            s.rps_active = True
            s.rps_stake = stake
            s.rps_last_stake = int(stake)
            s.rps_bot_choice = random.choice(("rock", "paper", "scissors"))
            s.rps_insurance = bool(_insurance_reserve_for_game(uid))
            s.awaiting_bet_for_game = None
            s.awaiting_bet_chat_id = None
            s.awaiting_bet_message_id = None
            _schedule_game_inactivity(uid, game="rps", chat_id=call.message.chat.id, message_id=call.message.message_id)
            try:
                bot.edit_message_text(
                    "🤖 Я сделал выбор. Теперь твой ход — выбери: камень, ножницы или бумага.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=rps_kb(),
                )
            except Exception:
                pass
            return

        if data.startswith("rps:choice:"):
            bot.answer_callback_query(call.id)
            parts = data.split(":", 2)
            if len(parts) < 3:
                return
            choice = parts[2]
            if choice not in ("rock", "paper", "scissors"):
                return
            s = session(uid)
            if not s.rps_active or s.rps_stake is None or s.rps_bot_choice is None:
                bot.send_message(call.message.chat.id, "❌ Нет активной игры. Сначала выберите ставку.")
                return
            _touch_game(uid, game="rps", chat_id=call.message.chat.id, message_id=call.message.message_id)
            bot_choice = s.rps_bot_choice
            stake = int(s.rps_stake)

            def _beats(a: str, b: str) -> bool:
                return (a == "rock" and b == "scissors") or (a == "scissors" and b == "paper") or (a == "paper" and b == "rock")

            now_ts = int(time.time())
            vip_active = db.is_vip_active(uid, now_ts=now_ts)

            display_names = {"rock": "Камень", "paper": "Бумага", "scissors": "Ножницы"}
            emoji_map = {"rock": "✊", "paper": "✋", "scissors": "✌"}

            your_display = f"{emoji_map.get(choice, '')} Вы: {display_names.get(choice, choice)}"
            bot_display = f"🤖 Бот: {emoji_map.get(bot_choice, '')} {display_names.get(bot_choice, bot_choice)}"

            if choice == bot_choice:
                db.add_balance(uid, stake)
                result_kind = "ничья"
                result_text = f"{your_display}\n{bot_display}\n\n🤝 Ничья"
                _insurance_after_game(uid=uid, insured_used=False)
            elif _beats(choice, bot_choice):
                mult = 1.9
                if vip_active:
                    mult += 0.05
                win_amount = int(stake * mult)
                db.add_balance(uid, win_amount)
                result_kind = "победа"
                result_text = f"{your_display}\n{bot_display}\n\n🎉 Победа! Выигрыш: {_fmt_points_ui(int(win_amount))} баллов"
                _insurance_after_game(uid=uid, insured_used=False)
            else:
                result_kind = "проигрыш"
                result_text = f"{your_display}\n{bot_display}\n\n😢 Проигрыш"

                used_ins, _refund, _pct = _insurance_apply_on_loss(
                    uid=uid,
                    stake=stake,
                    chat_id=int(call.message.chat.id),
                    game_label="КНБ",
                    reserved=bool(getattr(s, "rps_insurance", False)),
                )
                _insurance_after_game(uid=uid, insured_used=bool(used_ins))

                refund_i = 0
                try:
                    refund_i = int(_refund or 0)
                except Exception:
                    refund_i = 0
                lost_i = max(0, int(stake) - int(refund_i))
                result_text += f"\n💸 Потеря: {_fmt_points_ui(int(lost_i))} баллов"

            try:
                bal_after = int(db.get_balance(uid) or 0)
            except Exception:
                bal_after = 0

            result_text = (
                "✊✋✌ КНБ\n\n"
                + result_text
                + f"\n\nРезультат: {result_kind}\n"
                + f"💰 Баланс: {_fmt_points_ui(int(bal_after))} 💠"
            )

            # Сбрасываем состояние
            s.rps_active = False
            s.rps_stake = None
            s.rps_bot_choice = None
            s.rps_insurance = False

            from .keyboards import rps_result_kb
            bot.send_message(call.message.chat.id, result_text, reply_markup=rps_result_kb())
            return

        if data == "rps:again":
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            s = session(uid)
            if getattr(s, "rps_last_stake", None):
                try:
                    stake2 = int(s.rps_last_stake or 0)
                except Exception:
                    stake2 = 0
            else:
                stake2 = 0

            if stake2 > 0:
                min_bet, max_bet = _bet_limits_for(uid)
                if stake2 < min_bet or stake2 > max_bet:
                    stake2 = 0

            if stake2 > 0:
                spent2 = db.try_spend_points(uid, int(stake2))
                if not bool(spent2.get("ok")):
                    bal_now = 0
                    try:
                        bal_now = int(spent2.get("balance") or 0)
                    except Exception:
                        bal_now = 0
                    bot.send_message(
                        call.message.chat.id,
                        f"Недостаточно баллов. Баланс: {_fmt_points_ui(bal_now)}. Выбери ставку ниже.\n"
                        "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                    )
                    stake2 = 0
                else:
                    try:
                        db.push_last_bet(uid, "rps", int(stake2), limit=5)
                    except Exception:
                        pass
                    s.rps_active = True
                    s.rps_stake = int(stake2)
                    s.rps_last_stake = int(stake2)
                    s.rps_bot_choice = random.choice(("rock", "paper", "scissors"))
                    s.rps_insurance = bool(_insurance_reserve_for_game(uid))
                    _schedule_game_inactivity(uid, game="rps", chat_id=call.message.chat.id, message_id=call.message.message_id)
                    try:
                        bot.edit_message_text(
                            "🤖 Я сделал выбор. Теперь твой ход — выбери: камень, ножницы или бумага.",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=rps_kb(),
                        )
                    except Exception:
                        try:
                            bot.send_message(call.message.chat.id, "🤖 Я сделал выбор. Теперь твой ход — выбери:", reply_markup=rps_kb())
                        except Exception:
                            pass
                    return

            # Fallback: show stake picker
            try:
                bal = int(db.get_balance(uid) or 0)
            except Exception:
                bal = 0
            last_bets = db.get_last_bets(uid, "rps", limit=5)
            try:
                m = bot.send_message(
                    call.message.chat.id,
                    "✊✌️🖐 <b>Камень-Ножницы-Бумага (PvE)</b>\n\n"
                    f"Баланс: <b>{_fmt_points_ui(bal)}</b> 💠\n\n"
                    "Выбери ставку:\n"
                    "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)\n"
                    "Или отправь сумму числом — игра начнётся сразу. Пример: 750",
                    reply_markup=game_bet_kb(game="rps", last_bets=last_bets),
                    parse_mode="HTML",
                )
                try:
                    s.awaiting_bet_for_game = "rps"
                    s.awaiting_bet_chat_id = int(call.message.chat.id)
                    s.awaiting_bet_message_id = int(m.message_id)
                except Exception:
                    pass
            except Exception:
                pass
            return

        if data.startswith("dice:bet:"):
            bot.answer_callback_query(call.id)
            try:
                bet = int(data.split(":", 2)[2])
            except Exception:
                return
            try:
                s = session(uid)
                s.awaiting_bet_for_game = None
                s.awaiting_bet_chat_id = None
                s.awaiting_bet_message_id = None
            except Exception:
                pass
            _dice_start_auto_game(chat_id=call.message.chat.id, uid=uid, bet=bet, edit_message_id=call.message.message_id)
            return

        if data.startswith("dice:again:"):
            bot.answer_callback_query(call.id)
            try:
                bet = int(data.split(":", 2)[2])
            except Exception:
                return
            _dice_start_auto_game(chat_id=call.message.chat.id, uid=uid, bet=bet, edit_message_id=call.message.message_id)
            return

        if data.startswith("ladder:bet:"):
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return
            try:
                bet = int(data.split(":", 2)[2])
            except Exception:
                return
            min_bet, max_bet = _bet_limits_for(uid)
            if bet < min_bet or bet > max_bet:
                bot.send_message(call.message.chat.id, "❌ " + _bet_out_of_range_text(bet=bet, min_bet=min_bet, max_bet=max_bet))
                return

            spent = db.try_spend_points(uid, bet)
            if not bool(spent.get("ok")):
                bal_now = 0
                try:
                    bal_now = int(spent.get("balance") or 0)
                except Exception:
                    bal_now = 0
                bot.send_message(
                    call.message.chat.id,
                    f"Недостаточно баллов. Баланс: {_fmt_points_ui(bal_now)}. Выбери ставку ниже.\n"
                    "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                )
                return

            try:
                s = session(uid)
                s.awaiting_bet_for_game = None
                s.awaiting_bet_chat_id = None
                s.awaiting_bet_message_id = None
            except Exception:
                pass

            try:
                db.push_last_bet(uid, "ladder", bet, limit=5)
            except Exception:
                pass

            now_ts = int(time.time())
            # bet already spent atomically above
            s = session(uid)
            s.ladder_active = True
            s.ladder_bet = bet
            s.ladder_step = 0
            s.ladder_multiplier = 1.0
            s.ladder_chat_id = call.message.chat.id
            s.ladder_message_id = call.message.message_id
            s.ladder_rows = []
            s.ladder_mines = [random.randint(0, 2) for _ in range(6)]
            s.ladder_choices = [None for _ in range(6)]
            s.ladder_current_mine = int(s.ladder_mines[0])
            s.ladder_insurance = bool(_insurance_reserve_for_game(uid))

            _schedule_game_inactivity(uid, game="ladder", chat_id=call.message.chat.id, message_id=call.message.message_id)

            _schedule_game_inactivity(uid, game="ladder", chat_id=call.message.chat.id, message_id=call.message.message_id)

            # Weekly tasks progress
            try:
                wk = db.week_key_utc(now_ts)
                db.add_weekly_progress(uid, week_key=wk, code="ladder_games", delta=1, now_ts=now_ts)
            except Exception:
                pass

            bot.edit_message_text(
                _ladder_screen_text_v3(bet=bet, step=s.ladder_step, mult=s.ladder_multiplier, mines=s.ladder_mines, choices=s.ladder_choices),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=ladder_field_kb(
                    step=s.ladder_step,
                    mines=s.ladder_mines,
                    choices=s.ladder_choices,
                    show_cashout=(s.ladder_step > 0),
                ),
            )
            return

        if data.startswith("ladder:pick:"):
            bot.answer_callback_query(call.id)
            parts = data.split(":")
            if len(parts) != 4:
                return
            try:
                expected_step = int(parts[2])
                choice = int(parts[3])
            except Exception:
                return
            if choice not in (0, 1, 2):
                return

            s = session(uid)
            if not s.ladder_active or not s.ladder_bet:
                bot.send_message(call.message.chat.id, "❌ Нет активной игры. Откройте 🪜 Лесенка.")
                return

            _schedule_game_inactivity(uid, game="ladder", chat_id=call.message.chat.id, message_id=call.message.message_id)
            if int(s.ladder_step) != int(expected_step):
                # stale button
                try:
                    bot.answer_callback_query(call.id, "⏳ Это старый ход. Нажмите на актуальные клетки.", show_alert=True)
                except Exception:
                    pass
                return

            if expected_step < 0 or expected_step >= 6:
                return
            if not s.ladder_mines or len(s.ladder_mines) < 6:
                s.ladder_mines = [random.randint(0, 2) for _ in range(6)]
            if not s.ladder_choices or len(s.ladder_choices) < 6:
                s.ladder_choices = [None for _ in range(6)]

            bet = int(s.ladder_bet)
            mine_idx = int(s.ladder_mines[expected_step])
            s.ladder_choices[expected_step] = int(choice)

            # mine hit -> reveal all and end
            if int(choice) == mine_idx:
                potential = _ladder_cashout_amount(bet, float(s.ladder_multiplier or 1.0))
                mines_snapshot = list(s.ladder_mines or [])
                choices_snapshot = list(s.ladder_choices or [])

                used_ins, _refund, _pct = _insurance_apply_on_loss(
                    uid=uid,
                    stake=bet,
                    chat_id=int(call.message.chat.id),
                    game_label="Лесенка",
                    reserved=bool(getattr(s, "ladder_insurance", False)),
                )
                _insurance_after_game(uid=uid, insured_used=bool(used_ins))

                s.ladder_active = False
                s.ladder_bet = None
                s.ladder_step = 0
                s.ladder_multiplier = 1.0
                s.ladder_current_mine = None
                s.ladder_mines = []
                s.ladder_choices = []
                s.ladder_insurance = False

                bot.edit_message_text(
                    "❌ Вы попали на мину!\n\n"
                    f"👉 Вы могли забрать {potential} 💰",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=ladder_result_kb(bet=bet, mines=mines_snapshot, choices=choices_snapshot, step=expected_step),
                )
                return

            # safe -> advance step
            s.ladder_step = int(s.ladder_step) + 1
            s.ladder_multiplier = float(_ladder_next_multiplier(int(s.ladder_step)))

            if int(s.ladder_step) >= 6:
                mult = float(s.ladder_multiplier or 1.0)
                amount = _ladder_cashout_amount(bet, mult)
                db.add_balance(uid, amount)
                mines_snapshot = list(s.ladder_mines or [])
                choices_snapshot = list(s.ladder_choices or [])

                _insurance_after_game(uid=uid, insured_used=False)

                s.ladder_active = False
                s.ladder_bet = None
                s.ladder_step = 0
                s.ladder_multiplier = 1.0
                s.ladder_current_mine = None
                s.ladder_mines = []
                s.ladder_choices = []
                s.ladder_insurance = False

                bot.edit_message_text(
                    "🎉 Вы дошли до вершины!\n\n"
                    f"Начислено: +{amount} баллов\n"
                    f"Коэффициент: x{mult:.2f}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=ladder_result_kb(bet=bet, mines=mines_snapshot, choices=choices_snapshot, step=5),
                )
                return

            s.ladder_current_mine = int(s.ladder_mines[int(s.ladder_step)])

            bot.edit_message_text(
                _ladder_screen_text_v3(bet=bet, step=s.ladder_step, mult=s.ladder_multiplier, mines=s.ladder_mines, choices=s.ladder_choices),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=ladder_field_kb(
                    step=s.ladder_step,
                    mines=s.ladder_mines,
                    choices=s.ladder_choices,
                    show_cashout=True,
                ),
            )
            return

        if data == "ladder:cashout":
            bot.answer_callback_query(call.id)
            s = session(uid)
            if not s.ladder_active or not s.ladder_bet:
                bot.send_message(call.message.chat.id, "❌ Нет активной игры. Откройте 🪜 Лесенка.")
                return

            _schedule_game_inactivity(uid, game="ladder", chat_id=call.message.chat.id, message_id=call.message.message_id)
            if int(s.ladder_step) <= 0:
                try:
                    bot.answer_callback_query(call.id, "Сначала сделайте 1 ход", show_alert=False)
                except Exception:
                    pass
                return
            bet = int(s.ladder_bet)
            mult = float(s.ladder_multiplier or 1.0)
            amount = _ladder_cashout_amount(bet, mult)
            db.add_balance(uid, amount)

            reveal_step = max(0, int(s.ladder_step) - 1)

            mines = list(s.ladder_mines or [])
            choices = list(s.ladder_choices or [])
            if len(mines) < 6:
                mines = [random.randint(0, 2) for _ in range(6)]
            if len(choices) < 6:
                choices = [None for _ in range(6)]
            s.ladder_active = False
            s.ladder_bet = None
            s.ladder_step = 0
            s.ladder_multiplier = 1.0
            s.ladder_current_mine = None
            s.ladder_mines = []
            s.ladder_choices = []
            s.ladder_insurance = False

            _insurance_after_game(uid=uid, insured_used=False)

            bot.edit_message_text(
                "🪜 ЛЕСЕНКА\n\n"
                f"💰 Ты забрал выигрыш: +{_fmt_points_ui(int(amount))} баллов\n"
                f"Коэффициент: x{mult:.2f}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=ladder_result_kb(bet=bet, mines=mines, choices=choices, step=reveal_step),
            )
            return

        if data.startswith("ladder:again:"):
            bot.answer_callback_query(call.id)
            try:
                bet = int(data.split(":", 2)[2])
            except Exception:
                return
            min_bet, max_bet = _bet_limits_for(uid)
            if bet < min_bet or bet > max_bet:
                return
            if db.get_balance(uid) < bet:
                bot.send_message(call.message.chat.id, "❌ Недостаточно баллов для ставки")
                return

            try:
                db.push_last_bet(uid, "ladder", bet, limit=5)
            except Exception:
                pass

            db.add_balance(uid, -bet)
            s = session(uid)
            s.ladder_active = True
            s.ladder_bet = bet
            s.ladder_step = 0
            s.ladder_multiplier = 1.0
            s.ladder_chat_id = call.message.chat.id
            s.ladder_message_id = call.message.message_id
            s.ladder_rows = []
            s.ladder_mines = [random.randint(0, 2) for _ in range(6)]
            s.ladder_choices = [None for _ in range(6)]
            s.ladder_current_mine = int(s.ladder_mines[0])
            s.ladder_insurance = bool(_insurance_reserve_for_game(uid))

            bot.edit_message_text(
                _ladder_screen_text_v3(bet=bet, step=s.ladder_step, mult=s.ladder_multiplier, mines=s.ladder_mines, choices=s.ladder_choices),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=ladder_field_kb(
                    step=s.ladder_step,
                    mines=s.ladder_mines,
                    choices=s.ladder_choices,
                    show_cashout=(s.ladder_step > 0),
                ),
            )
            return

        if data.startswith("shop:"):
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return

            s = session(uid)
            chat_id = call.message.chat.id
            message_id = call.message.message_id
            now_ts = int(time.time())

            if data == "shop:home":
                bot.edit_message_text(_shop_main_text(uid), chat_id=chat_id, message_id=message_id, reply_markup=shop_main_kb())
                return

            if data == "shop:exit":
                reset_user_flow(uid)
                reset_admin_flow(uid)
                try:
                    _safe_delete_message(bot, int(chat_id), int(message_id))
                except Exception:
                    pass
                _set_reply_keyboard_silent(chat_id, main_menu_kb(is_admin=_is_admin(uid, settings)))
                return

            if data == "shop:profile":
                _send_profile(chat_id, uid)
                return

            # Disabled sections
            if data.startswith("shop:title") or data.startswith("shop:emoji"):
                try:
                    s.shop_expect_custom_title = False
                    s.shop_custom_title_pending = None
                except Exception:
                    pass
                bot.edit_message_text(
                    "❌ Раздел отключен.",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_main_kb(),
                )
                return

            # --- VIP ---

            if data == "shop:vip":
                s.shop_vip_plan = None
                bot.edit_message_text(_shop_vip_text(), chat_id=chat_id, message_id=message_id, reply_markup=shop_vip_kb())
                return

            if data.startswith("shop:vip:plan:"):
                plan = data.split(":")[-1]
                if plan not in ("7", "30", "forever"):
                    bot.send_message(chat_id, "❌ Неизвестный пакет")
                    return
                s.shop_vip_plan = plan
                vip_until = db.get_vip_until(uid)
                if vip_until > now_ts:
                    bot.edit_message_text(
                        "⚠ VIP уже активен\n\n"
                        "Ваш VIP действует до:\n"
                        f"{_fmt_date_ddmmyyyy(vip_until)}\n\n"
                        "Вы можете продлить VIP,\n"
                        "сроки суммируются.",
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=shop_vip_extend_kb(),
                    )
                    return

                cost_rub = _vip_cost_rub(plan)
                bot.edit_message_text(
                    ("💎 VIP на 7 дней" if plan == "7" else "💎 VIP на 30 дней" if plan == "30" else "💎 VIP навсегда")
                    + "\n\n"
                    + f"Цена: {cost_rub} ₽\n\n"
                    + "Вы получите:\n"
                    + "• x2 фарм баллов\n"
                    + "• +20% к заданиям\n"
                    + "• +0.10 — +0.50 к коэффициенту в игре Мины\n"
                    + "• VIP-статус в профиле\n\n"
                    + "Подтвердить покупку?",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_confirm_kb(buy_cb="shop:vip:buy", cancel_cb="shop:vip"),
                )
                return

            if data == "shop:vip:extend":
                plan = s.shop_vip_plan or ""
                if plan not in ("7", "30", "forever"):
                    bot.send_message(chat_id, "❌ Сначала выберите пакет VIP")
                    return
                cost_rub = _vip_cost_rub(plan)
                bot.edit_message_text(
                    ("💎 VIP на 7 дней" if plan == "7" else "💎 VIP на 30 дней" if plan == "30" else "💎 VIP навсегда")
                    + "\n\n"
                    + f"Цена: {cost_rub} ₽\n\n"
                    + "Вы получите:\n"
                    + "• x2 фарм баллов\n"
                    + "• +20% к заданиям\n"
                    + "• +0.10 — +0.50 к коэффициенту в игре Мины\n"
                    + "• VIP-статус в профиле\n\n"
                    + "Подтвердить покупку?",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_confirm_kb(buy_cb="shop:vip:buy", cancel_cb="shop:vip"),
                )
                return

            if data == "shop:vip:buy":
                plan = s.shop_vip_plan or ""
                if plan not in ("7", "30", "forever"):
                    bot.send_message(chat_id, "❌ Сначала выберите пакет VIP")
                    return

                cost_points = _rub_to_points(_vip_cost_rub(plan))
                if db.get_balance(uid) < cost_points:
                    bot.send_message(chat_id, "❌ Недостаточно баллов")
                    return

                db.add_balance(uid, -cost_points)
                new_until = db.extend_vip_until(uid, now_ts=now_ts, add_seconds=_vip_add_seconds(plan))

                bot.edit_message_text(
                    "🎉 Поздравляем!\n\n"
                    + ("👑 VIP-статус активирован на 7 дней\n\n" if plan == "7" else "👑 VIP-статус активирован на 30 дней\n\n" if plan == "30" else "👑 VIP-статус активирован навсегда\n\n")
                    + f"⏳ Действует до: {_fmt_date_ddmmyyyy(new_until)}\n"
                    + "⚡ Фарм теперь x2\n"
                    + "⭐ В профиле появился VIP-значок\n\n"
                    + "Спасибо за поддержку проекта 💙",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_vip_success_kb(),
                )
                return

            # --- Farm boost ---

            if data == "shop:farm":
                s.shop_farm_plan = None
                bot.edit_message_text(
                    "⚡ УСКОРЕНИЕ ФАРМА\n\n"
                    "Увеличьте количество бесплатных баллов:\n\n"
                    "⚡ x2 — в 2 раза больше баллов\n"
                    "🔥 x3 — в 3 раза больше баллов\n\n"
                    "Работает только на кнопку «Фарм баллов».\n"
                    "Не суммируется с другими ускорениями.",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_farm_kb(),
                )
                return

            if data.startswith("shop:farm:plan:"):
                plan = data.split(":")[-1]
                price_rub, duration_seconds, mult = _farm_plan_meta(plan)
                if price_rub <= 0:
                    bot.send_message(chat_id, "❌ Неизвестный буст")
                    return
                s.shop_farm_plan = plan
                bot.edit_message_text(
                    ("⚡ x2 Фарм на 24 часа" if mult == 2 else "🔥 x3 Фарм на 24 часа")
                    + "\n\n"
                    + f"Цена: {price_rub} ₽\n\n"
                    + f"Фарм баллов будет умножаться на {mult}\n"
                    + "в течение 24 часов.\n\n"
                    + "Подтвердить покупку?",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_confirm_kb(buy_cb="shop:farm:buy", cancel_cb="shop:farm"),
                )
                return

            if data == "shop:farm:buy":
                plan = s.shop_farm_plan or ""
                price_rub, duration_seconds, mult = _farm_plan_meta(plan)
                if price_rub <= 0:
                    bot.send_message(chat_id, "❌ Сначала выберите буст")
                    return
                cost_points = _rub_to_points(price_rub)
                res = db.try_buy_farm_booster(uid, now_ts=now_ts, cost_points=cost_points, duration_seconds=duration_seconds, multiplier=mult)
                if not res.get("ok"):
                    if res.get("reason") == "already_active":
                        booster_until = int(res.get("booster_until") or 0)
                        left = max(0, booster_until - now_ts)
                        bot.send_message(chat_id, f"⚠ Ускорение уже активно\n⏳ Осталось: {_fmt_hhmmss(left)}")
                    elif res.get("reason") == "insufficient":
                        bot.send_message(chat_id, "❌ Недостаточно баллов")
                    else:
                        bot.send_message(chat_id, "❌ Не удалось")
                    return

                booster_until = int(res.get("booster_until") or 0)
                left = max(0, booster_until - now_ts)
                bot.edit_message_text(
                    "🚀 Ускорение активировано!\n\n"
                    + ("⚡ Фарм теперь x2\n" if mult == 2 else "🔥 Фарм теперь x3\n")
                    + f"⏳ Осталось: {_fmt_hhmmss(left)}",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_farm_success_kb(),
                )
                return

            if data == "shop:farm:go":
                _farm_send_or_edit(call, chat_id, message_id, uid)
                return

            if data == "shop:boosts":
                if db.is_blocked(uid):
                    bot.send_message(chat_id, "Ваш аккаунт заблокирован.")
                    return
                _channel_on_activity(uid, chat_id=chat_id, message_id=message_id)

                luck = db.get_mines_luck_boosts(uid)
                ins = db.get_insurance_state(uid)
                insurance_balance = int(ins.get("balance") or 0)
                insurance_next = bool(int(ins.get("next") or 0))
                insurance_blocked = bool(int(ins.get("block") or 0))

                bot.edit_message_text(
                    "🚀 БУСТЫ\n\n"
                    "⚡ Ускорение фарма: активируется на 24 часа\n"
                    "🍀 Шанс +: применяется к следующей игре в 💣 Мины\n"
                    "🛡 Страховка: работает, пока не выключишь (Мины/Лесенка/КНБ/Кости/Колесо)\n"
                    "   • при проигрыше вернём 30% ставки\n"
                    "   • с шансом вернём 50%\n"
                    "   • тратится только при проигрыше\n"
                    "   • нельзя 2 игры подряд\n\n"
                    f"Доступно 🍀: {luck}\n"
                    f"Страховок 🛡: {insurance_balance}",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=boosts_kb(
                        luck_available=luck,
                        insurance_balance=insurance_balance,
                        insurance_next=insurance_next,
                        insurance_blocked=insurance_blocked,
                    ),
                )
                return

            # --- Insurance shop ---

            if data == "shop:insurance":
                s.shop_insurance_plan = None
                st = db.get_insurance_state(uid)
                bal = int(st.get("balance") or 0)
                trial_available = not bool(int(st.get("trial_used") or 0))

                text = (
                    "🛡 СИСТЕМА СТРАХОВОК\n\n"
                    "Страховка — это предмет в инвентаре.\n"
                    "Её можно включить в «🚀 Бусты» — она сработает на следующую игру.\n\n"
                    f"У вас страховок: {bal} шт.\n\n"
                    "Как работает:\n"
                    "1) Включаете страховку на следующую игру\n"
                    "2) Если проиграли — вернём 30% ставки\n"
                    "3) Иногда повезёт — вернём 50% ставки\n"
                    "4) Если выиграли — страховка НЕ тратится\n"
                    "5) Нельзя использовать 2 игры подряд (после срабатывания надо сыграть 1 игру без неё)\n\n"
                    "Покрывает игры: 💣 Мины, 🪜 Лесенка, ✊✋✌ КНБ, 🎲 Кости, 🎡 Колесо фортуны"
                )

                bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_insurance_kb(trial_available=bool(trial_available)),
                )
                return

            if data == "shop:insurance:trial":
                res = db.try_claim_insurance_trial(uid, qty=5)
                if not bool(res.get("ok")):
                    reason = str(res.get("reason") or "")
                    if reason == "already_used":
                        bot.send_message(chat_id, "🎁 Пробный набор уже получен ранее.")
                    else:
                        bot.send_message(chat_id, "❌ Не удалось получить пробный набор. Попробуйте позже.")
                    return

                new_bal = int(res.get("balance") or 0)
                bot.edit_message_text(
                    "🎁 Пробный набор получен!\n\n"
                    "Начислено: +5 страховок 🛡\n"
                    f"Теперь у вас: {new_bal} шт.",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_insurance_success_kb(),
                )
                return

            if data.startswith("shop:insurance:plan:"):
                plan = str(data.split(":")[-1]).strip()
                if plan not in {"10", "25", "70"}:
                    bot.send_message(chat_id, "❌ Неизвестный пакет")
                    return

                qty = int(plan)
                price_rub = 100 if plan == "10" else 200 if plan == "25" else 500
                s.shop_insurance_plan = plan

                cost_points = _rub_to_points(price_rub)
                bot.edit_message_text(
                    "🛡 Страховки\n\n"
                    f"Пакет: {qty} шт\n"
                    f"Цена: {price_rub} ₽\n"
                    f"К оплате: {cost_points} баллов\n\n"
                    "Подтвердить покупку?",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_confirm_kb(buy_cb="shop:insurance:buy", cancel_cb="shop:insurance"),
                )
                return

            if data == "shop:insurance:buy":
                plan = str(s.shop_insurance_plan or "").strip()
                if plan not in {"10", "25", "70"}:
                    bot.send_message(chat_id, "❌ Сначала выберите пакет")
                    return

                qty = int(plan)
                price_rub = 100 if plan == "10" else 200 if plan == "25" else 500
                cost_points = _rub_to_points(price_rub)
                if db.get_balance(uid) < cost_points:
                    bot.send_message(chat_id, "❌ Недостаточно баллов")
                    return

                db.add_balance(uid, -cost_points)
                new_bal = db.add_insurance_balance(uid, qty)
                s.shop_insurance_plan = None

                bot.edit_message_text(
                    "✅ Покупка успешна!\n\n"
                    f"Начислено: +{qty} страховок 🛡\n"
                    f"Теперь у вас: {new_bal} шт.",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_insurance_success_kb(),
                )
                return

            # --- Titles / Nick ---

            if data == "shop:title":
                s.shop_expect_custom_title = False
                s.shop_custom_title_pending = None
                bot.edit_message_text(
                    "🏷 ТИТУЛЫ И НИК\n\n"
                    "Сделайте профиль уникальным.\n"
                    "Титул отображается в профиле,\n"
                    "лидерборде и уведомлениях.",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_titles_kb(),
                )
                return

            if data == "shop:title:ready":
                bot.edit_message_text(
                    "🎖 ГОТОВЫЕ ТИТУЛЫ\n\n"
                    "Выберите титул:",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_titles_ready_kb(),
                )
                return

            if data.startswith("shop:title:ready:"):
                code = data.split(":")[-1]
                titles = {
                    "king": "👑 Король фарма",
                    "legend": "🔥 Легенда",
                    "top": "💎 Топ игрок",
                    "farm": "⚡ Фарм-машина",
                }
                title = titles.get(code)
                if not title:
                    bot.send_message(chat_id, "❌ Неизвестный титул")
                    return
                cost_points = _rub_to_points(49)
                if db.get_balance(uid) < cost_points:
                    bot.send_message(chat_id, "❌ Недостаточно баллов")
                    return
                db.add_balance(uid, -cost_points)
                db.set_custom_title(uid, title)
                bot.edit_message_text(
                    "🎉 Титул активирован!\n\n" + f"🏷 {title}",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_titles_kb(),
                )
                return

            if data == "shop:title:custom":
                s.shop_expect_custom_title = True
                s.shop_custom_title_pending = None
                bot.send_message(
                    chat_id,
                    "✏️ СВОЙ ТИТУЛ\n\n"
                    "Введите текст титула (до 20 символов).\n"
                    "Запрещены ссылки и мат.",
                )
                return

            if data == "shop:title:custom:buy":
                title = (s.shop_custom_title_pending or "").strip()
                if not title:
                    bot.send_message(chat_id, "❌ Сначала введите титул")
                    return
                cost_points = _rub_to_points(149)
                if db.get_balance(uid) < cost_points:
                    bot.send_message(chat_id, "❌ Недостаточно баллов")
                    return
                db.add_balance(uid, -cost_points)
                db.set_custom_title(uid, title)
                s.shop_custom_title_pending = None
                bot.send_message(chat_id, "✅ Титул активирован!", reply_markup=shop_titles_kb())
                return

            if data == "shop:title:color":
                bot.edit_message_text(
                    "🎨 ЦВЕТНОЙ НИК\n\n"
                    "Выберите цвет ника:",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_nick_colors_kb(),
                )
                return

            if data.startswith("shop:title:color:"):
                color = data.split(":")[-1]
                if color not in ("red", "blue", "green", "purple"):
                    bot.send_message(chat_id, "❌ Неизвестный цвет")
                    return
                cost_points = _rub_to_points(99)
                if db.get_balance(uid) < cost_points:
                    bot.send_message(chat_id, "❌ Недостаточно баллов")
                    return
                db.add_balance(uid, -cost_points)
                db.set_nick_color(uid, color)
                bot.edit_message_text(
                    "🎉 Цветной ник активирован!",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_titles_kb(),
                )
                return

            # --- Emoji ---

            if data == "shop:emoji":
                bot.edit_message_text(
                    "😎 УНИКАЛЬНЫЕ ЭМОДЗИ\n\n"
                    "Добавьте стиль в профиль\n"
                    "и сообщения бота.",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_emoji_kb(),
                )
                return

            if data.startswith("shop:emoji:pack:"):
                pack = data.split(":")[-1]
                if pack == "diamond":
                    text = (
                        "💎 DIAMOND PACK\n\n"
                        "В наборе:\n"
                        "💎 ♦️ 🔷 🔹 ✨\n\n"
                        "Эмодзи будут отображаться:\n"
                        "• в профиле\n"
                        "• при выигрыше\n"
                        "• в топе игроков"
                    )
                elif pack == "fire":
                    text = (
                        "🔥 FIRE PACK\n\n"
                        "В наборе:\n"
                        "🔥 🔥‍🧨 ⚡️ ✨\n\n"
                        "Эмодзи будут отображаться:\n"
                        "• в профиле\n"
                        "• при выигрыше\n"
                        "• в топе игроков"
                    )
                elif pack == "royal":
                    text = (
                        "👑 ROYAL PACK\n\n"
                        "В наборе:\n"
                        "👑 🏆 💎 ✨\n\n"
                        "Эмодзи будут отображаться:\n"
                        "• в профиле\n"
                        "• при выигрыше\n"
                        "• в топе игроков"
                    )
                else:
                    bot.send_message(chat_id, "❌ Неизвестный набор")
                    return
                bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=shop_emoji_pack_kb(pack=pack))
                return

            if data.startswith("shop:emoji:buy:"):
                pack = data.split(":")[-1]
                price_rub = 99 if pack in ("diamond", "fire") else 149 if pack == "royal" else 0
                if price_rub <= 0:
                    bot.send_message(chat_id, "❌ Неизвестный набор")
                    return
                cost_points = _rub_to_points(price_rub)
                if db.get_balance(uid) < cost_points:
                    bot.send_message(chat_id, "❌ Недостаточно баллов")
                    return
                db.add_balance(uid, -cost_points)
                db.set_emoji_pack(uid, pack)
                bot.edit_message_text(
                    "🎉 Набор эмодзи активирован!\n\n"
                    "💎 Ваш профиль стал уникальным",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=shop_emoji_success_kb(),
                )
                return

            bot.send_message(chat_id, "❌ Неизвестное действие")
            return

        if data.startswith("boosts:"):
            bot.answer_callback_query(call.id)
            if db.is_blocked(uid):
                bot.send_message(call.message.chat.id, "Ваш аккаунт заблокирован.")
                return

            action = data.split(":", 1)[1]
            if action == "farm":
                res = db.try_buy_farm_booster(
                    uid,
                    now_ts=int(time.time()),
                    cost_points=FARM_BOOSTER_COST,
                    duration_seconds=FARM_BOOSTER_DURATION_SECONDS,
                )
                if not res.get("ok"):
                    reason = res.get("reason")
                    if reason == "already_active":
                        bot.send_message(call.message.chat.id, "⚡ Ускорение уже активно")
                    elif reason == "insufficient":
                        bot.send_message(call.message.chat.id, "❌ Недостаточно баллов")
                    elif reason == "negative_balance":
                        bot.send_message(call.message.chat.id, "❌ Баланс меньше 0")
                    else:
                        bot.send_message(call.message.chat.id, "❌ Не удалось")
                else:
                    bot.send_message(call.message.chat.id, f"⚡ Ускорение x{FARM_BOOSTER_MULTIPLIER} активировано на 24ч")
                return

            if action == "luck":
                res = db.try_buy_mines_luck_boost(uid, cost_points=30)
                if not res.get("ok"):
                    if res.get("reason") == "insufficient":
                        bot.send_message(call.message.chat.id, "❌ Недостаточно баллов")
                    elif res.get("reason") == "blocked":
                        bot.send_message(call.message.chat.id, "⛔ Аккаунт заблокирован")
                    else:
                        bot.send_message(call.message.chat.id, "❌ Не удалось")
                else:
                    bot.send_message(call.message.chat.id, "✅ Куплено: 🍀 Шанс +\nОн будет применён к следующей игре в 💣 Мины.")

                luck = db.get_mines_luck_boosts(uid)
                ins = db.get_insurance_state(uid)
                insurance_balance = int(ins.get("balance") or 0)
                insurance_next = bool(int(ins.get("next") or 0))
                insurance_blocked = bool(int(ins.get("block") or 0))
                bot.send_message(
                    call.message.chat.id,
                    f"Доступно 🍀: {luck}",
                    reply_markup=boosts_kb(
                        luck_available=luck,
                        insurance_balance=insurance_balance,
                        insurance_next=insurance_next,
                        insurance_blocked=insurance_blocked,
                    ),
                )
                return

            if action == "insurance_toggle":
                res = db.toggle_insurance_next(uid)
                if not bool(res.get("ok")):
                    reason = str(res.get("reason") or "")
                    if reason == "blocked":
                        bot.send_message(call.message.chat.id, "🛡 Нельзя использовать страховку 2 игры подряд. Сыграйте 1 игру без страховки.")
                    elif reason == "no_insurance":
                        bot.send_message(call.message.chat.id, "🛡 У вас нет страховок. Купите их в магазине: 🛒 → 🛡 Страховки")
                    else:
                        bot.send_message(call.message.chat.id, "❌ Не удалось переключить страховку")
                    return

                luck = db.get_mines_luck_boosts(uid)
                ins = db.get_insurance_state(uid)
                insurance_balance = int(ins.get("balance") or 0)
                insurance_next = bool(int(ins.get("next") or 0))
                insurance_blocked = bool(int(ins.get("block") or 0))
                bot.send_message(
                    call.message.chat.id,
                    ("🛡 Страховка включена на следующую игру." if insurance_next else "🛡 Страховка выключена."),
                    reply_markup=boosts_kb(
                        luck_available=luck,
                        insurance_balance=insurance_balance,
                        insurance_next=insurance_next,
                        insurance_blocked=insurance_blocked,
                    ),
                )
                return

            if action == "insurance_info":
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("🛒 Купить страховки", callback_data="shop:insurance"))
                kb.row(InlineKeyboardButton("⬅ Назад", callback_data="back"))
                bot.send_message(
                    call.message.chat.id,
                    "🛡 Страховка\n\n"
                    "• Включается на следующую игру через «🚀 Бусты»\n"
                    "• Если проиграл — вернём 30% ставки\n"
                    "• Иногда повезёт — вернём 50% ставки\n"
                    "• Если выиграл — страховка не тратится\n"
                    "• Нельзя использовать 2 игры подряд\n\n"
                    "Покрывает: 💣 Мины, 🪜 Лесенка, ✊✋✌ КНБ, 🎲 Кости, 🎡 Колесо фортуны",
                    reply_markup=kb,
                )
                return

            bot.send_message(call.message.chat.id, "❌ Неизвестное действие")
            return

        # --- farm points ---

        if data.startswith("farm:"):
            s = session(uid)

            if data == "farm:limit":
                bot.answer_callback_query(
                    call.id,
                    f"🏁 Лимит на сегодня исчерпан\n🔥 Серия сохранена\n🎁 Завтра лимит: {FARM_DAILY_LIMIT}",
                    show_alert=False,
                )
                return

            if db.is_blocked(uid):
                bot.answer_callback_query(call.id, "⛔ Аккаунт заблокирован", show_alert=False)
                return

            if data == "farm:home":
                bot.answer_callback_query(call.id)
                _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)
                return

            if data == "farm:weekly":
                bot.answer_callback_query(call.id)
                now_ts = int(time.time())
                text, _tasks, km = _weekly_build_screen(uid, now_ts=now_ts, refresh_cb="farm:weekly", back_cb="farm:home")
                try:
                    bot.edit_message_text(
                        text,
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=km,
                    )
                except Exception:
                    bot.send_message(call.message.chat.id, text, reply_markup=km)
                return

            if data == "farm:tasks":
                bot.answer_callback_query(call.id)
                sub_task = db.get_task_by_code("channel_subscribe")
                tt_task = db.get_task_by_code("tiktok_comment")
                if not sub_task or not tt_task:
                    bot.send_message(call.message.chat.id, "Задания временно недоступны.")
                    return

                sub_reward = _next_reward_for_task(uid, sub_task)
                tt_reward = _next_reward_for_task(uid, tt_task)

                bot.send_message(
                    call.message.chat.id,
                    "📋 Доступные задания:\n\nВыберите задание, чтобы увидеть условия и награду:",
                    reply_markup=tasks_menu_kb(sub_reward=sub_reward, tiktok_reward=tt_reward),
                )
                return

            # Always refresh UI for wait/booster/claim actions
            if data == "farm:wait":
                st = db.get_farm_state(uid) or {}
                last_farm = int(st.get("last_farm_time") or 0)
                if last_farm <= 0:
                    bot.answer_callback_query(call.id, "✅ Можно фармить", show_alert=False)
                    _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)
                    return
                wait = FARM_COOLDOWN_SECONDS - (int(time.time()) - last_farm)
                if wait <= 0:
                    bot.answer_callback_query(call.id, "✅ Можно фармить", show_alert=False)
                    _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)
                    return
                bot.answer_callback_query(call.id, f"⏳ Фарм ещё недоступен\nПопробуй через {_fmt_mmss(wait)}", show_alert=False)
                _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)
                return

            if data == "farm:booster":
                res = db.try_buy_farm_booster(
                    uid,
                    now_ts=int(time.time()),
                    cost_points=FARM_BOOSTER_COST,
                    duration_seconds=FARM_BOOSTER_DURATION_SECONDS,
                )
                if not res.get("ok"):
                    reason = res.get("reason")
                    if reason == "already_active":
                        bot.answer_callback_query(call.id, "⚡ Ускорение уже активно", show_alert=False)
                    elif reason == "insufficient":
                        bot.answer_callback_query(call.id, "❌ Недостаточно баллов", show_alert=False)
                    elif reason == "negative_balance":
                        bot.answer_callback_query(call.id, "❌ Баланс меньше 0", show_alert=False)
                    else:
                        bot.answer_callback_query(call.id, "❌ Не удалось", show_alert=False)
                    _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)
                    return

                bot.answer_callback_query(call.id, f"⚡ Ускорение x{FARM_BOOSTER_MULTIPLIER} активировано на 24ч", show_alert=False)
                _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)
                return

            if data == "farm:claim":
                now_ts = int(time.time())

                res = db.try_claim_farm_points(
                    uid,
                    now_ts=now_ts,
                    cooldown_seconds=FARM_COOLDOWN_SECONDS,
                    base_reward=FARM_REWARD,
                    daily_limit=FARM_DAILY_LIMIT,
                    referral_bonus_per_active=FARM_REFERRAL_BONUS_PER_ACTIVE,
                    streak_bonus_map=FARM_STREAK_BONUSES,
                    booster_multiplier=FARM_BOOSTER_MULTIPLIER,
                )
                if not res.get("ok"):
                    reason = res.get("reason")
                    if reason == "cooldown":
                        wait = int(res.get("wait_seconds") or 0)
                        # Мягкое предупреждение о кулдауне
                        if wait <= 30:
                            bot.answer_callback_query(call.id, "⏳ Следующий фарм через 30 секунд", show_alert=False)
                        else:
                            bot.answer_callback_query(call.id, f"⏳ Фарм ещё недоступен\nПопробуй через {_fmt_mmss(wait)}", show_alert=False)
                        _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)
                        return
                    if reason == "daily_limit":
                        bot.answer_callback_query(
                            call.id,
                            f"🏁 Лимит на сегодня исчерпан\n🔥 Серия сохранена\n🎁 Завтра лимит: {FARM_DAILY_LIMIT}",
                            show_alert=False,
                        )
                        _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)
                        return
                    if reason == "blocked":
                        bot.answer_callback_query(call.id, "⛔ Аккаунт заблокирован", show_alert=False)
                        return
                    bot.answer_callback_query(call.id, "❌ Не удалось", show_alert=False)
                    return

                awarded = int(res.get("awarded") or 0)
                bot.answer_callback_query(call.id, f"🎉 Ты получил {awarded} баллов!", show_alert=False)

                # Weekly tasks progress
                try:
                    wk = db.week_key_utc(now_ts)
                    db.add_weekly_progress(uid, week_key=wk, code="farm_claims", delta=1, now_ts=now_ts)
                    db.add_weekly_progress(uid, week_key=wk, code="farm_points", delta=awarded, now_ts=now_ts)
                except Exception:
                    pass

                # Дополнительные UX-сообщения: удача и серия дней
                luck_bonus = int(res.get("luck_bonus") or 0)
                if luck_bonus > 0:
                    try:
                        bot.send_message(call.message.chat.id, f"🎁 Удача!\nДополнительно +{luck_bonus} баллов")
                    except Exception:
                        pass

                streak_days = int(res.get("streak_days") or 0)
                day_streak_bonus = int(res.get("streak_bonus") or 0)
                if day_streak_bonus > 0 and streak_days > 0:
                    try:
                        bot.send_message(
                            call.message.chat.id,
                            f"🎉 Серия {streak_days} дней!\nБонус: +{day_streak_bonus} баллов",
                        )
                    except Exception:
                        pass

                # Обновляем основной экран фарма с учётом кулдауна и прогресса
                _farm_send_or_edit(call, call.message.chat.id, call.message.message_id, uid)

                achievements = res.get("achievements_unlocked") or []
                if achievements:
                    try:
                        bot.send_message(
                            call.message.chat.id,
                            "🏆 Достижения получены:\n" + "\n".join(f"• {a.get('name', 'Достижение')}" for a in achievements),
                        )
                    except Exception:
                        pass

                if res.get("leveled_up"):
                    try:
                        bot.send_message(uid, "🎉 Поздравляем!\n" f"Вы достигли уровня: {res.get('new_title')}")
                    except Exception:
                        pass
                return

            bot.answer_callback_query(call.id)
            return

        if data == "minigame:mines":
            bot.answer_callback_query(call.id)
            s = session(uid)
            # Restore active round from DB (survives bot restarts)
            if s.mines_state != "active":
                try:
                    active = db.get_active_mines_round(uid)
                except Exception:
                    active = None
                if active and str(active.get("status")) in ("active", "created"):
                    try:
                        mode = str(active.get("mode") or "classic")
                        size = int(active.get("size") or 3)
                        mines_cnt = int(active.get("mines") or 1)
                        bet = int(active.get("bet_points") or 0)
                        started_at = int(active.get("started_at") or int(time.time()))
                        mine_cells = set(json.loads(str(active.get("mine_cells") or "[]")))
                        opened = set(json.loads(str(active.get("opened_cells") or "[]")))

                        # Timeout handling
                        if (int(time.time()) - started_at) >= MINES_TIMEOUT_SECONDS:
                            try:
                                db.update_mines_round(int(active["round_id"]), status="timeout", ended_at=int(time.time()))
                            except Exception:
                                pass
                            _audit_mines(
                                "timeout",
                                user_id=uid,
                                round_id=int(active.get("round_id") or 0),
                                mode=mode,
                                size=size,
                                mines=mines_cnt,
                                bet=bet,
                            )
                            _mines_reset(uid, preserve_params=True)
                            bot.edit_message_text(
                                "⏳ Время вышло. Раунд закрыт.",
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=mines_timeout_kb(),
                            )
                            return

                        s.mines_mode = mode
                        s.mines_round_id = int(active.get("round_id") or 0)
                        s.mines_size = size
                        s.mines_mines = mines_cnt
                        s.mines_bet = bet if bet > 0 else None
                        s.mines_started_at = float(started_at)
                        s.mines_mine_cells = set(int(x) for x in mine_cells)
                        s.mines_opened = set(int(x) for x in opened)
                        s.mines_state = "active"

                        opened_safe = len(s.mines_opened)
                        # Stabilized message layout: always show a small fixed template
                        if mode == "nobet":
                            text = f"💎 Открыто алмазов: {opened_safe}"
                        else:
                            try:
                                vip_active = db.is_vip_active(uid, now_ts=int(time.time()))
                            except Exception:
                                vip_active = False
                            # multiplier returns full coefficient (1.0 == stake returned)
                            mult = _mines_multiplier(size, mines_cnt, opened_safe, vip_active=vip_active)
                            cashout = _mines_cashout_amount(bet, mult) if opened_safe > 0 else 0
                            text = (
                                f"💣 МИНЫ {size}x{size}\n"
                                f"Открыто: {opened_safe}\n"
                                f"Твоя ставка: {_fmt_points_ui(int(bet))}\n"
                                f"👉 Ты можешь забрать {_fmt_points_ui(int(cashout))} 💰"
                            )

                        _safe_edit_message_text(
                            bot,
                            text,
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=mines_field_kb(size=size, opened_cells=set(s.mines_opened), show_cashout=True),
                        )
                        _schedule_game_inactivity(uid, game="mines", chat_id=call.message.chat.id, message_id=call.message.message_id)
                        return
                    except Exception:
                        # If restore fails, fall back to fresh menu.
                        pass

            # Fresh entry: immediately show parameters screen (classic mode by default, но без отображения названия режима)
            s.mines_mode = "classic"
            s.mines_state = "setup"
            bot.edit_message_text(
                "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode="classic", attempts_text=None),
            )
            return

        if data == "mines:params":
            bot.answer_callback_query(call.id)
            s = session(uid)
            if getattr(s, "tourn_active_match_id", None):
                bot.send_message(call.message.chat.id, "🏆 Турнирный матч: параметры фиксированы (3×3, 3 мины).")
                return
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            attempts_txt = None
            if mode == "nobet":
                today = str(dt.datetime.utcfromtimestamp(int(time.time())).date())
                try:
                    vip_active = db.is_vip_active(uid, now_ts=int(time.time()))
                except Exception:
                    vip_active = False
                limit = MINES_NOBET_ATTEMPTS_PER_DAY_VIP if vip_active else MINES_NOBET_ATTEMPTS_PER_DAY
                st = db.mines_get_energy(uid, today=today, attempts_per_day=limit) or {"remaining": 0, "limit": limit}
                attempts_txt = f"{int(st.get('remaining') or 0)}/{int(st.get('limit') or limit)}"
            bot.edit_message_text(
                "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode=mode, attempts_text=attempts_txt),
            )
            return

        # callback 'mines:quick' больше не используется (быстрый старт убран)

        if data.startswith("mines:mode:"):
            bot.answer_callback_query(call.id)
            s = session(uid)
            if getattr(s, "tourn_active_match_id", None):
                bot.send_message(call.message.chat.id, "🏆 Турнирный матч: нельзя менять режим.")
                return
            mode = str(data.split(":", 2)[2] or "classic")
            if mode not in MINES_MODES:
                mode = "classic"
            _mines_reset(uid)
            s.mines_mode = mode
            s.mines_state = "setup"
            # defaults per mode
            if mode in ("hardcore", "nobet"):
                s.mines_size = 3
            attempts_txt = None
            if mode == "nobet":
                today = str(dt.datetime.utcfromtimestamp(int(time.time())).date())
                try:
                    vip_active = db.is_vip_active(uid, now_ts=int(time.time()))
                except Exception:
                    vip_active = False
                limit = MINES_NOBET_ATTEMPTS_PER_DAY_VIP if vip_active else MINES_NOBET_ATTEMPTS_PER_DAY
                st = db.mines_get_energy(uid, today=today, attempts_per_day=limit) or {"remaining": 0, "limit": limit}
                attempts_txt = f"{int(st.get('remaining') or 0)}/{int(st.get('limit') or limit)}"

            bot.edit_message_text(
                "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode=mode, attempts_text=attempts_txt),
            )
            return

        if data == "mines:rules":
            bot.answer_callback_query(call.id)
            s = session(uid)
            profit_cap = MINES_CLASSIC_DAILY_PROFIT_CAP if mode == "classic" else MINES_HARDCORE_DAILY_PROFIT_CAP
            rules = (
                "💣 МИНЫ 3.2 — правила\n\n"
                "• Таймаут раунда: 5 минут\n"
                "• Макс. множитель: 10x\n"
                f"• Антиспам: 1 действие / ~{MINES_ACTION_COOLDOWN_SECONDS:.2f}с\n"
                f"• Лимит стартов: {MINES_MAX_ROUNDS_PER_MINUTE}/мин\n\n"
            )
            if mode == "nobet":
                rules += (
                    f"• Попытки в день: {MINES_NOBET_ATTEMPTS_PER_DAY} (VIP: {MINES_NOBET_ATTEMPTS_PER_DAY_VIP})\n"
                    f"• Награда: {MINES_NOBET_POINTS_PER_SAFE} за 💎 + {MINES_NOBET_CASHOUT_BONUS} за кэшаут\n"
                    f"• Дневной кап: {MINES_NOBET_DAILY_POINTS_CAP} баллов и {MINES_NOBET_DAILY_XP_CAP} XP\n\n"
                    "ℹ В этом боте XP считается как «баллы, заработанные за всё время».\n"
                )
            else:
                rules += (
                    f"• Дневной лимит чистой прибыли: +{profit_cap} баллов\n"
                    "• При проигрыше ставка сгорает\n"
                )
            bot.send_message(call.message.chat.id, rules, reply_markup=back_inline_kb())
            return

        if data == "mines:energy_info":
            bot.answer_callback_query(call.id)
            today = str(dt.datetime.utcfromtimestamp(int(time.time())).date())
            try:
                vip_active = db.is_vip_active(uid, now_ts=int(time.time()))
            except Exception:
                vip_active = False
            limit = MINES_NOBET_ATTEMPTS_PER_DAY_VIP if vip_active else MINES_NOBET_ATTEMPTS_PER_DAY
            st = db.mines_get_energy(uid, today=today, attempts_per_day=limit) or {"remaining": 0, "limit": limit}
            bot.send_message(
                call.message.chat.id,
                f"⚡ Попытки на сегодня: {int(st.get('remaining') or 0)}/{int(st.get('limit') or limit)}",
                reply_markup=back_inline_kb(),
            )
            return

        if data == "mines:pick_size":
            bot.answer_callback_query(call.id)
            s = session(uid)
            if getattr(s, "tourn_active_match_id", None):
                bot.send_message(call.message.chat.id, "🏆 Турнирный матч: размер фиксирован.")
                return
            if s.mines_state == "active":
                bot.send_message(call.message.chat.id, "Нельзя менять параметры во время игры.")
                return
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            if mode in ("hardcore", "nobet"):
                bot.send_message(call.message.chat.id, "В этом режиме размер фиксированный: 3×3")
                return
            s.mines_state = "setup"
            bot.edit_message_text(
                "📐 Выберите размер поля:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_size_kb(),
            )
            return

        if data.startswith("mines:size:"):
            bot.answer_callback_query(call.id)
            s = session(uid)
            if getattr(s, "tourn_active_match_id", None):
                bot.send_message(call.message.chat.id, "🏆 Турнирный матч: размер фиксирован.")
                return
            if s.mines_state == "active":
                bot.send_message(call.message.chat.id, "Нельзя менять параметры во время игры.")
                return
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            if mode in ("hardcore", "nobet"):
                bot.send_message(call.message.chat.id, "В этом режиме размер фиксированный: 3×3")
                return
            try:
                size = int(data.split(":", 2)[2])
            except Exception:
                return

            if not _mines_allowed_size(size):
                bot.send_message(call.message.chat.id, "Некорректный размер.")
                return
            s.mines_size = size
            if s.mines_mines is not None and not _mines_allowed_mines(size, int(s.mines_mines)):
                s.mines_mines = None
            s.mines_state = "setup"
            attempts_txt = None
            bot.edit_message_text(
                "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode=mode, attempts_text=attempts_txt),
            )
            return

        if data == "mines:pick_mines":
            bot.answer_callback_query(call.id)
            s = session(uid)
            if getattr(s, "tourn_active_match_id", None):
                bot.send_message(call.message.chat.id, "🏆 Турнирный матч: мины фиксированы.")
                return
            if s.mines_state == "active":
                bot.send_message(call.message.chat.id, "Нельзя менять параметры во время игры.")
                return
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            if mode in ("hardcore", "nobet"):
                s.mines_size = 3
            if not s.mines_size:
                bot.send_message(call.message.chat.id, "Сначала выберите размер поля.")
                return
            s.mines_state = "setup"
            try:
                vip_active = db.is_vip_active(uid, now_ts=int(time.time()))
            except Exception:
                vip_active = False
            title = "💣 Выберите количество мин:"
            bot.edit_message_text(
                title,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_mines_kb(int(s.mines_size), vip_active=vip_active, mode=mode),
            )
            return

        if data.startswith("mines:mines:"):
            bot.answer_callback_query(call.id)
            s = session(uid)
            if getattr(s, "tourn_active_match_id", None):
                bot.send_message(call.message.chat.id, "🏆 Турнирный матч: мины фиксированы.")
                return
            if s.mines_state == "active":
                bot.send_message(call.message.chat.id, "Нельзя менять параметры во время игры.")
                return
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            if mode in ("hardcore", "nobet"):
                s.mines_size = 3
            if not s.mines_size:
                bot.send_message(call.message.chat.id, "Сначала выберите размер поля.")
                return
            try:
                mines_cnt = int(data.split(":", 2)[2])
            except Exception:
                return
            if mode == "classic" and not _mines_allowed_mines(int(s.mines_size), mines_cnt):
                bot.send_message(call.message.chat.id, "Некорректное число мин.")
                return
            if mode == "hardcore" and mines_cnt not in (4, 5):
                bot.send_message(call.message.chat.id, "Некорректное число мин.")
                return
            if mode == "nobet" and mines_cnt not in (2, 3):
                bot.send_message(call.message.chat.id, "Некорректное число мин.")
                return
            s.mines_mines = mines_cnt
            s.mines_state = "setup"
            attempts_txt = None
            if mode == "nobet":
                today = str(dt.datetime.utcfromtimestamp(int(time.time())).date())
                try:
                    vip_active = db.is_vip_active(uid, now_ts=int(time.time()))
                except Exception:
                    vip_active = False
                limit = MINES_NOBET_ATTEMPTS_PER_DAY_VIP if vip_active else MINES_NOBET_ATTEMPTS_PER_DAY
                st = db.mines_get_energy(uid, today=today, attempts_per_day=limit) or {"remaining": 0, "limit": limit}
                attempts_txt = f"{int(st.get('remaining') or 0)}/{int(st.get('limit') or limit)}"
            bot.edit_message_text(
                "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode=mode, attempts_text=attempts_txt),
            )
            return

        if data == "mines:pick_bet":
            bot.answer_callback_query(call.id)
            s = session(uid)
            if getattr(s, "tourn_active_match_id", None):
                bot.send_message(call.message.chat.id, "🏆 Турнирный матч: ставки отключены.")
                return
            if s.mines_state == "active":
                bot.send_message(call.message.chat.id, "Нельзя менять параметры во время игры.")
                return
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            if mode == "nobet":
                bot.send_message(call.message.chat.id, "В режиме «Без ставок» ставка не нужна.")
                return
            s.mines_state = "setup"
            try:
                bal = int(db.get_balance(uid) or 0)
            except Exception:
                bal = 0
            last_bets = db.get_last_bets(uid, "mines", limit=5)
            bot.edit_message_text(
                "💣 МИНЫ 3.2\n\n"
                f"Баланс: {_fmt_points_ui(bal)} 💠\n\n"
                "Выбери ставку:\n"
                "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)\n"
                "Или отправь сумму числом — игра начнётся сразу. Пример: 750",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=game_bet_kb(game="mines", last_bets=last_bets),
            )
            try:
                s.awaiting_bet_for_game = "mines"
                s.awaiting_bet_chat_id = int(call.message.chat.id)
                s.awaiting_bet_message_id = int(call.message.message_id)
            except Exception:
                pass
            return

        if data.startswith("mines:bet:"):
            bot.answer_callback_query(call.id)
            s = session(uid)
            if getattr(s, "tourn_active_match_id", None):
                bot.send_message(call.message.chat.id, "🏆 Турнирный матч: ставки отключены.")
                return
            if s.mines_state == "active":
                bot.send_message(call.message.chat.id, "Нельзя менять параметры во время игры.")
                return
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            if mode == "nobet":
                bot.send_message(call.message.chat.id, "В режиме «Без ставок» ставка не нужна.")
                return
            try:
                bet = int(data.split(":", 2)[2])
            except Exception:
                return
            min_bet, max_bet = _bet_limits_for(uid)
            if bet < min_bet or bet > max_bet:
                bot.send_message(call.message.chat.id, "❌ " + _bet_out_of_range_text(bet=bet, min_bet=min_bet, max_bet=max_bet))
                return

            try:
                balance_now = int(db.get_balance(uid) or 0)
            except Exception:
                balance_now = 0
            if bet > balance_now:
                bot.send_message(
                    call.message.chat.id,
                    f"Недостаточно баллов. Баланс: {_fmt_points_ui(balance_now)}. Выбери ставку ниже.\n"
                    "⭐💰...💰⭐ — последняя ставка (кнопка со ⭐)",
                )
                return

            try:
                db.push_last_bet(uid, "mines", bet, limit=5)
            except Exception:
                pass
            s.mines_bet = bet
            s.mines_state = "setup"
            s.awaiting_bet_for_game = None
            s.awaiting_bet_chat_id = None
            s.awaiting_bet_message_id = None
            attempts_txt = None
            bot.edit_message_text(
                "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode=mode, attempts_text=attempts_txt),
            )
            return

        if data == "mines:confirm":
            # Нажатие "Начать игру" после выбора параметров: сразу запускаем раунд без экрана подтверждения.
            bot.answer_callback_query(call.id)
            _mines_start_round_from_call(call, uid)
            return

        if data == "mines:restart":
            bot.answer_callback_query(call.id)
            # Per UX: restart should return to settings, keeping previous params.
            _mines_reset(uid, preserve_params=True)
            s = session(uid)
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            bot.edit_message_text(
                "💣 МИНЫ 3.2\n\nВыберите параметры игры:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_params_kb(s.mines_size, s.mines_mines, s.mines_bet, mode=mode, attempts_text=None),
            )
            return

        if data == "mines:vip_info":
            bot.answer_callback_query(call.id)
            try:
                vip_until = db.get_vip_until(uid)
                vip_active = db.is_vip_active(uid, now_ts=int(time.time()))
            except Exception:
                vip_active = False
                vip_until = 0
            if vip_active:
                bot.send_message(
                    call.message.chat.id,
                    f"👑 VIP активен до: {_fmt_date_ddmmyyyy(int(vip_until))}\n\n🎮 Бонус в Минах: +0.10 — +0.50 к коэффициенту (зависит от поля/мин и прибавляется к базовому коэффициенту).",
                )
            else:
                bot.send_message(
                    call.message.chat.id,
                    "👑 У вас нет активного VIP.\n\n" "🎮 VIP даёт: +0.10 — +0.50 к коэффициенту в игре Мины. Купить можно в магазине.",
                )
            return


        if data.startswith("mines:cell:"):
            bot.answer_callback_query(call.id)
            s = session(uid)
            if not _mines_action_allowed(uid):
                return
            _schedule_game_inactivity(uid, game="mines", chat_id=call.message.chat.id, message_id=call.message.message_id)
            if s.mines_state != "active" or not (s.mines_round_id and s.mines_size and s.mines_mines and s.mines_started_at):
                # Try restore
                active = db.get_active_mines_round(uid)
                if active:
                    s.mines_mode = str(active.get("mode") or "classic")
                    s.mines_round_id = int(active.get("round_id") or 0)
                    s.mines_size = int(active.get("size") or 3)
                    s.mines_mines = int(active.get("mines") or 1)
                    s.mines_bet = int(active.get("bet_points") or 0) or None
                    s.mines_started_at = float(int(active.get("started_at") or int(time.time())))
                    s.mines_mine_cells = set(int(x) for x in json.loads(str(active.get("mine_cells") or "[]")))
                    s.mines_opened = set(int(x) for x in json.loads(str(active.get("opened_cells") or "[]")))
                    s.mines_state = "active"
                else:
                    sent = bot.send_message(call.message.chat.id, "Игра не активна. Откройте 🎮 Мини игры → 💣 Мины")
                    _remember_temp_notice(uid, sent)
                    return

            now_ts = int(time.time())
            if (now_ts - int(float(s.mines_started_at))) >= MINES_TIMEOUT_SECONDS:
                rnd_timeout = None
                try:
                    rnd_timeout = db.get_mines_round(int(s.mines_round_id))
                except Exception:
                    rnd_timeout = None
                try:
                    db.update_mines_round(int(s.mines_round_id), status="timeout", ended_at=now_ts)
                except Exception:
                    pass
                _audit_mines("timeout", user_id=uid, round_id=int(s.mines_round_id), mode=str(s.mines_mode))

                if rnd_timeout and str(rnd_timeout.get("mode") or "") == "nobet":
                    try:
                        opened = set(int(x) for x in json.loads(str(rnd_timeout.get("opened_cells") or "[]")))
                    except Exception:
                        opened = set()
                    _tourn_submit_from_mines_round(rnd=rnd_timeout, user_id=uid, score=len(opened), now_ts=now_ts)
                _insurance_after_game(uid=uid, insured_used=False)
                _mines_reset(uid, preserve_params=True)
                bot.edit_message_text(
                    "⏳ Время вышло (5 минут). Раунд закрыт.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=mines_timeout_kb(),
                )
                return

            try:
                cell = int(data.split(":", 2)[2])
            except Exception:
                return
            size = int(s.mines_size)
            total = _mines_total_cells(size)
            if cell < 1 or cell > total:
                return
            mode = str(getattr(s, "mines_mode", "classic") or "classic")

            rnd = db.get_mines_round(int(s.mines_round_id)) if s.mines_round_id else None
            if not rnd or int(rnd.get("user_id") or 0) != int(uid) or str(rnd.get("status") or "") != "active":
                bot.send_message(call.message.chat.id, "Раунд уже завершён.")
                _mines_reset(uid, preserve_params=True)
                return

            opened_db = set(int(x) for x in json.loads(str(rnd.get("opened_cells") or "[]")))
            if cell in opened_db:
                return

            max_d = _mines_max_diamonds_mode(size, int(s.mines_mines), mode=mode)
            if len(opened_db) >= max_d:
                bot.answer_callback_query(call.id, "Достигнут лимит 💎")
                return

            mine_cells = set(int(x) for x in json.loads(str(rnd.get("mine_cells") or "[]")))
            bet = int(rnd.get("bet_points") or 0)
            mines_cnt = int(rnd.get("mines") or s.mines_mines)
            opened = set(opened_db)

            if cell in mine_cells:
                # Luck boost: small chance to avoid a mine hit (stake modes only)
                if mode != "nobet" and s.mines_luck_boost_active and random.random() < 0.05:
                    opened.add(cell)
                else:
                    used_ins, refund, _ = _insurance_apply_on_loss(
                        uid=uid,
                        stake=bet,
                        chat_id=call.message.chat.id,
                        game_label="mines",
                        reserved=(mode != "nobet" and bool(s.mines_insurance)),
                    )
                    _insurance_after_game(uid=uid, insured_used=bool(used_ins))

                    try:
                        db.update_mines_round(int(s.mines_round_id), status="lost", ended_at=now_ts, opened_cells=sorted(opened), multiplier=0.0, win_points=0)
                    except Exception:
                        pass
                    _audit_mines(
                        "loss",
                        user_id=uid,
                        round_id=int(s.mines_round_id),
                        mode=mode,
                        size=size,
                        mines=mines_cnt,
                        bet=bet,
                        cell=cell,
                        opened_safe=len(opened),
                        insurance=bool(s.mines_insurance),
                    )

                    if mode == "nobet":
                        _tourn_submit_from_mines_round(rnd=rnd, user_id=uid, score=len(opened), now_ts=now_ts)

                    _mines_reset(uid, preserve_params=True)
                    loss_text = "❌ Ты проиграл."
                    if refund > 0:
                        loss_text += f"\n\n+{refund} баллов (страховка)"
                    loss_text += "\n\nНажмите «♻️ Играть снова», чтобы начать заново."
                    bot.edit_message_text(
                        loss_text,
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=mines_field_kb(
                            size=size,
                            opened_cells=opened,
                            mine_cell=cell,
                            mine_cells=mine_cells,
                            reveal=True,
                            disabled=True,
                            show_restart=True,
                        ),
                    )
                    return

            # safe cell
            opened.add(cell)
            opened_safe = len(opened)
            try:
                vip_active = db.is_vip_active(uid, now_ts=now_ts)
            except Exception:
                vip_active = False
            mult = 1.0
            cashout = 0
            if mode != "nobet":
                base_mult = _mines_base_multiplier(size, mines_cnt, opened_safe)
                mult = _mines_multiplier(size, mines_cnt, opened_safe, vip_active=vip_active)
                cashout = _mines_cashout_amount(bet, mult)
            next_p = _mines_survival_probability(total, mines_cnt, opened_safe)

            try:
                db.update_mines_round(int(s.mines_round_id), opened_cells=sorted(opened), multiplier=float(mult))
            except Exception:
                pass

            s.mines_opened = set(opened)
            _audit_mines(
                "open",
                user_id=uid,
                round_id=int(s.mines_round_id),
                mode=mode,
                cell=cell,
                opened_safe=opened_safe,
                multiplier=float(mult),
                cashout=int(cashout),
            )

            if mode == "nobet":
                text = f"💎 Открыто алмазов: {opened_safe}"
            else:
                text = (
                    f"💣 МИНЫ {size}x{size}\n"
                    f"Открыто: {opened_safe}\n"
                    f"Твоя ставка: {_fmt_points_ui(int(bet))}\n"
                    f"👉 Ты можешь забрать {_fmt_points_ui(int(cashout))} 💰"
                )
            _safe_edit_message_text(
                bot,
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_field_kb(size=size, opened_cells=set(opened), show_cashout=True),
            )
            return

        if data == "mines:cashout":
            s = session(uid)
            if not _mines_action_allowed(uid):
                bot.answer_callback_query(call.id)
                return
            _schedule_game_inactivity(uid, game="mines", chat_id=call.message.chat.id, message_id=call.message.message_id)
            if s.mines_state != "active" or not (s.mines_round_id and s.mines_size and s.mines_mines and s.mines_started_at):
                bot.answer_callback_query(call.id)
                sent = bot.send_message(call.message.chat.id, "Игра не активна. Откройте 🎮 Мини игры → 💣 Мины")
                _remember_temp_notice(uid, sent)
                return

            now_ts = int(time.time())
            if (now_ts - int(float(s.mines_started_at))) >= MINES_TIMEOUT_SECONDS:
                rnd_timeout = None
                try:
                    rnd_timeout = db.get_mines_round(int(s.mines_round_id))
                except Exception:
                    rnd_timeout = None
                try:
                    db.update_mines_round(int(s.mines_round_id), status="timeout", ended_at=now_ts)
                except Exception:
                    pass
                _audit_mines("timeout", user_id=uid, round_id=int(s.mines_round_id), mode=str(s.mines_mode))

                if rnd_timeout and str(rnd_timeout.get("mode") or "") == "nobet":
                    try:
                        opened = set(int(x) for x in json.loads(str(rnd_timeout.get("opened_cells") or "[]")))
                    except Exception:
                        opened = set()
                    _tourn_submit_from_mines_round(rnd=rnd_timeout, user_id=uid, score=len(opened), now_ts=now_ts)
                _insurance_after_game(uid=uid, insured_used=False)
                _mines_reset(uid, preserve_params=True)
                bot.edit_message_text(
                    "⏳ Время вышло (5 минут). Раунд закрыт.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=mines_timeout_kb(),
                )
                return

            rnd = db.get_mines_round(int(s.mines_round_id))
            if not rnd or int(rnd.get("user_id") or 0) != int(uid) or str(rnd.get("status") or "") != "active":
                bot.answer_callback_query(call.id)
                bot.send_message(call.message.chat.id, "Раунд уже завершён.")
                _mines_reset(uid, preserve_params=True)
                return

            opened = set(int(x) for x in json.loads(str(rnd.get("opened_cells") or "[]")))
            opened_safe = len(opened)
            if opened_safe <= 0:
                bot.answer_callback_query(call.id, "Сначала откройте хотя бы 1 💎", show_alert=False)
                return

            bot.answer_callback_query(call.id)

            size = int(s.mines_size)
            mines_cnt = int(s.mines_mines)
            bet = int(rnd.get("bet_points") or 0)
            total = _mines_total_cells(size)
            mode = str(getattr(s, "mines_mode", "classic") or "classic")
            try:
                vip_active = db.is_vip_active(uid, now_ts=now_ts)
            except Exception:
                vip_active = False
            mult = 1.0
            win = 0
            if mode != "nobet":
                mult = _mines_multiplier(size, mines_cnt, opened_safe, vip_active=vip_active)
                win = _mines_cashout_amount(bet, mult)

            mine_cells = set(int(x) for x in json.loads(str(rnd.get("mine_cells") or "[]")))

            capped_note = ""
            lvl_res = {"leveled_up": False, "new_title": ""}
            if mode == "nobet":
                today = str(dt.datetime.utcfromtimestamp(now_ts).date())
                raw_points = int(opened_safe * MINES_NOBET_POINTS_PER_SAFE + MINES_NOBET_CASHOUT_BONUS)
                rr = db.mines_add_nobet_rewards(
                    uid,
                    today=today,
                    add_points=raw_points,
                    add_xp=raw_points,
                    cap_points=MINES_NOBET_DAILY_POINTS_CAP,
                    cap_xp=MINES_NOBET_DAILY_XP_CAP,
                )
                gained = int(rr.get("points_added") or 0)
                if gained > 0:
                    lvl_res = db.add_balance(uid, gained)
                win = gained
                if gained < raw_points:
                    capped_note = "\n(сработал дневной лимит)"

                try:
                    db.update_mines_round(
                        int(s.mines_round_id),
                        status="cashed_out",
                        ended_at=now_ts,
                        opened_cells=sorted(opened),
                        multiplier=1.0,
                        win_points=int(win),
                        xp_earned=int(rr.get("xp_added") or 0),
                    )
                except Exception:
                    pass
            else:
                # Apply daily profit cap
                profit_cap = MINES_CLASSIC_DAILY_PROFIT_CAP if mode == "classic" else MINES_HARDCORE_DAILY_PROFIT_CAP
                today = str(dt.datetime.utcfromtimestamp(now_ts).date())
                profit = max(0, int(win) - int(bet))
                applied_profit = profit
                if profit > 0:
                    pr = db.mines_add_profit(uid, today=today, profit_delta=profit, profit_cap=profit_cap)
                    applied_profit = int(pr.get("applied") or 0)
                payout = int(bet + max(0, applied_profit))
                if payout != int(win):
                    capped_note = "\n(сработал дневной лимит прибыли)"
                win = payout
                lvl_res = db.add_balance(uid, win)

                try:
                    db.update_mines_round(
                        int(s.mines_round_id),
                        status="cashed_out",
                        ended_at=now_ts,
                        opened_cells=sorted(opened),
                        multiplier=float(mult),
                        win_points=int(win),
                        xp_earned=int(win),
                    )
                except Exception:
                    pass

            _audit_mines(
                "cashout",
                user_id=uid,
                round_id=int(s.mines_round_id),
                mode=mode,
                opened_safe=opened_safe,
                multiplier=float(mult),
                win=int(win),
                bet=int(bet),
            )

            if mode == "nobet":
                _tourn_submit_from_mines_round(rnd=rnd, user_id=uid, score=int(opened_safe), now_ts=now_ts)
            _insurance_after_game(uid=uid, insured_used=False)
            _mines_reset(uid, preserve_params=True)

            bot.edit_message_text(
                (
                    "🎉 Ты забрал выигрыш!\n"
                    f"Начислено: +{_fmt_points_ui(int(win))} баллов\n"
                    f"🎖 Уровень: {lvl_res.get('new_title')}\n\n"
                    "Нажмите «♻️ Играть снова», чтобы начать заново."
                    + capped_note
                ),
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=mines_field_kb(
                    size=size,
                    opened_cells=opened,
                    mine_cells=mine_cells,
                    reveal=True,
                    disabled=True,
                    show_restart=True,
                ),
            )

            if lvl_res.get("leveled_up"):
                try:
                    bot.send_message(uid, "🎉 Поздравляем!\n" f"Вы достигли уровня: {lvl_res.get('new_title')}")
                except Exception:
                    pass
            return

        if data == "taskcode:channel":
            bot.answer_callback_query(call.id)
            _show_channel_task(call.message.chat.id, call.message.message_id, uid, edit=True)
            return

        if data == "taskcode:tiktok":
            bot.answer_callback_query(call.id)
            _show_tiktok_task(call.message.chat.id, call.message.message_id, uid, edit=True)
            return

        if data == "tiktok:text":
            bot.answer_callback_query(call.id)
            tt = db.get_task_by_code("tiktok_comment")
            if tt and tt.comment_text:
                bot.send_message(call.message.chat.id, tt.comment_text)
            return

        if data == "tiktok:sendproof":
            bot.answer_callback_query(call.id)
            _start_tiktok_proof(uid, call.message.chat.id)
            return

        if data.startswith("repeat:no:"):
            bot.answer_callback_query(call.id)
            task_code = data.split(":", 2)[2]
            _decline_repeat(uid, task_code)
            bot.send_message(call.message.chat.id, "Ок. Возвращаю в меню.", reply_markup=main_menu_kb(is_admin=_is_admin(uid, settings)))
            return

        if data.startswith("repeat:"):
            bot.answer_callback_query(call.id)
            task_code = data.split(":", 1)[1]
            _accept_repeat(uid, task_code)
            if task_code == "channel":
                _show_channel_task(call.message.chat.id, call.message.message_id, uid, edit=False)
            elif task_code == "tiktok":
                _show_tiktok_task(call.message.chat.id, call.message.message_id, uid, edit=False)
            return

        # IMPORTANT: handle confirm before generic withdraw:* branch
        if data == "withdraw:confirm":
            bot.answer_callback_query(call.id)
            s = session(uid)
            if not (s.withdraw_amount_rub and s.withdraw_bank and s.withdraw_requisites):
                bot.send_message(call.message.chat.id, "Не хватает данных. Начни заново: 💸 Вывод")
                return

            if int(s.withdraw_amount_rub) not in WITHDRAW_OPTIONS_RUB:
                bot.send_message(call.message.chat.id, "❌ Неверная сумма. Начни заново: 💸 Вывод")
                reset_user_flow(uid)
                return
            if str(s.withdraw_bank) not in BANK_OPTIONS:
                bot.send_message(call.message.chat.id, "❌ Неверный банк. Начни заново: 💸 Вывод")
                reset_user_flow(uid)
                return
            points_spent = s.withdraw_amount_rub * POINTS_PER_RUB
            balance = db.get_balance(uid)
            if balance < points_spent:
                bot.send_message(call.message.chat.id, "Недостаточно баллов")
                reset_user_flow(uid)
                return
            db.add_balance(uid, -points_spent)
            wd_id = db.create_withdrawal(uid, s.withdraw_amount_rub, points_spent, s.withdraw_bank, s.withdraw_requisites)
            bot.send_message(call.message.chat.id, "📩 Заявка на вывод отправлена администратору.", reply_markup=main_menu_kb(is_admin=_is_admin(uid, settings)))
            bot.send_message(
                settings.admin_id,
                (
                    f"👤 @{call.from_user.username or 'без_ника'} (ID {uid})\n"
                    f"💰 {s.withdraw_amount_rub}₽\n"
                    f"🏦 {s.withdraw_bank}\n"
                    f"📱 {s.withdraw_requisites}\n\n"
                    f"🆔 Withdrawal: {wd_id}"
                ),
                reply_markup=admin_review_withdraw_kb(wd_id),
            )
            reset_user_flow(uid)
            return

        if data.startswith("withdraw:"):
            payload = data.split(":", 1)[1]
            bot.answer_callback_query(call.id)
            try:
                amount_rub = int(payload)
            except Exception:
                bot.answer_callback_query(call.id, "❌ Неверная сумма", show_alert=False)
                return

            if amount_rub not in WITHDRAW_OPTIONS_RUB:
                bot.answer_callback_query(call.id, "❌ Неверная сумма", show_alert=False)
                return
            s = session(uid)
            reset_user_flow(uid)
            s.withdraw_amount_rub = amount_rub
            bot.edit_message_text("Выбор банка:", call.message.chat.id, call.message.message_id)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=banks_kb())
            return

        if data.startswith("bank:"):
            try:
                idx = int(data.split(":", 1)[1])
            except Exception:
                bot.answer_callback_query(call.id, "❌ Неверный банк", show_alert=False)
                return
            bot.answer_callback_query(call.id)
            s = session(uid)
            if not s.withdraw_amount_rub:
                bot.send_message(call.message.chat.id, "Начни вывод заново: нажми 💸 Вывод")
                return
            if idx < 0 or idx >= len(BANK_OPTIONS):
                bot.send_message(call.message.chat.id, "❌ Неверный банк. Начни вывод заново: нажми 💸 Вывод")
                reset_user_flow(uid)
                return
            s.withdraw_bank = BANK_OPTIONS[idx]
            bot.send_message(call.message.chat.id, "Введи реквизиты (номер карты/телефон):")
            return

        if data.startswith("sub:"):
            if not _is_admin(uid, settings):
                bot.answer_callback_query(call.id)
                return
            _, action, sid_raw = data.split(":", 2)
            submission_id = int(sid_raw)
            sub = db.get_submission(submission_id)
            if not sub or sub["status"] != "pending":
                bot.answer_callback_query(call.id, "Уже обработано")
                return

            task = db.get_task(sub["task_id"])

            if action == "ok":
                reward = task.reward_points if task else 0
                db.set_submission_status(submission_id, "approved", uid)
                if task and task.code == "tiktok_comment":
                    reward = _next_reward_for_task(sub["user_id"], task)
                    lvl_res = db.add_balance(sub["user_id"], reward)
                    db.inc_completed_tasks(sub["user_id"])

                    try:
                        now_ts = int(time.time())
                        wk = db.week_key_utc(now_ts)
                        db.add_weekly_progress(sub["user_id"], week_key=wk, code="tasks_completed", delta=1, now_ts=now_ts)
                    except Exception:
                        pass

                    db.update_user_task(sub["user_id"], task.id, status="completed", reward_credited=reward)
                    msg = f"✅ Задание подтверждено. +{reward} баллов\n🎖 Уровень: {lvl_res.get('new_title')}"
                    bot.send_message(sub["user_id"], msg)

                    if lvl_res.get("leveled_up"):
                        bot.send_message(sub["user_id"], "🎉 Поздравляем!\n" f"Вы достигли уровня: {lvl_res.get('new_title')}")
                else:
                    bot.send_message(sub["user_id"], f"✅ Задание подтверждено. +{reward} баллов")
                bot.edit_message_caption(
                    (call.message.caption or "") + "\n\n✅ Одобрено",
                    call.message.chat.id,
                    call.message.message_id,
                )
                bot.answer_callback_query(call.id)
                return

            if action == "bad":
                db.set_submission_status(submission_id, "rejected", uid)
                if task and task.code == "tiktok_comment":
                    _offer_repeat_tiktok(sub["user_id"], task.id)
                else:
                    bot.send_message(sub["user_id"], "❌ Задание отклонено. Попробуй ещё раз.")
                bot.edit_message_caption(
                    (call.message.caption or "") + "\n\n❌ Отклонено",
                    call.message.chat.id,
                    call.message.message_id,
                )
                bot.answer_callback_query(call.id)
                return

            if action == "block":
                db.set_submission_status(submission_id, "rejected", uid)
                # Admins cannot be blocked.
                try:
                    admin_ids = set(getattr(settings, "admin_ids", frozenset({settings.admin_id})))
                except Exception:
                    admin_ids = {int(settings.admin_id)}
                if int(sub["user_id"]) in admin_ids:
                    bot.answer_callback_query(call.id, "Нельзя блокировать администратора")
                    try:
                        bot.edit_message_caption(
                            (call.message.caption or "") + "\n\n❌ Нельзя блокировать администратора",
                            call.message.chat.id,
                            call.message.message_id,
                        )
                    except Exception:
                        pass
                    return

                db.set_blocked(sub["user_id"], True)
                bot.send_message(sub["user_id"], "🚫 Ваш аккаунт заблокирован.")
                bot.edit_message_caption(
                    (call.message.caption or "") + "\n\n🚫 Пользователь заблокирован",
                    call.message.chat.id,
                    call.message.message_id,
                )
                bot.answer_callback_query(call.id)
                return

        if data.startswith("wd:"):
            if not _is_admin(uid, settings):
                bot.answer_callback_query(call.id)
                return
            _, action, wid_raw = data.split(":", 2)
            withdrawal_id = int(wid_raw)
            wd = db.get_withdrawal(withdrawal_id)
            if not wd or wd["status"] != "pending":
                bot.answer_callback_query(call.id, "Уже обработано")
                return
            if action == "paid":
                db.set_withdrawal_status(withdrawal_id, "paid", uid)
                bot.send_message(wd["user_id"], "✅ Выплата отмечена как выполненная.")
                bot.edit_message_text((call.message.text or "") + "\n\n✅ Выплачено", call.message.chat.id, call.message.message_id)
                bot.answer_callback_query(call.id)
                return
            if action == "decline":
                db.set_withdrawal_status(withdrawal_id, "declined", uid)
                db.add_balance(wd["user_id"], wd["points_spent"])  # refund
                bot.send_message(wd["user_id"], "❌ Заявка на вывод отклонена. Баллы возвращены.")
                bot.edit_message_text((call.message.text or "") + "\n\n❌ Отклонено", call.message.chat.id, call.message.message_id)
                bot.answer_callback_query(call.id)
                return

        if data.startswith("addtask:type:"):
            if not _is_admin(uid, settings):
                bot.answer_callback_query(call.id)
                return
            code = data.split(":", 2)[2]
            s = session(uid)
            s.admin_add_task_code = code
            s.admin_add_task_step = "title"
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "Введи название задания:")
            return

        bot.answer_callback_query(call.id)

    def _channel_timer_loop() -> None:
        if not settings.channel_chat_id:
            return
        task = db.get_task_by_code("channel_subscribe")
        if not task:
            return
        while True:
            try:
                # Auto-complete
                for uid in db.list_user_ids_for_task_status(task.id, ("new", "repeat_offer"), limit=200):
                    _channel_on_activity(uid)

                # Auto-deduct
                for uid in db.list_user_ids_for_task_status(task.id, ("completed",), limit=200):
                    try:
                        member, e = _get_chat_member_safe(
                            int(settings.channel_chat_id),
                            int(uid),
                            purpose="timer_auto_deduct",
                            attempts=3,
                        )
                        status = getattr(member, "status", None) if member is not None else None
                        is_subbed = status in ("member", "administrator", "creator")
                        if member is None and e is not None:
                            raise e
                    except Exception as e:
                        _notify_admin_once(
                            "⚠ Не могу проверить подписку через getChatMember (таймер).\n"
                            "Проверь, что бот добавлен админом в канал и что CHANNEL_CHAT_ID верный.\n\n"
                            f"Ошибка: {e}"
                        )
                        is_subbed = True
                    if not is_subbed:
                        st = _task_state(uid, task)
                        if st["status"] == "completed":
                            _handle_channel_unsub(uid, task, st)
            except Exception:
                pass
            time.sleep(20)

    def _active_duels_expirer_loop() -> None:
        idle_seconds = 300
        while True:
            try:
                expired = db.expire_stale_active_duels(idle_seconds=int(idle_seconds))
                for d in expired:
                    try:
                        did = int(d.get("duel_id") or 0)
                    except Exception:
                        did = 0
                    try:
                        stake = int(d.get("stake") or 0)
                    except Exception:
                        stake = 0
                    try:
                        creator_id = int(d.get("creator_id") or 0)
                    except Exception:
                        creator_id = 0
                    opponent_id = d.get("opponent_id")
                    try:
                        opponent_id_int = int(opponent_id) if opponent_id is not None else None
                    except Exception:
                        opponent_id_int = None
                    try:
                        is_bot = int(d.get("is_bot") or 0)
                    except Exception:
                        is_bot = 0

                    msg = f"⏳ Дуэль #{did} завершена по таймауту. Ставка {_fmt_points_ui(int(stake))} возвращена."
                    if is_bot == 1 and int(creator_id) == 0:
                        if opponent_id_int is not None:
                            try:
                                bot.send_message(int(opponent_id_int), msg)
                            except Exception:
                                pass
                        continue

                    if int(creator_id) > 0:
                        try:
                            bot.send_message(int(creator_id), msg)
                        except Exception:
                            pass
                    if opponent_id_int is not None:
                        try:
                            bot.send_message(int(opponent_id_int), msg)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(20)

    def _tournament_loop() -> None:
        while True:
            try:
                now_ts = int(time.time())

                # Auto-start tournaments
                for tid in db.list_due_tournaments(now_ts=now_ts, limit=20):
                    try:
                        db.start_tournament(int(tid), now_ts=now_ts, round_deadline_seconds=int(TOURN_MATCH_DEADLINE_SECONDS))
                    except Exception:
                        pass
                    # Resolve any immediate byes and advance as far as possible.
                    for _ in range(16):
                        try:
                            r = db.maybe_advance_tournament(int(tid), now_ts=now_ts, round_deadline_seconds=int(TOURN_MATCH_DEADLINE_SECONDS))
                        except Exception:
                            break
                        if str(r.get("reason") or "") not in ("advanced", "finished"):
                            break

                # Expire no-shows
                for mid in db.list_expired_pending_matches(now_ts=now_ts, limit=100):
                    try:
                        res = db.expire_match_no_show(match_id=int(mid), now_ts=now_ts)
                    except Exception:
                        continue
                    tid = int(res.get("tournament_id") or 0)
                    if tid > 0:
                        for _ in range(16):
                            try:
                                r = db.maybe_advance_tournament(int(tid), now_ts=now_ts, round_deadline_seconds=int(TOURN_MATCH_DEADLINE_SECONDS))
                            except Exception:
                                break
                            if str(r.get("reason") or "") not in ("advanced", "finished"):
                                break

            except Exception:
                pass
            time.sleep(5)

    # Validate channel access once on startup
    if settings.channel_chat_id:
        try:
            # TEMP (diagnostics): disable channel access validation on startup.
            # If the bot starts fine after this change, the hang was inside get_chat
            # (network or channel access / privacy / incorrect ID).
            # bot.get_chat(settings.channel_chat_id)
            pass
        except Exception as e:
            _notify_admin_once(
                "⚠ Бот не имеет доступа к каналу для проверки подписки.\n"
                "Добавь бота администратором в канал и проверь CHANNEL_CHAT_ID.\n\n"
                f"Ошибка: {e}"
            )

    threading.Thread(target=_channel_timer_loop, daemon=True).start()
    threading.Thread(target=_active_duels_expirer_loop, daemon=True).start()
    threading.Thread(target=_weekly_event_scheduler_loop, daemon=True).start()
    threading.Thread(target=_tournament_loop, daemon=True).start()

    # Keep bot alive on transient Telegram/network errors.
    # Note: `infinity_polling` may sometimes *return* without raising (it logs "Break infinity polling").
    # Treat that as a crash and apply backoff to avoid log spam.
    backoff = 5
    while True:
        try:
            try:
                print("Starting polling...")
            except Exception:
                pass

            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30,
                restart_on_change=False,
                logger_level=int(log_level),
            )

            try:
                print("Polling returned.")
            except Exception:
                pass

            # If we reached here, polling exited without exception.
            try:
                print(f"Polling exited without exception. Restarting in {int(backoff)}s")
            except Exception:
                pass
        except KeyboardInterrupt:
            try:
                print("Бот остановлен вручную.")
            except Exception:
                pass
            return
        except BaseException as e:
            try:
                print(f"Polling crashed: {e!r}")
            except Exception:
                pass
            try:
                traceback.print_exc()
            except Exception:
                pass

        time.sleep(int(backoff))
        backoff = min(60, backoff + 5)


if __name__ == "__main__":
    main()
