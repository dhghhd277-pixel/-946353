from __future__ import annotations

from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# Import strategy:
# - preferred: package execution (`python -m bot`) using relative imports
# - fallback: direct script execution / flattened layout (e.g. `/app/keyboards.py`)
try:
    from .constants import BANK_OPTIONS, WITHDRAW_OPTIONS_RUB
except Exception:
    try:
        from bot.constants import BANK_OPTIONS, WITHDRAW_OPTIONS_RUB  # type: ignore
    except Exception:
        from constants import BANK_OPTIONS, WITHDRAW_OPTIONS_RUB  # type: ignore


def main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    # "📋 Задания" перенесены в раздел "✨ Фарм баллов"
    # "👥 Пригласить друга" убраны из главного меню
    kb.row(KeyboardButton("⛏️ Майнинг ферма"), KeyboardButton("🔄 Рынок"))
    kb.row(KeyboardButton("✨ Фарм баллов"))
    kb.row(KeyboardButton("🎮 Мини игры"), KeyboardButton("💼 Профиль"))
    kb.row(KeyboardButton("🛒 Магазин"))
    kb.row(KeyboardButton("❓ Поддержка"))
    if is_admin:
        kb.row(KeyboardButton("🛠 Админка"))
    return kb


def _fmt_points(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        n = 0
    return f"{n:,}".replace(",", " ")


def cryptomine_shop_main_kb(
    *,
    prefix: str = "cm",
    exit_cb: str | None = None,
    show_back: bool = True,
) -> InlineKeyboardMarkup:
    prefix = str(prefix)
    if exit_cb is None:
        exit_cb = f"{prefix}:exit"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🎮 Видеокарты", callback_data=f"{prefix}:cat:gpu"))
    kb.add(InlineKeyboardButton(text="🧠 Процессоры", callback_data=f"{prefix}:cat:upg"))
    kb.add(InlineKeyboardButton(text="❄ Охлаждение", callback_data=f"{prefix}:cat:cool"))
    kb.add(InlineKeyboardButton(text="⚡ Питание", callback_data=f"{prefix}:cat:psu"))
    kb.add(InlineKeyboardButton(text="📦 Ячейки", callback_data=f"{prefix}:cat:slots"))
    kb.add(InlineKeyboardButton(text="🚀 Бустеры", callback_data=f"{prefix}:cat:boost"))
    if show_back:
        kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data=str(exit_cb)))
    return kb


