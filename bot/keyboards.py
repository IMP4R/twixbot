from __future__ import annotations

import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.emoji import (
    MONEY, CHART_GROWTH, PROFILE, BOX, CLOCK, LOADING,
    SETTINGS, BELL, CHECK, CROSS, PIN_EMOJI,
    CRYPTO_BOT, LINK, ARROW_UP, DOWNLOAD,
    GIFT, PENCIL, ADD_TEXT, EXCHANGE,
)


def _safe_icon(raw: str | None) -> str | None:
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return raw
    m = re.search(r'emoji-id="(\d+)"', raw)
    if m:
        return m.group(1)
    return None


def _b(text: str, cb: str, icon: str | None = None) -> dict:
    kw: dict = {"text": text, "callback_data": cb}
    safe = _safe_icon(icon)
    if safe:
        kw["icon_custom_emoji_id"] = safe
    return kw


# ══════════════════════════════════════════════════════════════════════
#  HOME (главный экран клиента)
# ══════════════════════════════════════════════════════════════════════

def home_keyboard(is_manager: bool = False, is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Продать USDT", "sell_usdt", icon=MONEY))
    builder.button(**_b("Меню", "client_menu", icon=BOX))
    if is_manager:
        builder.button(**_b("Менеджер", "manager_menu", icon=PROFILE))
    if is_admin:
        builder.button(**_b("Админка", "admin_menu", icon=SETTINGS))
    builder.adjust(1)
    return builder.as_markup()


def manager_home_keyboard(mgr, current_deal=None, queued_count=0, is_admin=False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Shift toggle
    if mgr.is_online:
        builder.button(**_b("Завершить смену", "mgr_shift_end", icon=CROSS))
    else:
        builder.button(**_b("Начать смену", "mgr_shift_start", icon=CHECK))

    # Quick deal access
    if current_deal:
        rub = current_deal.amount_usdt * current_deal.client_rate
        builder.button(
            text=f"Текущая: {current_deal.amount_usdt} USDT ({rub:.0f} ₽)",
            callback_data=f"mgr_deal_{current_deal.id}",
        )
    else:
        builder.button(**_b("Нет текущей сделки", "mgr_deals", icon=LOADING))

    # Queue
    if queued_count:
        builder.button(**_b(f"Очередь: {queued_count} сделок", "mgr_deals", icon=DOWNLOAD))
    else:
        builder.button(**_b("Очередь пуста", "mgr_deals", icon=DOWNLOAD))

    # Commands cheat sheet + settings + client view
    builder.button(**_b("Команды в ЛС", "mgr_commands_help", icon=ADD_TEXT))
    builder.button(**_b("Настройки", "mgr_settings", icon=SETTINGS))
    builder.button(**_b("Меню", "manager_menu", icon=ARROW_UP))
    if is_admin:
        builder.button(**_b("Админка", "admin_menu", icon=SETTINGS))
    builder.adjust(1)
    return builder.as_markup()


def tos_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Согласен", "accept_tos", icon=CHECK))
    builder.adjust(1)
    return builder.as_markup()


# ══════════════════════════════════════════════════════════════════════
#  CLIENT MENU (побочное меню)
# ══════════════════════════════════════════════════════════════════════

def client_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Моя сделка", "my_deal", icon=EXCHANGE))
    builder.button(**_b("Курсы", "rates", icon=LINK))
    builder.button(**_b("Профиль", "profile", icon=CHART_GROWTH))
    builder.button(**_b("История", "history", icon=BOX))
    builder.button(**_b("Тикеты", "tickets", icon=GIFT))
    builder.button(**_b("Назад", "home", icon=ARROW_UP))
    builder.adjust(1)
    return builder.as_markup()


# ══════════════════════════════════════════════════════════════════════
#  DEAL FLOW
# ══════════════════════════════════════════════════════════════════════

def deal_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Подтвердить", "confirm_deal", icon=CHECK))
    builder.button(**_b("Отменить", "cancel_deal", icon=CROSS))
    builder.adjust(2)
    return builder.as_markup()


def my_deal_keyboard(has_deal: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_deal:
        builder.button(**_b("Отменить сделку", "client_cancel_deal", icon=CROSS))
        builder.button(**_b("Назад", "client_menu", icon=ARROW_UP))
    else:
        builder.button(**_b("Продать USDT", "sell_usdt", icon=MONEY))
        builder.button(**_b("Назад", "client_menu", icon=ARROW_UP))
    builder.adjust(1)
    return builder.as_markup()


def back_keyboard(callback_data: str = "home") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Назад", callback_data, icon=ARROW_UP))
    builder.adjust(1)
    return builder.as_markup()


# ══════════════════════════════════════════════════════════════════════
#  RATES
# ══════════════════════════════════════════════════════════════════════

def rates_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Продать USDT", "sell_usdt", icon=MONEY))
    builder.button(**_b("Назад", "client_menu", icon=ARROW_UP))
    builder.adjust(1)
    return builder.as_markup()


# ══════════════════════════════════════════════════════════════════════
#  MANAGER
# ══════════════════════════════════════════════════════════════════════

def manager_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Сделки", "mgr_deals", icon=DOWNLOAD))
    builder.button(**_b("Статистика", "mgr_stats", icon=CHART_GROWTH))
    builder.button(**_b("Уведомления", "mgr_notifications", icon=BELL))
    builder.button(**_b("Настройки", "mgr_settings", icon=SETTINGS))
    builder.button(**_b("Назад", "home", icon=ARROW_UP))
    builder.adjust(1)
    return builder.as_markup()


def manager_deals_keyboard(current_deal: object | None = None, queued_deals: list | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if current_deal:
        builder.button(
            text=f"{current_deal.amount_usdt} USDT — текущая",
            callback_data=f"mgr_deal_{current_deal.id}",
        )
    if queued_deals:
        for d in queued_deals:
            builder.button(
                text=f"{d.amount_usdt} USDT — в очереди",
                callback_data=f"mgr_deal_{d.id}",
            )
    builder.button(**_b("Назад", "manager_menu", icon=ARROW_UP))
    builder.adjust(1)
    return builder.as_markup()


def deal_action_keyboard(deal_id: str, is_pinned: bool = False, is_current: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Завершить", f"deal_close_{deal_id}", icon=CHECK))
    builder.button(**_b("Отменить", f"deal_cancel_{deal_id}", icon=CROSS))
    if not is_pinned:
        builder.button(**_b("Закрепить", f"deal_pin_{deal_id}", icon=PIN_EMOJI))
    else:
        builder.button(**_b("Открепить", f"deal_unpin_{deal_id}", icon=PIN_EMOJI))
    if not is_current:
        builder.button(**_b("Сделать текущей", f"deal_promote_{deal_id}", icon=ARROW_UP))
    builder.button(**_b("В общую очередь", f"deal_transfer_{deal_id}", icon=LOADING))
    builder.button(**_b("Назад", "mgr_deals", icon=ARROW_UP))
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


# ══════════════════════════════════════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════════════════════════════════════

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Статистика", "admin_stats", icon=CHART_GROWTH))
    builder.button(**_b("Отчёты", "admin_earnings_reports", icon=CHART_GROWTH))
    builder.button(**_b("Сделки", "admin_deals", icon=BOX))
    builder.button(**_b("Курсы", "admin_rates", icon=LINK))
    builder.button(**_b("Менеджеры", "admin_managers", icon=CHECK))
    builder.button(**_b("Система", "admin_tools", icon=BOX))
    builder.button(**_b("Настройки", "admin_settings", icon=SETTINGS))
    builder.button(**_b("Назад", "home", icon=ARROW_UP))
    builder.adjust(2, 1, 2, 2, 1)
    return builder.as_markup()


def profile_keyboard(is_anonymous: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    icon = CHECK if is_anonymous else CROSS
    status = "Анонимность: Вкл" if is_anonymous else "Анонимность: Выкл"
    builder.button(**_b(status, "profile_toggle_anonymous", icon=icon))
    builder.button(**_b("Назад", "client_menu", icon=ARROW_UP))
    builder.adjust(1)
    return builder.as_markup()


def confirm_keyboard(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(**_b("Да, подтвердить", yes_cb, icon=CHECK))
    builder.button(**_b("Отмена", no_cb, icon=CROSS))
    builder.adjust(2)
    return builder.as_markup()
