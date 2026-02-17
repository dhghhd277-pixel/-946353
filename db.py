from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
import re
import secrets
import sqlite3
import threading
import time
import logging
from dataclasses import dataclass


@dataclass
class Task:
    id: int
    code: str
    title: str
    description: str
    reward_points: int
    active: int
    comment_text: str | None


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._users_columns_cache: set[str] | None = None
        self._logger = logging.getLogger(__name__)

        # XP/Level system (spec 1.1):
        # XP = all points ever received (lifetime), never decreases.
        # Tiers are derived from XP thresholds.
        self._xp_thresholds: list[tuple[int, str]] = [
            (0, "🥉 Новичок"),
            (1_000, "🥈 Игрок"),
            (5_000, "🥇 Профи"),
            (20_000, "💎 VIP"),
        ]

        # Weekly events (4-week cycle): epoch Monday in UTC
        self._weekly_events_epoch = dt.date(2026, 1, 5)

    # Generic helpers for single-field access (used by duel/VIP logic)

    _IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def _users_columns(self, db: sqlite3.Connection) -> set[str]:
        if self._users_columns_cache is not None:
            return set(self._users_columns_cache)
        cols: set[str] = set()
        try:
            rows = db.execute("PRAGMA table_info(users)").fetchall()
            for r in rows or []:
                try:
                    cols.add(str(r[1]))
                except Exception:
                    continue
        except Exception:
            cols = set()
        self._users_columns_cache = set(cols)
        return cols

    def _safe_users_column(self, db: sqlite3.Connection, field: str) -> str | None:
        field = str(field)
        if not field or not self._IDENT_RE.match(field):
            return None
        cols = self._users_columns(db)
        if field not in cols:
            return None
        return field

    def get_user_field(self, user_id: int, field: str) -> int | str | None:
        """Return raw value of a column from users for given user_id.

        Used in higher-level logic (e.g. VIP, duel MMR) to avoid duplicating simple SELECTs.
        """
        with self._lock, self._connect() as db:
            try:
                safe = self._safe_users_column(db, field)
                if not safe:
                    return None
                row = db.execute(f"SELECT {safe} FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            except Exception:
                return None
            if not row:
                return None
            return row[0]

    def set_user_field(self, user_id: int, field: str, value: int | str) -> None:
        with self._lock, self._connect() as db:
            try:
                safe = self._safe_users_column(db, field)
                if not safe:
                    return
                db.execute(f"UPDATE users SET {safe} = ? WHERE user_id = ?", (value, int(user_id)))
            except Exception:
                pass

    def get_last_bets(self, user_id: int, game: str, *, limit: int = 5) -> list[int]:
        """Return last unique bets for a game (most recent first).

        Stored in users.last_bets_json.
        """
        game = str(game)
        limit = max(0, int(limit))
        if not game or limit <= 0:
            return []

        raw = self.get_user_field(int(user_id), "last_bets_json")
        if not raw:
            return []
        try:
            data = json.loads(str(raw) or "{}")
        except Exception:
            return []
        if not isinstance(data, dict):
            return []

        arr = data.get(game, [])
        if not isinstance(arr, list):
            return []

        out: list[int] = []
        for v in arr:
            try:
                n = int(v)
            except Exception:
                continue
            if n <= 0:
                continue
            if n in out:
                continue
            out.append(n)
            if len(out) >= limit:
                break
        return out

    def push_last_bet(self, user_id: int, game: str, amount: int, *, limit: int = 5) -> None:
        """Add bet to per-game history (most recent first), keeping last `limit` unique bets."""
        game = str(game)
        if not game:
            return
        try:
            amount_i = int(amount)
        except Exception:
            return
        if amount_i <= 0:
            return
        limit = max(1, int(limit))

        # ensure row exists
        try:
            self.ensure_user(int(user_id), None, None)
        except Exception:
            pass

        with self._lock, self._connect() as db:
            row = db.execute("SELECT last_bets_json FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            raw = row[0] if row else None
            try:
                data = json.loads(str(raw) or "{}")
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}

            cur = data.get(game, [])
            if not isinstance(cur, list):
                cur = []

            new_list: list[int] = []
            new_list.append(int(amount_i))
            for v in cur:
                try:
                    n = int(v)
                except Exception:
                    continue
                if n <= 0 or n == int(amount_i):
                    continue
                if n in new_list:
                    continue
                new_list.append(n)
                if len(new_list) >= limit:
                    break

            data[game] = new_list
            try:
                db.execute("UPDATE users SET last_bets_json = ? WHERE user_id = ?", (json.dumps(data, ensure_ascii=False), int(user_id)))
            except Exception:
                pass

    # --- CryptoMine helpers (inventory: code -> qty in JSON) ---

    def get_cm_inventory(self, user_id: int, inventory_field: str) -> dict[str, int]:
        """Return inventory dict from a JSON column.

        Expected format: {"rtx4090": 20, "rtx3080": 3}
        """
        inventory_field = str(inventory_field)
        raw = self.get_user_field(int(user_id), inventory_field)
        if not raw:
            return {}
        try:
            parsed = json.loads(str(raw))
        except Exception:
            return {}
        if not isinstance(parsed, dict):
            return {}
        out: dict[str, int] = {}
        for k, v in parsed.items():
            try:
                n = int(v)
            except Exception:
                continue
            if n <= 0:
                continue
            out[str(k)] = n
        return out

    def try_buy_cm_inventory_item(
        self,
        user_id: int,
        *,
        inventory_field: str,
        code: str,
        qty: int,
        unit_price_points: int,
    ) -> dict:
        """Atomically attempt to buy qty of an inventory item.

        - Checks balance_points >= unit_price_points * qty
        - Deducts points
        - Increments JSON inventory {code: qty}

        Returns: {ok: bool, reason?: str, cost?: int, new_qty?: int, balance?: int}
        """
        inventory_field = str(inventory_field)
        code = str(code)
        try:
            qty_i = int(qty)
        except Exception:
            return {"ok": False, "reason": "bad_qty"}
        try:
            unit_i = int(unit_price_points)
        except Exception:
            return {"ok": False, "reason": "bad_price"}
        if qty_i <= 0:
            return {"ok": False, "reason": "bad_qty"}
        if unit_i < 0:
            return {"ok": False, "reason": "bad_price"}
        if not code:
            return {"ok": False, "reason": "bad_code"}

        cost = int(unit_i) * int(qty_i)
        if cost <= 0:
            return {"ok": False, "reason": "bad_cost"}

        # ensure row exists
        try:
            self.ensure_user(int(user_id), None, None)
        except Exception:
            pass

        with self._lock, self._connect() as db:
            row = db.execute(
                f"SELECT balance_points, {inventory_field} FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}

            balance = int(row[0] or 0)
            raw = row[1]
            if balance < cost:
                return {"ok": False, "reason": "insufficient", "balance": balance, "cost": cost}

            try:
                data = json.loads(str(raw) or "{}")
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}

            cur = int(data.get(code, 0) or 0)
            new_qty = max(0, cur + int(qty_i))
            if new_qty <= 0:
                data.pop(code, None)
            else:
                data[code] = int(new_qty)

            db.execute(
                f"UPDATE users SET balance_points = balance_points - ?, {inventory_field} = ? WHERE user_id = ?",
                (int(cost), json.dumps(data, ensure_ascii=False), int(user_id)),
            )

            return {
                "ok": True,
                "reason": "ok",
                "cost": int(cost),
                "new_qty": int(new_qty),
                "balance": int(balance - cost),
            }

    def find_user_id_by_username(self, username: str) -> int | None:
        """Find user_id by @username if present in DB.

        Note: Telegram doesn't allow resolving arbitrary usernames to IDs unless the user
        has interacted with the bot. This only searches our stored `users.username`.
        """
        username = (username or "").strip()
        if username.startswith("@"):
            username = username[1:]
        username = username.strip()
        if not username:
            return None

        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT user_id FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1",
                (username,),
            ).fetchone()
            if not row:
                return None
            try:
                return int(row[0])
            except Exception:
                return None

    def rank_for_level(self, level: int) -> str:
        level = int(level)
        if level <= 0:
            return "🥉 Bronze"
        if 1 <= level <= 5:
            return "🥉 Bronze"
        if 6 <= level <= 10:
            return "🥈 Silver"
        if 11 <= level <= 20:
            return "🥇 Gold"
        return "💎 Diamond"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 30000")
        except Exception:
            pass
        return conn

    def init(self) -> None:
        with self._lock, self._connect() as db:

            def _has_column(table: str, column: str) -> bool:
                rows = db.execute(f"PRAGMA table_info({table})").fetchall()
                return any(str(r[1]) == column for r in rows)

            def _ensure_column(table: str, column: str, ddl: str) -> None:
                if _has_column(table, column):
                    return
                db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    balance_points INTEGER NOT NULL DEFAULT 0,
                    frozen_points INTEGER NOT NULL DEFAULT 0,
                    balance_coins INTEGER NOT NULL DEFAULT 0,
                    frozen_coins INTEGER NOT NULL DEFAULT 0,
                    completed_tasks INTEGER NOT NULL DEFAULT 0,
                    invited_by INTEGER,
                    referrals_count INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    experience INTEGER NOT NULL DEFAULT 0,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Frozen points (used for withdrawals). Older DBs won't have this column.
            _ensure_column("users", "frozen_points", "frozen_points INTEGER NOT NULL DEFAULT 0")

            # Coins economy (separate balance, not tied to XP/levels)
            _ensure_column("users", "balance_coins", "balance_coins INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "frozen_coins", "frozen_coins INTEGER NOT NULL DEFAULT 0")

            # Migrate existing DBs (created before level system)
            _ensure_column("users", "level", "level INTEGER NOT NULL DEFAULT 1")
            _ensure_column("users", "experience", "experience INTEGER NOT NULL DEFAULT 0")

            # VIP (paid status)
            _ensure_column("users", "vip_until", "vip_until INTEGER NOT NULL DEFAULT 0")

            # Shop cosmetics
            _ensure_column("users", "custom_title", "custom_title TEXT")
            _ensure_column("users", "nick_color", "nick_color TEXT")
            _ensure_column("users", "emoji_pack", "emoji_pack TEXT")

            # CryptoMine (mining farm)
            _ensure_column("users", "mining_btc", "mining_btc REAL NOT NULL DEFAULT 0")
            # Total lifetime mined BTC (persists across sells)
            _ensure_column("users", "mining_total_btc", "mining_total_btc REAL NOT NULL DEFAULT 0")
            # If there are existing mined BTC values from older versions, copy them
            # into the new `mining_total_btc` column so leaderboard reflects past activity.
            try:
                db.execute("UPDATE users SET mining_total_btc = mining_btc WHERE mining_total_btc = 0 AND mining_btc > 0")
            except Exception:
                pass
            _ensure_column("users", "mining_slots", "mining_slots INTEGER NOT NULL DEFAULT 2")
            _ensure_column("users", "mining_cards_json", "mining_cards_json TEXT")
            _ensure_column("users", "mining_gpu_inventory_json", "mining_gpu_inventory_json TEXT")
            _ensure_column("users", "mining_cooling", "mining_cooling TEXT")
            _ensure_column("users", "mining_cooling_qty", "mining_cooling_qty INTEGER NOT NULL DEFAULT 1")
            _ensure_column("users", "mining_cooling_inv_json", "mining_cooling_inv_json TEXT")
            _ensure_column("users", "mining_psu", "mining_psu TEXT")
            _ensure_column("users", "mining_psu_qty", "mining_psu_qty INTEGER NOT NULL DEFAULT 1")
            _ensure_column("users", "mining_psu_inv_json", "mining_psu_inv_json TEXT")
            _ensure_column("users", "mining_upgrades_json", "mining_upgrades_json TEXT")
            _ensure_column("users", "mining_boosters_json", "mining_boosters_json TEXT")
            _ensure_column("users", "mining_active", "mining_active INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_last_ts", "mining_last_ts INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_temp", "mining_temp REAL NOT NULL DEFAULT 0")
            # Persist latest computed target temperature (for gradual drift model)
            _ensure_column("users", "mining_temp_target", "mining_temp_target REAL NOT NULL DEFAULT 0")
            # Temperature animation state (used for smooth UI + variable heating steps)
            _ensure_column(
                "users",
                "mining_temp_animation_start",
                "mining_temp_animation_start INTEGER NOT NULL DEFAULT 0",
            )
            _ensure_column(
                "users",
                "mining_temp_animation_target",
                "mining_temp_animation_target REAL NOT NULL DEFAULT 0",
            )
            _ensure_column(
                "users",
                "mining_temp_animation_step",
                "mining_temp_animation_step INTEGER NOT NULL DEFAULT 0",
            )
            # Last timestamp when mining temperature drift was applied (for time-based heating/cooling)
            _ensure_column("users", "mining_temp_ts", "mining_temp_ts INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_cycle_seconds", "mining_cycle_seconds INTEGER NOT NULL DEFAULT 60")
            _ensure_column("users", "mining_boost_until", "mining_boost_until INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_boost_mult", "mining_boost_mult REAL NOT NULL DEFAULT 1.0")
            _ensure_column("users", "mining_event_log_json", "mining_event_log_json TEXT")
            _ensure_column("users", "mining_initialized", "mining_initialized INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_first_start_rewarded", "mining_first_start_rewarded INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_intro_seen", "mining_intro_seen INTEGER NOT NULL DEFAULT 0")

            # CryptoMine: admin-driven dangerous events (persistent state)
            _ensure_column("users", "mining_active_event", "mining_active_event TEXT")
            _ensure_column("users", "mining_event_end_ts", "mining_event_end_ts INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_locked_until", "mining_locked_until INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_event_notified", "mining_event_notified INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_event_msg_chat_id", "mining_event_msg_chat_id INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mining_event_msg_id", "mining_event_msg_id INTEGER NOT NULL DEFAULT 0")
            # Store broken GPUs separately so "repair" can restore them.
            _ensure_column("users", "mining_broken_gpu_json", "mining_broken_gpu_json TEXT")

            # Boosters / insurance
            _ensure_column("users", "mines_luck_boosts", "mines_luck_boosts INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mines_insurance_block", "mines_insurance_block INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mines_insurance_next", "mines_insurance_next INTEGER NOT NULL DEFAULT 0")

            # Global insurance system (covers all mini-games)
            _ensure_column("users", "insurance_balance", "insurance_balance INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "insurance_next", "insurance_next INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "insurance_block", "insurance_block INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "insurance_trial_used", "insurance_trial_used INTEGER NOT NULL DEFAULT 0")

            # Best-effort migration from legacy mines_* insurance fields
            try:
                db.execute(
                    "UPDATE users SET insurance_next = mines_insurance_next WHERE insurance_next = 0 AND mines_insurance_next = 1"
                )
            except Exception:
                pass
            try:
                db.execute(
                    "UPDATE users SET insurance_block = mines_insurance_block WHERE insurance_block = 0 AND mines_insurance_block = 1"
                )
            except Exception:
                pass

            # Migrate existing DBs (farm points system)
            _ensure_column("users", "last_farm_time", "last_farm_time INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "farm_streak_days", "farm_streak_days INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "farm_streak_last_date", "farm_streak_last_date TEXT")
            _ensure_column("users", "farm_booster_until", "farm_booster_until INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "farm_booster_mult", "farm_booster_mult INTEGER NOT NULL DEFAULT 2")
            _ensure_column("users", "farm_daily_date", "farm_daily_date TEXT")
            _ensure_column("users", "farm_daily_points", "farm_daily_points INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "farm_click_streak", "farm_click_streak INTEGER NOT NULL DEFAULT 0")

            # New mini-games: wheel of fortune & dice
            _ensure_column("users", "wheel_last_spin_date", "wheel_last_spin_date TEXT")
            _ensure_column("users", "wheel_free_spins_used", "wheel_free_spins_used INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_streak_days", "wheel_streak_days INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_hour_ts", "wheel_hour_ts INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_games_in_hour", "wheel_games_in_hour INTEGER NOT NULL DEFAULT 0")
            # Wheel stats for leaderboards
            _ensure_column("users", "wheel_total_win", "wheel_total_win INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_rolls", "wheel_rolls INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_best_win", "wheel_best_win INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_week_start_ts", "wheel_week_start_ts INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_week_win", "wheel_week_win INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_week_rolls", "wheel_week_rolls INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "wheel_week_best", "wheel_week_best INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "dice_hour_ts", "dice_hour_ts INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "dice_games_in_hour", "dice_games_in_hour INTEGER NOT NULL DEFAULT 0")

            # Last bets history (per game) stored as JSON
            _ensure_column("users", "last_bets_json", "last_bets_json TEXT")

            # Mines 3.x modes (no-bet energy + daily caps + rate-limits + profit caps)
            _ensure_column("users", "mines_energy_date", "mines_energy_date TEXT")
            _ensure_column("users", "mines_energy_used", "mines_energy_used INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mines_nobet_points_date", "mines_nobet_points_date TEXT")
            _ensure_column("users", "mines_nobet_points_earned", "mines_nobet_points_earned INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mines_nobet_xp_date", "mines_nobet_xp_date TEXT")
            _ensure_column("users", "mines_nobet_xp_earned", "mines_nobet_xp_earned INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mines_profit_date", "mines_profit_date TEXT")
            _ensure_column("users", "mines_profit_points", "mines_profit_points INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mines_rate_window_ts", "mines_rate_window_ts INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "mines_rounds_in_window", "mines_rounds_in_window INTEGER NOT NULL DEFAULT 0")

            # Duel rating / MMR system
            _ensure_column("users", "duel_mmr", "duel_mmr INTEGER NOT NULL DEFAULT 1000")
            _ensure_column("users", "duel_games", "duel_games INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "duel_wins", "duel_wins INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "duel_losses", "duel_losses INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "duel_streak", "duel_streak INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "duel_best_streak", "duel_best_streak INTEGER NOT NULL DEFAULT 0")
            _ensure_column("users", "duel_rank", "duel_rank TEXT")

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    reward_points INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    comment_text TEXT
                )
                """
            )

            # Indexes for performance at scale
            db.execute("CREATE INDEX IF NOT EXISTS idx_submissions_status_id ON submissions(status, submission_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_status_id ON withdrawals(status, withdrawal_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_user_tasks_task_status_updated ON user_tasks(task_id, status, updated_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_users_invited_by ON users(invited_by)")

            # tasks.code: prefer uniqueness (safe migration if DB has no duplicates)
            try:
                dup = db.execute(
                    "SELECT code, COUNT(*) c FROM tasks GROUP BY code HAVING c > 1 LIMIT 1"
                ).fetchone()
                if not dup:
                    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_code_unique ON tasks(code)")
                else:
                    db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_code ON tasks(code)")
            except Exception:
                # If something is off (e.g., old sqlite), do not fail startup.
                pass

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_tasks (
                    user_id INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    repeat_used INTEGER NOT NULL DEFAULT 0,
                    reward_credited INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, task_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                )
                """
            )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    photo_file_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewer_id INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                )
                """
            )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS withdrawals (
                    withdrawal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount_rub INTEGER NOT NULL,
                    points_spent INTEGER NOT NULL,
                    coins_spent INTEGER NOT NULL DEFAULT 0,
                    bank TEXT NOT NULL,
                    requisites TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewer_id INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )

            # Backward-compatible migration for older DBs.
            _ensure_column("withdrawals", "coins_spent", "coins_spent INTEGER NOT NULL DEFAULT 0")

            # Purchases history (admin analytics)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS purchases (
                    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    purchase_type TEXT NOT NULL,
                    item_code TEXT,
                    qty INTEGER NOT NULL DEFAULT 1,
                    points_spent INTEGER NOT NULL DEFAULT 0,
                    meta_json TEXT,
                    created_at_ts INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_purchases_user_ts ON purchases(user_id, created_at_ts)")
                db.execute("CREATE INDEX IF NOT EXISTS idx_purchases_ts ON purchases(created_at_ts)")
                db.execute("CREATE INDEX IF NOT EXISTS idx_purchases_type ON purchases(purchase_type)")
            except Exception:
                pass

            # Admin logs (withdraw review, etc.)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    entity TEXT,
                    entity_id INTEGER,
                    details_json TEXT,
                    created_at_ts INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_ts ON admin_logs(created_at_ts)")
                db.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_ts ON admin_logs(admin_id, created_at_ts)")
            except Exception:
                pass

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS referral_rewards (
                    invitee_id INTEGER PRIMARY KEY,
                    inviter_id INTEGER NOT NULL,
                    rewarded INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Weekly tasks (global rotation by week_key, per-user progress/claim)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS weekly_tasks (
                    week_key TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    target INTEGER NOT NULL,
                    reward_points INTEGER NOT NULL,
                    created_at_ts INTEGER NOT NULL,
                    PRIMARY KEY (week_key, slot)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS weekly_user_tasks (
                    user_id INTEGER NOT NULL,
                    week_key TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    claimed INTEGER NOT NULL DEFAULT 0,
                    updated_ts INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, week_key, slot),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_weekly_user_tasks_week_user ON weekly_user_tasks(week_key, user_id)"
            )

            # Weekly events (4 events rotating in a per-user shuffled order)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS weekly_event_claims (
                    user_id INTEGER NOT NULL,
                    week_index INTEGER NOT NULL,
                    event_id INTEGER NOT NULL,
                    claimed INTEGER NOT NULL DEFAULT 0,
                    notified_at_ts INTEGER,
                    claimed_at_ts INTEGER,
                    mood_emoji TEXT,
                    reward_points INTEGER,
                    PRIMARY KEY (user_id, week_index),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
                """
            )
            # Backward-compatible migration for older DBs.
            try:
                db.execute("ALTER TABLE weekly_event_claims ADD COLUMN notified_at_ts INTEGER")
            except Exception:
                pass
            try:
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_weekly_event_claims_week ON weekly_event_claims(week_index, claimed)"
                )
            except Exception:
                pass

            # Level system tables
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS level_rewards (
                    user_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    claimed INTEGER NOT NULL DEFAULT 0,
                    claimed_at TEXT,
                    PRIMARY KEY (user_id, level),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
                """
            )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS experience_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
                """
            )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS achievements (
                    achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    icon TEXT DEFAULT '🏆',
                    reward_points INTEGER DEFAULT 0,
                    reward_experience INTEGER DEFAULT 0,
                    requirement_type TEXT NOT NULL,
                    requirement_value INTEGER NOT NULL,
                    hidden INTEGER DEFAULT 0
                )
                """
            )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_achievements (
                    user_id INTEGER NOT NULL,
                    achievement_id INTEGER NOT NULL,
                    unlocked_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, achievement_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (achievement_id) REFERENCES achievements(achievement_id)
                )
                """
            )

            # Seed base achievements (idempotent)
            base_achievements = [
                ("first_task", "Первые шаги", "Выполните первое задание", "🌟", 50, 100, "tasks_completed", 1, 0),
                ("five_tasks", "Активист", "Выполните 5 заданий", "⭐", 100, 250, "tasks_completed", 5, 0),
                ("ten_tasks", "Трудяга", "Выполните 10 заданий", "💫", 200, 500, "tasks_completed", 10, 0),
                ("first_referral", "Пригласитель", "Пригласите первого друга", "🤝", 100, 200, "referrals_count", 1, 0),
                ("five_referrals", "Популярный", "Пригласите 5 друзей", "👥", 300, 500, "referrals_count", 5, 0),
                ("level_5", "Новичок", "Достигните 5 уровня", "📊", 150, 0, "level", 5, 0),
                ("level_10", "Опытный", "Достигните 10 уровня", "📈", 300, 0, "level", 10, 0),
                ("level_20", "Мастер", "Достигните 20 уровня", "🎯", 500, 0, "level", 20, 0),
                ("points_1000", "Богач", "Накопите 1000 баллов", "💰", 200, 300, "balance_points", 1000, 0),
                ("points_5000", "Магнат", "Накопите 5000 баллов", "💎", 500, 750, "balance_points", 5000, 0),
            ]
            for ach in base_achievements:
                db.execute(
                    """
                    INSERT OR IGNORE INTO achievements
                    (code, title, description, icon, reward_points, reward_experience, requirement_type, requirement_value, hidden)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ach,
                )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS duels (
                    duel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    creator_id INTEGER NOT NULL,
                    opponent_id INTEGER,
                    stake INTEGER NOT NULL,
                    game_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    is_bot INTEGER NOT NULL DEFAULT 0,
                    creator_choice TEXT,
                    opponent_choice TEXT,
                    creator_roll INTEGER,
                    opponent_roll INTEGER,
                    state_json TEXT,
                    winner_id INTEGER,
                    created_at TEXT NOT NULL,
                    joined_at TEXT,
                    resolved_at TEXT
                )
                """
            )

            # Migrate duels table
            _ensure_column("duels", "is_bot", "is_bot INTEGER NOT NULL DEFAULT 0")
            _ensure_column("duels", "is_rematch", "is_rematch INTEGER NOT NULL DEFAULT 0")
            _ensure_column("duels", "state_json", "state_json TEXT")
            _ensure_column("duels", "last_action_at", "last_action_at TEXT")

            # Indexes to speed up duel lookups and anti-abuse checks
            try:
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_duels_status_created ON duels(status, created_at)"
                )
            except Exception:
                pass
            try:
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_duels_players_resolved ON duels(status, creator_id, opponent_id, resolved_at)"
                )
            except Exception:
                pass
            try:
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_duels_status_last_action ON duels(status, last_action_at)"
                )
            except Exception:
                pass

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            # --- Admin dialogs (admin <-> user) ---
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS active_dialogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    admin_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'initiated',
                    created_at INTEGER NOT NULL,
                    last_message_at INTEGER NOT NULL,
                    closed_at INTEGER
                )
                """
            )
            try:
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_active_dialogs_user_status ON active_dialogs(user_id, status, last_message_at)"
                )
            except Exception:
                pass

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS dialog_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dialog_id INTEGER NOT NULL,
                    sender_type TEXT NOT NULL,
                    sender_id INTEGER NOT NULL,
                    message_text TEXT NOT NULL,
                    sent_at INTEGER NOT NULL,
                    read_at INTEGER
                )
                """
            )
            try:
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_dialog_messages_dialog_sent ON dialog_messages(dialog_id, sent_at DESC)"
                )
            except Exception:
                pass

            # Admin-scheduled global events (e.g. mining dangerous events)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_code TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'active_farms',
                    run_at_ts INTEGER NOT NULL,
                    created_at_ts INTEGER NOT NULL,
                    created_by INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    params_json TEXT
                )
                """
            )
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_admin_events_runat ON admin_events(status, run_at_ts)")
            except Exception:
                pass

            # Random opponent matching queue
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS random_queue (
                    rq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    stake INTEGER NOT NULL,
                    game_type TEXT NOT NULL,
                    balance_snapshot INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Persistent game rounds (Mines first)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS game_rounds (
                    round_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    bet_points INTEGER NOT NULL DEFAULT 0,
                    energy_spent INTEGER NOT NULL DEFAULT 0,
                    size INTEGER NOT NULL,
                    mines INTEGER NOT NULL,
                    mine_cells TEXT NOT NULL,
                    opened_cells TEXT NOT NULL,
                    status TEXT NOT NULL,
                    multiplier REAL NOT NULL DEFAULT 1.0,
                    win_points INTEGER NOT NULL DEFAULT 0,
                    xp_earned INTEGER NOT NULL DEFAULT 0,
                    started_at INTEGER NOT NULL,
                    ended_at INTEGER,
                    client_seed TEXT,
                    server_seed_hash TEXT,
                    server_seed TEXT
                )
                """
            )

            # Optional tournament linkage for persistent rounds
            _ensure_column("game_rounds", "tournament_id", "tournament_id INTEGER")
            _ensure_column("game_rounds", "tournament_match_id", "tournament_match_id INTEGER")
            _ensure_column("game_rounds", "tournament_game_index", "tournament_game_index INTEGER")

            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_game_rounds_user_started ON game_rounds(user_id, started_at)")
            except Exception:
                pass
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_game_rounds_game_status ON game_rounds(game, status)")
            except Exception:
                pass

            # -------------------------
            # Tournaments (MVP)
            # -------------------------
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS tournaments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_by_admin_id INTEGER,
                    games_json TEXT NOT NULL,
                    max_players INTEGER NOT NULL,
                    entry_fee_points INTEGER NOT NULL DEFAULT 0,
                    prize_pool_points INTEGER NOT NULL DEFAULT 0,
                    prize_json TEXT NOT NULL,
                    rules_json TEXT,
                    state TEXT NOT NULL DEFAULT 'registering',
                    start_at INTEGER NOT NULL,
                    end_at INTEGER,
                    created_at INTEGER NOT NULL
                )
                """
            )
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_tournaments_state_start ON tournaments(state, start_at)")
            except Exception:
                pass

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS tournament_players (
                    tournament_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    seed INTEGER,
                    status TEXT NOT NULL DEFAULT 'registered',
                    joined_at INTEGER NOT NULL,
                    eliminated_round INTEGER,
                    score_meta_json TEXT,
                    PRIMARY KEY (tournament_id, user_id)
                )
                """
            )
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_tournament_players_tid_status ON tournament_players(tournament_id, status)")
            except Exception:
                pass

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS tournament_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER NOT NULL,
                    round INTEGER NOT NULL,
                    p1_user_id INTEGER,
                    p2_user_id INTEGER,
                    p1_score INTEGER,
                    p2_score INTEGER,
                    p1_time_ms INTEGER,
                    p2_time_ms INTEGER,
                    winner_user_id INTEGER,
                    state TEXT NOT NULL DEFAULT 'pending',
                    deadline_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_tournament_matches_tid_round ON tournament_matches(tournament_id, round)")
            except Exception:
                pass
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_tournament_matches_deadline ON tournament_matches(state, deadline_at)")
            except Exception:
                pass

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS tournament_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER,
                    user_id INTEGER,
                    event TEXT NOT NULL,
                    amount_points INTEGER,
                    details_json TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_tournament_audit_tid ON tournament_audit(tournament_id, created_at)")
            except Exception:
                pass

    # --- Admin events scheduling ---

    def create_admin_event(
        self,
        *,
        event_code: str,
        scope: str,
        run_at_ts: int,
        created_by: int,
        params: dict | None = None,
    ) -> int | None:
        event_code = str(event_code).strip()
        scope = str(scope).strip() or "active_farms"
        try:
            run_at_ts_i = int(run_at_ts)
        except Exception:
            return None
        try:
            created_by_i = int(created_by)
        except Exception:
            return None
        if not event_code or run_at_ts_i <= 0:
            return None

        with self._lock, self._connect() as db:
            try:
                cur = db.execute(
                    "INSERT INTO admin_events(event_code, scope, run_at_ts, created_at_ts, created_by, status, params_json) VALUES(?,?,?,?,?,?,?)",
                    (
                        event_code,
                        scope,
                        run_at_ts_i,
                        int(time.time()),
                        created_by_i,
                        "scheduled",
                        json.dumps(params or {}, ensure_ascii=False),
                    ),
                )
                return int(cur.lastrowid)
            except Exception:
                return None

    def list_admin_events(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        limit = max(1, min(200, int(limit)))
        q = "SELECT * FROM admin_events"
        args: list = []
        if status is not None:
            q += " WHERE status = ?"
            args.append(str(status))
        q += " ORDER BY run_at_ts ASC, id ASC LIMIT ?"
        args.append(int(limit))

        with self._lock, self._connect() as db:
            try:
                rows = db.execute(q, tuple(args)).fetchall()
                return [dict(r) for r in rows or []]
            except Exception:
                return []

    def cancel_admin_event(self, event_id: int) -> bool:
        try:
            eid = int(event_id)
        except Exception:
            return False
        if eid <= 0:
            return False
        with self._lock, self._connect() as db:
            try:
                cur = db.execute(
                    "UPDATE admin_events SET status = 'cancelled' WHERE id = ? AND status = 'scheduled'",
                    (eid,),
                )
                return int(cur.rowcount or 0) > 0
            except Exception:
                return False

    def mark_admin_event_done(self, event_id: int) -> bool:
        try:
            eid = int(event_id)
        except Exception:
            return False
        if eid <= 0:
            return False
        with self._lock, self._connect() as db:
            try:
                cur = db.execute(
                    "UPDATE admin_events SET status = 'done' WHERE id = ? AND status = 'scheduled'",
                    (eid,),
                )
                return int(cur.rowcount or 0) > 0
            except Exception:
                return False

    # --- CryptoMine: per-user dangerous event state ---

    def get_mining_event_state(self, user_id: int) -> dict:
        """Return current mining event state for a user."""
        uid = int(user_id)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT mining_active_event, mining_event_end_ts, mining_locked_until, mining_event_notified, mining_event_msg_chat_id, mining_event_msg_id, mining_broken_gpu_json FROM users WHERE user_id = ?",
                (uid,),
            ).fetchone()
            if not row:
                return {}
            out = dict(row)
            # Parse broken GPUs JSON into dict[str,int]
            raw = out.get("mining_broken_gpu_json")
            broken: dict[str, int] = {}
            try:
                parsed = json.loads(str(raw) or "{}")
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        try:
                            n = int(v)
                        except Exception:
                            continue
                        if n > 0:
                            broken[str(k)] = n
            except Exception:
                broken = {}
            out["mining_broken_gpu"] = broken
            return out

    def try_start_mining_event(
        self,
        user_id: int,
        *,
        event_code: str,
        event_end_ts: int = 0,
        locked_until: int = 0,
    ) -> bool:
        """Atomically set mining_active_event if no event is active.

        Returns True if the event was started (i.e. we transitioned from None/'' to event_code).
        """
        uid = int(user_id)
        event_code = str(event_code).strip()
        if not event_code:
            return False
        with self._lock, self._connect() as db:
            try:
                cur = db.execute(
                    """
                    UPDATE users
                    SET mining_active_event = ?,
                        mining_event_end_ts = ?,
                        mining_locked_until = MAX(mining_locked_until, ?),
                        mining_event_notified = 0
                    WHERE user_id = ?
                      AND (mining_active_event IS NULL OR mining_active_event = '')
                    """,
                    (event_code, int(event_end_ts), int(locked_until), uid),
                )
                return int(cur.rowcount or 0) > 0
            except Exception:
                return False

    def set_mining_event_message(self, user_id: int, *, chat_id: int, message_id: int) -> None:
        uid = int(user_id)
        with self._lock, self._connect() as db:
            try:
                db.execute(
                    "UPDATE users SET mining_event_msg_chat_id = ?, mining_event_msg_id = ?, mining_event_notified = 1 WHERE user_id = ?",
                    (int(chat_id), int(message_id), uid),
                )
            except Exception:
                pass

    def clear_mining_event(self, user_id: int) -> None:
        uid = int(user_id)
        with self._lock, self._connect() as db:
            try:
                db.execute(
                    "UPDATE users SET mining_active_event = NULL, mining_event_end_ts = 0, mining_event_notified = 0, mining_event_msg_chat_id = 0, mining_event_msg_id = 0 WHERE user_id = ?",
                    (uid,),
                )
            except Exception:
                pass

    def add_broken_gpu(self, user_id: int, gpu_code: str, qty: int = 1) -> None:
        uid = int(user_id)
        gpu_code = str(gpu_code)
        try:
            qty_i = int(qty)
        except Exception:
            return
        if not gpu_code or qty_i <= 0:
            return

        with self._lock, self._connect() as db:
            row = db.execute("SELECT mining_broken_gpu_json FROM users WHERE user_id = ?", (uid,)).fetchone()
            raw = row[0] if row else None
            try:
                parsed = json.loads(str(raw) or "{}")
            except Exception:
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {}
            cur = int(parsed.get(gpu_code, 0) or 0)
            parsed[gpu_code] = cur + qty_i
            try:
                db.execute(
                    "UPDATE users SET mining_broken_gpu_json = ? WHERE user_id = ?",
                    (json.dumps(parsed, ensure_ascii=False), uid),
                )
            except Exception:
                pass

    def level_from_xp(self, xp: int) -> int:
        xp = int(xp)
        if xp >= 20_000:
            return 4
        if xp >= 5_000:
            return 3
        if xp >= 1_000:
            return 2
        return 1

    def get_level_title(self, level: int) -> str:
        level = int(level)
        if level <= 1:
            return "🥉 Новичок"
        if level == 2:
            return "🥈 Игрок"
        if level == 3:
            return "🥇 Профи"
        return "💎 VIP"

    def next_xp_threshold(self, level: int) -> int | None:
        level = int(level)
        if level <= 1:
            return 1_000
        if level == 2:
            return 5_000
        if level == 3:
            return 20_000
        return None

    def _award_achievements_in_conn(self, db: sqlite3.Connection, user_id: int, *, now: str) -> list[dict]:
        """Awards achievements that are satisfied.

        Important: XP is derived from points, so we only apply reward_points.
        reward_experience is ignored.
        """

        unlocked: list[dict] = []
        # Allow chaining (an achievement reward can enable another)
        for _ in range(5):
            stats = db.execute(
                "SELECT level, experience, balance_points, completed_tasks, referrals_count FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not stats:
                break

            user_stats = {
                "level": int(stats[0] or 1),
                "experience": int(stats[1] or 0),
                "balance_points": int(stats[2] or 0),
                "tasks_completed": int(stats[3] or 0),
                "referrals_count": int(stats[4] or 0),
            }

            all_ach = db.execute(
                "SELECT achievement_id, code, title, description, icon, reward_points, reward_experience, requirement_type, requirement_value, hidden FROM achievements"
            ).fetchall()
            unlocked_rows = db.execute(
                "SELECT achievement_id FROM user_achievements WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            unlocked_ids = {int(r[0]) for r in unlocked_rows}

            newly: list[dict] = []
            bonus_points_total = 0
            for a in all_ach:
                ach_id = int(a[0])
                if ach_id in unlocked_ids:
                    continue
                req_type = str(a[7])
                req_value = int(a[8])
                current_value = int(user_stats.get(req_type, 0))
                if current_value < req_value:
                    continue

                cur = db.execute(
                    "INSERT OR IGNORE INTO user_achievements(user_id, achievement_id, unlocked_at) VALUES(?, ?, ?)",
                    (user_id, ach_id, now),
                )
                if int(cur.rowcount or 0) != 1:
                    continue

                reward_points = int(a[5] or 0)
                bonus_points_total += reward_points
                newly.append(
                    {
                        "code": str(a[1]),
                        "title": str(a[2]),
                        "description": str(a[3]),
                        "icon": str(a[4] or "🏆"),
                        "reward_points": reward_points,
                    }
                )

            if not newly:
                break

            unlocked.extend(newly)
            if bonus_points_total > 0:
                xp_after = int(user_stats["experience"]) + int(bonus_points_total)
                lvl_after = self.level_from_xp(xp_after)
                db.execute(
                    "UPDATE users SET balance_points = balance_points + ?, experience = experience + ?, level = ? WHERE user_id = ?",
                    (int(bonus_points_total), int(bonus_points_total), int(lvl_after), user_id),
                )
                try:
                    db.execute(
                        "INSERT INTO experience_history(user_id, amount, source, description, created_at) VALUES(?, ?, ?, ?, ?)",
                        (user_id, int(bonus_points_total), "achievement_points", None, now),
                    )
                except Exception:
                    pass

        return unlocked

    # --- Farm points system ---

    def get_farm_state(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT
                    balance_points,
                    blocked,
                    level,
                    experience,
                    last_farm_time,
                    farm_streak_days,
                    farm_streak_last_date,
                    farm_booster_until,
                    farm_booster_mult,
                    farm_daily_date,
                    farm_daily_points,
                    farm_click_streak
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def count_active_referrals(self, inviter_id: int) -> int:
        """Active referral = referred user not blocked and has completed at least 1 task."""
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM users
                WHERE invited_by = ?
                  AND blocked = 0
                  AND completed_tasks > 0
                """,
                (inviter_id,),
            ).fetchone()
            return int(row["cnt"] or 0) if row else 0

    def try_claim_farm_points(
        self,
        user_id: int,
        *,
        now_ts: int,
        cooldown_seconds: int,
        base_reward: int,
        daily_limit: int,
        referral_bonus_per_active: int,
        streak_bonus_map: dict[int, int],
        booster_multiplier: int,
    ) -> dict:
        """Atomically attempts to claim farm points.

        Returns dict with keys:
          ok(bool), reason(str), wait_seconds(int), awarded(int), streak_days(int), daily_used(int), daily_left(int), booster_active(bool)
        """

        now_ts = int(now_ts)
        cooldown_seconds = int(cooldown_seconds)
        base_reward = int(base_reward)
        daily_limit = int(daily_limit)
        referral_bonus_per_active = int(referral_bonus_per_active)
        booster_multiplier = int(booster_multiplier)
        today = dt.datetime.utcfromtimestamp(now_ts).date()

        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT
                    experience,
                    balance_points,
                    blocked,
                    last_farm_time,
                    farm_streak_days,
                    farm_streak_last_date,
                    farm_booster_until,
                    farm_booster_mult,
                    farm_daily_date,
                    farm_daily_points,
                    farm_click_streak
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}

            if int(row["blocked"] or 0) == 1:
                return {"ok": False, "reason": "blocked"}

            old_xp = int(row["experience"] or 0)
            old_level = self.level_from_xp(old_xp)

            # Farm claim is allowed even if user's balance is negative.
            # (Admin may withdraw points; user can farm back to non-negative.)

            last_farm = int(row["last_farm_time"] or 0)
            elapsed = now_ts - last_farm
            if last_farm and elapsed < cooldown_seconds:
                return {"ok": False, "reason": "cooldown", "wait_seconds": int(cooldown_seconds - elapsed)}

            # Daily limit reset
            daily_date_raw = row["farm_daily_date"]
            daily_points = int(row["farm_daily_points"] or 0)
            if not daily_date_raw or str(daily_date_raw) != str(today):
                daily_points = 0

            if daily_points >= daily_limit:
                return {"ok": False, "reason": "daily_limit", "daily_used": daily_points, "daily_left": 0}

            # Daily streak (days with at least one successful farm)
            streak_days = int(row["farm_streak_days"] or 0)
            streak_last_raw = row["farm_streak_last_date"]
            streak_last_date: dt.date | None
            if streak_last_raw:
                try:
                    streak_last_date = dt.date.fromisoformat(str(streak_last_raw))
                except Exception:
                    streak_last_date = None
            else:
                streak_last_date = None

            if streak_last_date == today:
                new_streak_days = max(1, streak_days) if streak_days else 1
            elif streak_last_date == (today - dt.timedelta(days=1)):
                new_streak_days = (streak_days or 0) + 1
            else:
                # Пропуск дня — начинаем серию заново
                new_streak_days = 1

            # Бонус за серию дней: выдаём один раз в день при достижении порога
            day_streak_bonus = 0
            if streak_last_date != today:
                day_streak_bonus = int(streak_bonus_map.get(int(new_streak_days), 0) or 0)

            # Стрик кликов (успешные фармы подряд)
            click_streak = int(row["farm_click_streak"] or 0)
            # При любом успешном фарме увеличиваем стрик; при долгом перерыве он фактически начнётся с 1
            if streak_last_date is None or streak_last_date < (today - dt.timedelta(days=1)):
                new_click_streak = 1
            else:
                new_click_streak = max(0, click_streak) + 1

            click_bonus = min(6, (new_click_streak // 3) * 2)

            # Мини-бонус "Удача" (2%)
            luck_bonus = 0
            try:
                if random.random() < 0.02:
                    luck_bonus = int(random.randint(3, 7))
            except Exception:
                luck_bonus = 0

            booster_until = int(row["farm_booster_until"] or 0)
            booster_active = booster_until > now_ts
            booster_mult_db = int(row["farm_booster_mult"] or 2)
            booster_mult_db = max(1, booster_mult_db)
            booster_mult = booster_mult_db if booster_active else 1

            # VIP не влияет напрямую на фарм (по новой спецификации)

            # Базовая формула: (base + click_bonus + luck_bonus) * booster + day_streak_bonus
            reward_before_limit = (base_reward + click_bonus + luck_bonus) * int(booster_mult) + int(day_streak_bonus)

            # Cap by daily limit
            daily_left = max(0, daily_limit - daily_points)
            reward = min(reward_before_limit, daily_left)
            if reward <= 0:
                return {"ok": False, "reason": "daily_limit", "daily_used": daily_points, "daily_left": 0}

            daily_points_after = daily_points + reward
            new_xp = old_xp + int(reward)
            new_level = self.level_from_xp(new_xp)
            db.execute(
                """
                UPDATE users
                SET
                    balance_points = balance_points + ?,
                    experience = experience + ?,
                    level = ?,
                    last_farm_time = ?,
                    farm_streak_days = ?,
                    farm_streak_last_date = ?,
                    farm_click_streak = ?,
                    farm_daily_date = ?,
                    farm_daily_points = ?
                WHERE user_id = ?
                """,
                (
                    int(reward),
                    int(reward),
                    int(new_level),
                    int(now_ts),
                    int(new_streak_days),
                    str(today),
                    int(new_click_streak),
                    str(today),
                    int(daily_points_after),
                    user_id,
                ),
            )

            achievements_unlocked: list[dict] = []
            try:
                achievements_unlocked = self._award_achievements_in_conn(db, user_id, now=dt.datetime.utcnow().isoformat())
            except Exception:
                achievements_unlocked = []

            return {
                "ok": True,
                "reason": "ok",
                "awarded": int(reward),
                "old_level": int(old_level),
                "new_level": int(new_level),
                "leveled_up": bool(new_level > old_level),
                "new_title": self.get_level_title(new_level),
                "achievements_unlocked": achievements_unlocked,
                "streak_days": int(new_streak_days),
                "daily_used": int(daily_points_after),
                "daily_left": int(max(0, daily_limit - daily_points_after)),
                "booster_active": bool(booster_active),
                "streak_bonus": int(day_streak_bonus),
                "multiplier": int(booster_mult),
                "click_streak": int(new_click_streak),
                "click_bonus": int(click_bonus),
                "luck_bonus": int(luck_bonus),
            }

    def try_buy_farm_booster(
        self,
        user_id: int,
        *,
        now_ts: int,
        cost_points: int,
        duration_seconds: int,
        multiplier: int = 2,
    ) -> dict:
        now_ts = int(now_ts)
        cost_points = int(cost_points)
        duration_seconds = int(duration_seconds)
        multiplier = max(2, int(multiplier))
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT balance_points, blocked, farm_booster_until FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}
            if int(row["blocked"] or 0) == 1:
                return {"ok": False, "reason": "blocked"}
            balance = int(row["balance_points"] or 0)
            if balance < 0:
                return {"ok": False, "reason": "negative_balance"}

            booster_until = int(row["farm_booster_until"] or 0)
            if booster_until > now_ts:
                return {"ok": False, "reason": "already_active", "booster_until": booster_until}
            if balance < cost_points:
                return {"ok": False, "reason": "insufficient", "balance": balance}

            new_until = now_ts + duration_seconds
            db.execute(
                """
                UPDATE users
                SET balance_points = balance_points - ?, farm_booster_until = ?, farm_booster_mult = ?
                WHERE user_id = ?
                """,
                (int(cost_points), int(new_until), int(multiplier), user_id),
            )
            return {"ok": True, "reason": "ok", "booster_until": int(new_until)}

    def grant_or_refresh_farm_booster(
        self,
        user_id: int,
        *,
        now_ts: int,
        duration_seconds: int,
        multiplier: int,
    ) -> dict:
        now_ts = int(now_ts)
        duration_seconds = int(duration_seconds)
        multiplier = max(2, int(multiplier))
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT blocked, farm_booster_until, farm_booster_mult FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}
            if int(row["blocked"] or 0) == 1:
                return {"ok": False, "reason": "blocked"}

            current_until = int(row["farm_booster_until"] or 0)
            current_mult = int(row["farm_booster_mult"] or 2)

            if current_until > now_ts and current_mult >= multiplier:
                new_until = max(int(current_until), int(now_ts + duration_seconds))
                new_mult = int(current_mult)
            else:
                new_until = int(now_ts + duration_seconds)
                new_mult = max(int(current_mult), int(multiplier))
            db.execute(
                "UPDATE users SET farm_booster_until = ?, farm_booster_mult = ? WHERE user_id = ?",
                (int(new_until), int(new_mult), user_id),
            )
            return {"ok": True, "reason": "ok", "booster_until": int(new_until), "multiplier": int(new_mult)}

    def get_vip_until(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT vip_until FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return int(row[0] or 0) if row else 0

    def is_vip_active(self, user_id: int, *, now_ts: int | None = None) -> bool:
        if now_ts is None:
            now_ts = int(dt.datetime.utcnow().timestamp())
        return self.get_vip_until(user_id) > int(now_ts)

    def extend_vip_until(self, user_id: int, *, now_ts: int, add_seconds: int) -> int:
        now_ts = int(now_ts)
        add_seconds = int(add_seconds)
        with self._lock, self._connect() as db:
            row = db.execute("SELECT vip_until FROM users WHERE user_id = ?", (user_id,)).fetchone()
            current = int(row[0] or 0) if row else 0
            base = max(int(current), int(now_ts))
            new_until = int(base + add_seconds)
            db.execute("UPDATE users SET vip_until = ? WHERE user_id = ?", (int(new_until), user_id))
            return int(new_until)

    def set_custom_title(self, user_id: int, title: str | None) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET custom_title = ? WHERE user_id = ?", (title, user_id))

    def set_nick_color(self, user_id: int, color: str | None) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET nick_color = ? WHERE user_id = ?", (color, user_id))

    def set_emoji_pack(self, user_id: int, pack: str | None) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET emoji_pack = ? WHERE user_id = ?", (pack, user_id))

    def get_user_level_info(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                "SELECT level, experience, balance_points, balance_coins, completed_tasks, referrals_count, blocked, vip_until, mines_luck_boosts, mines_insurance_block, custom_title, nick_color, emoji_pack FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not r:
                return None

            xp = int(r[1] or 0)
            level = self.level_from_xp(xp)
            balance = int(r[2] or 0)
            balance_coins = int(r[3] or 0)
            tasks = int(r[4] or 0)
            refs = int(r[5] or 0)
            blocked = int(r[6] or 0)
            vip_until = int(r[7] or 0)
            vip_active = vip_until > int(dt.datetime.utcnow().timestamp())
            mines_luck_boosts = int(r[8] or 0)
            mines_insurance_block = int(r[9] or 0)
            custom_title = r[10]
            nick_color = r[11]
            emoji_pack = r[12]

            next_thr = self.next_xp_threshold(level)
            if next_thr is None:
                xp_in_level = xp
                xp_needed_in_level = 1
                xp_for_next = 0
                progress_percent = 100.0
            else:
                start_thr = 0
                if level == 2:
                    start_thr = 1_000
                elif level == 3:
                    start_thr = 5_000
                elif level >= 4:
                    start_thr = 20_000
                xp_in_level = max(0, xp - start_thr)
                xp_needed_in_level = max(1, next_thr - start_thr)
                xp_for_next = max(0, next_thr - xp)
                progress_percent = round((xp_in_level / xp_needed_in_level) * 100, 1)

            filled = int((progress_percent / 100) * 10)
            filled = max(0, min(10, filled))
            progress_bar = "█" * filled + "░" * (10 - filled)

            return {
                "user_id": user_id,
                "level": int(level),
                "title": self.get_level_title(level),
                "xp": int(xp),
                "balance_points": balance,
                "balance_coins": int(balance_coins),
                "completed_tasks": tasks,
                "referrals_count": refs,
                "blocked": blocked,
                "vip_until": int(vip_until),
                "vip_active": bool(vip_active),
                "custom_title": str(custom_title) if custom_title else None,
                "nick_color": str(nick_color) if nick_color else None,
                "emoji_pack": str(emoji_pack) if emoji_pack else None,
                "mines_luck_boosts": int(mines_luck_boosts),
                "mines_insurance_block": int(mines_insurance_block),
                "xp_in_level": int(xp_in_level),
                "xp_needed_in_level": int(xp_needed_in_level),
                "xp_for_next": int(xp_for_next),
                "progress_bar": progress_bar,
                "progress_percent": float(progress_percent),
            }

    def get_mines_luck_boosts(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            r = db.execute("SELECT mines_luck_boosts FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return int(r[0] or 0) if r else 0

    def try_buy_mines_luck_boost(self, user_id: int, *, cost_points: int = 30) -> dict:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT balance_points, blocked, mines_luck_boosts FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}
            if int(row[1] or 0) == 1:
                return {"ok": False, "reason": "blocked"}
            balance = int(row[0] or 0)
            if balance < int(cost_points):
                return {"ok": False, "reason": "insufficient", "balance": balance}

            db.execute(
                "UPDATE users SET balance_points = balance_points - ?, mines_luck_boosts = mines_luck_boosts + 1 WHERE user_id = ?",
                (int(cost_points), user_id),
            )
            return {"ok": True, "reason": "ok", "cost": int(cost_points)}

    def consume_mines_luck_boost(self, user_id: int) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT mines_luck_boosts FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return False
            cnt = int(row[0] or 0)
            if cnt <= 0:
                return False
            db.execute("UPDATE users SET mines_luck_boosts = mines_luck_boosts - 1 WHERE user_id = ?", (user_id,))
            return True

    # --- Insurance (global) ---

    def get_insurance_state(self, user_id: int) -> dict:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT insurance_balance, insurance_next, insurance_block, insurance_trial_used FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"balance": 0, "next": 0, "block": 0, "trial_used": 0}
            return {
                "balance": int(row[0] or 0),
                "next": int(row[1] or 0),
                "block": int(row[2] or 0),
                "trial_used": int(row[3] or 0),
            }

    def get_insurance_balance(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT insurance_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return int(row[0] or 0) if row else 0

    def add_insurance_balance(self, user_id: int, delta: int) -> int:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE users SET insurance_balance = MAX(0, insurance_balance + ?) WHERE user_id = ?",
                (int(delta), user_id),
            )
            row = db.execute("SELECT insurance_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return int(row[0] or 0) if row else 0

    def try_claim_insurance_trial(self, user_id: int, *, qty: int = 5) -> dict:
        qty = int(qty)
        if qty <= 0:
            return {"ok": False, "reason": "bad_qty"}
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT insurance_trial_used FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}
            if int(row[0] or 0) == 1:
                return {"ok": False, "reason": "already_used"}
            db.execute(
                "UPDATE users SET insurance_trial_used = 1, insurance_balance = insurance_balance + ? WHERE user_id = ?",
                (qty, user_id),
            )
            bal = db.execute("SELECT insurance_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return {"ok": True, "reason": "ok", "balance": int(bal[0] or 0) if bal else 0}

    def set_insurance_next(self, user_id: int, enabled: bool) -> dict:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT insurance_balance, insurance_block, insurance_next FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}
            bal = int(row[0] or 0)
            blocked = int(row[1] or 0)
            cur = int(row[2] or 0)
            want = 1 if enabled else 0
            if want == 1:
                if blocked == 1:
                    return {"ok": False, "reason": "blocked", "balance": bal, "next": cur, "block": blocked}
                if bal <= 0:
                    return {"ok": False, "reason": "no_insurance", "balance": bal, "next": cur, "block": blocked}

            db.execute("UPDATE users SET insurance_next = ? WHERE user_id = ?", (want, user_id))
            return {"ok": True, "reason": "ok", "balance": bal, "next": want, "block": blocked}

    def toggle_insurance_next(self, user_id: int) -> dict:
        st = self.get_insurance_state(user_id)
        enabled = bool(int(st.get("next") or 0))
        return self.set_insurance_next(user_id, not enabled)

    def insurance_clear_block_if_needed(self, user_id: int) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET insurance_block = 0 WHERE user_id = ? AND insurance_block = 1", (user_id,))

    def insurance_try_refund_on_loss(
        self,
        user_id: int,
        *,
        stake: int,
        refund_pct: int,
        source: str = "",
    ) -> dict:
        """Apply insurance refund on a losing bet if armed.

        Consumes exactly 1 insurance and sets block=1 + next=0 atomically.
        Returns {ok, refund, pct, balance_left}.
        """
        stake = int(stake)
        refund_pct = int(refund_pct)
        if stake <= 0 or refund_pct <= 0:
            return {"ok": False, "reason": "bad_args"}
        refund = int((stake * refund_pct) // 100)
        refund = max(0, refund)
        if refund <= 0:
            return {"ok": False, "reason": "zero"}

        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT balance_points, insurance_balance, insurance_next, insurance_block FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}
            ins_bal = int(row[1] or 0)
            ins_next = int(row[2] or 0)
            ins_block = int(row[3] or 0)
            if ins_next != 1 or ins_block == 1 or ins_bal <= 0:
                return {"ok": False, "reason": "not_armed", "balance_left": ins_bal, "next": ins_next, "block": ins_block}

            cur = db.execute(
                "SELECT insurance_balance FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not cur or int(cur[0] or 0) <= 0:
                return {"ok": False, "reason": "no_insurance"}

            db.execute(
                """
                UPDATE users
                SET balance_points = balance_points + ?,
                    insurance_balance = insurance_balance - 1,
                    insurance_next = 0,
                    insurance_block = 1
                WHERE user_id = ?
                  AND insurance_next = 1
                  AND insurance_block = 0
                  AND insurance_balance > 0
                """,
                (refund, user_id),
            )

            left_row = db.execute(
                "SELECT insurance_balance, insurance_next, insurance_block FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            left = int(left_row[0] or 0) if left_row else 0
            return {
                "ok": True,
                "reason": "ok",
                "refund": int(refund),
                "pct": int(refund_pct),
                "balance_left": left,
                "next": int(left_row[1] or 0) if left_row else 0,
                "block": int(left_row[2] or 0) if left_row else 0,
                "source": str(source or ""),
            }

    def insurance_try_refund_on_loss_reserved(
        self,
        user_id: int,
        *,
        stake: int,
        refund_pct: int,
        source: str = "",
    ) -> dict:
        """Apply insurance refund on a losing bet for a game that already reserved insurance.

        Consumes exactly 1 insurance and sets block=1 atomically.
        Does NOT require insurance_next=1 (since it is cleared at game start).
        Returns {ok, refund, pct, balance_left}.
        """
        stake = int(stake)
        refund_pct = int(refund_pct)
        if stake <= 0 or refund_pct <= 0:
            return {"ok": False, "reason": "bad_args"}
        refund = int((stake * refund_pct) // 100)
        refund = max(0, refund)
        if refund <= 0:
            return {"ok": False, "reason": "zero"}

        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT insurance_balance, insurance_block FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}
            ins_bal = int(row[0] or 0)
            ins_block = int(row[1] or 0)
            if ins_block == 1 or ins_bal <= 0:
                return {"ok": False, "reason": "not_available", "balance_left": ins_bal, "block": ins_block}

            db.execute(
                """
                UPDATE users
                SET balance_points = balance_points + ?,
                    insurance_balance = insurance_balance - 1,
                    insurance_next = 0,
                    insurance_block = 1
                WHERE user_id = ?
                  AND insurance_block = 0
                  AND insurance_balance > 0
                """,
                (refund, user_id),
            )

            left_row = db.execute(
                "SELECT insurance_balance, insurance_next, insurance_block FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            left = int(left_row[0] or 0) if left_row else 0
            return {
                "ok": True,
                "reason": "ok",
                "refund": int(refund),
                "pct": int(refund_pct),
                "balance_left": left,
                "next": int(left_row[1] or 0) if left_row else 0,
                "block": int(left_row[2] or 0) if left_row else 0,
                "source": str(source or ""),
            }

    def get_mines_insurance_block(self, user_id: int) -> bool:
        # Backward-compat: map legacy mines insurance fields to the global insurance system.
        with self._lock, self._connect() as db:
            row = db.execute("SELECT insurance_block FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return bool(int(row[0] or 0)) if row else False

    def set_mines_insurance_block(self, user_id: int, blocked: bool) -> None:
        # Backward-compat: map legacy mines insurance fields to the global insurance system.
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET insurance_block = ? WHERE user_id = ?", (1 if blocked else 0, user_id))

    def get_mines_insurance_next(self, user_id: int) -> bool:
        # Backward-compat: map legacy mines insurance fields to the global insurance system.
        with self._lock, self._connect() as db:
            row = db.execute("SELECT insurance_next FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return bool(int(row[0] or 0)) if row else False

    def set_mines_insurance_next(self, user_id: int, enabled: bool) -> None:
        # Backward-compat: map legacy mines insurance fields to the global insurance system.
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET insurance_next = ? WHERE user_id = ?", (1 if enabled else 0, user_id))

    def add_experience_from_source(self, user_id: int, source: str, *, description: str | None = None, amount: int | None = None) -> dict:
        # XP is now derived from earned points; do not add standalone XP.
        return {
            "success": True,
            "exp_added": 0,
            "leveled_up": False,
            "old_level": None,
            "new_level": None,
            "rewards": [],
            "total_reward_points": 0,
            "achievements_unlocked": [],
        }

    def add_experience(self, user_id: int, amount: int, source: str, *, description: str | None = None) -> dict:
        return self.add_experience_from_source(user_id, source, description=description, amount=amount)

    def get_leaderboard(self, *, limit: int = 10) -> list[dict]:
        """Backward-compatible: top by experience (level)."""
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT user_id, username, experience, balance_points FROM users WHERE blocked = 0 ORDER BY experience DESC, balance_points DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for i, r in enumerate(rows, 1):
                xp = int(r[2] or 0)
                lvl = self.level_from_xp(xp)
                out.append(
                    {
                        "pos": i,
                        "user_id": int(r[0]),
                        "username": r[1],
                        "level": int(lvl),
                        "experience": xp,
                        "balance_points": int(r[3] or 0),
                        "rank": self.rank_for_level(lvl),
                    }
                )
            return out

    def get_leaderboard_by_level(self, *, limit: int = 20) -> list[dict]:
        limit = max(1, int(limit))
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT user_id, username, experience, balance_points FROM users WHERE blocked = 0 ORDER BY experience DESC, balance_points DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for i, r in enumerate(rows, 1):
                xp = int(r[2] or 0)
                lvl = self.level_from_xp(xp)
                out.append(
                    {
                        "pos": i,
                        "user_id": int(r[0]),
                        "username": r[1],
                        "level": int(lvl),
                        "experience": xp,
                        "balance_points": int(r[3] or 0),
                        "rank": self.rank_for_level(lvl),
                    }
                )
            return out

    def get_mining_leaderboard(self, *, limit: int = 10) -> list[dict]:
        limit = max(1, int(limit))
        with self._lock, self._connect() as db:
            # Use lifetime total mined BTC for leaderboard so selling doesn't reset ranks.
            rows = db.execute(
                "SELECT user_id, username, mining_total_btc FROM users WHERE blocked = 0 ORDER BY mining_total_btc DESC, experience DESC LIMIT ?",
                (limit,),
            ).fetchall()
            out: list[dict] = []
            for r in rows:
                out.append({"user_id": int(r[0]), "username": r[1], "mining_btc": float(r[2] or 0)})
            return out

    def get_mining_rank_position(self, user_id: int) -> dict | None:
        user_id = int(user_id)
        with self._lock, self._connect() as db:
            # Use lifetime total mined BTC to compute rank position
            row = db.execute(
                "SELECT mining_total_btc, blocked, username FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            if int(row[1] or 0) != 0:
                return None
            me_btc = float(row[0] or 0)
            uname = row[2]
            pos_row = db.execute(
                "SELECT COUNT(*) FROM users WHERE blocked = 0 AND (mining_total_btc > ?)",
                (float(me_btc),),
            ).fetchone()
            pos = int(pos_row[0] or 0) + 1 if pos_row else 1
            return {"position": pos, "mining_btc": float(me_btc), "username": uname}

    def get_leaderboard_by_balance(self, *, limit: int = 20) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT user_id, username, experience, balance_points FROM users WHERE blocked = 0 ORDER BY balance_points DESC, experience DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for i, r in enumerate(rows, 1):
                xp = int(r[2] or 0)
                lvl = self.level_from_xp(xp)
                out.append(
                    {
                        "pos": i,
                        "user_id": int(r[0]),
                        "username": r[1],
                        "level": int(lvl),
                        "experience": xp,
                        "balance_points": int(r[3] or 0),
                        "rank": self.rank_for_level(lvl),
                    }
                )
            return out

    def get_leaderboard_by_duel_mmr(self, *, limit: int = 20) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT user_id, username, duel_mmr, duel_wins, duel_losses, duel_games FROM users WHERE blocked = 0 ORDER BY duel_mmr DESC, duel_wins DESC, duel_games DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for i, r in enumerate(rows, 1):
                wins = int(r[3] or 0)
                losses = int(r[4] or 0)
                total = int(r[5] or 0)
                winrate = (wins / total * 100.0) if total > 0 else 0.0
                out.append(
                    {
                        "pos": i,
                        "user_id": int(r[0]),
                        "username": r[1],
                        "mmr": int(r[2] or 1000),
                        "wins": wins,
                        "losses": losses,
                        "total": total,
                        "winrate": float(winrate),
                    }
                )
            return out

    def get_leaderboard_by_referrals(self, *, limit: int = 20) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT user_id, username, referrals_count, experience FROM users WHERE blocked = 0 ORDER BY referrals_count DESC, experience DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for i, r in enumerate(rows, 1):
                out.append(
                    {
                        "pos": i,
                        "user_id": int(r[0]),
                        "username": r[1],
                        "referrals_count": int(r[2] or 0),
                        "experience": int(r[3] or 0),
                    }
                )
            return out

    def get_user_rank_position_by_level(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT experience FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return None
            xp = int(row[0] or 0)
            lvl = self.level_from_xp(xp)
            better = db.execute(
                "SELECT COUNT(*) FROM users WHERE blocked = 0 AND (experience > ?)",
                (xp,),
            ).fetchone()
            pos = int(better[0] or 0) + 1
            return {"position": pos, "level": int(lvl), "rank": self.rank_for_level(lvl)}

    def get_user_rank_position_by_balance(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT balance_points, experience FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return None
            bal = int(row[0] or 0)
            xp = int(row[1] or 0)
            better = db.execute(
                "SELECT COUNT(*) FROM users WHERE blocked = 0 AND (balance_points > ?)",
                (bal,),
            ).fetchone()
            pos = int(better[0] or 0) + 1
            lvl = self.level_from_xp(xp)
            return {"position": pos, "balance_points": bal, "level": int(lvl), "rank": self.rank_for_level(lvl)}

    def get_user_rank_position_by_duel_mmr(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT duel_mmr FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return None
            mmr = int(row[0] or 1000)
            better = db.execute(
                "SELECT COUNT(*) FROM users WHERE blocked = 0 AND (duel_mmr > ?)",
                (mmr,),
            ).fetchone()
            pos = int(better[0] or 0) + 1
            return {"position": pos, "mmr": mmr}

    def get_user_rank_position_by_referrals(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT referrals_count FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return None
            refs = int(row[0] or 0)
            better = db.execute(
                "SELECT COUNT(*) FROM users WHERE blocked = 0 AND (referrals_count > ?)",
                (refs,),
            ).fetchone()
            pos = int(better[0] or 0) + 1
            return {"position": pos, "referrals_count": refs}

    # --- Stats helpers (commands /stats, /top) ---

    def user_exists(self, user_id: int) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT 1 FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            return bool(row)

    def get_user_stats_snapshot(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT
                    user_id,
                    username,
                    created_at,
                    balance_points,
                    completed_tasks,
                    referrals_count,
                    level,
                    experience,
                    farm_streak_days,
                    duel_mmr,
                    duel_games,
                    duel_wins,
                    duel_losses,
                    duel_best_streak,
                    duel_rank
                FROM users
                WHERE user_id = ?
                """,
                (int(user_id),),
            ).fetchone()
            return dict(row) if row else None

    def get_user_total_earned(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM experience_history WHERE user_id = ? AND amount > 0",
                (int(user_id),),
            ).fetchone()
            return int(row[0] or 0) if row else 0

    def get_user_total_withdrawn_rub(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(amount_rub), 0) FROM withdrawals WHERE user_id = ? AND status = 'paid'",
                (int(user_id),),
            ).fetchone()
            return int(row[0] or 0) if row else 0

    def get_user_games_count(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT COALESCE(duel_games, 0), COALESCE(wheel_rolls, 0) FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return 0
            return int(row[0] or 0) + int(row[1] or 0)

    def get_total_achievements_count(self) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT COUNT(*) FROM achievements WHERE hidden = 0").fetchone()
            return int(row[0] or 0) if row else 0

    # --- Duels (PvP) ---

    def create_duel(self, creator_id: int, *, stake: int, game_type: str, is_bot: bool = False, is_rematch: bool = False) -> dict:
        stake = int(stake)
        game_type = str(game_type)
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            # generate unique short code
            import random
            import string

            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            while True:
                code = "DUEL" + "".join(random.choice(alphabet) for _ in range(5))
                row = db.execute("SELECT duel_id FROM duels WHERE code = ?", (code,)).fetchone()
                if not row:
                    break

            db.execute(
                "INSERT INTO duels(code, creator_id, stake, game_type, status, is_bot, is_rematch, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (code, int(creator_id), stake, game_type, "waiting", 1 if is_bot else 0, 1 if is_rematch else 0, now),
            )
            duel_id = db.execute("SELECT duel_id FROM duels WHERE code = ?", (code,)).fetchone()[0]
            return {"duel_id": int(duel_id), "code": str(code), "stake": stake, "game_type": game_type}

    def duel_is_waiting(self, duel_id: int) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT status FROM duels WHERE duel_id = ?", (int(duel_id),)).fetchone()
            return bool(row and str(row[0]) == "waiting")

    def get_duel_by_id(self, duel_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT duel_id, code, creator_id, opponent_id, stake, game_type, status, is_bot, creator_choice, opponent_choice, creator_roll, opponent_roll, state_json, winner_id, created_at, joined_at, resolved_at, is_rematch FROM duels WHERE duel_id = ?",
                (int(duel_id),),
            ).fetchone()
            if not row:
                return None
            return {
                "duel_id": int(row[0]),
                "code": str(row[1]),
                "creator_id": int(row[2]),
                "opponent_id": int(row[3]) if row[3] is not None else None,
                "stake": int(row[4]),
                "game_type": str(row[5]),
                "status": str(row[6]),
                "is_bot": int(row[7] or 0),
                "creator_choice": row[8],
                "opponent_choice": row[9],
                "creator_roll": int(row[10]) if row[10] is not None else None,
                "opponent_roll": int(row[11]) if row[11] is not None else None,
                "state_json": (str(row[12]) if row[12] is not None else None),
                "winner_id": int(row[13]) if row[13] is not None else None,
                "created_at": str(row[14]),
                "joined_at": str(row[15]) if row[15] is not None else None,
                "resolved_at": str(row[16]) if row[16] is not None else None,
                "is_rematch": int(row[17] or 0),
            }

    def get_duel_by_code(self, code: str) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT duel_id, code, creator_id, opponent_id, stake, game_type, status, is_bot, creator_choice, opponent_choice, creator_roll, opponent_roll, state_json, winner_id, created_at, joined_at, resolved_at, is_rematch FROM duels WHERE code = ?",
                (code,),
            ).fetchone()
            if not row:
                return None
            return {
                "duel_id": int(row[0]),
                "code": str(row[1]),
                "creator_id": int(row[2]),
                "opponent_id": int(row[3]) if row[3] is not None else None,
                "stake": int(row[4]),
                "game_type": str(row[5]),
                "status": str(row[6]),
                "is_bot": int(row[7] or 0),
                "creator_choice": row[8],
                "opponent_choice": row[9],
                "creator_roll": int(row[10]) if row[10] is not None else None,
                "opponent_roll": int(row[11]) if row[11] is not None else None,
                "state_json": (str(row[12]) if row[12] is not None else None),
                "winner_id": int(row[13]) if row[13] is not None else None,
                "created_at": str(row[14]),
                "joined_at": str(row[15]) if row[15] is not None else None,
                "resolved_at": str(row[16]) if row[16] is not None else None,
                "is_rematch": int(row[17] or 0),
            }

    def set_duel_opponent(self, duel_id: int, opponent_id: int) -> bool:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            cur = db.execute(
                "UPDATE duels SET opponent_id = ?, status = 'active', joined_at = ?, last_action_at = ? WHERE duel_id = ? AND status = 'waiting'",
                (int(opponent_id), now, now, int(duel_id)),
            )
            return int(getattr(cur, "rowcount", 0) or 0) > 0

    def join_waiting_duel_atomic(self, duel_id: int, *, user_id: int) -> dict:
        """Atomically join a waiting duel and deduct stake.

        Prevents race conditions and avoids stake loss if the bot crashes mid-flow.
        Returns:
          ok: bool
          reason: str (if not ok)
          duel: dict (if ok)
          balance: int|None (if insufficient)
        """
        did = int(duel_id)
        uid = int(user_id)
        now = dt.datetime.utcnow().isoformat()

        with self._lock, self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")

                row = db.execute(
                    "SELECT status, opponent_id, stake, is_bot, creator_id, game_type FROM duels WHERE duel_id = ?",
                    (did,),
                ).fetchone()
                if not row:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "not_found"}

                status = str(row[0] or "")
                opponent_id = int(row[1]) if row[1] is not None else None
                stake = int(row[2] or 0)
                is_bot = int(row[3] or 0)
                creator_id = int(row[4] or 0)
                game_type = str(row[5] or "")

                if status != "waiting" or opponent_id is not None:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "unavailable"}
                if stake <= 0:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "bad_stake"}

                # Deduct stake (must have enough balance)
                cur = db.execute(
                    "UPDATE users SET balance_points = balance_points - ? WHERE user_id = ? AND balance_points >= ?",
                    (stake, uid, stake),
                )
                if int(getattr(cur, "rowcount", 0) or 0) <= 0:
                    bal_row = db.execute("SELECT balance_points FROM users WHERE user_id = ?", (uid,)).fetchone()
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "no_balance", "balance": (int(bal_row[0] or 0) if bal_row else 0)}

                # Claim duel
                cur2 = db.execute(
                    "UPDATE duels SET opponent_id = ?, status = 'active', joined_at = ?, last_action_at = ? WHERE duel_id = ? AND status = 'waiting' AND opponent_id IS NULL",
                    (uid, now, now, did),
                )
                if int(getattr(cur2, "rowcount", 0) or 0) <= 0:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "unavailable"}

                db.execute("COMMIT")
                return {
                    "ok": True,
                    "duel": {
                        "duel_id": did,
                        "stake": stake,
                        "is_bot": is_bot,
                        "creator_id": creator_id,
                        "opponent_id": uid,
                        "game_type": game_type,
                    },
                }
            except Exception:
                try:
                    db.execute("ROLLBACK")
                except Exception:
                    pass
                return {"ok": False, "reason": "error"}

    def cancel_waiting_duel(self, duel_id: int) -> bool:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            cur = db.execute(
                "UPDATE duels SET status = 'cancelled', resolved_at = ? WHERE duel_id = ? AND status = 'waiting'",
                (now, int(duel_id)),
            )
            ok = int(getattr(cur, "rowcount", 0) or 0) > 0
            if not ok:
                return False

            # Refund creator stake only after successful cancellation
            row = db.execute("SELECT creator_id, stake FROM duels WHERE duel_id = ?", (int(duel_id),)).fetchone()
            if not row:
                return True
            creator_id = int(row[0])
            stake = int(row[1] or 0)
            if stake > 0:
                try:
                    db.execute("UPDATE users SET balance_points = balance_points + ? WHERE user_id = ?", (stake, creator_id))
                except Exception:
                    pass
            return True

    def list_waiting_duels_by_creator(self, creator_id: int, *, limit: int = 50) -> list[dict]:
        """List waiting (public) duels created by a user (non-bot)."""
        with self._lock, self._connect() as db:
            rows = db.execute(
                """
                SELECT duel_id, stake, game_type, is_bot, creator_id, created_at
                FROM duels
                WHERE status = 'waiting' AND creator_id = ? AND (is_bot = 0)
                ORDER BY duel_id DESC
                LIMIT ?
                """,
                (int(creator_id), int(limit)),
            ).fetchall()
            out: list[dict] = []
            for r in rows:
                out.append(
                    {
                        "duel_id": int(r[0]),
                        "stake": int(r[1] or 0),
                        "game_type": str(r[2] or ""),
                        "is_bot": int(r[3] or 0),
                        "creator_id": int(r[4] or 0),
                        "created_at": str(r[5] or ""),
                        "status": "waiting",
                    }
                )
            return out

    def expire_stale_active_duels(self, *, idle_seconds: int) -> list[dict]:
        """Expire active duels that have been idle too long.

        Policy: mark as finished (no winner) and refund stakes to all paid players.
        Returns a list of expired duels with players for notifications.
        """
        now_dt = dt.datetime.utcnow()
        now = now_dt.isoformat()
        cutoff = (now_dt - dt.timedelta(seconds=int(idle_seconds))).isoformat()

        expired: list[dict] = []
        with self._lock, self._connect() as db:
            try:
                rows = db.execute(
                    """
                    SELECT duel_id, creator_id, opponent_id, stake, is_bot, game_type
                    FROM duels
                    WHERE status = 'active'
                      AND COALESCE(last_action_at, joined_at, created_at) < ?
                    ORDER BY duel_id ASC
                    LIMIT 50
                    """,
                    (cutoff,),
                ).fetchall()
            except Exception:
                rows = []

            for r in rows:
                did = int(r[0])
                creator_id = int(r[1] or 0)
                opponent_id = int(r[2]) if r[2] is not None else None
                stake = int(r[3] or 0)
                is_bot = int(r[4] or 0)
                game_type = str(r[5] or "")
                if stake <= 0:
                    continue

                cur = db.execute(
                    "UPDATE duels SET status = 'finished', winner_id = NULL, resolved_at = ? WHERE duel_id = ? AND status = 'active'",
                    (now, did),
                )
                if int(getattr(cur, "rowcount", 0) or 0) <= 0:
                    continue

                if is_bot == 1 and creator_id == 0:
                    if opponent_id is not None:
                        db.execute(
                            "UPDATE users SET balance_points = balance_points + ? WHERE user_id = ?",
                            (stake, int(opponent_id)),
                        )
                else:
                    db.execute(
                        "UPDATE users SET balance_points = balance_points + ? WHERE user_id = ?",
                        (stake, int(creator_id)),
                    )
                    if opponent_id is not None:
                        db.execute(
                            "UPDATE users SET balance_points = balance_points + ? WHERE user_id = ?",
                            (stake, int(opponent_id)),
                        )

                expired.append(
                    {
                        "duel_id": did,
                        "creator_id": creator_id,
                        "opponent_id": opponent_id,
                        "stake": stake,
                        "is_bot": is_bot,
                        "game_type": game_type,
                    }
                )

        return expired

    def list_open_duels(self, *, limit: int = 10) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT duel_id, stake, game_type, is_bot, created_at FROM duels WHERE status = 'waiting' ORDER BY duel_id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for r in rows:
                out.append(
                    {
                        "duel_id": int(r[0]),
                        "stake": int(r[1]),
                        "game_type": str(r[2]),
                        "is_bot": int(r[3] or 0),
                        "created_at": str(r[4]),
                    }
                )
            return out

    def list_waiting_duels_admin(self, *, limit: int = 30, offset: int = 0) -> list[dict]:
        """Admin listing: all waiting duels (players + bots), newest first."""
        limit = max(1, int(limit))
        offset = max(0, int(offset))
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT duel_id, stake, game_type, is_bot, creator_id, created_at FROM duels WHERE status = 'waiting' ORDER BY duel_id DESC LIMIT ? OFFSET ?",
                (int(limit), int(offset)),
            ).fetchall()
            out: list[dict] = []
            for r in rows or []:
                out.append(
                    {
                        "duel_id": int(r[0]),
                        "stake": int(r[1] or 0),
                        "game_type": str(r[2] or ""),
                        "is_bot": int(r[3] or 0),
                        "creator_id": int(r[4] or 0),
                        "created_at": str(r[5] or ""),
                    }
                )
            return out

    def count_waiting_duels(self) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT COUNT(*) FROM duels WHERE status = 'waiting'").fetchone()
            return int(row[0] or 0) if row else 0

    def get_or_create_dialog(self, *, user_id: int, admin_id: int, now_ts: int) -> int:
        """Return existing non-closed dialog id for user, or create new initiated dialog."""
        user_id = int(user_id)
        admin_id = int(admin_id)
        now_ts = int(now_ts)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT id FROM active_dialogs WHERE user_id = ? AND status != 'closed' ORDER BY last_message_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if row:
                did = int(row[0] or 0)
                try:
                    db.execute(
                        "UPDATE active_dialogs SET admin_id = ?, last_message_at = ? WHERE id = ?",
                        (admin_id, now_ts, did),
                    )
                except Exception:
                    pass
                return did

            cur = db.execute(
                "INSERT INTO active_dialogs(user_id, admin_id, status, created_at, last_message_at) VALUES(?, ?, 'initiated', ?, ?)",
                (user_id, admin_id, now_ts, now_ts),
            )
            return int(cur.lastrowid or 0)

    def get_open_dialog_id(self, *, user_id: int) -> int | None:
        """Return latest non-closed dialog id for user, or None."""
        user_id = int(user_id)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT id FROM active_dialogs WHERE user_id = ? AND status != 'closed' ORDER BY last_message_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            try:
                did = int(row[0] or 0)
            except Exception:
                did = 0
            return did if did > 0 else None

    def get_dialog(self, dialog_id: int) -> dict | None:
        dialog_id = int(dialog_id)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT id, user_id, admin_id, status, created_at, last_message_at, closed_at FROM active_dialogs WHERE id = ?",
                (dialog_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": int(row[0]),
                "user_id": int(row[1]),
                "admin_id": int(row[2]),
                "status": str(row[3] or ""),
                "created_at": int(row[4] or 0),
                "last_message_at": int(row[5] or 0),
                "closed_at": int(row[6] or 0) if row[6] is not None else None,
            }

    def set_dialog_status(self, *, dialog_id: int, status: str, now_ts: int) -> None:
        dialog_id = int(dialog_id)
        status = str(status)
        now_ts = int(now_ts)
        with self._lock, self._connect() as db:
            if status == "closed":
                db.execute(
                    "UPDATE active_dialogs SET status = 'closed', last_message_at = ?, closed_at = ? WHERE id = ?",
                    (now_ts, now_ts, dialog_id),
                )
            else:
                db.execute(
                    "UPDATE active_dialogs SET status = ?, last_message_at = ? WHERE id = ?",
                    (status, now_ts, dialog_id),
                )

    def add_dialog_message(
        self,
        *,
        dialog_id: int,
        sender_type: str,
        sender_id: int,
        message_text: str,
        sent_at: int,
    ) -> int:
        dialog_id = int(dialog_id)
        sender_type = str(sender_type)
        sender_id = int(sender_id)
        message_text = str(message_text)
        sent_at = int(sent_at)
        with self._lock, self._connect() as db:
            cur = db.execute(
                "INSERT INTO dialog_messages(dialog_id, sender_type, sender_id, message_text, sent_at) VALUES(?, ?, ?, ?, ?)",
                (dialog_id, sender_type, sender_id, message_text, sent_at),
            )
            try:
                db.execute(
                    "UPDATE active_dialogs SET last_message_at = ?, status = 'active' WHERE id = ? AND status != 'closed'",
                    (sent_at, dialog_id),
                )
            except Exception:
                pass
            return int(cur.lastrowid or 0)

    def list_dialog_messages(self, *, dialog_id: int, limit: int = 5) -> list[dict]:
        dialog_id = int(dialog_id)
        limit = max(1, int(limit))
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT sender_type, sender_id, message_text, sent_at FROM dialog_messages WHERE dialog_id = ? ORDER BY sent_at DESC, id DESC LIMIT ?",
                (dialog_id, int(limit)),
            ).fetchall()
            out: list[dict] = []
            for r in rows or []:
                out.append(
                    {
                        "sender_type": str(r[0] or ""),
                        "sender_id": int(r[1] or 0),
                        "message_text": str(r[2] or ""),
                        "sent_at": int(r[3] or 0),
                    }
                )
            return out

    def list_open_server_duels(self, *, limit: int = 10) -> list[dict]:
        """List duels created by the admin duel server pool.

        Pool duels are identified by status='waiting' and creator_id=0.
        (Some legacy rows may have is_bot=0, so we do not rely on is_bot here.)
        """
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT duel_id, stake, game_type, is_bot, created_at FROM duels WHERE status = 'waiting' AND creator_id = 0 ORDER BY duel_id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for r in rows:
                out.append(
                    {
                        "duel_id": int(r[0]),
                        "stake": int(r[1]),
                        "game_type": str(r[2]),
                        "is_bot": int(r[3] or 0),
                        "created_at": str(r[4]),
                    }
                )
            return out

    def list_open_server_duels_admin(self, *, limit: int = 30, offset: int = 0) -> list[dict]:
        """Admin listing of server duels (bot pool), waiting only, newest first."""
        limit = max(1, int(limit))
        offset = max(0, int(offset))
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT duel_id, stake, game_type, created_at FROM duels WHERE status = 'waiting' AND creator_id = 0 ORDER BY duel_id DESC LIMIT ? OFFSET ?",
                (int(limit), int(offset)),
            ).fetchall()
            out: list[dict] = []
            for r in rows or []:
                out.append(
                    {
                        "duel_id": int(r[0]),
                        "stake": int(r[1] or 0),
                        "game_type": str(r[2] or ""),
                        "created_at": str(r[3] or ""),
                    }
                )
            return out

    def delete_open_server_duel(self, duel_id: int) -> bool:
        """Delete a waiting server duel from the pool. Returns True if deleted."""
        with self._lock, self._connect() as db:
            cur = db.execute(
                "DELETE FROM duels WHERE duel_id = ? AND status = 'waiting' AND creator_id = 0",
                (int(duel_id),),
            )
            return bool(cur.rowcount and int(cur.rowcount) > 0)

    def delete_all_open_server_duels(self) -> int:
        """Delete all waiting server duels from the pool. Returns count deleted."""
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM duels WHERE status = 'waiting' AND creator_id = 0")
            try:
                row = db.execute("SELECT changes()").fetchone()
                return int(row[0] or 0) if row else 0
            except Exception:
                return 0

    def list_open_public_duels(self, *, limit: int = 10) -> list[dict]:
        """List all waiting duels that могут быть доступны другим игрокам.

        Включает как серверные дуэли (creator_id = 0, is_bot = 1), так и обычные
        дуэли между игроками, которые ещё ждут соперника.
        """
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT duel_id, stake, game_type, is_bot, creator_id, created_at FROM duels WHERE status = 'waiting' ORDER BY duel_id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for r in rows:
                out.append(
                    {
                        "duel_id": int(r[0]),
                        "stake": int(r[1]),
                        "game_type": str(r[2]),
                        "is_bot": int(r[3] or 0),
                        "creator_id": int(r[4] or 0),
                        "created_at": str(r[5]),
                    }
                )
            return out

    def count_open_duels(self) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT COUNT(*) FROM duels WHERE status = 'waiting'").fetchone()
            return int(row[0] or 0) if row else 0

    def count_open_server_duels(self) -> int:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM duels WHERE status = 'waiting' AND creator_id = 0"
            ).fetchone()
            return int(row[0] or 0) if row else 0

    def get_user_vip_until(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT vip_until FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            return int(row[0] or 0) if row else 0

    def has_active_duel(self, user_id: int) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM duels WHERE status = 'active' AND (creator_id = ? OR opponent_id = ?) LIMIT 1",
                (int(user_id), int(user_id)),
            ).fetchone()
            return bool(row)

    def recent_duels_with(self, creator_id: int, opponent_id: int, *, limit: int = 3) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                """
                SELECT duel_id, status, winner_id, resolved_at
                FROM duels
                WHERE creator_id = ? AND opponent_id = ?
                ORDER BY duel_id DESC
                LIMIT ?
                """,
                (int(creator_id), int(opponent_id), int(limit)),
            ).fetchall()
            return [{"duel_id": int(r[0]), "status": str(r[1]), "winner_id": (int(r[2]) if r[2] is not None else None), "resolved_at": str(r[3] or "")} for r in rows]

    def enqueue_random(self, user_id: int, *, stake: int, game_type: str, balance: int) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO random_queue(user_id, stake, game_type, balance_snapshot, created_at) VALUES(?, ?, ?, ?, ?)",
                (int(user_id), int(stake), str(game_type), int(balance), str(now)),
            )

    def find_random_match(self, user_id: int, *, stake: int, game_type: str, balance: int, pct: int = 30) -> int | None:
        with self._lock, self._connect() as db:
            low = int(balance * (100 - pct) / 100)
            high = int(balance * (100 + pct) / 100)
            row = db.execute(
                """
                SELECT user_id FROM random_queue
                WHERE user_id != ? AND stake = ? AND game_type = ? AND balance_snapshot BETWEEN ? AND ?
                ORDER BY rq_id ASC
                LIMIT 1
                """,
                (int(user_id), int(stake), str(game_type), int(low), int(high)),
            ).fetchone()
            return int(row[0]) if row else None

    def dequeue_random_for_users(self, a_user_id: int, b_user_id: int, *, stake: int, game_type: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "DELETE FROM random_queue WHERE (user_id = ? OR user_id = ?) AND stake = ? AND game_type = ?",
                (int(a_user_id), int(b_user_id), int(stake), str(game_type)),
            )

    def list_recent_opponents(self, user_id: int, *, limit: int = 5) -> list[dict]:
        """Return recent opponents the user has played with, most recent first.

        Includes usernames when available.
        """
        with self._lock, self._connect() as db:
            rows = db.execute(
                """
                SELECT other_id, u.username, MAX(COALESCE(d.resolved_at, d.joined_at, d.created_at)) AS last_ts
                FROM (
                    SELECT opponent_id AS other_id, duel_id FROM duels WHERE creator_id = ? AND opponent_id IS NOT NULL
                    UNION ALL
                    SELECT creator_id AS other_id, duel_id FROM duels WHERE opponent_id = ? AND creator_id IS NOT NULL
                ) x
                JOIN duels d ON d.duel_id = x.duel_id
                LEFT JOIN users u ON u.user_id = other_id
                WHERE other_id IS NOT NULL AND other_id != 0
                GROUP BY other_id, u.username
                ORDER BY last_ts DESC
                LIMIT ?
                """,
                (int(user_id), int(user_id), int(limit)),
            ).fetchall()
            out: list[dict] = []
            for r in rows:
                out.append({"user_id": int(r[0]), "username": (str(r[1]) if r[1] is not None else None)})
            return out

    def get_setting(self, key: str) -> str | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT value FROM bot_settings WHERE key = ?", (str(key),)).fetchone()
            if not row:
                return None
            return str(row[0])

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO bot_settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(key), str(value)),
            )

    def update_duel_rps_choice(self, duel_id: int, *, user_id: int, choice: str) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT creator_id, opponent_id FROM duels WHERE duel_id = ?", (int(duel_id),)).fetchone()
            if not row:
                return
            creator_id = int(row[0])
            opponent_id = int(row[1]) if row[1] is not None else None
            if user_id == creator_id:
                db.execute(
                    "UPDATE duels SET creator_choice = ?, last_action_at = ? WHERE duel_id = ?",
                    (choice, now, int(duel_id)),
                )
            elif opponent_id is not None and user_id == opponent_id:
                db.execute(
                    "UPDATE duels SET opponent_choice = ?, last_action_at = ? WHERE duel_id = ?",
                    (choice, now, int(duel_id)),
                )

    def update_duel_roll(self, duel_id: int, *, user_id: int, roll: int) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT creator_id, opponent_id FROM duels WHERE duel_id = ?", (int(duel_id),)).fetchone()
            if not row:
                return
            creator_id = int(row[0])
            opponent_id = int(row[1]) if row[1] is not None else None
            if user_id == creator_id:
                db.execute(
                    "UPDATE duels SET creator_roll = ?, last_action_at = ? WHERE duel_id = ?",
                    (int(roll), now, int(duel_id)),
                )
            elif opponent_id is not None and user_id == opponent_id:
                db.execute(
                    "UPDATE duels SET opponent_roll = ?, last_action_at = ? WHERE duel_id = ?",
                    (int(roll), now, int(duel_id)),
                )

    def get_duel_by_id(self, duel_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT duel_id, code, creator_id, opponent_id, stake, game_type, status, is_bot, creator_choice, opponent_choice, creator_roll, opponent_roll, state_json, winner_id, created_at, joined_at, resolved_at, is_rematch FROM duels WHERE duel_id = ?",
                (int(duel_id),),
            ).fetchone()
            if not row:
                return None
            return {
                "duel_id": int(row[0]),
                "code": str(row[1]),
                "creator_id": int(row[2]),
                "opponent_id": int(row[3]) if row[3] is not None else None,
                "stake": int(row[4]),
                "game_type": str(row[5]),
                "status": str(row[6]),
                "is_bot": int(row[7] or 0),
                "creator_choice": row[8],
                "opponent_choice": row[9],
                "creator_roll": int(row[10]) if row[10] is not None else None,
                "opponent_roll": int(row[11]) if row[11] is not None else None,
                "state_json": (str(row[12]) if row[12] is not None else None),
                "winner_id": int(row[13]) if row[13] is not None else None,
                "created_at": str(row[14]),
                "joined_at": str(row[15]) if row[15] is not None else None,
                "resolved_at": str(row[16]) if row[16] is not None else None,
                "is_rematch": int(row[17] or 0),
            }

    def duel_ttt_init(self, duel_id: int, *, creator_id: int, opponent_id: int, creator_msg_id: int, opponent_msg_id: int) -> dict:
        state = {
            "v": 1,
            "board": ".........",
            "turn": int(creator_id),
            "sym": {str(int(creator_id)): "❌", str(int(opponent_id)): "⭕"},
            "msg": {str(int(creator_id)): int(creator_msg_id or 0), str(int(opponent_id)): int(opponent_msg_id or 0)},
        }
        raw = json.dumps(state, ensure_ascii=False)
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE duels SET state_json = ? WHERE duel_id = ?",
                (raw, int(duel_id)),
            )
        return state

    def duel_ttt_set_msg(self, duel_id: int, *, user_id: int, message_id: int) -> None:
        """Persist (or update) last known board message_id for a user in duel.state_json."""
        did = int(duel_id)
        uid = int(user_id)
        mid = int(message_id)
        if mid <= 0:
            return
        with self._lock, self._connect() as db:
            row = db.execute("SELECT state_json FROM duels WHERE duel_id = ?", (did,)).fetchone()
            raw = row[0] if row else None
            try:
                state = json.loads(str(raw) or "{}") if raw else {}
            except Exception:
                state = {}
            if not isinstance(state, dict):
                state = {}
            msg = state.get("msg") if isinstance(state.get("msg"), dict) else {}
            msg[str(uid)] = mid
            state["msg"] = msg
            db.execute("UPDATE duels SET state_json = ? WHERE duel_id = ?", (json.dumps(state, ensure_ascii=False), did))

    def duel_ttt_make_move(self, duel_id: int, *, user_id: int, pos: int) -> dict:
        """Apply a TicTacToe move.

        Returns dict:
          ok: bool
          error: str (if not ok)
          finished: bool
          finalized_now: bool
          winner_id: int|None
          state: dict
          creator_id/opponent_id/stake
        """
        did = int(duel_id)
        uid = int(user_id)
        p = int(pos)
        if p < 0 or p > 8:
            return {"ok": False, "error": "Некорректный ход"}

        def _winner(board: str) -> str | None:
            lines = (
                (0, 1, 2),
                (3, 4, 5),
                (6, 7, 8),
                (0, 3, 6),
                (1, 4, 7),
                (2, 5, 8),
                (0, 4, 8),
                (2, 4, 6),
            )
            for a, b, c in lines:
                ch = board[a]
                if ch != "." and ch == board[b] and ch == board[c]:
                    return ch
            return None

        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT creator_id, opponent_id, stake, status, game_type, state_json FROM duels WHERE duel_id = ?",
                (did,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "Дуэль не найдена"}
            creator_id = int(row[0])
            opponent_id = int(row[1]) if row[1] is not None else None
            stake = int(row[2] or 0)
            status = str(row[3] or "")
            game_type = str(row[4] or "")
            raw = row[5]

            if game_type != "ttt":
                return {"ok": False, "error": "Не та игра"}
            if status != "active" or opponent_id is None:
                return {"ok": False, "error": "Дуэль недоступна"}
            if uid not in (creator_id, opponent_id):
                return {"ok": False, "error": "Эта дуэль не для вас"}

            try:
                state = json.loads(str(raw) or "{}") if raw else {}
            except Exception:
                state = {}
            if not isinstance(state, dict):
                state = {}

            board = str(state.get("board") or ".........")
            if len(board) != 9:
                board = "........."
            turn = int(state.get("turn") or creator_id)

            sym = state.get("sym") if isinstance(state.get("sym"), dict) else {}
            msg = state.get("msg") if isinstance(state.get("msg"), dict) else {}
            if not sym:
                sym = {str(creator_id): "❌", str(opponent_id): "⭕"}
            if not msg:
                msg = {}

            if uid != turn:
                return {"ok": False, "error": "Сейчас ход соперника"}
            if board[p] != ".":
                return {"ok": False, "error": "Клетка занята"}

            my_sym = str(sym.get(str(uid)) or ("❌" if uid == creator_id else "⭕"))
            b_list = list(board)
            b_list[p] = my_sym
            board2 = "".join(b_list)

            w = _winner(board2)
            finished = False
            winner_id: int | None = None
            if w is not None:
                finished = True
                # map symbol back to user
                if str(sym.get(str(creator_id)) or "X") == w:
                    winner_id = creator_id
                elif str(sym.get(str(opponent_id)) or "O") == w:
                    winner_id = opponent_id
                else:
                    winner_id = uid
            elif "." not in board2:
                finished = True
                winner_id = None

            next_turn = opponent_id if uid == creator_id else creator_id
            state2 = {
                "v": 1,
                "board": board2,
                "turn": int(next_turn if not finished else turn),
                "sym": {str(creator_id): str(sym.get(str(creator_id)) or "❌"), str(opponent_id): str(sym.get(str(opponent_id)) or "⭕")},
                "msg": msg,
            }
            raw2 = json.dumps(state2, ensure_ascii=False)

            finalized_now = False
            if finished:
                cur = db.execute(
                    "UPDATE duels SET status = 'finished', winner_id = ?, state_json = ?, resolved_at = ?, last_action_at = ? WHERE duel_id = ? AND status = 'active'",
                    (winner_id, raw2, now, now, did),
                )
                finalized_now = int(getattr(cur, "rowcount", 0) or 0) > 0
            else:
                db.execute(
                    "UPDATE duels SET state_json = ?, last_action_at = ? WHERE duel_id = ? AND status = 'active'",
                    (raw2, now, did),
                )

            return {
                "ok": True,
                "finished": bool(finished),
                "finalized_now": bool(finalized_now),
                "winner_id": winner_id,
                "state": state2,
                "creator_id": creator_id,
                "opponent_id": opponent_id,
                "stake": stake,
            }

    def finalize_duel_result(self, duel_id: int, *, winner_id: int | None, creator_roll: int | None = None, opponent_roll: int | None = None) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE duels SET status = 'finished', winner_id = ?, creator_roll = COALESCE(?, creator_roll), opponent_roll = COALESCE(?, opponent_roll), resolved_at = ? WHERE duel_id = ?",
                (winner_id, creator_roll, opponent_roll, now, int(duel_id)),
            )

    def count_recent_duels_between(self, user1_id: int, user2_id: int, *, window_seconds: int) -> int:
        """Количество завершённых дуэлей между двумя игроками за последнее окно времени."""
        u1 = int(user1_id)
        u2 = int(user2_id)
        if u1 == u2:
            return 0
        now = dt.datetime.utcnow()
        threshold = now - dt.timedelta(seconds=int(window_seconds))
        thr_str = threshold.isoformat()
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT COUNT(*) FROM duels
                WHERE status = 'finished'
                  AND resolved_at IS NOT NULL
                  AND resolved_at >= ?
                  AND (
                        (creator_id = ? AND opponent_id = ?)
                     OR (creator_id = ? AND opponent_id = ?)
                  )
                """,
                (thr_str, u1, u2, u2, u1),
            ).fetchone()
            return int(row[0] or 0) if row else 0

    # --- Wheel of fortune ---

    def get_wheel_state(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT wheel_last_spin_date, wheel_free_spins_used, wheel_streak_days, vip_until FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "last_spin_date": row[0],
                "free_spins_used": int(row[1] or 0),
                "streak_days": int(row[2] or 0),
                "vip_until": int(row[3] or 0),
            }

    def update_wheel_state(self, user_id: int, *, last_spin_date: str, free_spins_used: int, streak_days: int) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE users SET wheel_last_spin_date = ?, wheel_free_spins_used = ?, wheel_streak_days = ? WHERE user_id = ?",
                (last_spin_date, int(free_spins_used), int(streak_days), user_id),
            )

    def get_wheel_window(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT wheel_hour_ts, wheel_games_in_hour FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "hour_ts": int(row[0] or 0),
                "games_in_hour": int(row[1] or 0),
            }

    def update_wheel_window(self, user_id: int, *, hour_ts: int, games_in_hour: int) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE users SET wheel_hour_ts = ?, wheel_games_in_hour = ? WHERE user_id = ?",
                (int(hour_ts), int(games_in_hour), user_id),
            )

    def _week_start_ts(self, now_ts: int) -> int:
        # Monday 00:00 UTC for the week of now_ts
        dt_now = dt.datetime.utcfromtimestamp(int(now_ts))
        monday = dt_now - dt.timedelta(days=dt_now.weekday())
        monday_midnight = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(monday_midnight.timestamp())

    def update_wheel_stats(self, user_id: int, *, now_ts: int, add_roll: int, points_won: int) -> None:
        now_ts = int(now_ts)
        add_roll = int(add_roll)
        points_won = max(0, int(points_won))
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT wheel_total_win, wheel_rolls, wheel_best_win, wheel_week_start_ts, wheel_week_win, wheel_week_rolls, wheel_week_best FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return
            total_win = int(row[0] or 0) + points_won
            rolls = int(row[1] or 0) + add_roll
            best_win = max(int(row[2] or 0), points_won)
            week_start = int(row[3] or 0)
            cur_week = self._week_start_ts(now_ts)
            if week_start != cur_week:
                week_win = 0
                week_rolls = 0
                week_best = 0
                week_start = cur_week
            else:
                week_win = int(row[4] or 0)
                week_rolls = int(row[5] or 0)
                week_best = int(row[6] or 0)
            week_win += points_won
            week_rolls += add_roll
            week_best = max(week_best, points_won)
            db.execute(
                """
                UPDATE users
                SET wheel_total_win = ?, wheel_rolls = ?, wheel_best_win = ?,
                    wheel_week_start_ts = ?, wheel_week_win = ?, wheel_week_rolls = ?, wheel_week_best = ?
                WHERE user_id = ?
                """,
                (total_win, rolls, best_win, week_start, week_win, week_rolls, week_best, user_id),
            )

    def get_wheel_top_weekly_total(self, *, limit: int = 10) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT user_id, username, wheel_week_win FROM users WHERE blocked = 0 ORDER BY wheel_week_win DESC, wheel_week_rolls DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for i, r in enumerate(rows, 1):
                out.append({
                    "pos": i,
                    "user_id": int(r[0]),
                    "username": r[1],
                    "value": int(r[2] or 0),
                })
            return out

    def get_wheel_top_weekly_rolls(self, *, limit: int = 10) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT user_id, username, wheel_week_rolls FROM users WHERE blocked = 0 ORDER BY wheel_week_rolls DESC, wheel_week_win DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for i, r in enumerate(rows, 1):
                out.append({
                    "pos": i,
                    "user_id": int(r[0]),
                    "username": r[1],
                    "value": int(r[2] or 0),
                })
            return out

    def get_wheel_top_weekly_best(self, *, limit: int = 10) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT user_id, username, wheel_week_best FROM users WHERE blocked = 0 ORDER BY wheel_week_best DESC, wheel_week_win DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for i, r in enumerate(rows, 1):
                out.append({
                    "pos": i,
                    "user_id": int(r[0]),
                    "username": r[1],
                    "value": int(r[2] or 0),
                })
            return out

    # --- Dice game ---

    def get_dice_window(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT dice_hour_ts, dice_games_in_hour FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "hour_ts": int(row[0] or 0),
                "games_in_hour": int(row[1] or 0),
            }

    def update_dice_window(self, user_id: int, *, hour_ts: int, games_in_hour: int) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE users SET dice_hour_ts = ?, dice_games_in_hour = ? WHERE user_id = ?",
                (int(hour_ts), int(games_in_hour), user_id),
            )

    def get_user_achievements(self, user_id: int) -> dict:
        with self._lock, self._connect() as db:
            total = db.execute("SELECT COUNT(*) FROM achievements WHERE hidden = 0").fetchone()
            total_cnt = int(total[0] or 0) if total else 0

            unlocked = db.execute(
                """
                SELECT a.code, a.title, a.description, a.icon, a.reward_points, a.reward_experience, ua.unlocked_at
                FROM user_achievements ua
                JOIN achievements a ON a.achievement_id = ua.achievement_id
                WHERE ua.user_id = ? AND a.hidden = 0
                ORDER BY ua.unlocked_at ASC
                """,
                (user_id,),
            ).fetchall()
            unlocked_list = [
                {
                    "code": str(r[0]),
                    "title": str(r[1]),
                    "description": str(r[2]),
                    "icon": str(r[3] or "🏆"),
                    "reward_points": int(r[4] or 0),
                    "reward_experience": int(r[5] or 0),
                    "unlocked_at": str(r[6]),
                }
                for r in unlocked
            ]

            return {"total": total_cnt, "unlocked": unlocked_list, "unlocked_count": len(unlocked_list)}

    def ensure_user(self, user_id: int, username: str | None, invited_by: int | None) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            try:
                row = db.execute("SELECT invited_by FROM users WHERE user_id = ?", (user_id,)).fetchone()
                if row is None:
                    db.execute(
                        "INSERT INTO users(user_id, username, invited_by, created_at) VALUES(?, ?, ?, ?)",
                        (user_id, username, invited_by, now),
                    )
                    if invited_by and invited_by != user_id:
                        db.execute(
                            "INSERT OR IGNORE INTO referral_rewards(invitee_id, inviter_id, rewarded, created_at) VALUES(?, ?, 0, ?)",
                            (user_id, invited_by, now),
                        )
                        db.execute(
                            "UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?",
                            (invited_by,),
                        )
                else:
                    db.execute(
                        "UPDATE users SET username = COALESCE(?, username) WHERE user_id = ?",
                        (username, user_id),
                    )
            except Exception as e:
                try:
                    self._logger.exception("DB ensure_user failed: user_id=%s invited_by=%s err=%r", user_id, invited_by, e)
                except Exception:
                    pass

    def register_user_from_start(self, user_id: int, username: str | None, inviter_id: int | None, *, bonus_points: int) -> dict | None:
        """Creates user on first /start and immediately rewards inviter if valid.

        Returns dict with inviter reward info if inviter was rewarded, otherwise None.
        Checks:
        - user must be new
        - inviter cannot be the same user
        - only one inviter per user (enforced by 'new user only')
        """
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            try:
                exists = db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
                if exists:
                    db.execute(
                        "UPDATE users SET username = COALESCE(?, username) WHERE user_id = ?",
                        (username, user_id),
                    )
                    return None

                inviter_to_set: int | None = None
                if inviter_id and inviter_id != user_id:
                    inviter_to_set = int(inviter_id)

                db.execute(
                    "INSERT INTO users(user_id, username, invited_by, created_at) VALUES(?, ?, ?, ?)",
                    (user_id, username, inviter_to_set, now),
                )

                if not inviter_to_set:
                    return None

                db.execute(
                    "INSERT OR IGNORE INTO referral_rewards(invitee_id, inviter_id, rewarded, created_at) VALUES(?, ?, 1, ?)",
                    (user_id, inviter_to_set, now),
                )
                inv_row = db.execute("SELECT experience FROM users WHERE user_id = ?", (inviter_to_set,)).fetchone()
                old_xp = int(inv_row[0] or 0) if inv_row else 0
                old_level = self.level_from_xp(old_xp)
                new_xp = old_xp + int(bonus_points)
                new_level = self.level_from_xp(new_xp)

                db.execute(
                    "UPDATE users SET referrals_count = referrals_count + 1, balance_points = balance_points + ?, experience = ?, level = ? WHERE user_id = ?",
                    (int(bonus_points), int(new_xp), int(new_level), inviter_to_set),
                )

                return {
                    "inviter_id": int(inviter_to_set),
                    "awarded": int(bonus_points),
                    "old_level": int(old_level),
                    "new_level": int(new_level),
                    "leveled_up": bool(new_level > old_level),
                    "new_title": self.get_level_title(new_level),
                }
            except Exception as e:
                try:
                    self._logger.exception("DB register_user_from_start failed: user_id=%s inviter_id=%s err=%r", user_id, inviter_id, e)
                except Exception:
                    pass
                return None

    def is_blocked(self, user_id: int) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT blocked FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return bool(row and row[0])

    def set_blocked(self, user_id: int, blocked: bool) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET blocked = ? WHERE user_id = ?", (1 if blocked else 0, user_id))

    def get_balance(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT balance_points FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return int(row[0]) if row else 0

    def get_coins_balance(self, user_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT balance_coins FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            return int(row[0] or 0) if row else 0

    def try_spend_coins(self, user_id: int, amount: int) -> dict:
        """Atomically subtract coins if sufficient balance exists.

        Returns: {"ok": bool, "balance": int}
        """
        user_id = int(user_id)
        amount = int(amount)
        if amount <= 0:
            return {"ok": True, "balance": int(self.get_coins_balance(user_id))}

        with self._lock, self._connect() as db:
            cur = db.execute(
                "UPDATE users SET balance_coins = balance_coins - ? WHERE user_id = ? AND balance_coins >= ?",
                (int(amount), int(user_id), int(amount)),
            )
            ok = bool(getattr(cur, "rowcount", 0) and int(cur.rowcount) > 0)
            row = db.execute("SELECT balance_coins FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            bal = int(row[0] or 0) if row else 0
            return {"ok": ok, "balance": bal}

    def add_coins_balance(self, user_id: int, delta: int) -> dict:
        """Add/subtract coins (does NOT affect XP/level). Returns {balance_coins}."""
        user_id = int(user_id)
        delta = int(delta)
        with self._lock, self._connect() as db:
            try:
                db.execute(
                    "UPDATE users SET balance_coins = CASE WHEN balance_coins + ? >= 0 THEN balance_coins + ? ELSE 0 END WHERE user_id = ?",
                    (int(delta), int(delta), int(user_id)),
                )
            except Exception:
                pass
            row = db.execute("SELECT balance_coins FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            bal = int(row[0] or 0) if row else 0
            return {"balance_coins": int(bal)}

    def try_spend_points(self, user_id: int, amount: int) -> dict:
        """Atomically subtract points if sufficient balance exists.

        Returns: {"ok": bool, "balance": int}
        """
        user_id = int(user_id)
        amount = int(amount)
        if amount <= 0:
            return {"ok": True, "balance": int(self.get_balance(user_id))}

        with self._lock, self._connect() as db:
            cur = db.execute(
                "UPDATE users SET balance_points = balance_points - ? WHERE user_id = ? AND balance_points >= ?",
                (int(amount), int(user_id), int(amount)),
            )
            ok = bool(getattr(cur, "rowcount", 0) and int(cur.rowcount) > 0)
            row = db.execute("SELECT balance_points FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            bal = int(row[0] or 0) if row else 0
            return {"ok": ok, "balance": bal}

    def spend_points_clamped(self, user_id: int, amount: int) -> dict:
        """Atomically subtract up to `amount`, never letting balance go below 0.

        Useful for penalties where we must not create negative balances.
        Returns: {"ok": True, "spent": int, "balance": int}
        """
        user_id = int(user_id)
        amount = int(amount)
        if amount <= 0:
            bal = int(self.get_balance(user_id))
            return {"ok": True, "spent": 0, "balance": bal}

        with self._lock, self._connect() as db:
            row0 = db.execute("SELECT balance_points FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            before = int(row0[0] or 0) if row0 else 0
            db.execute(
                "UPDATE users SET balance_points = CASE WHEN balance_points >= ? THEN balance_points - ? ELSE 0 END WHERE user_id = ?",
                (int(amount), int(amount), int(user_id)),
            )
            row1 = db.execute("SELECT balance_points FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            after = int(row1[0] or 0) if row1 else 0
            spent = max(0, int(before) - int(after))
            return {"ok": True, "spent": int(spent), "balance": int(after)}

    def add_balance(self, user_id: int, delta: int) -> dict:
        delta = int(delta)
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT experience FROM users WHERE user_id = ?", (user_id,)).fetchone()
            old_xp = int(row[0] or 0) if row else 0
            old_level = self.level_from_xp(old_xp)

            xp_added = int(delta) if delta > 0 else 0
            new_xp = old_xp + xp_added
            new_level = self.level_from_xp(new_xp)

            achievements_unlocked: list[dict] = []
            if delta > 0:
                db.execute(
                    "UPDATE users SET balance_points = balance_points + ?, experience = ?, level = ? WHERE user_id = ?",
                    (int(delta), int(new_xp), int(new_level), user_id),
                )
                try:
                    db.execute(
                        "INSERT INTO experience_history(user_id, amount, source, description, created_at) VALUES(?, ?, ?, ?, ?)",
                        (user_id, int(xp_added), "points", None, now),
                    )
                except Exception:
                    pass

                # Achievements may award extra points (and thus XP)
                try:
                    achievements_unlocked = self._award_achievements_in_conn(db, user_id, now=now)
                except Exception:
                    achievements_unlocked = []
            else:
                db.execute(
                    "UPDATE users SET balance_points = balance_points + ? WHERE user_id = ?",
                    (int(delta), user_id),
                )

            # Re-read final XP/level after potential achievement points
            final_row = db.execute("SELECT experience FROM users WHERE user_id = ?", (user_id,)).fetchone()
            final_xp = int(final_row[0] or new_xp) if final_row else int(new_xp)
            final_level = self.level_from_xp(final_xp)

            # Return dict (callers may ignore)
            return {
                "xp_added": int(xp_added),
                "xp_total": int(final_xp),
                "old_level": int(old_level),
                "new_level": int(final_level),
                "leveled_up": bool(final_level > old_level),
                "new_title": self.get_level_title(final_level),
                "achievements_unlocked": achievements_unlocked,
            }

    def inc_completed_tasks(self, user_id: int) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE users SET completed_tasks = completed_tasks + 1 WHERE user_id = ?",
                (user_id,),
            )

    def get_profile(self, user_id: int) -> dict:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT user_id, balance_points, completed_tasks, referrals_count, blocked FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {
                    "user_id": user_id,
                    "balance_points": 0,
                    "completed_tasks": 0,
                    "referrals_count": 0,
                    "blocked": 0,
                }
            return {
                "user_id": int(row[0]),
                "balance_points": int(row[1]),
                "completed_tasks": int(row[2]),
                "referrals_count": int(row[3]),
                "blocked": int(row[4]),
            }

    def ensure_default_tasks(self) -> None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT COUNT(*) FROM tasks").fetchone()
            count = int(row[0]) if row else 0
            if count > 0:
                return

            db.execute(
                "INSERT INTO tasks(code, title, description, reward_points, comment_text, active) VALUES(?, ?, ?, ?, ?, 1)",
                (
                    "channel_subscribe",
                    "📢 Подписка на канал",
                    "Задание: Подпишитесь на канал\n\nНаграда: +200 баллов\n\nНажмите кнопку ниже, чтобы перейти на канал:",
                    200,
                    None,
                ),
            )
            db.execute(
                "INSERT INTO tasks(code, title, description, reward_points, comment_text, active) VALUES(?, ?, ?, ?, ?, 1)",
                (
                    "tiktok_comment",
                    "📝 TikTok — комментарий",
                    "Задание: Напишите комментарий в TikTok\n\n1️⃣ Найдите любое видео с 100 000+ лайков\n2️⃣ Вставьте комментарий ниже под видео:\n\n@zadaniya_za_cashBot в этом боте реально можно получить деньги выполняя легкие задания\n\n3️⃣ Сделайте скрин с вашим комментарием, ником и лайками\n\nНаграда: +200 баллов",
                    200,
                    "@zadaniya_za_cashBot в этом боте реально можно получить деньги выполняя легкие задания",
                ),
            )

    def get_task_by_code(self, code: str) -> Task | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                "SELECT task_id, code, title, description, reward_points, active, comment_text FROM tasks WHERE code = ? LIMIT 1",
                (code,),
            ).fetchone()
            if not r:
                return None
            return Task(
                id=int(r[0]),
                code=str(r[1]),
                title=str(r[2]),
                description=str(r[3]),
                reward_points=int(r[4]),
                active=int(r[5]),
                comment_text=(str(r[6]) if r[6] is not None else None),
            )

    def get_user_task(self, user_id: int, task_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                "SELECT status, repeat_used, reward_credited, updated_at FROM user_tasks WHERE user_id = ? AND task_id = ?",
                (user_id, task_id),
            ).fetchone()
            if not r:
                return None
            return {
                "status": str(r[0]),
                "repeat_used": int(r[1]),
                "reward_credited": int(r[2]),
                "updated_at": str(r[3]),
            }

    def ensure_user_task(self, user_id: int, task_id: int) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            # Defensive: ensure referenced task exists to avoid FOREIGN KEY failures
            r = db.execute("SELECT 1 FROM tasks WHERE task_id = ? LIMIT 1", (task_id,)).fetchone()
            if not r:
                return
            db.execute(
                "INSERT OR IGNORE INTO user_tasks(user_id, task_id, status, repeat_used, reward_credited, updated_at) VALUES(?, ?, 'new', 0, 0, ?)",
                (user_id, task_id, now),
            )

    def update_user_task(self, user_id: int, task_id: int, *, status: str, repeat_used: int | None = None, reward_credited: int | None = None) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            # Defensive: only initialize if task exists
            r = db.execute("SELECT 1 FROM tasks WHERE task_id = ? LIMIT 1", (task_id,)).fetchone()
            if not r:
                return
            db.execute(
                "INSERT OR IGNORE INTO user_tasks(user_id, task_id, status, repeat_used, reward_credited, updated_at) VALUES(?, ?, 'new', 0, 0, ?)",
                (user_id, task_id, now),
            )
            if repeat_used is None and reward_credited is None:
                db.execute(
                    "UPDATE user_tasks SET status = ?, updated_at = ? WHERE user_id = ? AND task_id = ?",
                    (status, now, user_id, task_id),
                )
            elif reward_credited is None:
                db.execute(
                    "UPDATE user_tasks SET status = ?, repeat_used = ?, updated_at = ? WHERE user_id = ? AND task_id = ?",
                    (status, int(repeat_used), now, user_id, task_id),
                )
            elif repeat_used is None:
                db.execute(
                    "UPDATE user_tasks SET status = ?, reward_credited = ?, updated_at = ? WHERE user_id = ? AND task_id = ?",
                    (status, int(reward_credited), now, user_id, task_id),
                )
            else:
                db.execute(
                    "UPDATE user_tasks SET status = ?, repeat_used = ?, reward_credited = ?, updated_at = ? WHERE user_id = ? AND task_id = ?",
                    (status, int(repeat_used), int(reward_credited), now, user_id, task_id),
                )

    def list_user_ids_for_task_status(self, task_id: int, statuses: tuple[str, ...], *, limit: int = 200) -> list[int]:
        if not statuses:
            return []
        placeholders = ",".join(["?"] * len(statuses))
        with self._lock, self._connect() as db:
            rows = db.execute(
                f"SELECT user_id FROM user_tasks WHERE task_id = ? AND status IN ({placeholders}) ORDER BY updated_at ASC LIMIT ?",
                (task_id, *statuses, int(limit)),
            ).fetchall()
            return [int(r[0]) for r in rows]

    def try_mark_task_completed(self, user_id: int, task_id: int, *, reward_credited: int, repeat_used: int) -> bool:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            # Defensive: ensure task exists before touching user_tasks
            r = db.execute("SELECT 1 FROM tasks WHERE task_id = ? LIMIT 1", (task_id,)).fetchone()
            if not r:
                return False
            db.execute(
                "INSERT OR IGNORE INTO user_tasks(user_id, task_id, status, repeat_used, reward_credited, updated_at) VALUES(?, ?, 'new', 0, 0, ?)",
                (user_id, task_id, now),
            )
            cur = db.execute(
                "UPDATE user_tasks SET status = 'completed', repeat_used = ?, reward_credited = ?, updated_at = ? "
                "WHERE user_id = ? AND task_id = ? AND status IN ('new', 'repeat_offer')",
                (int(repeat_used), int(reward_credited), now, user_id, task_id),
            )
            return int(cur.rowcount or 0) == 1

    def try_transition_channel_unsub(self, user_id: int, task_id: int) -> tuple[bool, int, int, str]:
        """If current status is completed, transition to repeat_offer/revoked and return (ok, deducted, repeat_used, new_status)."""
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT status, repeat_used, reward_credited FROM user_tasks WHERE user_id = ? AND task_id = ?",
                (user_id, task_id),
            ).fetchone()
            if not row:
                return (False, 0, 0, "")
            status = str(row[0])
            repeat_used = int(row[1])
            reward_credited = int(row[2])
            if status != "completed":
                return (False, reward_credited, repeat_used, status)

            new_status = "repeat_offer" if repeat_used == 0 else "revoked"
            now = dt.datetime.utcnow().isoformat()
            cur = db.execute(
                "UPDATE user_tasks SET status = ?, updated_at = ? WHERE user_id = ? AND task_id = ? AND status = 'completed'",
                (new_status, now, user_id, task_id),
            )
            if int(cur.rowcount or 0) != 1:
                return (False, reward_credited, repeat_used, status)
            return (True, reward_credited, repeat_used, new_status)

    def create_task(self, code: str, title: str, description: str, reward_points: int, comment_text: str | None) -> int:
        with self._lock, self._connect() as db:
            cur = db.execute(
                "INSERT INTO tasks(code, title, description, reward_points, comment_text, active) VALUES(?, ?, ?, ?, ?, 1)",
                (code, title, description, reward_points, comment_text),
            )
            return int(cur.lastrowid)

    def list_active_tasks(self) -> list[Task]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT task_id, code, title, description, reward_points, active, comment_text FROM tasks WHERE active = 1 ORDER BY task_id ASC"
            ).fetchall()
            return [
                Task(
                    id=int(r[0]),
                    code=str(r[1]),
                    title=str(r[2]),
                    description=str(r[3]),
                    reward_points=int(r[4]),
                    active=int(r[5]),
                    comment_text=(str(r[6]) if r[6] is not None else None),
                )
                for r in rows
            ]

    def get_task(self, task_id: int) -> Task | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                "SELECT task_id, code, title, description, reward_points, active, comment_text FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if not r:
                return None
            return Task(
                id=int(r[0]),
                code=str(r[1]),
                title=str(r[2]),
                description=str(r[3]),
                reward_points=int(r[4]),
                active=int(r[5]),
                comment_text=(str(r[6]) if r[6] is not None else None),
            )

    def create_submission(self, user_id: int, task_id: int, photo_file_id: str) -> int:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            cur = db.execute(
                "INSERT INTO submissions(user_id, task_id, photo_file_id, status, created_at) VALUES(?, ?, ?, 'pending', ?)",
                (user_id, task_id, photo_file_id, now),
            )
            return int(cur.lastrowid)

    def get_pending_submission(self) -> dict | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                """
                SELECT s.submission_id, s.user_id, u.username, s.task_id, t.title, t.reward_points, s.photo_file_id
                FROM submissions s
                JOIN users u ON u.user_id = s.user_id
                JOIN tasks t ON t.task_id = s.task_id
                WHERE s.status = 'pending'
                ORDER BY s.submission_id ASC
                LIMIT 1
                """
            ).fetchone()
            if not r:
                return None
            return {
                "submission_id": int(r[0]),
                "user_id": int(r[1]),
                "username": r[2],
                "task_id": int(r[3]),
                "task_title": str(r[4]),
                "reward_points": int(r[5]),
                "photo_file_id": str(r[6]),
            }

    def set_submission_status(self, submission_id: int, status: str, reviewer_id: int) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE submissions SET status = ?, reviewed_at = ?, reviewer_id = ? WHERE submission_id = ?",
                (status, now, reviewer_id, submission_id),
            )

    def get_submission(self, submission_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                "SELECT submission_id, user_id, task_id, status FROM submissions WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
            if not r:
                return None
            return {
                "submission_id": int(r[0]),
                "user_id": int(r[1]),
                "task_id": int(r[2]),
                "status": str(r[3]),
            }

    def create_withdrawal(self, user_id: int, amount_rub: int, points_spent: int, bank: str, requisites: str) -> int:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            cur = db.execute(
                "INSERT INTO withdrawals(user_id, amount_rub, points_spent, bank, requisites, status, created_at) VALUES(?, ?, ?, ?, ?, 'pending', ?)",
                (user_id, amount_rub, points_spent, bank, requisites, now),
            )
            return int(cur.lastrowid)

    def get_pending_withdrawal(self) -> dict | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                """
                SELECT w.withdrawal_id, w.user_id, u.username,
                       u.balance_points, u.frozen_points,
                       u.balance_coins, u.frozen_coins,
                       w.amount_rub, w.points_spent, w.coins_spent, w.bank, w.requisites
                FROM withdrawals w
                JOIN users u ON u.user_id = w.user_id
                WHERE w.status = 'pending'
                ORDER BY w.withdrawal_id ASC
                LIMIT 1
                """
            ).fetchone()
            if not r:
                return None
            return {
                "withdrawal_id": int(r[0]),
                "user_id": int(r[1]),
                "username": r[2],
                "balance_points": int(r[3] or 0),
                "frozen_points": int(r[4] or 0),
                "balance_coins": int(r[5] or 0),
                "frozen_coins": int(r[6] or 0),
                "amount_rub": int(r[7]),
                "points_spent": int(r[8] or 0),
                "coins_spent": int(r[9] or 0),
                "bank": str(r[10]),
                "requisites": str(r[11]),
            }

    def set_withdrawal_status(self, withdrawal_id: int, status: str, reviewer_id: int) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE withdrawals SET status = ?, reviewed_at = ?, reviewer_id = ? WHERE withdrawal_id = ?",
                (status, now, reviewer_id, withdrawal_id),
            )

    def get_withdrawal(self, withdrawal_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                "SELECT withdrawal_id, user_id, status, points_spent, coins_spent FROM withdrawals WHERE withdrawal_id = ?",
                (withdrawal_id,),
            ).fetchone()
            if not r:
                return None
            return {
                "withdrawal_id": int(r[0]),
                "user_id": int(r[1]),
                "status": str(r[2]),
                "points_spent": int(r[3] or 0),
                "coins_spent": int(r[4] or 0),
            }

    def _log_admin_action(
        self,
        admin_id: int,
        action: str,
        entity: str | None = None,
        entity_id: int | None = None,
        details_json: str | None = None,
        now_ts: int | None = None,
    ) -> None:
        admin_id = int(admin_id)
        action = str(action or "").strip()
        if not action:
            return
        if now_ts is None:
            now_ts = int(time.time())
        else:
            now_ts = int(now_ts)
        now_iso = dt.datetime.utcfromtimestamp(now_ts).isoformat()
        with self._lock, self._connect() as db:
            try:
                db.execute(
                    "INSERT INTO admin_logs(admin_id, action, entity, entity_id, details_json, created_at_ts, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (
                        admin_id,
                        action,
                        (str(entity) if entity is not None else None),
                        (int(entity_id) if entity_id is not None else None),
                        (str(details_json) if details_json is not None else None),
                        int(now_ts),
                        str(now_iso),
                    ),
                )
            except Exception:
                pass

    def get_user_balances(self, user_id: int) -> dict:
        user_id = int(user_id)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT balance_points, frozen_points, balance_coins, frozen_coins FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"balance_points": 0, "frozen_points": 0, "balance_coins": 0, "frozen_coins": 0}
            return {
                "balance_points": int(row[0] or 0),
                "frozen_points": int(row[1] or 0),
                "balance_coins": int(row[2] or 0),
                "frozen_coins": int(row[3] or 0),
            }

    def try_create_withdrawal_atomic_coins(
        self,
        user_id: int,
        amount_rub: int,
        coins_spent: int,
        bank: str,
        requisites: str,
        now_ts: int | None = None,
    ) -> dict:
        """Create withdrawal and freeze coins atomically.

        Same guards as points-withdrawals:
        - only 1 pending withdrawal at a time
        - at most 1 withdrawal request per last 24 hours

        Returns: {ok, reason, withdrawal_id}
        reasons: bad_args | insufficient | active_exists | rate_limit | db
        """
        user_id = int(user_id)
        amount_rub = int(amount_rub)
        coins_spent = int(coins_spent)
        bank = str(bank or "").strip()
        requisites = str(requisites or "").strip()
        if now_ts is None:
            now_ts = int(time.time())
        else:
            now_ts = int(now_ts)

        if amount_rub <= 0 or coins_spent <= 0 or not bank or not requisites:
            return {"ok": False, "reason": "bad_args"}

        now_iso = dt.datetime.utcfromtimestamp(now_ts).isoformat()
        cutoff_iso = (dt.datetime.utcfromtimestamp(now_ts) - dt.timedelta(hours=24)).isoformat()

        with self._lock, self._connect() as db:
            try:
                db.execute("BEGIN")

                row = db.execute(
                    "SELECT COUNT(*) FROM withdrawals WHERE user_id = ? AND status = 'pending'",
                    (user_id,),
                ).fetchone()
                if row and int(row[0] or 0) > 0:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "active_exists"}

                row2 = db.execute(
                    "SELECT COUNT(*) FROM withdrawals WHERE user_id = ? AND created_at >= ?",
                    (user_id, str(cutoff_iso)),
                ).fetchone()
                if row2 and int(row2[0] or 0) > 0:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "rate_limit"}

                cur = db.execute(
                    "UPDATE users SET balance_coins = balance_coins - ?, frozen_coins = frozen_coins + ? "
                    "WHERE user_id = ? AND balance_coins >= ?",
                    (coins_spent, coins_spent, user_id, coins_spent),
                )
                if int(getattr(cur, "rowcount", 0) or 0) <= 0:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "insufficient"}

                cur2 = db.execute(
                    "INSERT INTO withdrawals(user_id, amount_rub, points_spent, coins_spent, bank, requisites, status, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (user_id, amount_rub, 0, coins_spent, bank, requisites, str(now_iso)),
                )
                wid = int(cur2.lastrowid or 0)
                db.execute("COMMIT")
                return {"ok": True, "withdrawal_id": wid}
            except Exception:
                try:
                    db.execute("ROLLBACK")
                except Exception:
                    pass
                return {"ok": False, "reason": "db"}

    def try_create_withdrawal_atomic(
        self,
        user_id: int,
        amount_rub: int,
        points_spent: int,
        bank: str,
        requisites: str,
        now_ts: int | None = None,
    ) -> dict:
        """Create withdrawal and freeze points atomically.

        Guards:
        - only 1 pending withdrawal at a time
        - at most 1 withdrawal request per last 24 hours

        Returns: {ok, reason, withdrawal_id}
        reasons: bad_args | insufficient | active_exists | rate_limit | db
        """
        user_id = int(user_id)
        amount_rub = int(amount_rub)
        points_spent = int(points_spent)
        bank = str(bank or "").strip()
        requisites = str(requisites or "").strip()
        if now_ts is None:
            now_ts = int(time.time())
        else:
            now_ts = int(now_ts)

        if amount_rub <= 0 or points_spent <= 0 or not bank or not requisites:
            return {"ok": False, "reason": "bad_args"}

        now_iso = dt.datetime.utcfromtimestamp(now_ts).isoformat()
        cutoff_iso = (dt.datetime.utcfromtimestamp(now_ts) - dt.timedelta(hours=24)).isoformat()

        with self._lock, self._connect() as db:
            try:
                db.execute("BEGIN")

                row = db.execute(
                    "SELECT COUNT(*) FROM withdrawals WHERE user_id = ? AND status = 'pending'",
                    (user_id,),
                ).fetchone()
                if row and int(row[0] or 0) > 0:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "active_exists"}

                row2 = db.execute(
                    "SELECT COUNT(*) FROM withdrawals WHERE user_id = ? AND created_at >= ?",
                    (user_id, str(cutoff_iso)),
                ).fetchone()
                if row2 and int(row2[0] or 0) > 0:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "rate_limit"}

                cur = db.execute(
                    "UPDATE users SET balance_points = balance_points - ?, frozen_points = frozen_points + ? "
                    "WHERE user_id = ? AND balance_points >= ?",
                    (points_spent, points_spent, user_id, points_spent),
                )
                if int(getattr(cur, "rowcount", 0) or 0) <= 0:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "insufficient"}

                cur2 = db.execute(
                    "INSERT INTO withdrawals(user_id, amount_rub, points_spent, bank, requisites, status, created_at) VALUES(?, ?, ?, ?, ?, 'pending', ?)",
                    (user_id, amount_rub, points_spent, bank, requisites, str(now_iso)),
                )
                wid = int(cur2.lastrowid or 0)
                db.execute("COMMIT")
                return {"ok": True, "withdrawal_id": wid}
            except Exception:
                try:
                    db.execute("ROLLBACK")
                except Exception:
                    pass
                return {"ok": False, "reason": "db"}

    def finalize_withdrawal_paid(self, withdrawal_id: int, reviewer_id: int, now_ts: int | None = None) -> dict:
        """Mark withdrawal paid and unfreeze points."""
        withdrawal_id = int(withdrawal_id)
        reviewer_id = int(reviewer_id)
        if now_ts is None:
            now_ts = int(time.time())
        else:
            now_ts = int(now_ts)
        now_iso = dt.datetime.utcfromtimestamp(now_ts).isoformat()

        with self._lock, self._connect() as db:
            try:
                db.execute("BEGIN")
                wd = db.execute(
                    "SELECT user_id, points_spent, coins_spent, status FROM withdrawals WHERE withdrawal_id = ?",
                    (withdrawal_id,),
                ).fetchone()
                if not wd:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "not_found"}
                user_id = int(wd[0] or 0)
                points_spent = int(wd[1] or 0)
                coins_spent = int(wd[2] or 0)
                status = str(wd[3] or "")
                if status != "pending":
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "not_pending"}

                db.execute(
                    "UPDATE withdrawals SET status = 'paid', reviewed_at = ?, reviewer_id = ? WHERE withdrawal_id = ?",
                    (str(now_iso), reviewer_id, withdrawal_id),
                )
                db.execute(
                    "UPDATE users SET frozen_points = CASE WHEN frozen_points >= ? THEN frozen_points - ? ELSE 0 END WHERE user_id = ?",
                    (points_spent, points_spent, user_id),
                )
                db.execute(
                    "UPDATE users SET frozen_coins = CASE WHEN frozen_coins >= ? THEN frozen_coins - ? ELSE 0 END WHERE user_id = ?",
                    (coins_spent, coins_spent, user_id),
                )
                db.execute("COMMIT")
            except Exception:
                try:
                    db.execute("ROLLBACK")
                except Exception:
                    pass
                return {"ok": False, "reason": "db"}

        try:
            self._log_admin_action(
                admin_id=reviewer_id,
                action="withdrawal_paid",
                entity="withdrawal",
                entity_id=withdrawal_id,
                details_json=None,
                now_ts=now_ts,
            )
        except Exception:
            pass
        return {"ok": True}

    def finalize_withdrawal_declined(self, withdrawal_id: int, reviewer_id: int, now_ts: int | None = None) -> dict:
        """Decline withdrawal: unfreeze and refund points back to balance."""
        withdrawal_id = int(withdrawal_id)
        reviewer_id = int(reviewer_id)
        if now_ts is None:
            now_ts = int(time.time())
        else:
            now_ts = int(now_ts)
        now_iso = dt.datetime.utcfromtimestamp(now_ts).isoformat()

        with self._lock, self._connect() as db:
            try:
                db.execute("BEGIN")
                wd = db.execute(
                    "SELECT user_id, points_spent, coins_spent, status FROM withdrawals WHERE withdrawal_id = ?",
                    (withdrawal_id,),
                ).fetchone()
                if not wd:
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "not_found"}
                user_id = int(wd[0] or 0)
                points_spent = int(wd[1] or 0)
                coins_spent = int(wd[2] or 0)
                status = str(wd[3] or "")
                if status != "pending":
                    db.execute("ROLLBACK")
                    return {"ok": False, "reason": "not_pending"}

                db.execute(
                    "UPDATE withdrawals SET status = 'declined', reviewed_at = ?, reviewer_id = ? WHERE withdrawal_id = ?",
                    (str(now_iso), reviewer_id, withdrawal_id),
                )
                db.execute(
                    "UPDATE users SET frozen_points = CASE WHEN frozen_points >= ? THEN frozen_points - ? ELSE 0 END, balance_points = balance_points + ? WHERE user_id = ?",
                    (points_spent, points_spent, points_spent, user_id),
                )
                db.execute(
                    "UPDATE users SET frozen_coins = CASE WHEN frozen_coins >= ? THEN frozen_coins - ? ELSE 0 END, balance_coins = balance_coins + ? WHERE user_id = ?",
                    (coins_spent, coins_spent, coins_spent, user_id),
                )
                db.execute("COMMIT")
            except Exception:
                try:
                    db.execute("ROLLBACK")
                except Exception:
                    pass
                return {"ok": False, "reason": "db"}

        try:
            self._log_admin_action(
                admin_id=reviewer_id,
                action="withdrawal_declined",
                entity="withdrawal",
                entity_id=withdrawal_id,
                details_json=None,
                now_ts=now_ts,
            )
        except Exception:
            pass
        return {"ok": True}

    def record_purchase(
        self,
        user_id: int,
        purchase_type: str,
        item_code: str | None,
        points_spent: int,
        qty: int = 1,
        meta_json: str | None = None,
        now_ts: int | None = None,
    ) -> None:
        user_id = int(user_id)
        purchase_type = str(purchase_type or "").strip()
        if not purchase_type:
            return
        points_spent = int(points_spent)
        qty = int(qty)
        if qty <= 0:
            qty = 1
        if now_ts is None:
            now_ts = int(time.time())
        else:
            now_ts = int(now_ts)
        now_iso = dt.datetime.utcfromtimestamp(now_ts).isoformat()
        with self._lock, self._connect() as db:
            try:
                db.execute(
                    "INSERT INTO purchases(user_id, purchase_type, item_code, qty, points_spent, meta_json, created_at_ts, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        purchase_type,
                        (str(item_code) if item_code is not None else None),
                        qty,
                        points_spent,
                        (str(meta_json) if meta_json is not None else None),
                        int(now_ts),
                        str(now_iso),
                    ),
                )
            except Exception:
                pass

    def admin_purchases_summary(self, days: int | None = None, now_ts: int | None = None) -> dict:
        if now_ts is None:
            now_ts = int(time.time())
        else:
            now_ts = int(now_ts)
        since_ts: int | None = None
        if days is not None:
            days = int(days)
            if days > 0:
                since_ts = int(now_ts - days * 86400)

        with self._lock, self._connect() as db:
            if since_ts is None:
                row = db.execute("SELECT COUNT(*), COALESCE(SUM(points_spent), 0) FROM purchases").fetchone()
                last = db.execute(
                    "SELECT purchase_id, user_id, purchase_type, item_code, qty, points_spent, created_at_ts FROM purchases ORDER BY purchase_id DESC LIMIT 5"
                ).fetchall()
            else:
                row = db.execute(
                    "SELECT COUNT(*), COALESCE(SUM(points_spent), 0) FROM purchases WHERE created_at_ts >= ?",
                    (since_ts,),
                ).fetchone()
                last = db.execute(
                    "SELECT purchase_id, user_id, purchase_type, item_code, qty, points_spent, created_at_ts FROM purchases WHERE created_at_ts >= ? ORDER BY purchase_id DESC LIMIT 5",
                    (since_ts,),
                ).fetchall()

        total_cnt = int((row[0] if row else 0) or 0)
        total_pts = int((row[1] if row else 0) or 0)
        items: list[dict] = []
        for r in last or []:
            try:
                items.append(
                    {
                        "purchase_id": int(r[0] or 0),
                        "user_id": int(r[1] or 0),
                        "purchase_type": str(r[2] or ""),
                        "item_code": (str(r[3]) if r[3] is not None else None),
                        "qty": int(r[4] or 0),
                        "points_spent": int(r[5] or 0),
                        "created_at_ts": int(r[6] or 0),
                    }
                )
            except Exception:
                pass
        return {"count": total_cnt, "points": total_pts, "last": items}

    def admin_get_purchase(self, purchase_id: int) -> dict | None:
        purchase_id = int(purchase_id)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT purchase_id, user_id, purchase_type, item_code, qty, points_spent, meta_json, created_at FROM purchases WHERE purchase_id = ?",
                (purchase_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "purchase_id": int(row[0] or 0),
                "user_id": int(row[1] or 0),
                "purchase_type": str(row[2] or ""),
                "item_code": (str(row[3]) if row[3] is not None else None),
                "qty": int(row[4] or 0),
                "points_spent": int(row[5] or 0),
                "meta_json": (str(row[6]) if row[6] is not None else None),
                "created_at": str(row[7] or ""),
            }

    def admin_list_purchases_by_user(self, user_id: int, limit: int = 10) -> list[dict]:
        user_id = int(user_id)
        limit = int(limit)
        if limit <= 0 or limit > 50:
            limit = 10
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT purchase_id, purchase_type, item_code, qty, points_spent, created_at FROM purchases WHERE user_id = ? ORDER BY purchase_id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        items: list[dict] = []
        for r in rows or []:
            try:
                items.append(
                    {
                        "purchase_id": int(r[0] or 0),
                        "purchase_type": str(r[1] or ""),
                        "item_code": (str(r[2]) if r[2] is not None else None),
                        "qty": int(r[3] or 0),
                        "points_spent": int(r[4] or 0),
                        "created_at": str(r[5] or ""),
                    }
                )
            except Exception:
                pass
        return items

    def admin_list_purchases_period(self, start_ts: int, end_ts: int, limit: int = 20) -> list[dict]:
        start_ts = int(start_ts)
        end_ts = int(end_ts)
        limit = int(limit)
        if limit <= 0 or limit > 100:
            limit = 20
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT purchase_id, user_id, purchase_type, item_code, qty, points_spent, created_at FROM purchases WHERE created_at_ts >= ? AND created_at_ts <= ? ORDER BY purchase_id DESC LIMIT ?",
                (start_ts, end_ts, limit),
            ).fetchall()
        items: list[dict] = []
        for r in rows or []:
            try:
                items.append(
                    {
                        "purchase_id": int(r[0] or 0),
                        "user_id": int(r[1] or 0),
                        "purchase_type": str(r[2] or ""),
                        "item_code": (str(r[3]) if r[3] is not None else None),
                        "qty": int(r[4] or 0),
                        "points_spent": int(r[5] or 0),
                        "created_at": str(r[6] or ""),
                    }
                )
            except Exception:
                pass
        return items

    def list_users_count(self) -> dict:
        with self._lock, self._connect() as db:
            r = db.execute("SELECT COUNT(*), SUM(CASE WHEN blocked = 0 THEN 1 ELSE 0 END) FROM users").fetchone()
            total = int(r[0]) if r and r[0] is not None else 0
            active = int(r[1]) if r and r[1] is not None else 0
            r2 = db.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'paid'").fetchone()
            paid_cnt = int(r2[0]) if r2 and r2[0] is not None else 0
            return {"total": total, "active": active, "paid": paid_cnt}

    def list_user_ids(self, *, active_only: bool = True, limit: int = 500, offset: int = 0) -> list[int]:
        """Return user IDs for bulk operations (e.g., scheduled notifications).

        Notes:
        - `active_only=True` filters out blocked users.
        - Result is ordered deterministically.
        """
        where = "WHERE blocked = 0" if bool(active_only) else ""
        sql = f"SELECT user_id FROM users {where} ORDER BY created_at DESC, user_id DESC LIMIT ? OFFSET ?"
        with self._lock, self._connect() as db:
            rows = db.execute(sql, (int(limit), int(offset))).fetchall() or []
            out: list[int] = []
            for r in rows:
                try:
                    out.append(int(r[0]))
                except Exception:
                    continue
            return out

    # --- Admin statistics (aggregates) ---

    def admin_stats_users(self, *, now_ts: int, since_iso: str) -> dict:
        """Return user aggregates for admin statistics."""
        now_ts = int(now_ts)
        since_iso = str(since_iso)
        with self._lock, self._connect() as db:
            r = db.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN blocked = 0 THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN blocked = 1 THEN 1 ELSE 0 END) AS blocked,
                    SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS new_since,
                    SUM(CASE WHEN COALESCE(vip_until, 0) > ? THEN 1 ELSE 0 END) AS vip_active,
                    COALESCE(SUM(balance_points), 0) AS balances_sum,
                    COALESCE(MAX(balance_points), 0) AS balance_max
                FROM users
                """,
                (since_iso, now_ts),
            ).fetchone()
            if not r:
                return {
                    "total": 0,
                    "active": 0,
                    "blocked": 0,
                    "new_since": 0,
                    "vip_active": 0,
                    "balances_sum": 0,
                    "balance_max": 0,
                }
            return {
                "total": int(r[0] or 0),
                "active": int(r[1] or 0),
                "blocked": int(r[2] or 0),
                "new_since": int(r[3] or 0),
                "vip_active": int(r[4] or 0),
                "balances_sum": int(r[5] or 0),
                "balance_max": int(r[6] or 0),
            }

    def admin_stats_withdrawals(self, *, since_iso: str) -> dict:
        """Return withdrawals/finance aggregates for admin statistics."""
        since_iso = str(since_iso)
        with self._lock, self._connect() as db:
            r = db.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid_cnt,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_cnt,
                    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_cnt,
                    COALESCE(SUM(CASE WHEN status = 'paid' THEN points_spent ELSE 0 END), 0) AS paid_points,
                    COALESCE(SUM(CASE WHEN status = 'paid' THEN amount_rub ELSE 0 END), 0) AS paid_rub,
                    COALESCE(SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END), 0) AS new_since
                FROM withdrawals
                """,
                (since_iso,),
            ).fetchone()
            if not r:
                return {
                    "total": 0,
                    "paid_cnt": 0,
                    "pending_cnt": 0,
                    "rejected_cnt": 0,
                    "paid_points": 0,
                    "paid_rub": 0,
                    "new_since": 0,
                }
            return {
                "total": int(r[0] or 0),
                "paid_cnt": int(r[1] or 0),
                "pending_cnt": int(r[2] or 0),
                "rejected_cnt": int(r[3] or 0),
                "paid_points": int(r[4] or 0),
                "paid_rub": int(r[5] or 0),
                "new_since": int(r[6] or 0),
            }

    def admin_stats_mines(self, *, since_ts: int) -> dict:
        """Return Mines aggregates (persistent rounds)."""
        since_ts = int(since_ts)
        with self._lock, self._connect() as db:
            r = db.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status IN ('active','created') AND ended_at IS NULL THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN status = 'cashed_out' THEN 1 ELSE 0 END) AS cashed_out,
                    SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) AS lost,
                    SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) AS timeout,
                    COALESCE(SUM(bet_points), 0) AS bet_sum,
                    COALESCE(SUM(CASE WHEN status = 'cashed_out' THEN win_points ELSE 0 END), 0) AS payout_sum,
                    COALESCE(SUM(CASE WHEN status = 'cashed_out' THEN (win_points - bet_points) ELSE 0 END), 0) AS profit_sum,
                    SUM(CASE WHEN started_at >= ? THEN 1 ELSE 0 END) AS started_since
                FROM game_rounds
                WHERE game = 'mines'
                """,
                (since_ts,),
            ).fetchone()

            r2 = db.execute(
                """
                SELECT
                    SUM(CASE WHEN mode = 'nobet' THEN 1 ELSE 0 END) AS nobet_total,
                    SUM(CASE WHEN mode != 'nobet' THEN 1 ELSE 0 END) AS stake_total
                FROM game_rounds
                WHERE game = 'mines'
                """
            ).fetchone()

            if not r:
                r = [0] * 9
            if not r2:
                r2 = [0, 0]

            return {
                "total": int(r[0] or 0),
                "active": int(r[1] or 0),
                "cashed_out": int(r[2] or 0),
                "lost": int(r[3] or 0),
                "timeout": int(r[4] or 0),
                "bet_sum": int(r[5] or 0),
                "payout_sum": int(r[6] or 0),
                "profit_sum": int(r[7] or 0),
                "started_since": int(r[8] or 0),
                "nobet_total": int(r2[0] or 0),
                "stake_total": int(r2[1] or 0),
            }

    def admin_stats_wheel(self) -> dict:
        """Return Wheel aggregates (stored on users table)."""
        with self._lock, self._connect() as db:
            r = db.execute(
                """
                SELECT
                    COALESCE(SUM(wheel_rolls), 0) AS rolls,
                    COALESCE(SUM(wheel_total_win), 0) AS win_sum,
                    COALESCE(MAX(wheel_best_win), 0) AS best_win,
                    SUM(CASE WHEN COALESCE(wheel_rolls, 0) > 0 THEN 1 ELSE 0 END) AS players
                FROM users
                """
            ).fetchone()
            if not r:
                return {"rolls": 0, "win_sum": 0, "best_win": 0, "players": 0}
            return {
                "rolls": int(r[0] or 0),
                "win_sum": int(r[1] or 0),
                "best_win": int(r[2] or 0),
                "players": int(r[3] or 0),
            }

    def admin_stats_duels(self, *, since_iso: str) -> dict:
        """Return duel aggregates (from duels + user counters)."""
        since_iso = str(since_iso)
        with self._lock, self._connect() as db:
            r = db.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'waiting' THEN 1 ELSE 0 END) AS waiting,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved,
                    COALESCE(SUM(stake), 0) AS stake_sum,
                    SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS created_since
                FROM duels
                """,
                (since_iso,),
            ).fetchone()

            r2 = db.execute(
                """
                SELECT
                    COALESCE(SUM(duel_games), 0) AS games,
                    COALESCE(SUM(duel_wins), 0) AS wins,
                    COALESCE(SUM(duel_losses), 0) AS losses,
                    COALESCE(MAX(duel_mmr), 0) AS best_mmr
                FROM users
                """
            ).fetchone()

            if not r:
                r = [0] * 6
            if not r2:
                r2 = [0, 0, 0, 0]

            return {
                "total": int(r[0] or 0),
                "waiting": int(r[1] or 0),
                "active": int(r[2] or 0),
                "resolved": int(r[3] or 0),
                "stake_sum": int(r[4] or 0),
                "created_since": int(r[5] or 0),
                "user_games": int(r2[0] or 0),
                "user_wins": int(r2[1] or 0),
                "user_losses": int(r2[2] or 0),
                "best_mmr": int(r2[3] or 0),
            }

    def admin_stats_farm(self, *, now_ts: int, since_ts: int) -> dict:
        """Return CryptoMine farm aggregates (stored on users table)."""
        now_ts = int(now_ts)
        since_ts = int(since_ts)
        with self._lock, self._connect() as db:
            r = db.execute(
                """
                SELECT
                    SUM(CASE WHEN COALESCE(mining_initialized, 0) = 1 THEN 1 ELSE 0 END) AS farms,
                    SUM(CASE WHEN COALESCE(mining_active, 0) = 1 THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN COALESCE(mining_locked_until, 0) > ? THEN 1 ELSE 0 END) AS locked,
                    COALESCE(SUM(COALESCE(mining_total_btc, 0)), 0) AS total_btc,
                    COALESCE(SUM(COALESCE(mining_btc, 0)), 0) AS current_btc,
                    SUM(CASE WHEN COALESCE(mining_last_ts, 0) >= ? THEN 1 ELSE 0 END) AS active_since
                FROM users
                """,
                (now_ts, since_ts),
            ).fetchone()
            if not r:
                return {
                    "farms": 0,
                    "active": 0,
                    "locked": 0,
                    "total_btc": 0.0,
                    "current_btc": 0.0,
                    "active_since": 0,
                }
            return {
                "farms": int(r[0] or 0),
                "active": int(r[1] or 0),
                "locked": int(r[2] or 0),
                "total_btc": float(r[3] or 0.0),
                "current_btc": float(r[4] or 0.0),
                "active_since": int(r[5] or 0),
            }

    def admin_stats_activity(self, *, since_ts: int, since_iso: str) -> dict:
        """Return last-24h activity signals across key modules."""
        since_ts = int(since_ts)
        since_iso = str(since_iso)
        with self._lock, self._connect() as db:
            r_users = db.execute(
                "SELECT SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) FROM users",
                (since_iso,),
            ).fetchone()
            new_users = int(r_users[0] or 0) if r_users else 0

            r_farm = db.execute(
                "SELECT SUM(CASE WHEN COALESCE(last_farm_time, 0) >= ? THEN 1 ELSE 0 END) FROM users",
                (since_ts,),
            ).fetchone()
            farm_active = int(r_farm[0] or 0) if r_farm else 0

            r_mining = db.execute(
                "SELECT SUM(CASE WHEN COALESCE(mining_last_ts, 0) >= ? THEN 1 ELSE 0 END) FROM users",
                (since_ts,),
            ).fetchone()
            mining_active = int(r_mining[0] or 0) if r_mining else 0

            r_mines = db.execute(
                "SELECT COUNT(*) FROM game_rounds WHERE game = 'mines' AND started_at >= ?",
                (since_ts,),
            ).fetchone()
            mines_rounds = int(r_mines[0] or 0) if r_mines else 0

            r_dialog = db.execute(
                "SELECT COUNT(*) FROM dialog_messages WHERE sent_at >= ?",
                (since_ts,),
            ).fetchone()
            dialog_msgs = int(r_dialog[0] or 0) if r_dialog else 0

            r_withdraw = db.execute(
                "SELECT COUNT(*) FROM withdrawals WHERE created_at >= ?",
                (since_iso,),
            ).fetchone()
            withdrawals = int(r_withdraw[0] or 0) if r_withdraw else 0

            return {
                "new_users": int(new_users),
                "farm_active": int(farm_active),
                "mining_active": int(mining_active),
                "mines_rounds": int(mines_rounds),
                "dialog_msgs": int(dialog_msgs),
                "withdrawals": int(withdrawals),
            }

    # -------------------------
    # Weekly events (gifts)
    # -------------------------

    def _weekly_events_week_index(self, *, now_ts: int) -> int:
        now_ts = int(now_ts)
        try:
            d = dt.datetime.utcfromtimestamp(now_ts).date()
        except Exception:
            d = dt.datetime.utcnow().date()
        delta_days = (d - self._weekly_events_epoch).days
        if delta_days < 0:
            return 0
        return int(delta_days // 7)

    @staticmethod
    def _weekly_events_perm_for_user(user_id: int) -> list[int]:
        """Deterministic per-user permutation of [1..4]."""
        seed = hashlib.sha256(f"weekly_events:v1:{int(user_id)}".encode("utf-8")).hexdigest()
        rng = random.Random(int(seed, 16))
        perm = [1, 2, 3, 4]
        rng.shuffle(perm)
        return perm

    def get_weekly_event_state(self, user_id: int, *, now_ts: int) -> dict:
        """Return weekly event assignment for current week and whether it's claimed.

        Guarantees a stable (user_id, week_index) row in weekly_event_claims.
        """
        user_id = int(user_id)
        now_ts = int(now_ts)
        week_index = self._weekly_events_week_index(now_ts=now_ts)
        perm = self._weekly_events_perm_for_user(user_id)
        event_id = int(perm[int(week_index) % 4])

        with self._lock, self._connect() as db:
            try:
                # Ensure user exists (best-effort)
                db.execute(
                    "INSERT OR IGNORE INTO users(user_id, created_at) VALUES(?, ?)",
                    (user_id, dt.datetime.utcnow().isoformat()),
                )
            except Exception:
                pass

            # Create row if not exists
            try:
                db.execute(
                    """
                    INSERT OR IGNORE INTO weekly_event_claims(user_id, week_index, event_id, claimed)
                    VALUES(?, ?, ?, 0)
                    """,
                    (user_id, int(week_index), int(event_id)),
                )
            except Exception:
                pass

            row = db.execute(
                "SELECT event_id, claimed, notified_at_ts, mood_emoji, reward_points FROM weekly_event_claims WHERE user_id = ? AND week_index = ?",
                (user_id, int(week_index)),
            ).fetchone()

            if not row:
                return {
                    "user_id": user_id,
                    "week_index": int(week_index),
                    "event_id": int(event_id),
                    "claimed": 0,
                    "notified_at_ts": None,
                    "mood_emoji": None,
                    "reward_points": None,
                }

            return {
                "user_id": user_id,
                "week_index": int(week_index),
                "event_id": int(row[0] or event_id),
                "claimed": int(row[1] or 0),
                "notified_at_ts": int(row[2]) if row[2] is not None else None,
                "mood_emoji": row[3],
                "reward_points": int(row[4]) if row[4] is not None else None,
            }

    def mark_weekly_event_notified(self, user_id: int, *, week_index: int, now_ts: int) -> None:
        """Mark the current weekly event as notified (so we won't auto-send again)."""
        user_id = int(user_id)
        week_index = int(week_index)
        now_ts = int(now_ts)
        with self._lock, self._connect() as db:
            try:
                db.execute(
                    "UPDATE weekly_event_claims SET notified_at_ts = ? WHERE user_id = ? AND week_index = ? AND (notified_at_ts IS NULL)",
                    (now_ts, user_id, week_index),
                )
            except Exception:
                pass

    def claim_weekly_event(
        self,
        user_id: int,
        *,
        week_index: int,
        event_id: int,
        now_ts: int,
        mood_emoji: str | None = None,
        reward_points: int | None = None,
    ) -> dict:
        """Atomically mark the weekly event as claimed and add reward points (with XP/level).

        Returns: {ok, reason, reward_points, leveled_up, new_title}
        """
        user_id = int(user_id)
        week_index = int(week_index)
        event_id = int(event_id)
        now_ts = int(now_ts)

        if event_id not in {1, 2, 3, 4}:
            return {"ok": False, "reason": "bad_event"}

        if reward_points is None:
            # Default rewards (caller may override)
            if event_id in {1, 2}:
                reward_points = int(secrets.choice([1000, 3000, 5000, 7000]))
            elif event_id == 3:
                reward_points = 5000
            else:
                reward_points = 7000

        reward_points = int(reward_points)
        if reward_points <= 0:
            return {"ok": False, "reason": "bad_reward"}

        now_iso = dt.datetime.utcnow().isoformat()

        with self._lock, self._connect() as db:
            # Ensure row exists and matches expected event_id
            try:
                db.execute(
                    "INSERT OR IGNORE INTO weekly_event_claims(user_id, week_index, event_id, claimed) VALUES(?, ?, ?, 0)",
                    (user_id, week_index, event_id),
                )
            except Exception:
                pass

            row = db.execute(
                "SELECT event_id, claimed FROM weekly_event_claims WHERE user_id = ? AND week_index = ?",
                (user_id, week_index),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_row"}

            stored_event_id = int(row[0] or 0)
            if stored_event_id != int(event_id):
                return {"ok": False, "reason": "event_mismatch"}
            if int(row[1] or 0) == 1:
                return {"ok": False, "reason": "already_claimed"}

            # Apply reward with XP/level
            u = db.execute("SELECT experience FROM users WHERE user_id = ?", (user_id,)).fetchone()
            old_xp = int(u[0] or 0) if u else 0
            old_level = self.level_from_xp(old_xp)

            xp_added = int(reward_points)
            new_xp = old_xp + xp_added
            new_level = self.level_from_xp(new_xp)

            db.execute(
                "UPDATE users SET balance_points = balance_points + ?, experience = ?, level = ? WHERE user_id = ?",
                (int(reward_points), int(new_xp), int(new_level), user_id),
            )
            try:
                db.execute(
                    "INSERT INTO experience_history(user_id, amount, source, description, created_at) VALUES(?, ?, ?, ?, ?)",
                    (user_id, int(xp_added), "weekly_event", None, now_iso),
                )
            except Exception:
                pass

            # Achievements may award extra points
            try:
                self._award_achievements_in_conn(db, user_id, now=now_iso)
            except Exception:
                pass

            db.execute(
                """
                UPDATE weekly_event_claims
                SET claimed = 1, claimed_at_ts = ?, mood_emoji = ?, reward_points = ?
                WHERE user_id = ? AND week_index = ? AND claimed = 0
                """,
                (now_ts, None if mood_emoji is None else str(mood_emoji), int(reward_points), user_id, week_index),
            )

            # Return final title
            final_row = db.execute("SELECT experience FROM users WHERE user_id = ?", (user_id,)).fetchone()
            final_xp = int(final_row[0] or new_xp) if final_row else int(new_xp)
            final_level = self.level_from_xp(final_xp)

            return {
                "ok": True,
                "reason": "ok",
                "reward_points": int(reward_points),
                "old_level": int(old_level),
                "new_level": int(final_level),
                "leveled_up": bool(int(final_level) > int(old_level)),
                "new_title": self.get_level_title(int(final_level)),
            }

    def find_user(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            r = db.execute(
                "SELECT user_id, username, balance_points, blocked FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not r:
                return None
            return {"user_id": int(r[0]), "username": r[1], "balance_points": int(r[2]), "blocked": int(r[3])}

    def count_users_filtered(self, *, blocked_only: bool = False, query: str | None = None) -> int:
        where: list[str] = []
        params: list[object] = []

        if bool(blocked_only):
            where.append("blocked = 1")

        q = (query or "").strip()
        if q:
            if q.startswith("@"):  # allow @username input
                q = q[1:].strip()

            if q.isdigit():
                where.append("user_id = ?")
                params.append(int(q))
            else:
                where.append("LOWER(COALESCE(username, '')) LIKE ?")
                params.append(f"%{q.lower()}%")

        sql = "SELECT COUNT(*) FROM users"
        if where:
            sql += " WHERE " + " AND ".join(where)

        with self._lock, self._connect() as db:
            r = db.execute(sql, tuple(params)).fetchone()
            return int(r[0]) if r and r[0] is not None else 0

    def list_users_filtered(
        self,
        *,
        blocked_only: bool = False,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        where: list[str] = []
        params: list[object] = []

        if bool(blocked_only):
            where.append("blocked = 1")

        q = (query or "").strip()
        if q:
            if q.startswith("@"):  # allow @username input
                q = q[1:].strip()

            if q.isdigit():
                where.append("user_id = ?")
                params.append(int(q))
            else:
                where.append("LOWER(COALESCE(username, '')) LIKE ?")
                params.append(f"%{q.lower()}%")

        sql = (
            "SELECT user_id, username, balance_points, blocked, created_at "
            "FROM users"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC, user_id DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])

        with self._lock, self._connect() as db:
            rows = db.execute(sql, tuple(params)).fetchall() or []
            out: list[dict] = []
            for r in rows:
                out.append(
                    {
                        "user_id": int(r[0]),
                        "username": r[1],
                        "balance_points": int(r[2] or 0),
                        "blocked": int(r[3] or 0),
                        "created_at": str(r[4] or ""),
                    }
                )
            return out

    def maybe_reward_referral_on_first_approval(self, invitee_id: int, bonus_points: int) -> int | None:
        """If invitee has inviter and not yet rewarded, reward inviter and return inviter_id."""
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT inviter_id, rewarded FROM referral_rewards WHERE invitee_id = ?",
                (invitee_id,),
            ).fetchone()
            if not row:
                return None
            inviter_id = int(row[0])
            rewarded = int(row[1])
            if rewarded:
                return None
            db.execute("UPDATE referral_rewards SET rewarded = 1 WHERE invitee_id = ?", (invitee_id,))
            inv_row = db.execute("SELECT experience FROM users WHERE user_id = ?", (inviter_id,)).fetchone()
            old_xp = int(inv_row[0] or 0) if inv_row else 0
            old_level = self.level_from_xp(old_xp)
            new_xp = old_xp + int(bonus_points)
            new_level = self.level_from_xp(new_xp)
            db.execute(
                "UPDATE users SET balance_points = balance_points + ?, experience = ?, level = ? WHERE user_id = ?",
                (int(bonus_points), int(new_xp), int(new_level), inviter_id),
            )
            return inviter_id

    # --- Mines rounds persistence (modes: classic|hardcore|nobet) ---

    def mines_check_and_inc_rate_limit(self, user_id: int, *, now_ts: int, max_rounds_per_minute: int) -> bool:
        now_ts = int(now_ts)
        window = int(now_ts // 60)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT mines_rate_window_ts, mines_rounds_in_window FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return False
            current_window = int(row[0] or 0)
            current_cnt = int(row[1] or 0)
            if current_window != window:
                current_window = window
                current_cnt = 0
            if current_cnt >= int(max_rounds_per_minute):
                return False
            current_cnt += 1
            db.execute(
                "UPDATE users SET mines_rate_window_ts = ?, mines_rounds_in_window = ? WHERE user_id = ?",
                (int(current_window), int(current_cnt), int(user_id)),
            )
            return True

    def mines_get_energy(self, user_id: int, *, today: str, attempts_per_day: int) -> dict | None:
        attempts_per_day = int(attempts_per_day)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT mines_energy_date, mines_energy_used FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return None
            d = str(row[0] or "")
            used = int(row[1] or 0)
            if d != str(today):
                used = 0
            remaining = max(0, attempts_per_day - used)
            return {"date": str(today), "used": used, "remaining": remaining, "limit": attempts_per_day}

    def mines_consume_energy(self, user_id: int, *, today: str, attempts_per_day: int) -> dict:
        attempts_per_day = int(attempts_per_day)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT mines_energy_date, mines_energy_used FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}
            d = str(row[0] or "")
            used = int(row[1] or 0)
            if d != str(today):
                d = str(today)
                used = 0
            if used >= attempts_per_day:
                return {"ok": False, "reason": "no_energy", "remaining": 0, "used": used, "limit": attempts_per_day}
            used_new = used + 1
            db.execute(
                "UPDATE users SET mines_energy_date = ?, mines_energy_used = ? WHERE user_id = ?",
                (str(d), int(used_new), int(user_id)),
            )
            remaining = max(0, attempts_per_day - used_new)
            return {"ok": True, "reason": "ok", "remaining": remaining, "used": used_new, "limit": attempts_per_day}

    def mines_get_nobet_caps(self, user_id: int, *, today: str) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT mines_nobet_points_date, mines_nobet_points_earned, mines_nobet_xp_date, mines_nobet_xp_earned FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return None
            p_date = str(row[0] or "")
            p_earned = int(row[1] or 0)
            x_date = str(row[2] or "")
            x_earned = int(row[3] or 0)
            if p_date != str(today):
                p_earned = 0
            if x_date != str(today):
                x_earned = 0
            return {"date": str(today), "points_earned": p_earned, "xp_earned": x_earned}

    def mines_add_nobet_rewards(self, user_id: int, *, today: str, add_points: int, add_xp: int, cap_points: int, cap_xp: int) -> dict:
        add_points = max(0, int(add_points))
        add_xp = max(0, int(add_xp))
        cap_points = max(0, int(cap_points))
        cap_xp = max(0, int(cap_xp))

        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT mines_nobet_points_date, mines_nobet_points_earned, mines_nobet_xp_date, mines_nobet_xp_earned FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}

            p_date = str(row[0] or "")
            p_earned = int(row[1] or 0)
            x_date = str(row[2] or "")
            x_earned = int(row[3] or 0)
            if p_date != str(today):
                p_date = str(today)
                p_earned = 0
            if x_date != str(today):
                x_date = str(today)
                x_earned = 0

            p_left = max(0, cap_points - p_earned)
            x_left = max(0, cap_xp - x_earned)
            p_add = min(p_left, add_points)
            x_add = min(x_left, add_xp)

            db.execute(
                "UPDATE users SET mines_nobet_points_date = ?, mines_nobet_points_earned = ?, mines_nobet_xp_date = ?, mines_nobet_xp_earned = ? WHERE user_id = ?",
                (
                    str(p_date),
                    int(p_earned + p_add),
                    str(x_date),
                    int(x_earned + x_add),
                    int(user_id),
                ),
            )

            return {
                "ok": True,
                "reason": "ok",
                "points_added": int(p_add),
                "xp_added": int(x_add),
                "points_total_today": int(p_earned + p_add),
                "xp_total_today": int(x_earned + x_add),
            }

    def mines_get_profit_state(self, user_id: int, *, today: str) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT mines_profit_date, mines_profit_points FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return None
            d = str(row[0] or "")
            p = int(row[1] or 0)
            if d != str(today):
                p = 0
            return {"date": str(today), "profit_points": int(p)}

    def mines_add_profit(self, user_id: int, *, today: str, profit_delta: int, profit_cap: int) -> dict:
        profit_delta = int(profit_delta)
        profit_cap = int(profit_cap)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT mines_profit_date, mines_profit_points FROM users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "no_user"}

            d = str(row[0] or "")
            p = int(row[1] or 0)
            if d != str(today):
                d = str(today)
                p = 0

            # We only track positive profit; negative profit doesn't increase the cap.
            if profit_delta <= 0:
                return {"ok": True, "reason": "ok", "profit_today": p, "left": max(0, profit_cap - p)}

            left = max(0, profit_cap - p)
            applied = min(left, profit_delta)
            new_p = p + applied
            db.execute(
                "UPDATE users SET mines_profit_date = ?, mines_profit_points = ? WHERE user_id = ?",
                (str(d), int(new_p), int(user_id)),
            )
            return {"ok": True, "reason": "ok", "applied": int(applied), "profit_today": int(new_p), "left": max(0, profit_cap - new_p)}

    def create_mines_round(
        self,
        user_id: int,
        *,
        mode: str,
        size: int,
        mines: int,
        bet_points: int,
        extra_cost_points: int = 0,
        energy_spent: int,
        now_ts: int,
        client_seed: str | None = None,
        tournament_id: int | None = None,
        tournament_match_id: int | None = None,
        tournament_game_index: int | None = None,
    ) -> dict:
        """Create a persistent Mines round and (for stake modes) deduct bet_points atomically.

        mine_cells are generated deterministically from (server_seed, client_seed, round_id).
        """

        mode = str(mode)
        size = int(size)
        mines = int(mines)
        bet_points = int(bet_points)
        extra_cost_points = int(extra_cost_points)
        energy_spent = int(energy_spent)
        now_ts = int(now_ts)

        server_seed = secrets.token_hex(16)
        server_seed_hash = hashlib.sha256(server_seed.encode("utf-8")).hexdigest()
        if client_seed is None:
            client_seed = f"{int(user_id)}:{now_ts}"
        client_seed = str(client_seed)

        with self._lock, self._connect() as db:
            # Ensure user exists
            u = db.execute("SELECT balance_points FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            if not u:
                return {"ok": False, "reason": "no_user"}

            total_cost = max(0, int(bet_points) + int(extra_cost_points))
            if total_cost > 0:
                bal = int(u[0] or 0)
                if bal < total_cost:
                    return {"ok": False, "reason": "insufficient"}
                db.execute(
                    "UPDATE users SET balance_points = balance_points - ? WHERE user_id = ?",
                    (int(total_cost), int(user_id)),
                )

            # Create row first to get round_id
            db.execute(
                """
                INSERT INTO game_rounds(
                    user_id, game, mode, bet_points, energy_spent, size, mines,
                    mine_cells, opened_cells, status, multiplier, win_points, xp_earned,
                    started_at, client_seed, server_seed_hash, server_seed,
                    tournament_id, tournament_match_id, tournament_game_index
                ) VALUES(?, 'mines', ?, ?, ?, ?, ?, ?, ?, 'active', 1.0, 0, 0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id),
                    mode,
                    int(bet_points),
                    int(energy_spent),
                    int(size),
                    int(mines),
                    "[]",
                    "[]",
                    int(now_ts),
                    client_seed,
                    server_seed_hash,
                    server_seed,
                    None if tournament_id is None else int(tournament_id),
                    None if tournament_match_id is None else int(tournament_match_id),
                    None if tournament_game_index is None else int(tournament_game_index),
                ),
            )
            round_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])

            # Deterministic mine placement
            seed_material = f"{server_seed}:{client_seed}:{round_id}"
            digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
            seed_int = int(digest, 16)
            rng = random.Random(seed_int)
            total = size * size
            mine_cells = sorted(rng.sample(range(1, total + 1), mines))

            db.execute(
                "UPDATE game_rounds SET mine_cells = ? WHERE round_id = ?",
                (json.dumps(mine_cells, ensure_ascii=False), int(round_id)),
            )

            return {
                "ok": True,
                "reason": "ok",
                "round_id": int(round_id),
                "server_seed_hash": str(server_seed_hash),
                "client_seed": str(client_seed),
            }

    def get_mines_round(self, round_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT round_id, user_id, mode, bet_points, energy_spent, size, mines,
                       mine_cells, opened_cells, status, multiplier, win_points, xp_earned,
                       started_at, ended_at, client_seed, server_seed_hash, server_seed,
                       tournament_id, tournament_match_id, tournament_game_index
                FROM game_rounds
                WHERE round_id = ? AND game = 'mines'
                """,
                (int(round_id),),
            ).fetchone()
            return dict(row) if row else None

    def get_active_mines_round(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT round_id, user_id, mode, bet_points, energy_spent, size, mines,
                       mine_cells, opened_cells, status, multiplier, win_points, xp_earned,
                       started_at, ended_at, client_seed, server_seed_hash, server_seed,
                       tournament_id, tournament_match_id, tournament_game_index
                FROM game_rounds
                WHERE user_id = ? AND game = 'mines' AND status IN ('active','created') AND ended_at IS NULL
                ORDER BY round_id DESC
                LIMIT 1
                """,
                (int(user_id),),
            ).fetchone()
            return dict(row) if row else None

    def update_mines_round(
        self,
        round_id: int,
        *,
        opened_cells: list[int] | None = None,
        status: str | None = None,
        multiplier: float | None = None,
        win_points: int | None = None,
        xp_earned: int | None = None,
        ended_at: int | None = None,
        reveal_server_seed: bool = False,
        server_seed: str | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[object] = []

        if opened_cells is not None:
            sets.append("opened_cells = ?")
            params.append(json.dumps([int(x) for x in opened_cells], ensure_ascii=False))
        if status is not None:
            sets.append("status = ?")
            params.append(str(status))
        if multiplier is not None:
            sets.append("multiplier = ?")
            params.append(float(multiplier))
        if win_points is not None:
            sets.append("win_points = ?")
            params.append(int(win_points))
        if xp_earned is not None:
            sets.append("xp_earned = ?")
            params.append(int(xp_earned))
        if ended_at is not None:
            sets.append("ended_at = ?")
            params.append(int(ended_at))
        if reveal_server_seed:
            sets.append("server_seed = ?")
            params.append(None if server_seed is None else str(server_seed))

        if not sets:
            return

        with self._lock, self._connect() as db:
            params.append(int(round_id))
            db.execute(
                f"UPDATE game_rounds SET {', '.join(sets)} WHERE round_id = ? AND game = 'mines'",
                tuple(params),
            )

    def reveal_mines_server_seed(self, round_id: int, *, server_seed: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE game_rounds SET server_seed = ? WHERE round_id = ? AND game = 'mines'",
                (str(server_seed), int(round_id)),
            )

    def get_mines_server_seed_hash(self, round_id: int) -> str | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT server_seed_hash FROM game_rounds WHERE round_id = ? AND game = 'mines'",
                (int(round_id),),
            ).fetchone()
            return str(row[0]) if row and row[0] else None

    def get_mines_server_seed_plain(self, round_id: int) -> str | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT server_seed FROM game_rounds WHERE round_id = ? AND game = 'mines'",
                (int(round_id),),
            ).fetchone()
            return str(row[0]) if row and row[0] else None

    # -------------------------
    # Tournaments (MVP)
    # -------------------------

    @staticmethod
    def _tour_next_pow2(n: int) -> int:
        n = int(n)
        if n <= 1:
            return 1
        return 1 << (n - 1).bit_length()

    def create_tournament(
        self,
        *,
        created_by_admin_id: int,
        games: list[str],
        max_players: int,
        prize_pool_points: int,
        entry_fee_points: int,
        prize: dict,
        start_at: int,
        rules: dict | None = None,
    ) -> dict:
        games = [str(x) for x in (games or [])]
        if not games:
            return {"ok": False, "reason": "no_games"}
        max_players = int(max_players)
        if max_players <= 1:
            return {"ok": False, "reason": "bad_max_players"}
        prize_pool_points = int(prize_pool_points)
        entry_fee_points = int(entry_fee_points)
        start_at = int(start_at)
        now_ts = int(time.time())

        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO tournaments(
                    created_by_admin_id, games_json, max_players, entry_fee_points,
                    prize_pool_points, prize_json, rules_json, state, start_at, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 'registering', ?, ?)
                """,
                (
                    int(created_by_admin_id),
                    json.dumps(games, ensure_ascii=False),
                    int(max_players),
                    int(max(0, entry_fee_points)),
                    int(max(0, prize_pool_points)),
                    json.dumps(prize or {}, ensure_ascii=False),
                    None if rules is None else json.dumps(rules, ensure_ascii=False),
                    int(start_at),
                    int(now_ts),
                ),
            )
            tid = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
            return {"ok": True, "tournament_id": tid}

    def list_tournaments(self, *, states: tuple[str, ...] = ("registering", "running"), limit: int = 10) -> list[dict]:
        limit = max(1, int(limit))
        with self._lock, self._connect() as db:
            placeholders = ",".join("?" for _ in states)
            rows = db.execute(
                f"SELECT id, games_json, max_players, entry_fee_points, prize_pool_points, prize_json, state, start_at, end_at FROM tournaments WHERE state IN ({placeholders}) ORDER BY start_at ASC LIMIT ?",
                tuple(list(states) + [int(limit)]),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_tournament(self, tournament_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT id, created_by_admin_id, games_json, max_players, entry_fee_points, prize_pool_points, prize_json, rules_json, state, start_at, end_at, created_at FROM tournaments WHERE id = ?",
                (int(tournament_id),),
            ).fetchone()
            return dict(row) if row else None

    def get_tournament_players_count(self, tournament_id: int) -> int:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM tournament_players WHERE tournament_id = ? AND status IN ('registered','active')",
                (int(tournament_id),),
            ).fetchone()
            return int(row[0] or 0)

    def is_user_registered_in_tournament(self, tournament_id: int, user_id: int) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM tournament_players WHERE tournament_id = ? AND user_id = ?",
                (int(tournament_id), int(user_id)),
            ).fetchone()
            return bool(row)

    def register_for_tournament(self, tournament_id: int, *, user_id: int, username: str | None, now_ts: int) -> dict:
        now_ts = int(now_ts)
        with self._lock, self._connect() as db:
            t = db.execute(
                "SELECT state, max_players, entry_fee_points, start_at FROM tournaments WHERE id = ?",
                (int(tournament_id),),
            ).fetchone()
            if not t:
                return {"ok": False, "reason": "no_tournament"}
            if str(t[0]) != "registering":
                return {"ok": False, "reason": "closed"}
            max_players = int(t[1] or 0)
            entry_fee = int(t[2] or 0)
            start_at = int(t[3] or 0)
            if start_at and now_ts >= start_at:
                return {"ok": False, "reason": "already_started"}

            # 1 tournament/day limit (same start day)
            row = db.execute(
                """
                SELECT 1
                FROM tournament_players tp
                JOIN tournaments tt ON tt.id = tp.tournament_id
                WHERE tp.user_id = ?
                  AND tt.state IN ('registering','running','finished')
                  AND date(tt.start_at, 'unixepoch') = date(?, 'unixepoch')
                LIMIT 1
                """,
                (int(user_id), int(start_at if start_at else now_ts)),
            ).fetchone()
            if row:
                return {"ok": False, "reason": "daily_limit"}

            already = db.execute(
                "SELECT 1 FROM tournament_players WHERE tournament_id = ? AND user_id = ?",
                (int(tournament_id), int(user_id)),
            ).fetchone()
            if already:
                return {"ok": True, "reason": "already", "entry_fee": entry_fee}

            cnt = int(
                db.execute(
                    "SELECT COUNT(*) FROM tournament_players WHERE tournament_id = ? AND status = 'registered'",
                    (int(tournament_id),),
                ).fetchone()[0]
                or 0
            )
            if cnt >= max_players:
                return {"ok": False, "reason": "full"}

            if entry_fee > 0:
                bal_row = db.execute("SELECT balance_points FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
                bal = int(bal_row[0] or 0) if bal_row else 0
                if bal < entry_fee:
                    return {"ok": False, "reason": "insufficient"}
                db.execute(
                    "UPDATE users SET balance_points = balance_points - ? WHERE user_id = ?",
                    (int(entry_fee), int(user_id)),
                )

            db.execute(
                "INSERT INTO tournament_players(tournament_id, user_id, username, status, joined_at) VALUES(?, ?, ?, 'registered', ?)",
                (int(tournament_id), int(user_id), (None if username is None else str(username)), int(now_ts)),
            )
            db.execute(
                "INSERT INTO tournament_audit(tournament_id, user_id, event, amount_points, details_json, created_at) VALUES(?, ?, 'join', ?, ?, ?)",
                (int(tournament_id), int(user_id), int(entry_fee), json.dumps({"fee": entry_fee}, ensure_ascii=False), int(now_ts)),
            )
            return {"ok": True, "reason": "ok", "entry_fee": entry_fee}

    def unregister_from_tournament(self, tournament_id: int, *, user_id: int, now_ts: int) -> dict:
        now_ts = int(now_ts)
        with self._lock, self._connect() as db:
            t = db.execute(
                "SELECT state, entry_fee_points, start_at FROM tournaments WHERE id = ?",
                (int(tournament_id),),
            ).fetchone()
            if not t:
                return {"ok": False, "reason": "no_tournament"}
            if str(t[0]) != "registering":
                return {"ok": False, "reason": "closed"}
            entry_fee = int(t[1] or 0)
            start_at = int(t[2] or 0)
            if start_at and now_ts >= start_at:
                return {"ok": False, "reason": "already_started"}

            row = db.execute(
                "SELECT 1 FROM tournament_players WHERE tournament_id = ? AND user_id = ? AND status = 'registered'",
                (int(tournament_id), int(user_id)),
            ).fetchone()
            if not row:
                return {"ok": True, "reason": "not_in"}

            db.execute(
                "DELETE FROM tournament_players WHERE tournament_id = ? AND user_id = ?",
                (int(tournament_id), int(user_id)),
            )
            if entry_fee > 0:
                db.execute(
                    "UPDATE users SET balance_points = balance_points + ? WHERE user_id = ?",
                    (int(entry_fee), int(user_id)),
                )
            db.execute(
                "INSERT INTO tournament_audit(tournament_id, user_id, event, amount_points, details_json, created_at) VALUES(?, ?, 'leave', ?, ?, ?)",
                (int(tournament_id), int(user_id), int(entry_fee), json.dumps({"refund": entry_fee}, ensure_ascii=False), int(now_ts)),
            )
            return {"ok": True, "reason": "ok", "refund": entry_fee}

    def list_due_tournaments(self, *, now_ts: int, limit: int = 20) -> list[int]:
        now_ts = int(now_ts)
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT id FROM tournaments WHERE state = 'registering' AND start_at <= ? ORDER BY start_at ASC LIMIT ?",
                (int(now_ts), int(limit)),
            ).fetchall()
            return [int(r[0]) for r in rows]

    def start_tournament(self, tournament_id: int, *, now_ts: int, round_deadline_seconds: int) -> dict:
        now_ts = int(now_ts)
        round_deadline_seconds = int(round_deadline_seconds)
        with self._lock, self._connect() as db:
            t = db.execute(
                "SELECT state, start_at FROM tournaments WHERE id = ?",
                (int(tournament_id),),
            ).fetchone()
            if not t:
                return {"ok": False, "reason": "no_tournament"}
            if str(t[0]) != "registering":
                return {"ok": False, "reason": "not_registering"}

            players = db.execute(
                "SELECT user_id, username, joined_at FROM tournament_players WHERE tournament_id = ? AND status = 'registered' ORDER BY joined_at ASC",
                (int(tournament_id),),
            ).fetchall()
            if len(players) < 2:
                db.execute("UPDATE tournaments SET state = 'cancelled', end_at = ? WHERE id = ?", (int(now_ts), int(tournament_id)))
                return {"ok": False, "reason": "not_enough_players"}

            ids = [int(p[0]) for p in players]
            digest = hashlib.sha256(f"{tournament_id}:{now_ts}".encode("utf-8")).hexdigest()
            rng = random.Random(int(digest, 16))
            rng.shuffle(ids)

            for i, uid in enumerate(ids, 1):
                db.execute(
                    "UPDATE tournament_players SET seed = ?, status = 'active' WHERE tournament_id = ? AND user_id = ?",
                    (int(i), int(tournament_id), int(uid)),
                )

            bracket = self._tour_next_pow2(len(ids))
            slots: list[int | None] = ids + [None] * max(0, bracket - len(ids))
            deadline_at = now_ts + round_deadline_seconds
            created: list[dict] = []
            for i in range(0, len(slots), 2):
                p1 = slots[i]
                p2 = slots[i + 1] if i + 1 < len(slots) else None
                db.execute(
                    "INSERT INTO tournament_matches(tournament_id, round, p1_user_id, p2_user_id, state, deadline_at, created_at) VALUES(?, 1, ?, ?, 'pending', ?, ?)",
                    (int(tournament_id), None if p1 is None else int(p1), None if p2 is None else int(p2), int(deadline_at), int(now_ts)),
                )
                mid = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
                if p1 is not None and p2 is None:
                    db.execute(
                        "UPDATE tournament_matches SET winner_user_id = ?, state = 'done' WHERE id = ?",
                        (int(p1), int(mid)),
                    )
                created.append({"match_id": mid, "p1": p1, "p2": p2, "round": 1, "deadline_at": deadline_at})

            db.execute("UPDATE tournaments SET state = 'running' WHERE id = ?", (int(tournament_id),))
            return {"ok": True, "reason": "ok", "match_list": created, "player_ids": ids, "deadline_at": int(deadline_at)}

    def list_expired_pending_matches(self, *, now_ts: int, limit: int = 50) -> list[int]:
        now_ts = int(now_ts)
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT id FROM tournament_matches WHERE state = 'pending' AND deadline_at <= ? ORDER BY deadline_at ASC LIMIT ?",
                (int(now_ts), int(limit)),
            ).fetchall()
            return [int(r[0]) for r in rows]

    def get_match(self, match_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT id, tournament_id, round, p1_user_id, p2_user_id, p1_score, p2_score, p1_time_ms, p2_time_ms, winner_user_id, state, deadline_at FROM tournament_matches WHERE id = ?",
                (int(match_id),),
            ).fetchone()
            return dict(row) if row else None

    def get_user_pending_match(self, tournament_id: int, user_id: int) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT id, tournament_id, round, p1_user_id, p2_user_id, p1_score, p2_score,
                       p1_time_ms, p2_time_ms, winner_user_id, state, deadline_at
                FROM tournament_matches
                WHERE tournament_id = ? AND state = 'pending' AND (p1_user_id = ? OR p2_user_id = ?)
                ORDER BY round ASC, id ASC
                LIMIT 1
                """,
                (int(tournament_id), int(user_id), int(user_id)),
            ).fetchone()
            return dict(row) if row else None

    def submit_match_result(self, *, tournament_id: int, match_id: int, user_id: int, score: int, time_ms: int, now_ts: int) -> dict:
        tournament_id = int(tournament_id)
        match_id = int(match_id)
        user_id = int(user_id)
        score = int(score)
        time_ms = int(time_ms)
        now_ts = int(now_ts)

        with self._lock, self._connect() as db:
            m = db.execute(
                "SELECT tournament_id, round, p1_user_id, p2_user_id, p1_score, p2_score, state, deadline_at FROM tournament_matches WHERE id = ? AND tournament_id = ?",
                (int(match_id), int(tournament_id)),
            ).fetchone()
            if not m:
                return {"ok": False, "reason": "no_match"}
            if str(m[6]) != "pending":
                return {"ok": False, "reason": "not_pending"}
            if int(m[7] or 0) < now_ts:
                return {"ok": False, "reason": "deadline"}
            p1 = int(m[2] or 0) if m[2] is not None else None
            p2 = int(m[3] or 0) if m[3] is not None else None
            if user_id not in (p1, p2):
                return {"ok": False, "reason": "not_player"}

            if user_id == p1:
                if m[4] is not None:
                    return {"ok": True, "reason": "already"}
                db.execute("UPDATE tournament_matches SET p1_score = ?, p1_time_ms = ? WHERE id = ?", (int(score), int(time_ms), int(match_id)))
            else:
                if m[5] is not None:
                    return {"ok": True, "reason": "already"}
                db.execute("UPDATE tournament_matches SET p2_score = ?, p2_time_ms = ? WHERE id = ?", (int(score), int(time_ms), int(match_id)))

            db.execute(
                "INSERT INTO tournament_audit(tournament_id, user_id, event, amount_points, details_json, created_at) VALUES(?, ?, 'submit', NULL, ?, ?)",
                (int(tournament_id), int(user_id), json.dumps({"match_id": match_id, "score": score, "time_ms": time_ms}, ensure_ascii=False), int(now_ts)),
            )
            return self._try_resolve_match_in_conn(db, match_id=int(match_id), now_ts=now_ts)

    def _try_resolve_match_in_conn(self, db: sqlite3.Connection, *, match_id: int, now_ts: int) -> dict:
        m = db.execute(
            "SELECT tournament_id, round, p1_user_id, p2_user_id, p1_score, p2_score, p1_time_ms, p2_time_ms, state FROM tournament_matches WHERE id = ?",
            (int(match_id),),
        ).fetchone()
        if not m or str(m[8]) != "pending":
            return {"ok": False, "reason": "not_pending"}

        tid = int(m[0])
        rnd = int(m[1])
        p1 = int(m[2] or 0) if m[2] is not None else None
        p2 = int(m[3] or 0) if m[3] is not None else None
        p1s = m[4]
        p2s = m[5]
        p1t = int(m[6] or 10**12)
        p2t = int(m[7] or 10**12)

        # Bye
        if p1 is not None and p2 is None:
            db.execute("UPDATE tournament_matches SET winner_user_id = ?, state = 'done' WHERE id = ?", (int(p1), int(match_id)))
            return {"ok": True, "reason": "bye", "tournament_id": tid, "round": rnd, "winner_user_id": int(p1)}

        if p1 is None or p2 is None:
            db.execute("UPDATE tournament_matches SET winner_user_id = NULL, state = 'both_noshow' WHERE id = ?", (int(match_id),))
            return {"ok": True, "reason": "invalid", "tournament_id": tid, "round": rnd, "winner_user_id": None}

        if p1s is None or p2s is None:
            return {"ok": True, "reason": "waiting", "tournament_id": tid, "round": rnd}

        p1s_i = int(p1s)
        p2s_i = int(p2s)
        if p1s_i > p2s_i:
            winner = p1
        elif p2s_i > p1s_i:
            winner = p2
        else:
            if p1t < p2t:
                winner = p1
            elif p2t < p1t:
                winner = p2
            else:
                digest = hashlib.sha256(f"{tid}:{match_id}:{p1}:{p2}".encode("utf-8")).hexdigest()
                winner = p1 if (int(digest, 16) % 2 == 0) else p2

        db.execute("UPDATE tournament_matches SET winner_user_id = ?, state = 'done' WHERE id = ?", (int(winner), int(match_id)))
        loser = p2 if winner == p1 else p1
        db.execute(
            "UPDATE tournament_players SET status = 'eliminated', eliminated_round = ? WHERE tournament_id = ? AND user_id = ?",
            (int(rnd), int(tid), int(loser)),
        )
        return {"ok": True, "reason": "done", "tournament_id": tid, "round": rnd, "winner_user_id": int(winner), "loser_user_id": int(loser)}

    def expire_match_no_show(self, *, match_id: int, now_ts: int) -> dict:
        now_ts = int(now_ts)
        with self._lock, self._connect() as db:
            m = db.execute(
                "SELECT tournament_id, round, p1_user_id, p2_user_id, p1_score, p2_score, state FROM tournament_matches WHERE id = ?",
                (int(match_id),),
            ).fetchone()
            if not m or str(m[6]) != "pending":
                return {"ok": False, "reason": "not_pending"}
            tid = int(m[0])
            rnd = int(m[1])
            p1 = int(m[2] or 0) if m[2] is not None else None
            p2 = int(m[3] or 0) if m[3] is not None else None
            p1s = m[4]
            p2s = m[5]
            if p1 is None or p2 is None:
                db.execute("UPDATE tournament_matches SET state = 'both_noshow', winner_user_id = NULL WHERE id = ?", (int(match_id),))
                return {"ok": True, "reason": "both_noshow", "tournament_id": tid, "round": rnd}

            if p1s is None and p2s is None:
                db.execute("UPDATE tournament_matches SET state = 'both_noshow', winner_user_id = NULL WHERE id = ?", (int(match_id),))
                db.execute(
                    "UPDATE tournament_players SET status = 'eliminated', eliminated_round = ? WHERE tournament_id = ? AND user_id IN (?, ?)",
                    (int(rnd), int(tid), int(p1), int(p2)),
                )
                return {"ok": True, "reason": "both_noshow", "tournament_id": tid, "round": rnd}
            if p1s is None and p2s is not None:
                db.execute("UPDATE tournament_matches SET state = 'p1_noshow', winner_user_id = ? WHERE id = ?", (int(p2), int(match_id)))
                db.execute(
                    "UPDATE tournament_players SET status = 'eliminated', eliminated_round = ? WHERE tournament_id = ? AND user_id = ?",
                    (int(rnd), int(tid), int(p1)),
                )
                return {"ok": True, "reason": "p1_noshow", "winner_user_id": int(p2), "tournament_id": tid, "round": rnd}
            if p2s is None and p1s is not None:
                db.execute("UPDATE tournament_matches SET state = 'p2_noshow', winner_user_id = ? WHERE id = ?", (int(p1), int(match_id)))
                db.execute(
                    "UPDATE tournament_players SET status = 'eliminated', eliminated_round = ? WHERE tournament_id = ? AND user_id = ?",
                    (int(rnd), int(tid), int(p2)),
                )
                return {"ok": True, "reason": "p2_noshow", "winner_user_id": int(p1), "tournament_id": tid, "round": rnd}

            return self._try_resolve_match_in_conn(db, match_id=int(match_id), now_ts=now_ts)

    def maybe_advance_tournament(self, tournament_id: int, *, now_ts: int, round_deadline_seconds: int) -> dict:
        now_ts = int(now_ts)
        round_deadline_seconds = int(round_deadline_seconds)
        with self._lock, self._connect() as db:
            t = db.execute("SELECT state, prize_json FROM tournaments WHERE id = ?", (int(tournament_id),)).fetchone()
            if not t or str(t[0]) != "running":
                return {"ok": False, "reason": "not_running"}

            last_round_row = db.execute("SELECT MAX(round) FROM tournament_matches WHERE tournament_id = ?", (int(tournament_id),)).fetchone()
            last_round = int(last_round_row[0] or 0)
            if last_round <= 0:
                return {"ok": True, "reason": "no_rounds"}

            pending_row = db.execute(
                "SELECT COUNT(*) FROM tournament_matches WHERE tournament_id = ? AND round = ? AND state = 'pending'",
                (int(tournament_id), int(last_round)),
            ).fetchone()
            if int(pending_row[0] or 0) > 0:
                return {"ok": True, "reason": "waiting"}

            winners = db.execute(
                "SELECT winner_user_id FROM tournament_matches WHERE tournament_id = ? AND round = ? AND state != 'pending' ORDER BY id ASC",
                (int(tournament_id), int(last_round)),
            ).fetchall()
            winner_ids = [int(r[0]) for r in winners if r and r[0] is not None]

            if len(winner_ids) <= 1:
                if len(winner_ids) == 1:
                    self._finish_and_pay_in_conn(db, tournament_id=int(tournament_id), champion=int(winner_ids[0]), now_ts=now_ts)
                    return {"ok": True, "reason": "finished", "champion": int(winner_ids[0])}
                db.execute("UPDATE tournaments SET state = 'finished', end_at = ? WHERE id = ?", (int(now_ts), int(tournament_id)))
                return {"ok": True, "reason": "finished_no_winner"}

            next_round = last_round + 1
            bracket = self._tour_next_pow2(len(winner_ids))
            slots: list[int | None] = winner_ids + [None] * max(0, bracket - len(winner_ids))
            deadline_at = now_ts + round_deadline_seconds
            match_ids: list[int] = []
            for i in range(0, len(slots), 2):
                p1 = slots[i]
                p2 = slots[i + 1] if i + 1 < len(slots) else None
                db.execute(
                    "INSERT INTO tournament_matches(tournament_id, round, p1_user_id, p2_user_id, state, deadline_at, created_at) VALUES(?, ?, ?, ?, 'pending', ?, ?)",
                    (int(tournament_id), int(next_round), None if p1 is None else int(p1), None if p2 is None else int(p2), int(deadline_at), int(now_ts)),
                )
                mid = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
                if p1 is not None and p2 is None:
                    db.execute(
                        "UPDATE tournament_matches SET winner_user_id = ?, state = 'done' WHERE id = ?",
                        (int(p1), int(mid)),
                    )
                match_ids.append(mid)
            return {"ok": True, "reason": "advanced", "round": int(next_round), "match_ids": match_ids, "deadline_at": int(deadline_at)}

    def _finish_and_pay_in_conn(self, db: sqlite3.Connection, *, tournament_id: int, champion: int, now_ts: int) -> None:
        t = db.execute("SELECT prize_json FROM tournaments WHERE id = ?", (int(tournament_id),)).fetchone()
        prize = {}
        try:
            prize = json.loads(str(t[0] or "{}")) if t else {}
        except Exception:
            prize = {}

        # Second = loser of final
        final_round_row = db.execute("SELECT MAX(round) FROM tournament_matches WHERE tournament_id = ?", (int(tournament_id),)).fetchone()
        final_round = int(final_round_row[0] or 0)
        final = db.execute(
            "SELECT p1_user_id, p2_user_id, winner_user_id FROM tournament_matches WHERE tournament_id = ? AND round = ? ORDER BY id DESC LIMIT 1",
            (int(tournament_id), int(final_round)),
        ).fetchone()
        second = None
        if final and final[2] is not None:
            p1 = int(final[0] or 0)
            p2 = int(final[1] or 0)
            w = int(final[2] or 0)
            second = p2 if w == p1 else p1

        # Third = best semifinal loser
        third = None
        if final_round >= 2:
            semis = db.execute(
                "SELECT p1_user_id, p2_user_id, p1_score, p2_score, p1_time_ms, p2_time_ms, winner_user_id FROM tournament_matches WHERE tournament_id = ? AND round = ?",
                (int(tournament_id), int(final_round - 1)),
            ).fetchall()
            candidates: list[tuple[int, int, int]] = []
            for r in semis:
                if not r or r[6] is None:
                    continue
                w = int(r[6])
                p1 = int(r[0] or 0)
                p2 = int(r[1] or 0)
                if w == p1:
                    loser = p2
                    score = int(r[3] or 0)
                    tm = int(r[5] or 10**12)
                else:
                    loser = p1
                    score = int(r[2] or 0)
                    tm = int(r[4] or 10**12)
                if loser:
                    candidates.append((int(loser), int(score), int(tm)))
            if candidates:
                candidates.sort(key=lambda x: (-x[1], x[2]))
                third = candidates[0][0]

        def _pay(place: str, user_id: int | None) -> None:
            if not user_id:
                return
            amt = int((prize or {}).get(place, 0) or 0)
            if amt <= 0:
                return
            db.execute("UPDATE users SET balance_points = balance_points + ? WHERE user_id = ?", (int(amt), int(user_id)))
            db.execute(
                "INSERT INTO tournament_audit(tournament_id, user_id, event, amount_points, details_json, created_at) VALUES(?, ?, 'prize', ?, ?, ?)",
                (int(tournament_id), int(user_id), int(amt), json.dumps({"place": place}, ensure_ascii=False), int(now_ts)),
            )

        _pay("1", champion)
        _pay("2", second)
        _pay("3", third)

        db.execute("UPDATE tournament_players SET status = 'winner' WHERE tournament_id = ? AND user_id = ?", (int(tournament_id), int(champion)))
        db.execute("UPDATE tournaments SET state = 'finished', end_at = ? WHERE id = ?", (int(now_ts), int(tournament_id)))


    # --- Weekly tasks system ---

    WEEKLY_TASK_TEMPLATES: list[dict] = [
        {"code": "farm_claims", "title": "⭐ Фарм: собрать 20 раз", "target": 20, "reward_points": 200},
        {"code": "farm_points", "title": "💰 Фарм: заработать 1500 баллов", "target": 1500, "reward_points": 250},
        {"code": "mines_games", "title": "💣 Мины: сыграть 15 игр", "target": 15, "reward_points": 250},
        {"code": "dice_games", "title": "🎲 Кости: сыграть 15 игр", "target": 15, "reward_points": 250},
        {"code": "ladder_games", "title": "🪜 Лесенка: сыграть 10 игр", "target": 10, "reward_points": 250},
        {"code": "tasks_completed", "title": "📋 Задания: выполнить 3", "target": 3, "reward_points": 200},
    ]

    @staticmethod
    def week_key_utc(now_ts: int | None = None) -> str:
        now_dt = dt.datetime.utcfromtimestamp(int(now_ts)) if now_ts is not None else dt.datetime.utcnow()
        monday = now_dt.date() - dt.timedelta(days=int(now_dt.weekday()))
        return monday.isoformat()

    def _ensure_weekly_tasks_in_conn(self, db: sqlite3.Connection, *, week_key: str, now_ts: int) -> None:
        week_key = str(week_key)
        row = db.execute("SELECT COUNT(*) AS c FROM weekly_tasks WHERE week_key = ?", (week_key,)).fetchone()
        existing = int(row[0] or 0) if row else 0
        if existing >= 4:
            return

        # If partially created, reset for consistency
        if existing > 0:
            db.execute("DELETE FROM weekly_tasks WHERE week_key = ?", (week_key,))

        templates = list(self.WEEKLY_TASK_TEMPLATES)
        if len(templates) < 4:
            raise RuntimeError("WEEKLY_TASK_TEMPLATES must have at least 4 templates")

        rng = random.Random(str(week_key))
        chosen = rng.sample(templates, k=4)
        for i, t in enumerate(chosen, start=1):
            db.execute(
                "INSERT INTO weekly_tasks(week_key, slot, code, title, target, reward_points, created_at_ts) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    str(week_key),
                    int(i),
                    str(t.get("code")),
                    str(t.get("title")),
                    int(t.get("target") or 0),
                    int(t.get("reward_points") or 0),
                    int(now_ts),
                ),
            )

    def ensure_weekly_tasks(self, *, week_key: str, now_ts: int | None = None) -> None:
        ts = int(now_ts) if now_ts is not None else int(dt.datetime.utcnow().timestamp())
        with self._lock, self._connect() as db:
            self._ensure_weekly_tasks_in_conn(db, week_key=str(week_key), now_ts=ts)

    def get_weekly_tasks_for_user(self, user_id: int, *, week_key: str, now_ts: int | None = None) -> list[dict]:
        user_id = int(user_id)
        ts = int(now_ts) if now_ts is not None else int(dt.datetime.utcnow().timestamp())
        with self._lock, self._connect() as db:
            self._ensure_weekly_tasks_in_conn(db, week_key=str(week_key), now_ts=ts)

            # Ensure progress rows exist for all slots of this week
            db.execute(
                """
                INSERT OR IGNORE INTO weekly_user_tasks(user_id, week_key, slot, progress, claimed, updated_ts)
                SELECT ?, week_key, slot, 0, 0, ?
                FROM weekly_tasks
                WHERE week_key = ?
                """,
                (int(user_id), int(ts), str(week_key)),
            )

            rows = db.execute(
                """
                SELECT
                    wt.slot AS slot,
                    wt.code AS code,
                    wt.title AS title,
                    wt.target AS target,
                    wt.reward_points AS reward_points,
                    COALESCE(uwt.progress, 0) AS progress,
                    COALESCE(uwt.claimed, 0) AS claimed
                FROM weekly_tasks wt
                LEFT JOIN weekly_user_tasks uwt
                  ON uwt.user_id = ? AND uwt.week_key = wt.week_key AND uwt.slot = wt.slot
                WHERE wt.week_key = ?
                ORDER BY wt.slot ASC
                """,
                (int(user_id), str(week_key)),
            ).fetchall()

            out: list[dict] = []
            for r in rows or []:
                out.append(
                    {
                        "slot": int(r[0]),
                        "code": str(r[1]),
                        "title": str(r[2]),
                        "target": int(r[3] or 0),
                        "reward_points": int(r[4] or 0),
                        "progress": int(r[5] or 0),
                        "claimed": int(r[6] or 0),
                    }
                )
            return out

    def add_weekly_progress(
        self,
        user_id: int,
        *,
        week_key: str,
        code: str,
        delta: int = 1,
        now_ts: int | None = None,
    ) -> None:
        user_id = int(user_id)
        delta = int(delta)
        if delta <= 0:
            return

        ts = int(now_ts) if now_ts is not None else int(dt.datetime.utcnow().timestamp())
        with self._lock, self._connect() as db:
            self._ensure_weekly_tasks_in_conn(db, week_key=str(week_key), now_ts=ts)

            slots = db.execute(
                "SELECT slot, target FROM weekly_tasks WHERE week_key = ? AND code = ?",
                (str(week_key), str(code)),
            ).fetchall()
            if not slots:
                return

            for sl in slots:
                slot = int(sl[0])
                target = int(sl[1] or 0)
                if target <= 0:
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO weekly_user_tasks(user_id, week_key, slot, progress, claimed, updated_ts) VALUES(?, ?, ?, 0, 0, ?)",
                    (int(user_id), str(week_key), int(slot), int(ts)),
                )
                # cap progress to target
                db.execute(
                    """
                    UPDATE weekly_user_tasks
                    SET
                        progress = CASE
                            WHEN progress + ? >= ? THEN ?
                            ELSE progress + ?
                        END,
                        updated_ts = ?
                    WHERE user_id = ? AND week_key = ? AND slot = ?
                    """,
                    (int(delta), int(target), int(target), int(delta), int(ts), int(user_id), str(week_key), int(slot)),
                )

    def try_claim_weekly_task(
        self,
        user_id: int,
        *,
        week_key: str,
        slot: int,
        now_ts: int | None = None,
    ) -> dict:
        user_id = int(user_id)
        slot = int(slot)
        ts = int(now_ts) if now_ts is not None else int(dt.datetime.utcnow().timestamp())
        with self._lock, self._connect() as db:
            self._ensure_weekly_tasks_in_conn(db, week_key=str(week_key), now_ts=ts)

            t = db.execute(
                "SELECT target, reward_points FROM weekly_tasks WHERE week_key = ? AND slot = ?",
                (str(week_key), int(slot)),
            ).fetchone()
            if not t:
                return {"ok": False, "reason": "not_found"}
            target = int(t[0] or 0)
            reward = int(t[1] or 0)

            db.execute(
                "INSERT OR IGNORE INTO weekly_user_tasks(user_id, week_key, slot, progress, claimed, updated_ts) VALUES(?, ?, ?, 0, 0, ?)",
                (int(user_id), str(week_key), int(slot), int(ts)),
            )

            # Atomic claim if completed
            cur = db.execute(
                """
                UPDATE weekly_user_tasks
                SET claimed = 1, updated_ts = ?
                WHERE user_id = ? AND week_key = ? AND slot = ?
                  AND claimed = 0
                  AND progress >= ?
                """,
                (int(ts), int(user_id), str(week_key), int(slot), int(target)),
            )
            if int(cur.rowcount or 0) != 1:
                row = db.execute(
                    "SELECT progress, claimed FROM weekly_user_tasks WHERE user_id = ? AND week_key = ? AND slot = ?",
                    (int(user_id), str(week_key), int(slot)),
                ).fetchone()
                if not row:
                    return {"ok": False, "reason": "not_found"}
                prog = int(row[0] or 0)
                claimed = int(row[1] or 0)
                if claimed:
                    return {"ok": False, "reason": "already_claimed"}
                if prog < target:
                    return {"ok": False, "reason": "not_completed", "progress": int(prog), "target": int(target)}
                return {"ok": False, "reason": "not_completed"}

            return {"ok": True, "reward_points": int(reward)}