def cryptomine_category_kb(
    category: str,
    *,
    prefix: str = "cm",
    home_cb: str | None = None,
    gpu_suffix_by_code: dict[str, str] | None = None,
    cool_suffix_by_code: dict[str, str] | None = None,
) -> InlineKeyboardMarkup:
    category = str(category)
    prefix = str(prefix)
    if home_cb is None:
        home_cb = f"{prefix}:home"
    kb = InlineKeyboardMarkup()
    if category == "gpu":
        for code, label in (
            ("gtx1060", "GTX 1060"),
            ("rtx2060", "RTX 2060"),
            ("rtx3060", "RTX 3060"),
            ("rtx3080", "RTX 3080"),
            ("rtx4090", "RTX 4090"),
        ):
            suffix = (gpu_suffix_by_code or {}).get(str(code))
            text = f"{label} — {suffix}" if suffix else str(label)
            kb.add(InlineKeyboardButton(text=text, callback_data=f"{prefix}:item:gpu:{code}"))

        kb.add(InlineKeyboardButton(text="━━━━━━━━━━━━━━━━━━━━", callback_data=f"{prefix}:noop"))

        for code, label in (
            ("rtx5060", "RTX 5060"),
            ("rtx5070", "RTX 5070"),
            ("rtx5080", "RTX 5080"),
            ("rtx5090", "RTX 5090"),
            ("rtx5090ti", "RTX 5090 Ti"),
        ):
            suffix = (gpu_suffix_by_code or {}).get(str(code))
            text = f"{label} — {suffix}" if suffix else str(label)
            kb.add(InlineKeyboardButton(text=text, callback_data=f"{prefix}:item:gpu:{code}"))
    elif category == "cool":
        for code, label in (
            ("fan", "🌀 Обычный кулер"),
            ("water", "💧 Водяное охлаждение"),
            ("server", "🧊 Серверное охлаждение"),
            ("immersion", "🛢 Иммерсионное охлаждение"),
        ):
            suffix = (cool_suffix_by_code or {}).get(str(code))
            text = f"{label} {suffix}" if suffix else str(label)
            kb.add(InlineKeyboardButton(text=text, callback_data=f"{prefix}:item:cool:{code}"))
    elif category == "psu":
        for code, label in (("600", "🔌 БП 600W"), ("1000", "🔌 БП 1000W"), ("1600", "🔌 БП 1600W")):
            kb.add(InlineKeyboardButton(text=label, callback_data=f"{prefix}:item:psu:{code}"))
    elif category == "slots":
        for code, label in (("rack4", "📦 Стойка +4 карты"), ("cont16", "🏭 Контейнер +16 карт"), ("dc64", "🏢 Дата-центр +64 карты")):
            kb.add(InlineKeyboardButton(text=label, callback_data=f"{prefix}:item:slots:{code}"))
    elif category == "upg":
        for code, label in (("soft", "🧠 Оптимизация ПО"), ("shield", "🛡 Защита от сбоев"), ("eff", "📈 Эффективность")):
            kb.add(InlineKeyboardButton(text=label, callback_data=f"{prefix}:item:upg:{code}"))
    elif category == "boost":
        for code, label in (("x2_10", "⚡ x2 доход (10 мин)"), ("x3_5", "⚡ x3 доход (5 мин)"), ("cool", "❄ Мгновенное охлаждение")):
            kb.add(InlineKeyboardButton(text=label, callback_data=f"{prefix}:item:boost:{code}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data=str(home_cb)))
    return kb


def cryptomine_item_kb(
    *,
    category: str,
    code: str,
    show_badge: str | None = None,
    prefix: str = "cm",
    back_to_category_prefix: str | None = None,
) -> InlineKeyboardMarkup:
    category = str(category)
    code = str(code)
    prefix = str(prefix)
    if back_to_category_prefix is None:
        back_to_category_prefix = prefix
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✅ Купить", callback_data=f"{prefix}:buy:{category}:{code}"))
    if show_badge:
        kb.add(InlineKeyboardButton(text=str(show_badge), callback_data=f"{prefix}:noop"))
    if category == "gpu":
        kb.add(InlineKeyboardButton(text="ℹ Подробнее", callback_data=f"{prefix}:info:{category}:{code}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data=f"{back_to_category_prefix}:cat:{category}"))
    return kb


def cryptomine_farm_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⛏ Майнить", callback_data="cmf:mine"))
    kb.add(InlineKeyboardButton(text="🖥 Ферма", callback_data="cmf:farm"))
    kb.add(InlineKeyboardButton(text="🛒 Магазин", callback_data="cmf:shop"))
    kb.add(InlineKeyboardButton(text="🔄 Рынок", callback_data="cmf:market"))
    kb.add(InlineKeyboardButton(text="🏆 Рейтинг", callback_data="cmf:rating"))
    kb.add(InlineKeyboardButton(text="⚙ Настройки", callback_data="cmf:settings"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:exit"))
    return kb


def cryptomine_mining_kb(*, is_active: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    # Removed direct 'Охладить' and 'Статус' buttons per user request
    if is_active:
        kb.add(InlineKeyboardButton(text="⛔ Остановить", callback_data="cmf:stop"))
    else:
        kb.add(InlineKeyboardButton(text="⛏ Запустить", callback_data="cmf:start"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:home"))
    return kb


def cryptomine_farm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="➕ Добавить карту", callback_data="cmf:add_card"))
    kb.add(InlineKeyboardButton(text="🛒 Магазин", callback_data="cmf:upgrade"))
    kb.add(InlineKeyboardButton(text="🗑 Удалить", callback_data="cmf:delete_menu"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:home"))
    return kb


def cryptomine_market_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="💱 Продать всё BTC", callback_data="cmf:market:sell_all"))
    kb.add(InlineKeyboardButton(text="🔁 Коины → Баллы", callback_data="cmf:coins:to_points:all"))
    kb.add(InlineKeyboardButton(text="💸 Вывод (коины → ₽)", callback_data="cmf:coins:withdraw"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="cmf:home"))
    return kb


def cryptomine_market_confirm_kb(*, amt: str) -> InlineKeyboardMarkup:
    amt = str(amt)
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="✅ Продать", callback_data=f"cmf:market:confirm:{amt}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cmf:market:cancel"),
    )
    return kb


def cryptomine_farm_reply_kb(*, is_active: bool = False) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if is_active:
        kb.row(KeyboardButton("⛔ Остановить"), KeyboardButton("🖥 Ферма"))
    else:
        kb.row(KeyboardButton("⛏ Майнить"), KeyboardButton("🖥 Ферма"))
    kb.row(KeyboardButton("🔄 Рынок"), KeyboardButton("🛒 Магазин фермы"))
    kb.row(KeyboardButton("🏆 Рейтинг"))
    kb.row(KeyboardButton("⌨ Главное меню"))
    return kb


def tournaments_menu_kb(*, is_registered: bool, can_unregister: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="tourn:list"),
        InlineKeyboardButton(text="📜 Правила", callback_data="tourn:rules"),
    )
    if is_registered:
        kb.add(InlineKeyboardButton(text="▶️ Играть матч", callback_data="tourn:play"))
        if can_unregister:
            kb.add(InlineKeyboardButton(text="❌ Отменить участие", callback_data="tourn:unreg"))
    else:
        kb.add(InlineKeyboardButton(text="✅ Участвовать", callback_data="tourn:reg"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def boosts_kb(*, luck_available: int, insurance_balance: int, insurance_next: bool, insurance_blocked: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    if insurance_blocked:
        kb.add(
            InlineKeyboardButton(
                text=f"🛡 Страховка: ❌ недоступна (не подряд) (осталось: {max(0, int(insurance_balance))})",
                callback_data="boosts:insurance_info",
            )
        )
    else:
        left = max(0, int(insurance_balance))
        txt = ("🛡 Страховка: ВКЛ на следующую игру" if insurance_next else "🛡 Страховка: ВЫКЛ") + f" (осталось: {left})"
        kb.add(InlineKeyboardButton(text=txt, callback_data="boosts:insurance_toggle"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def shop_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="👑 VIP-статус", callback_data="shop:vip"))
    kb.add(InlineKeyboardButton(text="🛡 Страховки", callback_data="shop:insurance"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="shop:exit"))
    return kb


def shop_insurance_kb(*, trial_available: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    if trial_available:
        kb.add(InlineKeyboardButton(text="🎁 Попробовать бесплатно (+5)", callback_data="shop:insurance:trial"))
    kb.add(InlineKeyboardButton(text="🛡 10 шт — 100 ₽", callback_data="shop:insurance:plan:10"))
    kb.add(InlineKeyboardButton(text="🛡 25 шт — 200 ₽", callback_data="shop:insurance:plan:25"))
    kb.add(InlineKeyboardButton(text="🛡 70 шт — 500 ₽", callback_data="shop:insurance:plan:70"))
    kb.add(InlineKeyboardButton(text="⬅ Назад в магазин", callback_data="shop:home"))
    return kb


def shop_insurance_success_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🚀 Открыть бусты", callback_data="shop:boosts"))
    kb.add(InlineKeyboardButton(text="🛒 Вернуться в магазин", callback_data="shop:home"))
    return kb


def mines_timeout_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data="minigame:mines"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def shop_vip_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="💎 VIP на 7 дней — 299 ₽", callback_data="shop:vip:plan:7"))
    kb.add(InlineKeyboardButton(text="💎 VIP на 30 дней — 999 ₽", callback_data="shop:vip:plan:30"))
    kb.add(InlineKeyboardButton(text="💎 VIP навсегда — 2499 ₽", callback_data="shop:vip:plan:forever"))
    kb.add(InlineKeyboardButton(text="⬅ Назад в магазин", callback_data="shop:home"))
    return kb


def shop_confirm_kb(*, buy_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✅ Купить", callback_data=buy_cb))
    kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb))
    return kb


def shop_vip_extend_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="➕ Продлить VIP", callback_data="shop:vip:extend"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="shop:vip"))
    return kb


def shop_vip_success_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="👤 Перейти в профиль", callback_data="shop:profile"))
    kb.add(InlineKeyboardButton(text="🛒 Вернуться в магазин", callback_data="shop:home"))
    return kb


def shop_farm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⚡ x2 на 24 часа — 99 ₽", callback_data="shop:farm:plan:x2_24"))
    kb.add(InlineKeyboardButton(text="🔥 x3 на 24 часа — 199 ₽", callback_data="shop:farm:plan:x3_24"))
    kb.add(InlineKeyboardButton(text="⬅ Назад в магазин", callback_data="shop:home"))
    return kb


def shop_farm_success_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✨ Перейти к фарму", callback_data="shop:farm:go"))
    kb.add(InlineKeyboardButton(text="🛒 Вернуться в магазин", callback_data="shop:home"))
    return kb


def shop_titles_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🎖 Выбрать готовый титул", callback_data="shop:title:ready"))
    kb.add(InlineKeyboardButton(text="✏️ Свой титул", callback_data="shop:title:custom"))
    kb.add(InlineKeyboardButton(text="🎨 Цветной ник", callback_data="shop:title:color"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="shop:home"))
    return kb


def shop_titles_ready_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="👑 Король фарма — 49 ₽", callback_data="shop:title:ready:king"))
    kb.add(InlineKeyboardButton(text="🔥 Легенда", callback_data="shop:title:ready:legend"))
    kb.add(InlineKeyboardButton(text="💎 Топ игрок", callback_data="shop:title:ready:top"))
    kb.add(InlineKeyboardButton(text="⚡ Фарм-машина", callback_data="shop:title:ready:farm"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="shop:title"))
    return kb


def shop_nick_colors_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🔴 Красный — 99 ₽", callback_data="shop:title:color:red"))
    kb.add(InlineKeyboardButton(text="🔵 Синий", callback_data="shop:title:color:blue"))
    kb.add(InlineKeyboardButton(text="🟢 Зелёный", callback_data="shop:title:color:green"))
    kb.add(InlineKeyboardButton(text="🟣 Фиолетовый", callback_data="shop:title:color:purple"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="shop:title"))
    return kb


def shop_emoji_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="💎 Diamond Pack — 99 ₽", callback_data="shop:emoji:pack:diamond"))
    kb.add(InlineKeyboardButton(text="🔥 Fire Pack — 99 ₽", callback_data="shop:emoji:pack:fire"))
    kb.add(InlineKeyboardButton(text="👑 Royal Pack — 149 ₽", callback_data="shop:emoji:pack:royal"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="shop:home"))
    return kb


def shop_emoji_pack_kb(*, pack: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✅ Купить", callback_data=f"shop:emoji:buy:{pack}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="shop:emoji"))
    return kb


def shop_emoji_success_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="👤 Открыть профиль", callback_data="shop:profile"))
    kb.add(InlineKeyboardButton(text="🛒 Вернуться в магазин", callback_data="shop:home"))
    return kb


def profile_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="💸 Вывести", callback_data="profile:withdraw"),
        InlineKeyboardButton(text="🏆 Рейтинг", callback_data="profile:rating"),
    )
    kb.row(InlineKeyboardButton(text="📋 Задания", callback_data="farm:tasks"))
    return kb


def rating_main_kb() -> InlineKeyboardMarkup:
    # Simplified: only a back button. Rating categories removed — show miners ranking only.
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton(text="⬅ Назад", callback_data="rating:back"))
    return kb


def rating_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton(text="⬅ Назад", callback_data="rating:back"))
    return kb


def weekly_tasks_kb(tasks: list[dict], *, refresh_cb: str = "profile:weekly", back_cb: str = "profile") -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for t in tasks or []:
        try:
            slot = int(t.get("slot") or 0)
            title = str(t.get("title") or "")
            reward = int(t.get("reward_points") or 0)
            progress = int(t.get("progress") or 0)
            target = int(t.get("target") or 0)
            claimed = int(t.get("claimed") or 0)
        except Exception:
            continue

        if target > 0 and progress >= target and not claimed:
            kb.add(InlineKeyboardButton(text=f"🎁 Забрать: +{_fmt_points(reward)} — {title}", callback_data=f"weekly:claim:{slot}"))

    kb.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data=str(refresh_cb)),
        InlineKeyboardButton(text="⬅ Назад", callback_data=str(back_cb)),
    )
    return kb


def farm_points_kb(*, can_claim: bool, wait_seconds: int, limit_reached: bool, booster_active: bool, reward_preview: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    if limit_reached:
        kb.add(InlineKeyboardButton(text="🏁 Лимит на сегодня исчерпан", callback_data="farm:limit"))
        return kb

    if can_claim:
        if reward_preview and reward_preview > 0:
            kb.add(InlineKeyboardButton(text=f"💰 Забрать +{_fmt_points(int(reward_preview))}", callback_data="farm:claim"))
        else:
            kb.add(InlineKeyboardButton(text="⭐ Фармить баллы", callback_data="farm:claim"))
    else:
        mm = max(0, int(wait_seconds)) // 60
        ss = max(0, int(wait_seconds)) % 60
        kb.add(InlineKeyboardButton(text=f"⏳ Подождать {mm}:{ss:02d}", callback_data="farm:wait"))

    kb.add(InlineKeyboardButton(text="📅 Недельные задания", callback_data="farm:weekly"))
    kb.add(InlineKeyboardButton(text="📋 Задания", callback_data="farm:tasks"))
    return kb


def minigames_menu_kb(*, show_back: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="💣 Мины", callback_data="minigame:mines"))
    kb.add(InlineKeyboardButton(text="🎡 Колесо фортуны", callback_data="minigame:wheel"))
    kb.add(InlineKeyboardButton(text="🎲 Кости с ботом", callback_data="minigame:dice"))
    kb.add(InlineKeyboardButton(text="🪜 Лесенка", callback_data="minigame:ladder"))
    kb.add(InlineKeyboardButton(text="✊✌️🖐 КНБ с ботом", callback_data="minigame:rps"))
    kb.add(InlineKeyboardButton(text="⚔ Дуэли (PvP)", callback_data="minigame:duels"))
    if show_back:
        kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def game_bet_kb(
    *,
    game: str,
    last_bets: list[int] | None = None,
    presets: list[int] | None = None,
    show_presets: bool = True,
    extra_buttons: list[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    """Universal bet picker.

    New UX: fixed 3×3 grid + one back row.

    Callback data:
    - bet:pick:<game>:<amount>  (amount is int as string)
    - bet:pick:<game>:p25
    - bet:pick:<game>:p50
    - bet:pick:<game>:max
    - bet:back:<game>

    Notes:
    - `presets/show_presets/extra_buttons` are kept for backward compatibility but are ignored.
    """

    game = str(game)
    kb = InlineKeyboardMarkup()

    def _fmt_space(n: int) -> str:
        try:
            return f"{int(n):,}".replace(",", " ")
        except Exception:
            return str(n)

    last = None
    if last_bets:
        try:
            last = int(list(last_bets)[0])
        except Exception:
            last = None

    amounts = [10, 100, 1_000, 2_500, 5_000, 10_000]
    labels: dict[int, str] = {}
    for a in amounts:
        lbl = f"💰 {_fmt_space(a)} 💰"
        if last is not None and int(last) == int(a):
            lbl = f"⭐{lbl}⭐"
        labels[a] = lbl

    kb.row(
        InlineKeyboardButton(text=labels[10], callback_data=f"bet:pick:{game}:10"),
        InlineKeyboardButton(text=labels[100], callback_data=f"bet:pick:{game}:100"),
        InlineKeyboardButton(text=labels[1_000], callback_data=f"bet:pick:{game}:1000"),
    )
    kb.row(
        InlineKeyboardButton(text=labels[2_500], callback_data=f"bet:pick:{game}:2500"),
        InlineKeyboardButton(text=labels[5_000], callback_data=f"bet:pick:{game}:5000"),
        InlineKeyboardButton(text=labels[10_000], callback_data=f"bet:pick:{game}:10000"),
    )
    # For PvP duels we only allow fixed preset stakes.
    if str(game) != "duel":
        kb.row(
            InlineKeyboardButton(text="💰 25% 💰", callback_data=f"bet:pick:{game}:p25"),
            InlineKeyboardButton(text="💰 50% 💰", callback_data=f"bet:pick:{game}:p50"),
            InlineKeyboardButton(text="💰 MAX 💰", callback_data=f"bet:pick:{game}:max"),
        )
    kb.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"bet:back:{game}"))
    return kb


def rps_result_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data="rps:again"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def rps_stake_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for amount in (100, 500, 1000):
        kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(amount)} 💰", callback_data=f"rps:stake:{amount}"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def rps_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✊ Камень", callback_data="rps:choice:rock"))
    kb.add(InlineKeyboardButton(text="✌ Ножницы", callback_data="rps:choice:scissors"))
    kb.add(InlineKeyboardButton(text="✋ Бумага", callback_data="rps:choice:paper"))
    return kb


def wheel_kb(*, show_top: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(100)} 💰", callback_data="wheel:bet:100"))
    kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(500)} 💰", callback_data="wheel:bet:500"))
    kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(1000)} 💰", callback_data="wheel:bet:1000"))
    if show_top:
        kb.add(InlineKeyboardButton(text="🏆 Топ колеса", callback_data="wheel:top"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def wheel_result_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data="wheel:again"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def wheel_top_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="🥇 По выигрышам", callback_data="wheel:top:total"),
        InlineKeyboardButton(text="🎲 По спинам", callback_data="wheel:top:rolls"),
    )
    kb.add(InlineKeyboardButton(text="💎 Крупнейший выигрыш", callback_data="wheel:top:best"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="minigame:wheel"))
    return kb


def dice_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(100)} 💰", callback_data="dice:bet:100"))
    kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(500)} 💰", callback_data="dice:bet:500"))
    kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(1000)} 💰", callback_data="dice:bet:1000"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def dice_again_kb(bet: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data=f"dice:again:{int(bet)}"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def ladder_bet_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for b in (10, 50, 100, 500, 1000):
        kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(b)} 💰", callback_data=f"ladder:bet:{b}"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def ladder_play_kb(step: int, *, can_cashout: bool = True) -> InlineKeyboardMarkup:
    raise RuntimeError("ladder_play_kb signature changed; use ladder_field_kb")


def ladder_field_kb(
    *,
    step: int,
    mines: list[int],
    choices: list[int | None],
    reveal: bool = False,
    disabled: bool = False,
    show_cashout: bool = False,
) -> InlineKeyboardMarkup:
    """Inline grid for Ladder: 3 columns × 6 levels.

    Levels: 0(bottom) .. 5(top).
    During play:
      - higher levels are hidden (⬛)
      - current level is clickable (❓)
      - completed levels show mine (💣), chosen safe (✅), other safe (💰)
    On reveal:
      - show full layout with 💣/💰 and ✅ for opened safes; 💥 if a mine was chosen
    """
    kb = InlineKeyboardMarkup()
    total_levels = 6
    mines = list(mines or [])
    choices = list(choices or [])
    if len(mines) < total_levels:
        mines += [0] * (total_levels - len(mines))
    if len(choices) < total_levels:
        choices += [None] * (total_levels - len(choices))

    for level in range(total_levels - 1, -1, -1):
        mine_idx = int(mines[level])
        chosen_idx = choices[level]

        row_texts: list[str] = []
        row_cbs: list[str] = []

        if reveal:
            for col in range(3):
                if chosen_idx is not None and int(chosen_idx) == col and col == mine_idx:
                    row_texts.append("💥")
                elif col == mine_idx:
                    row_texts.append("💣")
                elif chosen_idx is not None and int(chosen_idx) == col:
                    row_texts.append("✅")
                else:
                    row_texts.append("💰")
                row_cbs.append("noop")
        else:
            if level > int(step):
                row_texts = ["❌", "❌", "❌"]
                row_cbs = ["noop", "noop", "noop"]
            elif level == int(step):
                for col in range(3):
                    row_texts.append("❓")
                    row_cbs.append("noop" if disabled else f"ladder:pick:{int(step)}:{col}")
            else:
                # completed level: reveal that level only
                for col in range(3):
                    if chosen_idx is not None and int(chosen_idx) == col:
                        row_texts.append("✅")
                    elif col == mine_idx:
                        row_texts.append("💣")
                    else:
                        row_texts.append("💰")
                    row_cbs.append("noop")

        kb.row(
            InlineKeyboardButton(text=row_texts[0], callback_data=row_cbs[0]),
            InlineKeyboardButton(text=row_texts[1], callback_data=row_cbs[1]),
            InlineKeyboardButton(text=row_texts[2], callback_data=row_cbs[2]),
        )

    if show_cashout and not reveal:
        kb.add(InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data=("noop" if disabled else "ladder:cashout")))

    return kb


def ladder_result_kb(*, bet: int, mines: list[int], choices: list[int | None], step: int) -> InlineKeyboardMarkup:
    kb = ladder_field_kb(step=step, mines=mines, choices=choices, reveal=True, disabled=True, show_cashout=False)
    kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data=f"ladder:again:{int(bet)}"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def ladder_again_kb(bet: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data=f"ladder:again:{int(bet)}"))
    kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def duels_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⚔ Создать дуэль", callback_data="duel:create"))
    kb.add(InlineKeyboardButton(text="🔍 Найти дуэль", callback_data="duel:find"))
    kb.add(InlineKeyboardButton(text="👥 Играть с другом", callback_data="duel:friend"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="minigames:open"))
    return kb


def duel2_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🎲 Кости", callback_data="duel2:game:dice"))
    kb.add(InlineKeyboardButton(text="✊✋✌ Камень Ножницы Бумага", callback_data="duel2:game:rps"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="minigames:open"))
    return kb


def duel2_stake_kb(game_type: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for amount in (50, 100, 250, 500):
        kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(int(amount))} 💰", callback_data=f"duel2:stake:{game_type}:{amount}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel2:menu"))
    return kb


def duel2_invite_kb(code: str, *, bot_username: str | None, stake: int, game_type: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    # switch_inline_query opens inline picker with a prefilled query
    kb.add(InlineKeyboardButton(text="👤 Выбрать друга", switch_inline_query=f"duel_{code}"))
    # deep-link
    if bot_username:
        kb.add(InlineKeyboardButton(text="🔗 Ссылка на дуэль", url=f"https://t.me/{bot_username}?start=duel_{code}"))
    else:
        kb.add(InlineKeyboardButton(text="🔗 Ссылка на дуэль", callback_data="noop"))
    kb.add(InlineKeyboardButton(text="🎯 Случайный игрок", callback_data=f"duel2:random:start:{game_type}:{stake}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel2:menu"))
    return kb


def duel_friend_actions_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="👥 Друзья", callback_data=f"duel:friends_for_duel:{int(duel_id)}"))
    kb.add(InlineKeyboardButton(text="➕ Пригласить друга", callback_data=f"duel:invite_link:{int(duel_id)}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:menu"))
    return kb


def duel_invite_link_back_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data=f"duel:invite_menu:{int(duel_id)}"))
    return kb


def duel2_friend_actions_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="👥 Друзья", callback_data=f"duel2:friends_for_duel:{int(duel_id)}"))
    kb.add(InlineKeyboardButton(text="➕ Пригласить друга", callback_data=f"duel2:invite_link:{int(duel_id)}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel2:menu"))
    return kb


def duel2_invite_link_back_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data=f"duel2:invite_menu:{int(duel_id)}"))
    return kb


def server_duels_list_kb(
    duels: list[dict],
    *,
    current_user_id: int | None = None,
    own_duel: dict | None = None,
    enabled_games: set[str],
    enabled_stakes: set[int],
    page: int,
    pages: int,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()

    try:
        current_uid = int(current_user_id) if current_user_id is not None else None
    except Exception:
        current_uid = None

    for d in duels:
        duel_id = int(d.get("duel_id") or 0)
        stake = int(d.get("stake") or 0)
        gt = str(d.get("game_type") or "")
        try:
            creator_id = int(d.get("creator_id") or 0)
        except Exception:
            creator_id = 0
        try:
            is_bot = int(d.get("is_bot") or 0)
        except Exception:
            is_bot = 0
        if gt == "dice":
            type_txt = "🎲 Кубики"
        elif gt == "rps":
            type_txt = "✊✋✌ КНБ"
        else:
            type_txt = "❌⭕ Крестики-нолики"

        is_own = (current_uid is not None and creator_id == int(current_uid) and is_bot == 0)
        if is_own:
            label = str(d.get("label") or f"🧾 Моя дуэль · {type_txt} · {stake}")
            cb = f"duel:my:{duel_id}"
        else:
            label = str(d.get("label") or f"{type_txt} · {stake} · Ожидает соперника")
            cb = f"duel:join:{duel_id}"
        kb.add(
            InlineKeyboardButton(
                text=label,
                callback_data=cb,
            )
        )

    # filters: games
    g_dice = "✅ 🎲" if "dice" in enabled_games else "❌ 🎲"
    g_rps = "✅ ✊✋✌" if "rps" in enabled_games else "❌ ✊✋✌"
    g_ttt = "✅ ❌⭕" if "ttt" in enabled_games else "❌ ❌⭕"
    kb.row(
        InlineKeyboardButton(text=g_dice, callback_data="duel:filter:game:dice"),
        InlineKeyboardButton(text=g_rps, callback_data="duel:filter:game:rps"),
        InlineKeyboardButton(text=g_ttt, callback_data="duel:filter:game:ttt"),
    )

    # filters: stakes
    stake_opts = (10, 100, 1000, 2500, 5000, 10000)
    stake_buttons: list[InlineKeyboardButton] = []
    for a in stake_opts:
        stake_buttons.append(
            InlineKeyboardButton(
                text=(f"✅ {a}" if int(a) in enabled_stakes else f"❌ {a}"),
                callback_data=f"duel:filter:stake:{int(a)}",
            )
        )
    kb.row(stake_buttons[0], stake_buttons[1], stake_buttons[2])
    kb.row(stake_buttons[3], stake_buttons[4], stake_buttons[5])

    # pages (emoji only)
    try:
        pages_int = int(pages)
    except Exception:
        pages_int = 1
    if pages_int < 1:
        pages_int = 1
    if pages_int > 1:
        page_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
        page_buttons: list[InlineKeyboardButton] = []
        for i in range(min(pages_int, len(page_emojis))):
            page_buttons.append(
                InlineKeyboardButton(text=page_emojis[i], callback_data=f"duel:filter:page:{int(i)}")
            )
        if page_buttons:
            kb.row(*page_buttons)

    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:menu"))
    return kb


def admin_duel_server_kb(*, auto_recreate: bool, random_enabled: bool, max_pool: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✅ Быстрый запуск", callback_data="admin:duel_server:quick"))
    kb.add(InlineKeyboardButton(text="🎲 Рандом пул", callback_data="admin:duel_server:random"))
    kb.row(
        InlineKeyboardButton(text="➕ Добавить 1 дуэль", callback_data="admin:duel_server:add_one"),
        InlineKeyboardButton(text="➕ Добавить дуэли", callback_data="admin:duel_server:add"),
    )
    kb.add(InlineKeyboardButton(text="🛠 Управление", callback_data="admin:duel_server:manage"))
    ar_txt = "♻ Авто-перезапуск: ВКЛ" if auto_recreate else "♻ Авто-перезапуск: ВЫКЛ"
    kb.add(InlineKeyboardButton(text=ar_txt, callback_data="admin:duel_server:auto_recreate"))
    limit_txt = f"⚙ Лимит пула: {int(max_pool)}" if int(max_pool) > 0 else "⚙ Лимит пула: не задан"
    kb.add(InlineKeyboardButton(text=limit_txt, callback_data="admin:duel_server:limit"))
    return kb


def admin_duel_server_quick_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="✅ Запустить +5", callback_data="admin:duel_server:quick:do"),
        InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:menu"),
    )
    return kb


def admin_duel_server_limit_kb(*, max_pool: int) -> InlineKeyboardMarkup:
    cur = int(max_pool)
    kb = InlineKeyboardMarkup()

    def _btn(n: int) -> InlineKeyboardButton:
        txt = f"✅ {n}" if int(cur) == int(n) else str(n)
        return InlineKeyboardButton(text=txt, callback_data=f"admin:duel_server:limit:set:{int(n)}")

    kb.row(_btn(5), _btn(10), _btn(15))
    kb.row(_btn(20), _btn(30), InlineKeyboardButton(text="✏️ Другое", callback_data="admin:duel_server:limit:custom"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:menu"))
    return kb


def admin_duel_server_add_game_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🎲", callback_data="admin:duel_server:add_game:dice"))
    kb.add(InlineKeyboardButton(text="✊✋✌", callback_data="admin:duel_server:add_game:rps"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:menu"))
    return kb


def admin_duel_server_add_stake_kb(*, game_type: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for amount in (200, 500, 1000):
        kb.add(
            InlineKeyboardButton(
                text=f"Ставка {amount}",
                callback_data=f"admin:duel_server:add_stake:{game_type}:{amount}",
            )
        )
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:add"))
    return kb


def admin_duel_server_random_kb(
    *,
    enabled: bool,
    min_pool: int,
    max_pool: int,
    games: set[str],
    stakes: set[int],
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            text=("🎲 Рандом: ВКЛ" if enabled else "🎲 Рандом: ВЫКЛ"),
            callback_data="admin:duel_server:random:toggle",
        )
    )
    kb.row(
        InlineKeyboardButton(text=f"Мин: {int(min_pool)}", callback_data="admin:duel_server:random:setmin"),
        InlineKeyboardButton(text=f"Макс: {int(max_pool)}", callback_data="admin:duel_server:random:setmax"),
    )
    kb.row(
        InlineKeyboardButton(
            text=("✅ 🎲" if "dice" in games else "➕ 🎲"),
            callback_data="admin:duel_server:random:game:dice",
        ),
        InlineKeyboardButton(
            text=("✅ ✊✋✌" if "rps" in games else "➕ ✊✋✌"),
            callback_data="admin:duel_server:random:game:rps",
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text=("✅ 200" if 200 in stakes else "➕ 200"),
            callback_data="admin:duel_server:random:stake:200",
        ),
        InlineKeyboardButton(
            text=("✅ 500" if 500 in stakes else "➕ 500"),
            callback_data="admin:duel_server:random:stake:500",
        ),
        InlineKeyboardButton(
            text=("✅ 1000" if 1000 in stakes else "➕ 1000"),
            callback_data="admin:duel_server:random:stake:1000",
        ),
    )
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admin:duel_server:menu"))
    return kb


def duel_stake_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for amount in (200, 500, 1000):
        kb.add(InlineKeyboardButton(text=f"Ставка {amount}", callback_data=f"duel:stake:{amount}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:menu"))
    return kb


def duel_type_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🎲 Кубики", callback_data="duel:type:dice"))
    kb.add(InlineKeyboardButton(text="✊✋✌ КНБ", callback_data="duel:type:rps"))
    kb.add(InlineKeyboardButton(text="❌⭕ Крестики-нолики", callback_data="duel:type:ttt"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:menu"))
    return kb


def duel_rps_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✊ Камень", callback_data=f"duel:rps:{duel_id}:rock"))
    kb.add(InlineKeyboardButton(text="✌ Ножницы", callback_data=f"duel:rps:{duel_id}:scissors"))
    kb.add(InlineKeyboardButton(text="✋ Бумага", callback_data=f"duel:rps:{duel_id}:paper"))
    return kb


def duel_rematch_offer_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data=f"duel:rematch_offer:{duel_id}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:menu"))
    return kb


def duel_rematch_answer_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✅ Согласиться", callback_data=f"duel:rematch_accept:{duel_id}"))
    kb.add(InlineKeyboardButton(text="❌ Отказаться", callback_data=f"duel:rematch_decline:{duel_id}"))
    return kb


def bot_rematch_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="♻️ Сыграть ещё раз", callback_data=f"duel:bot_rematch:{duel_id}"))
    return kb


def duel_rematch_stake_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for amount in (200, 500, 1000):
        kb.add(InlineKeyboardButton(text=f"Ставка {_fmt_points(amount)}", callback_data=f"duel:rematch_stake:{duel_id}:{amount}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="duel:menu"))
    return kb


def duel_rematch_opponent_choice_kb(duel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🔁 Поменять ставку", callback_data=f"duel:rematch_change:{duel_id}"))
    kb.add(InlineKeyboardButton(text="✅ Согласен", callback_data=f"duel:rematch_confirm:{duel_id}"))
    kb.add(InlineKeyboardButton(text="🚫 Прекратить игру", callback_data=f"duel:rematch_stop:{duel_id}"))
    return kb


def mines_mode_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="minigames:open"))
    return kb


def mines_params_kb(
    size: int | None,
    mines: int | None,
    bet: int | None,
    *,
    mode: str = "classic",
    attempts_text: str | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    size_txt = f"{size}×{size}" if size else "выбрать"
    mines_txt = str(mines) if mines else "выбрать"
    bet_txt = _fmt_points(int(bet)) if bet else "выбрать"

    # Step-by-step wizard: size -> mines -> bet -> start
    kb.add(InlineKeyboardButton(text=f"📐 Размер поля: {size_txt}", callback_data="mines:pick_size"))

    if size:
        kb.add(InlineKeyboardButton(text=f"💣 Количество мин: {mines_txt}", callback_data="mines:pick_mines"))

    if size and mines:
        if str(mode) == "nobet":
            kb.add(InlineKeyboardButton(text=f"⚡ Попытки: {attempts_text or '—'}", callback_data="mines:energy_info"))
            kb.add(InlineKeyboardButton(text="✅ Начать игру", callback_data="mines:confirm"))
        else:
            kb.add(InlineKeyboardButton(text=f"💰 Ставка: {bet_txt}", callback_data="mines:pick_bet"))
            if bet:
                kb.add(InlineKeyboardButton(text="✅ Начать игру", callback_data="mines:confirm"))

    kb.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="minigames:open"))
    return kb


def mines_size_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="3×3", callback_data="mines:size:3"))
    kb.add(InlineKeyboardButton(text="6×6", callback_data="mines:size:6"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="mines:params"))
    return kb


def mines_mines_kb(size: int | None, vip_active: bool = False, *, mode: str = "classic") -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    # display multipliers for choices
    # Display adjusted multipliers (VIP прибавляется в игре; здесь только подсказка)
    display_map_3 = {1: 0.35, 2: 0.85, 3: 1.50, 4: 2.40, 5: 3.80}
    display_map_6 = {5: 0.35, 8: 0.60, 12: 0.95, 16: 1.40, 20: 2.06}

    def _vip_bonus_hint(s: int | None, m: int) -> float | None:
        if not vip_active:
            return None
        if s == 6:
            return {5: 0.30, 8: 0.35, 12: 0.40, 16: 0.45, 20: 0.50}.get(int(m))
        if s == 3:
            mm = max(0, min(5, int(m)))
            return round(min(0.50, 0.10 * mm), 2)
        return 0.50
    if str(mode) == "hardcore":
        options = [4, 5]
        disp = {}
    elif str(mode) == "nobet":
        options = [2, 3]
        disp = {}
    elif size == 3:
        options = [1, 2, 3, 4, 5]
        disp = display_map_3
    elif size == 6:
        options = [5, 8, 12, 16, 20]
        disp = display_map_6
    else:
        options = [1, 3, 5]
        disp = {}
    for m in options:
        vip_hint = _vip_bonus_hint(size, m)
        if m in disp:
            mult = disp[m]
            txt = f"{m} — x{mult:.2f}"
            if vip_hint is not None:
                txt += f" (+{vip_hint:.2f} VIP)"
            kb.add(InlineKeyboardButton(text=txt, callback_data=f"mines:mines:{m}"))
        else:
            txt = str(m)
            if vip_hint is not None:
                txt += f" (+{vip_hint:.2f} VIP)"
            kb.add(InlineKeyboardButton(text=txt, callback_data=f"mines:mines:{m}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="mines:params"))
    return kb


def mines_bet_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for b in [50, 100, 250, 500]:
        kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(int(b))} 💰", callback_data=f"mines:bet:{b}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="mines:params"))
    return kb


def mines_bet_kb_mode(*, mode: str = "classic") -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    bets = [50, 100, 250, 500]
    if str(mode) == "hardcore":
        bets = [100, 250, 500, 1000]
    for b in bets:
        kb.add(InlineKeyboardButton(text=f"💰 {_fmt_points(int(b))} 💰", callback_data=f"mines:bet:{b}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="mines:params"))
    return kb


def mines_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="▶️ Начать игру", callback_data="mines:begin"))
    kb.add(InlineKeyboardButton(text="⬅ Изменить параметры", callback_data="mines:params"))
    return kb


def mines_field_kb(
    *,
    size: int,
    opened_cells: set[int],
    mine_cell: int | None = None,
    mine_cells: set[int] | None = None,
    show_cashout: bool = False,
    disabled: bool = False,
    reveal: bool = False,
    show_restart: bool = False,
) -> InlineKeyboardMarkup:
    total = int(size) * int(size)
    kb = InlineKeyboardMarkup()
    cols = int(size)
    row: list[InlineKeyboardButton] = []
    for i in range(1, total + 1):
        if reveal:
            if mine_cell is not None and i == int(mine_cell):
                txt = "💥"
            elif mine_cells and i in mine_cells:
                txt = "💣"
            else:
                txt = "✅" if i in opened_cells else "💎"
            cb = "noop"
        else:
            if mine_cell == i:
                txt = "💥"
                cb = "noop"
            elif i in opened_cells:
                txt = "✅"
                cb = "noop"
            else:
                txt = "❓"
                cb = "noop" if disabled else f"mines:cell:{i}"
        row.append(InlineKeyboardButton(text=txt, callback_data=cb))
        if len(row) == cols:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)

    # Only show cashout button after at least one cell was opened — avoids keyboard reflow on first click
    if show_cashout and not reveal and opened_cells:
        cb = "mines:cashout" if not disabled else "noop"
        kb.add(InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data=cb))

    if reveal and show_restart:
        kb.add(InlineKeyboardButton(text="♻️ Играть снова", callback_data="mines:restart"))

    if reveal:
        kb.add(InlineKeyboardButton(text="🎮 Мини игры", callback_data="minigames:open"))
    return kb


def tasks_menu_kb(sub_reward: int, tiktok_reward: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text=f"📢 Подписка на канал – +{sub_reward} баллов", callback_data="taskcode:channel"))
    kb.add(InlineKeyboardButton(text=f"📝 TikTok — комментарий – +{tiktok_reward} баллов", callback_data="taskcode:tiktok"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def channel_task_kb(channel_url: str | None, show_subscribe: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    if show_subscribe and channel_url:
        kb.add(InlineKeyboardButton(text="🔴 Подписаться", url=channel_url))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def repeat_offer_kb(task_code: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="🔁 Выполнить повторно", callback_data=f"repeat:{task_code}"),
        InlineKeyboardButton(text="❌ Отказаться", callback_data=f"repeat:no:{task_code}"),
    )
    return kb


def tiktok_task_kb(state: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    if state == "available":
        kb.add(InlineKeyboardButton(text="📝 Получить текст для комментария", callback_data="tiktok:text"))
        kb.add(InlineKeyboardButton(text="📸 Отправить скрин", callback_data="tiktok:sendproof"))
        kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
        return kb

    if state == "pending":
        kb.add(InlineKeyboardButton(text="🕒 В обработке", callback_data="noop"))
        kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
        return kb

    if state == "completed":
        kb.add(InlineKeyboardButton(text="✅ Выполнено", callback_data="noop"))
        kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
        return kb

    # repeat_offer or refused
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def back_inline_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def points_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def withdraw_menu_kb(can_withdraw_30: bool, can_withdraw_50: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    if can_withdraw_30:
        kb.add(InlineKeyboardButton(text="💸 Вывести 30₽", callback_data=f"withdraw:{WITHDRAW_OPTIONS_RUB[0]}"))
    if can_withdraw_50:
        kb.add(InlineKeyboardButton(text="💸 Вывести 50₽", callback_data=f"withdraw:{WITHDRAW_OPTIONS_RUB[1]}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def banks_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for i, b in enumerate(BANK_OPTIONS):
        kb.add(InlineKeyboardButton(text=b, callback_data=f"bank:{i}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def confirm_withdraw_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="withdraw:confirm"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def invite_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="invite:link"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def support_kb(admin_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="📜 Правила", callback_data="support:rules"))
    kb.add(InlineKeyboardButton(text="✉ Связаться с админом", url=f"tg://user?id={admin_id}"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb


def admin_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("👤 Пользователи"), KeyboardButton("📸 Проверка заданий"))
    kb.row(KeyboardButton("💸 Выводы"), KeyboardButton("📊 Статистика"))
    kb.row(KeyboardButton("⚔ Сервер дуэлей"))
    kb.row(KeyboardButton("🏆 Турниры"))
    kb.row(KeyboardButton("⬅ Выйти из админки"))
    return kb


def admin_gift_user_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="🎁 Подарить баллы", callback_data="admin:gift:amount"),
        InlineKeyboardButton(text="💬 Написать", callback_data="admin:chat:start"),
    )
    kb.add(InlineKeyboardButton(text="🔎 Выбрать другого", callback_data="admin:gift:pick_user"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admin:panel"))
    return kb


def admin_gift_confirm_kb(*, notify_enabled: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="✅ Отправить", callback_data="admin:gift:send"))
    txt = "🔕 Уведомление: ВКЛ" if bool(notify_enabled) else "🔕 Уведомление: ВЫКЛ"
    kb.add(InlineKeyboardButton(text=txt, callback_data="admin:gift:notify:toggle"))
    kb.row(
        InlineKeyboardButton(text="🎁 Изменить сумму", callback_data="admin:gift:amount"),
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data="admin:gift:text"),
    )
    kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data="admin:gift:cancel"))
    return kb


def admin_chat_stop_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⛔ Завершить диалог", callback_data="admin:chat:stop"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="admin:panel"))
    return kb


def dialog_user_open_kb(dialog_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="📖 Открыть", callback_data=f"dialog:open:{int(dialog_id)}"))
    return kb


def dialog_user_kb(dialog_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="✍️ Ответить", callback_data=f"dialog:user_reply:{int(dialog_id)}"),
        InlineKeyboardButton(text="🚫 Закрыть", callback_data=f"dialog:user_close:{int(dialog_id)}"),
    )
    return kb


def dialog_admin_kb(dialog_id: int, *, history_count: int = 5) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="✍️ Ответить", callback_data=f"dialog:admin_reply:{int(dialog_id)}"),
        InlineKeyboardButton(text=f"📋 История ({int(history_count)})", callback_data=f"dialog:admin_history:{int(dialog_id)}"),
        InlineKeyboardButton(text="❌ Завершить", callback_data=f"dialog:admin_close:{int(dialog_id)}"),
    )
    return kb


def admin_review_submission_kb(submission_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="✅ Всё ок", callback_data=f"sub:ok:{submission_id}"),
        InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"sub:bad:{submission_id}"),
    )
    kb.add(InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"sub:block:{submission_id}"))
    return kb


def admin_review_withdraw_kb(withdrawal_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="✅ Выплачено", callback_data=f"wd:paid:{withdrawal_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd:decline:{withdrawal_id}"),
    )
    return kb


def admin_add_task_type_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="📱 TikTok — комментарий", callback_data="addtask:type:tiktok_comment"))
    kb.add(InlineKeyboardButton(text="📢 Подписка на канал", callback_data="addtask:type:channel_subscribe"))
    kb.add(InlineKeyboardButton(text="⬅ Назад", callback_data="back"))
    return kb
