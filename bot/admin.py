from __future__ import annotations
from presentation import send_text, send_chat
from tg_templates import SafeHTML

import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal

from bot.common import IsAdmin, IsManager, safe_edit_text
from bot.keyboards import confirm_keyboard, back_keyboard
from bot.emoji import (
    TAG_SETTINGS, TAG_CHART, TAG_CHECK, TAG_CROSS, TAG_MONEY,
    TAG_PEOPLE, TAG_PROFILE, TAG_RECEIPT, TAG_EXCHANGE, TAG_PIN,
    TAG_GIFT, TAG_PARTY, TAG_LOADING, TAG_BOX, TAG_PENCIL,
    TAG_ARROW_UP, TAG_CLIP, TAG_LINK, TAG_DOWNLOAD, TAG_INFO,
    TAG_MONEY_SEND, TAG_MONEY_RECEIVE, TAG_LOCK, TAG_BRUSH,
    TAG_TRASH,
    ARROW_UP, PEOPLE, CHECK, CROSS, LINK as LINK_ID, BOX, GIFT,
    SETTINGS as SETTINGS_ID, CHART_GROWTH, PROFILE, CLIP,
    PIN_EMOJI, LOADING, ADD_TEXT, MONEY, BELL, MEGAPHONE,
    PENCIL,
)
from config import ADMIN_IDS
from models import Manager, Rate
from repositories import ManagerRepository, DealRepository, UserRepository, RateRepository, ShiftReportRepository
from bot.client import STATUS_RU
from services import DealService, RateService, AuditService, ShiftReportService, PromocodeService
from html import escape as escape_html
import presentation as tpl

router = Router()
# Authorize every admin mutation/read before FSM and callback handlers.
router.message.filter(IsAdmin(ADMIN_IDS))
router.callback_query.filter(IsAdmin(ADMIN_IDS))


class AdminStates(StatesGroup):
    add_manager = State()
    edit_rate = State()
    edit_rate_name = State()
    edit_rate_min = State()
    edit_rate_max = State()
    edit_rate_value = State()
    edit_rate_rapira_percent = State()
    add_rate_name = State()
    add_rate_min = State()
    add_rate_max = State()
    add_rate_value = State()
    add_rate_rapira_percent = State()
    edit_manager_name = State()
    broadcast_message = State()
    promocode_add = State()


def _b(text: str, cb: str, icon: str | None = None) -> dict:
    kw: dict = {"text": text, "callback_data": cb}
    safe = _safe_icon(icon)
    if safe:
        kw["icon_custom_emoji_id"] = safe
    return kw


def _safe_icon(raw: str | None) -> str | None:
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return raw
    m = re.search(r'emoji-id="(\d+)"', raw)
    if m:
        return m.group(1)
    return None


async def _get_approx_rate() -> Decimal:
    """Return Rapira last price or fallback 84 for ₽↔USDT approx."""
    from twix_settings import get
    rapira = await get("rates.rapira_last_price")
    if rapira:
        return Decimal(str(rapira))
    return Decimal("84")


async def _sync_rapira_baseline():
    """Sync rapira_baseline to last_price so next poll sees delta ≈ 0."""
    from twix_settings import get as settings_get, set as settings_set
    last = await settings_get("rates.rapira_last_price")
    if last:
        await settings_set("rates.rapira_baseline", str(last))


# ── Admin Menu ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery):
    await callback.answer()
    await tpl.edit_template(callback, "admin.menu", {})


@router.callback_query(F.data == "admin_earnings_reports")
async def cb_admin_earnings_reports(callback: CallbackQuery):
    await callback.answer()
    await tpl.edit_template(callback, "admin.earnings_reports", {})


@router.callback_query(F.data == "admin_tools")
async def cb_admin_tools(callback: CallbackQuery):
    await callback.answer()
    await tpl.edit_template(callback, "admin.tools", {})




# ── Setup Guide ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_setup_guide")
async def cb_admin_setup_guide(callback: CallbackQuery):
    await callback.answer()
    await tpl.edit_template(callback, "admin.setup_guide", {})


# ── Statistics ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    await callback.answer()

    deal_repo = DealRepository()
    all_deals = deal_repo.list_all()
    closed = [d for d in all_deals if d.status == "closed"]
    total_profit = sum((d.profit for d in closed), Decimal("0"))
    total_volume = sum((d.amount_usdt for d in closed), Decimal("0"))
    total_volume_rub = sum((d.amount_usdt * d.client_rate for d in closed), Decimal("0"))

    mgr_repo = ManagerRepository()
    managers = mgr_repo.list_all()

    avg_rate = await _get_approx_rate()
    if closed:
        avg_rate = sum((d.client_rate for d in closed), Decimal("0")) / Decimal(len(closed))
    total_profit_usdt = total_profit / avg_rate if avg_rate else Decimal("0")

    await tpl.edit_template(
        callback, "admin.stats",
        {
            "total_deals": str(len(all_deals)),
            "closed": str(len(closed)),
            "profit": f"{total_profit:.2f}",
            "profit_usdt": f"{total_profit_usdt:.2f}",
            "volume": f"{total_volume:.2f}",
            "volume_rub": f"{total_volume_rub:.0f}",
            "manager_count": str(len(managers)),
        },
    )


@router.callback_query(F.data == "admin_stats_day")
async def cb_admin_stats_day(callback: CallbackQuery):
    await callback.answer()
    from services import StatsService
    stats_service = StatsService()
    daily = stats_service.get_daily_stats(days=30)
    avg_rate = await _get_approx_rate()

    items = ""
    if daily:
        for row in daily:
            profit_usdt = Decimal(str(row['profit'])) / avg_rate if avg_rate else Decimal("0")
            vol_rub = Decimal(str(row['volume'])) * avg_rate if avg_rate else Decimal("0")
            items += f"• {row['day']}: {row['deals']} сделок, {Decimal(str(row['profit'])):.0f} ₽ (~{profit_usdt:.1f} USDT), {Decimal(str(row['volume'])):.2f} USDT (~{vol_rub:.0f} ₽)\n"
    else:
        items = "Нет данных.\n"

    await tpl.edit_template(
        callback, "admin.stats_day",
        {"items": SafeHTML(items)},
    )


@router.callback_query(F.data == "admin_stats_week")
async def cb_admin_stats_week(callback: CallbackQuery):
    await callback.answer()
    from services import StatsService
    stats_service = StatsService()
    weekly = stats_service.get_weekly_stats(weeks=12)
    avg_rate = await _get_approx_rate()

    items = ""
    if weekly:
        for row in weekly:
            profit_usdt = Decimal(str(row['profit'])) / avg_rate if avg_rate else Decimal("0")
            vol_rub = Decimal(str(row['volume'])) * avg_rate if avg_rate else Decimal("0")
            items += f"• Неделя {row['week']}: {row['deals']} сделок, {Decimal(str(row['profit'])):.0f} ₽ (~{profit_usdt:.1f} USDT), {Decimal(str(row['volume'])):.2f} USDT (~{vol_rub:.0f} ₽)\n"
    else:
        items = "Нет данных.\n"

    await tpl.edit_template(
        callback, "admin.stats_week",
        {"items": SafeHTML(items)},
    )


@router.callback_query(F.data == "admin_stats_month")
async def cb_admin_stats_month(callback: CallbackQuery):
    await callback.answer()
    from services import StatsService
    stats_service = StatsService()
    monthly = stats_service.get_monthly_stats(months=12)
    avg_rate = await _get_approx_rate()

    items = ""
    if monthly:
        for row in monthly:
            profit_usdt = Decimal(str(row['profit'])) / avg_rate if avg_rate else Decimal("0")
            vol_rub = Decimal(str(row['volume'])) * avg_rate if avg_rate else Decimal("0")
            items += f"• {row['month']}: {row['deals']} сделок, {Decimal(str(row['profit'])):.0f} ₽ (~{profit_usdt:.1f} USDT), {Decimal(str(row['volume'])):.2f} USDT (~{vol_rub:.0f} ₽)\n"
    else:
        items = "Нет данных.\n"

    await tpl.edit_template(
        callback, "admin.stats_month",
        {"items": SafeHTML(items)},
    )


@router.callback_query(F.data == "admin_stats_managers")
async def cb_admin_stats_managers(callback: CallbackQuery):
    await callback.answer()
    from services import StatsService
    stats_service = StatsService()
    mgr_repo = ManagerRepository()
    managers = mgr_repo.list_all()

    extra = []
    items = ""
    for m in managers:
        summary = stats_service.get_manager_stats(m.id, days=30)
        items += f"• {escape_html(str(m.full_name or m.username or m.telegram_id))}: {summary['deals']} сделок, {summary['profit']:.0f} ₽\n"
        extra.append([{"text": f"{m.full_name or m.username or m.telegram_id}", "callback_data": f"admin_manager_stats_{m.id}"}])

    if not managers:
        items = "Нет менеджеров.\n"

    extra.append([{"text": "Назад", "callback_data": "admin_stats", "icon_custom_emoji_id": "5963103826075456248"}])

    tmpl = tpl.get_template("admin.stats_managers", "ru")
    text = tpl.render_text(tmpl, {"items": SafeHTML(items)})
    kb = tpl.build_keyboard(tmpl.get("buttons", []), extra)
    await safe_edit_text(callback, text, reply_markup=kb)


@router.callback_query(F.data.startswith("admin_manager_stats_"))
async def cb_admin_manager_stats(callback: CallbackQuery):
    await callback.answer()
    mgr_id = int(callback.data.replace("admin_manager_stats_", ""))
    from services import StatsService
    stats_service = StatsService()
    mgr_repo = ManagerRepository()
    mgr = mgr_repo.find_by_id(mgr_id)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("admin_stats_managers"))
        return

    summary = stats_service.get_manager_stats(mgr.id, days=30)
    name = mgr.full_name or mgr.username or str(mgr.telegram_id)

    # Build dynamic keyboard with manager_id injected
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(**_b("По дням", f"admin_mgr_stats_day_{mgr_id}", icon=CHART_GROWTH))
    builder.button(**_b("По неделям", f"admin_mgr_stats_week_{mgr_id}", icon=CHART_GROWTH))
    builder.button(**_b("По месяцам", f"admin_mgr_stats_month_{mgr_id}", icon=CHART_GROWTH))
    builder.button(**_b("Назад", "admin_stats_managers", icon=ARROW_UP))
    builder.adjust(1)

    text = (
        f"{TAG_CHART} <b>{escape_html(name)}</b>\n\n"
        f"Сделок: <b>{summary['deals']}</b>\n"
        f"Оборот: <b>{summary['volume']:.2f} USDT</b>\n"
        f"Прибыль: <b>{summary['profit']:.2f} ₽</b>\n\n"
        f"Выберите период:"
    )
    await safe_edit_text(callback, text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin_mgr_stats_day_"))
async def cb_admin_mgr_stats_day(callback: CallbackQuery):
    await callback.answer()
    mgr_id = int(callback.data.replace("admin_mgr_stats_day_", ""))
    from services import StatsService
    stats_service = StatsService()
    avg_rate = await _get_approx_rate()

    daily = stats_service.get_manager_daily_report(mgr_id, days=30)
    items = ""
    if daily:
        for row in daily:
            profit_usdt = row['profit'] / avg_rate if avg_rate else Decimal("0")
            vol_rub = row['volume'] * avg_rate if avg_rate else Decimal("0")
            items += f"• {row['day']}: {row['deals']} сделок, {row['profit']:.0f} ₽ (~{profit_usdt:.1f} USDT), {row['volume']:.2f} USDT (~{vol_rub:.0f} ₽)\n"
    else:
        items = "Нет данных.\n"

    await safe_edit_text(
        callback,
        f"{TAG_CHART} <b>По дням</b> (30 дней)\n\n{items}",
        reply_markup=back_keyboard(f"admin_manager_stats_{mgr_id}"),
    )


@router.callback_query(F.data.startswith("admin_mgr_stats_week_"))
async def cb_admin_mgr_stats_week(callback: CallbackQuery):
    await callback.answer()
    mgr_id = int(callback.data.replace("admin_mgr_stats_week_", ""))
    from services import StatsService
    stats_service = StatsService()
    avg_rate = await _get_approx_rate()

    weekly = stats_service.get_manager_weekly_report(mgr_id, weeks=12)
    items = ""
    if weekly:
        for row in weekly:
            profit_usdt = Decimal(str(row['profit'])) / avg_rate if avg_rate else Decimal("0")
            vol_rub = Decimal(str(row['volume'])) * avg_rate if avg_rate else Decimal("0")
            items += f"• Неделя {row['week']}: {row['deals']} сделок, {Decimal(str(row['profit'])):.0f} ₽ (~{profit_usdt:.1f} USDT), {Decimal(str(row['volume'])):.2f} USDT (~{vol_rub:.0f} ₽)\n"
    else:
        items = "Нет данных.\n"

    await safe_edit_text(
        callback,
        f"{TAG_CHART} <b>По неделям</b> (12 недель)\n\n{items}",
        reply_markup=back_keyboard(f"admin_manager_stats_{mgr_id}"),
    )


@router.callback_query(F.data.startswith("admin_mgr_stats_month_"))
async def cb_admin_mgr_stats_month(callback: CallbackQuery):
    await callback.answer()
    mgr_id = int(callback.data.replace("admin_mgr_stats_month_", ""))
    from services import StatsService
    stats_service = StatsService()
    avg_rate = await _get_approx_rate()

    monthly = stats_service.get_manager_monthly_report(mgr_id, months=12)
    items = ""
    if monthly:
        for row in monthly:
            profit_usdt = Decimal(str(row['profit'])) / avg_rate if avg_rate else Decimal("0")
            vol_rub = Decimal(str(row['volume'])) * avg_rate if avg_rate else Decimal("0")
            items += f"• {row['month']}: {row['deals']} сделок, {Decimal(str(row['profit'])):.0f} ₽ (~{profit_usdt:.1f} USDT), {Decimal(str(row['volume'])):.2f} USDT (~{vol_rub:.0f} ₽)\n"
    else:
        items = "Нет данных.\n"

    await safe_edit_text(
        callback,
        f"{TAG_CHART} <b>По месяцам</b> (12 месяцев)\n\n{items}",
        reply_markup=back_keyboard(f"admin_manager_stats_{mgr_id}"),
    )


# ── Manager Earnings Report ───────────────────────────────────────────────

@router.callback_query(F.data == "admin_earnings")
async def cb_admin_earnings(callback: CallbackQuery):
    await callback.answer()
    from services import StatsService
    stats_service = StatsService()
    days = 30
    rows = stats_service.get_all_managers_summary(days=days)
    approx_rate = await _get_approx_rate()
    items = ""
    if rows:
        for row in rows:
            volume_rub_approx = row["volume"] * approx_rate
            profit_usdt = row["profit"] / approx_rate if approx_rate else Decimal("0")
            items += (
                f"• {row['name']}: {row['deals']} сделок, "
                f"{row['volume']:.2f} USDT (~{volume_rub_approx:.0f} ₽), "
                f"прибыль {row['profit']:.2f} ₽ (~{profit_usdt:.2f} USDT)\n"
            )
    else:
        items = "Нет данных за периода.\n"
    extra = []
    for row in rows:
        extra.append([
            _b(
                f"{row['name']} (подробнее)",
                f"admin_earn_detail_{row['manager_id']}",
                icon=TAG_PROFILE,
            )
        ])
    tmpl = tpl.get_template("admin.earnings", "ru")
    kb = tpl.build_keyboard(tmpl.get("buttons", []), extra)
    text = tpl.render_text(tmpl, {"days": str(days), "items": SafeHTML(items)})
    await safe_edit_text(callback, text, reply_markup=kb)


@router.callback_query(F.data.startswith("admin_earn_detail_"))
async def cb_admin_earn_detail(callback: CallbackQuery):
    await callback.answer()
    mgr_id = int(callback.data.replace("admin_earn_detail_", ""))
    from services import StatsService
    from repositories import ManagerRepository
    stats_service = StatsService()
    days = 30
    mgr_repo = ManagerRepository()
    mgr = mgr_repo.find_by_id(mgr_id)
    name = (mgr.full_name or mgr.username or f"ID:{mgr.telegram_id}") if mgr else "Unknown"
    daily = stats_service.get_manager_daily_report(mgr_id, days=days)
    summary = stats_service.get_manager_stats(mgr_id, days=days)
    approx_rate = await _get_approx_rate()
    summary_profit_usdt = summary['profit'] / approx_rate if approx_rate else Decimal("0")
    summary_volume_rub = summary['volume'] * approx_rate
    summary_text = (
        f"Всего сделок: <b>{summary['deals']}</b>\n"
        f"Оборот: <b>{summary['volume']:.2f} USDT</b> (~{summary_volume_rub:.0f} ₽)\n"
        f"Прибыль: <b>{summary['profit']:.2f} ₽</b> (~{summary_profit_usdt:.2f} USDT)"
    )
    daily_items = ""
    if daily:
        for row in daily:
            profit_usdt = row['profit'] / approx_rate if approx_rate else Decimal("0")
            volume_rub = row['volume'] * approx_rate
            daily_items += (
                f"• {row['day']}: {row['deals']} сделок, "
                f"{row['volume']:.2f} USDT (~{volume_rub:.0f} ₽), "
                f"прибыль {row['profit']:.2f} ₽ (~{profit_usdt:.2f} USDT)\n"
            )
    else:
        daily_items = "Нет сделок за период.\n"
    tmpl = tpl.get_template("admin.earnings_detail", "ru")
    text = tpl.render_text(
        tmpl,
        {
            "name": name,
            "days": str(days),
            "summary": summary_text,
            "daily_items": daily_items,
        },
    )
    kb = tpl.build_keyboard(tmpl.get("buttons", []))
    await safe_edit_text(callback, text, reply_markup=kb)


# ── Rates Admin ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_rates")
async def cb_admin_rates(callback: CallbackQuery):
    await callback.answer()
    rate_service = RateService()
    tiers = rate_service.get_tiers()

    from twix_settings import get as settings_get
    rapira_price = await settings_get("rates.rapira_last_price")
    rapira_enabled = await settings_get("rates.rapira_enabled")
    mode = await settings_get("rates.mode") or "fixed"
    mode_label = "Rapira %" if mode == "rapira_percent" else "фикс"

    rapira_section = ""
    if rapira_enabled and rapira_price and rapira_price != 0:
        if mode == "rapira_percent":
            rapira_section = f"{TAG_CHART} Rapira: <b>{rapira_price} ₽</b> | Режим: <b>{mode_label}</b>\n\n"
        else:
            internal = Decimal(str(rapira_price)) * (await settings_get('rates.coefficient'))
            rapira_section = f"{TAG_CHART} Rapira: <b>{rapira_price} ₽</b> (внутренний: <b>{internal:.2f} ₽</b>) | Режим: <b>{mode_label}</b>\n\n"
    else:
        rapira_section = f"{TAG_CHART} Rapira: <i>мониторинг выключен</i> | Режим: <b>{mode_label}</b>\n\n"

    tiers_text = ""
    if tiers:
        for i, t in enumerate(tiers, 1):
            pct_str = ""
            display_rate = t.rate
            if mode == "rapira_percent" and rapira_price and t.rapira_percent is not None:
                display_rate = (Decimal(str(rapira_price)) * (Decimal("1") + t.rapira_percent / Decimal("100"))).quantize(Decimal("0.01"))
                pct_str = f" (+{t.rapira_percent}%)"
            tiers_text += f"{i}. {t.name} → <b>{display_rate} ₽</b>{pct_str}\n"
            tiers_text += f"   <i>({t.min_amount}-{t.max_amount} USDT)</i>\n"
    else:
        tiers_text += "<i>Нет активных курсов</i>\n"

    await tpl.edit_template(
        callback, "admin.rates",
        {"rapira_section": SafeHTML(rapira_section), "tiers": SafeHTML(tiers_text)},
    )


@router.callback_query(F.data.startswith("admin_rate_edit_"))
async def cb_admin_rate_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    rate_id = int(callback.data.replace("admin_rate_edit_", ""))
    rate_repo = RateRepository()
    rate = rate_repo.find_by_id(rate_id)
    if not rate:
        await safe_edit_text(callback, "Курс не найден.", reply_markup=back_keyboard("admin_rates"))
        return

    pct_str = ""
    if rate.rapira_percent is not None:
        pct_str = f" | Rapira %: {rate.rapira_percent}%"

    await state.update_data(
        edit_rate_id=rate_id,
        edit_rate_name=rate.name,
        edit_rate_min=str(rate.min_amount),
        edit_rate_max=str(rate.max_amount),
        edit_rate_value=str(rate.rate),
        edit_rate_rapira_percent=str(rate.rapira_percent) if rate.rapira_percent is not None else "",
    )
    await state.set_state(AdminStates.edit_rate_name)

    text = (
        f"{TAG_PENCIL} <b>Редактирование тира</b> (1/5)\n\n"
        f"<b>Текущие значения:</b>\n"
        f"Название: {rate.name}\n"
        f"Диапазон: {rate.min_amount} - {rate.max_amount} USDT\n"
        f"Курс: {rate.rate} ₽{pct_str}\n\n"
        f"Введите новое название (или <code>-</code> чтобы оставить):"
    )
    await safe_edit_text(callback, text, reply_markup=back_keyboard("admin_rates"))


@router.message(AdminStates.edit_rate_name)
async def process_edit_rate_name(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    if text != "-":
        await state.update_data(edit_rate_name=text)
    await state.set_state(AdminStates.edit_rate_min)
    await send_text(message, 
        f"{TAG_PENCIL} <b>Редактирование тира</b> (2/5)\n\n"
        f"Минимальная сумма (текущая: {data.get('edit_rate_min')} USDT)\n"
        f"Введите новое значение (или <code>-</code> чтобы оставить):"
    )


@router.message(AdminStates.edit_rate_min)
async def process_edit_rate_min(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    data = await state.get_data()
    if text != "-":
        try:
            val = Decimal(text)
            if val < 0:
                raise ValueError()
            await state.update_data(edit_rate_min=str(val))
        except Exception:
            await send_text(message, f"{TAG_CROSS} Введите число >= 0 или <code>-</code>.")
            return
    await state.set_state(AdminStates.edit_rate_max)
    await send_text(message, 
        f"{TAG_PENCIL} <b>Редактирование тира</b> (3/5)\n\n"
        f"Максимальная сумма (текущая: {data.get('edit_rate_max')} USDT, 0 = без лимита)\n"
        f"Введите новое значение (или <code>-</code> чтобы оставить):"
    )


@router.message(AdminStates.edit_rate_max)
async def process_edit_rate_max(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    data = await state.get_data()
    if text != "-":
        try:
            val = Decimal(text)
            if val < 0:
                raise ValueError()
            await state.update_data(edit_rate_max=str(val))
        except Exception:
            await send_text(message, f"{TAG_CROSS} Введите число >= 0 или <code>-</code>.")
            return
    await state.set_state(AdminStates.edit_rate_value)
    await send_text(message, 
        f"{TAG_PENCIL} <b>Редактирование тира</b> (4/5)\n\n"
        f"Курс в ₽ (текущий: {data.get('edit_rate_value')})\n"
        f"Введите новый курс или <code>+X</code>/<code>-X</code> (или <code>-</code> чтобы оставить):"
    )


@router.message(AdminStates.edit_rate_value)
async def process_edit_rate_value(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    data = await state.get_data()
    if text != "-":
        try:
            if text.startswith(("+", "-")):
                current = Decimal(data.get("edit_rate_value", "0"))
                new_val = current + Decimal(text)
            else:
                new_val = Decimal(text)
            await state.update_data(edit_rate_value=str(new_val))
        except Exception:
            await send_text(message, f"{TAG_CROSS} Введите число. Пример: 85.5, +1, -0.5 или <code>-</code>.")
            return
    await state.set_state(AdminStates.edit_rate_rapira_percent)
    current_pct = data.get("edit_rate_rapira_percent", "")
    pct_display = f"{current_pct}%" if current_pct else "не задан"
    await send_text(message, 
        f"{TAG_PENCIL} <b>Редактирование тира</b> (5/5)\n\n"
        f"Процент надбавки к Rapira (текущий: {pct_display})\n"
        f"Введите процент (0 чтобы убрать, или <code>-</code> чтобы оставить):"
    )


@router.message(AdminStates.edit_rate_rapira_percent)
async def process_edit_rate_rapira_percent(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    data = await state.get_data()
    rate_id = data.get("edit_rate_id")
    if not rate_id:
        await send_text(message, "Ошибка состояния.")
        await state.clear()
        return

    rate_repo = RateRepository()
    rate = rate_repo.find_by_id(rate_id)
    if not rate:
        await send_text(message, "Курс не найден.", reply_markup=back_keyboard("admin_rates"))
        await state.clear()
        return

    if text != "-":
        try:
            val = Decimal(text)
            if val < 0:
                raise ValueError()
            rate.rapira_percent = val if val != 0 else None
        except Exception:
            await send_text(message, f"{TAG_CROSS} Введите число >= 0, 0 чтобы убрать, или <code>-</code>.")
            return

    # Apply all collected changes
    rate.name = data.get("edit_rate_name", rate.name)
    rate.min_amount = Decimal(data.get("edit_rate_min", str(rate.min_amount)))
    rate.max_amount = Decimal(data.get("edit_rate_max", str(rate.max_amount)))
    rate.rate = Decimal(data.get("edit_rate_value", str(rate.rate)))

    rate_repo.update(rate)
    await _sync_rapira_baseline()

    pct_str = f" (+{rate.rapira_percent}%)" if rate.rapira_percent is not None else ""
    await send_text(message, 
        f"{TAG_CHECK} Тир обновлён:\n"
        f"{rate.name}: {rate.rate} ₽{pct_str} ({rate.min_amount}-{rate.max_amount} USDT)",
        reply_markup=back_keyboard("admin_rates"),
    )
    await state.clear()


@router.callback_query(F.data == "admin_rates_edit_list")
async def cb_admin_rates_edit_list(callback: CallbackQuery):
    await callback.answer()
    rate_service = RateService()
    tiers = rate_service.get_tiers()

    from twix_settings import get as settings_get
    rapira_price = await settings_get("rates.rapira_last_price")
    mode = await settings_get("rates.mode") or "fixed"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for i, t in enumerate(tiers, 1):
        pct_label = ""
        display_rate = t.rate
        if mode == "rapira_percent" and rapira_price and t.rapira_percent is not None:
            display_rate = (Decimal(str(rapira_price)) * (Decimal("1") + t.rapira_percent / Decimal("100"))).quantize(Decimal("0.01"))
            pct_label = f" (+{t.rapira_percent}%)"
        builder.button(
            text=f"{i}. {t.name} ({display_rate} ₽{pct_label})",
            callback_data=f"admin_rate_edit_{t.id}",
        )
    builder.button(**_b("Назад", "admin_rates", icon=ARROW_UP))
    builder.adjust(1)

    text = f"{TAG_PENCIL} <b>Выберите тир для редактирования</b>\n\n"
    for i, t in enumerate(tiers, 1):
        pct_str = ""
        display_rate = t.rate
        if mode == "rapira_percent" and rapira_price and t.rapira_percent is not None:
            display_rate = (Decimal(str(rapira_price)) * (Decimal("1") + t.rapira_percent / Decimal("100"))).quantize(Decimal("0.01"))
            pct_str = f" (+{t.rapira_percent}%)"
        text += f"{i}. {t.name}: {display_rate} ₽{pct_str} <i>({t.min_amount}-{t.max_amount} USDT)</i>\n"

    await safe_edit_text(callback, text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin_rates_shift_"))
async def cb_admin_rates_shift(callback: CallbackQuery):
    await callback.answer()
    delta = Decimal(callback.data.replace("admin_rates_shift_", ""))
    rate_service = RateService()
    count = rate_service.shift_all_rates(delta, actor_id=callback.from_user.id)
    await _sync_rapira_baseline()
    await safe_edit_text(callback, 
        f"{TAG_CHECK} Сдвинуто {count} курсов на {delta} ₽",
        reply_markup=back_keyboard("admin_rates"),
    )


# ── Add Rate (FSM) ────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_rate_add")
async def cb_admin_rate_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.add_rate_name)
    await safe_edit_text(callback, 
        f"{TAG_PENCIL} <b>Добавить тир</b> (1/4)\n\n"
        "Введите название тира (например: «до 100 USDT»):",
        reply_markup=back_keyboard("admin_rates"),
    )


@router.message(AdminStates.add_rate_name)
async def process_add_rate_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await send_text(message, f"{TAG_CROSS} Название не может быть пустым.")
        return
    await state.update_data(new_rate_name=name)
    await state.set_state(AdminStates.add_rate_min)
    await send_text(message, f"{TAG_PENCIL} <b>Добавить тир</b> (2/4)\n\nМинимальная сумма USDT:")


@router.message(AdminStates.add_rate_min)
async def process_add_rate_min(message: Message, state: FSMContext):
    try:
        min_amount = Decimal(message.text.strip().replace(",", "."))
        if not min_amount.is_finite() or min_amount < 0:
            raise ValueError()
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите число. Пример: 0")
        return
    await state.update_data(new_rate_min=str(min_amount))
    await state.set_state(AdminStates.add_rate_max)
    await send_text(message, f"{TAG_PENCIL} <b>Добавить тир</b> (3/4)\n\nМаксимальная сумма USDT (0 = без лимита):")


@router.message(AdminStates.add_rate_max)
async def process_add_rate_max(message: Message, state: FSMContext):
    try:
        max_amount = Decimal(message.text.strip().replace(",", "."))
        if not max_amount.is_finite() or max_amount < 0:
            raise ValueError()
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите число. Пример: 100 или 0")
        return
    await state.update_data(new_rate_max=str(max_amount))
    await state.set_state(AdminStates.add_rate_value)
    await send_text(message, f"{TAG_PENCIL} <b>Добавить тир</b> (4/4)\n\nКурс в ₽ за 1 USDT:")


@router.message(AdminStates.add_rate_value)
async def process_add_rate_value(message: Message, state: FSMContext):
    try:
        rate_val = Decimal(message.text.strip().replace(",", "."))
        if not rate_val.is_finite() or rate_val <= 0:
            raise ValueError()
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите положительное число. Пример: 85.5")
        return

    await state.update_data(new_rate_value=str(rate_val))
    await state.set_state(AdminStates.add_rate_rapira_percent)
    await send_text(message, 
        f"{TAG_PENCIL} <b>Добавить тир</b> (доп)\n\n"
        f"Процент надбавки к Rapira (только для режима Rapira %):\n"
        f"Пример: <code>8</code> или <code>0</code> чтобы пропустить:"
    )


@router.message(AdminStates.add_rate_rapira_percent)
async def process_add_rate_rapira_percent(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    rapira_percent = None
    if text and text != "0":
        try:
            rapira_percent = Decimal(text)
            if not rapira_percent.is_finite() or rapira_percent < 0:
                raise ValueError()
        except Exception:
            await send_text(message, f"{TAG_CROSS} Введите число >= 0 или 0 чтобы пропустить.")
            return

    data = await state.get_data()
    name = data.get("new_rate_name", "Тир")
    min_amount = Decimal(data.get("new_rate_min", "0"))
    max_amount = Decimal(data.get("new_rate_max", "0"))
    rate_val = Decimal(data.get("new_rate_value", "0"))

    rate_service = RateService()
    try:
        rate_service.create_tier(name,min_amount,max_amount,rate_val,actor_id=message.from_user.id,rapira_percent=rapira_percent)
    except ValueError as exc:
        await send_text(message,f'{TAG_CROSS} {escape_html(str(exc))}. Начните создание тира заново.',reply_markup=back_keyboard('admin_rates'))
        await state.clear()
        return
    await _sync_rapira_baseline()

    pct_str = f" (+{rapira_percent}%)" if rapira_percent is not None else ""
    await send_text(message, 
        f"{TAG_CHECK} Тир «{escape_html(name)}» добавлен: {rate_val} ₽{pct_str} ({min_amount}-{max_amount} USDT)",
        reply_markup=back_keyboard("admin_rates"),
    )
    await state.clear()


# ── Managers Admin ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_managers")
async def cb_admin_managers(callback: CallbackQuery):
    await callback.answer()
    mgr_repo = ManagerRepository()
    managers = mgr_repo.list_all()

    items = ""
    extra = []
    for m in managers:
        m_profit_usdt = m.profit / Decimal("84") if m.profit else Decimal("0")
        items += f"• {escape_html(m.full_name or m.username or str(m.telegram_id))}: {m.deal_count} сделок, {m.profit:.0f} ₽ (~{m_profit_usdt:.1f} USDT)\n"
        online = "Онлайн" if m.is_online else "Офлайн"
        extra.append([{"text": f"{online} | {m.full_name or m.username or m.telegram_id}", "callback_data": f"admin_mgr_detail_{m.id}"}])
    extra.append([{"text": "Назад", "callback_data": "admin_menu", "icon_custom_emoji_id": "5963103826075456248"}])
    await tpl.edit_template(
        callback, "admin.managers",
        {"count": str(len(managers)), "items": SafeHTML(items)},
        extra_buttons=extra,
    )


@router.callback_query(F.data == "admin_mgr_add")
async def cb_admin_mgr_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.add_manager)
    await safe_edit_text(callback, 
        f"{TAG_PENCIL} <b>Добавить менеджера</b>\n\n"
        "Введите Telegram ID пользователя:\n"
        "(Пользователь должен написать боту хотя бы раз)",
        reply_markup=back_keyboard("admin_managers"),
    )


@router.message(AdminStates.add_manager)
async def process_add_manager(message: Message, state: FSMContext):
    try:
        telegram_id = int(message.text.strip())
    except ValueError:
        await send_text(message, f"{TAG_CROSS} Введите числовой Telegram ID.")
        return

    mgr_repo = ManagerRepository()
    existing = mgr_repo.find_by_telegram_id(telegram_id)
    if existing:
        await send_text(message, f"{TAG_CROSS} Этот пользователь уже менеджер.", reply_markup=back_keyboard("admin_managers"))
        await state.clear()
        return

    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(telegram_id)

    mgr = Manager(
        telegram_id=telegram_id,
        username=user.username if user else None,
        full_name=user.full_name if user else None,
        is_active=True,
        is_online=True,
        can_receive_deals=True,
    )
    mgr_repo.create(mgr)

    await send_text(message, 
        f"{TAG_CHECK} Менеджер добавлен!\n\nID: <code>{telegram_id}</code>",
        reply_markup=back_keyboard("admin_managers"),
    )
    await state.clear()


@router.callback_query(F.data.startswith("admin_mgr_detail_"))
async def cb_admin_mgr_detail(callback: CallbackQuery):
    await callback.answer()
    mgr_id = int(callback.data.replace("admin_mgr_detail_", ""))
    mgr_repo = ManagerRepository()
    mgr = mgr_repo.find_by_id(mgr_id)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("admin_managers"))
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Удалить",
        callback_data=f"admin_mgr_confirm_delete_{mgr_id}",
    )
    builder.button(**_b("Изменить имя", f"admin_mgr_edit_name_{mgr_id}", icon=PENCIL))
    builder.button(**_b("Назад", "admin_managers", icon=ARROW_UP))
    builder.adjust(1)

    deal_repo = DealRepository()
    mgr_deals = [d for d in deal_repo.list_all() if d.manager_id == mgr_id and d.status == "closed"]
    mgr_volume_rub = sum((d.amount_usdt * d.client_rate for d in mgr_deals), Decimal("0"))

    # Active deals
    active_deals = [d for d in deal_repo.list_all() if d.manager_id == mgr_id and d.status in ("created", "queued", "active", "pinned")]
    active_text = ""
    if active_deals:
        active_text = f"\n{TAG_RECEIPT} <b>Активные сделки ({len(active_deals)}):</b>\n"
        for d in active_deals[:5]:
            rub = d.amount_usdt * d.client_rate
            active_text += f"• {d.amount_usdt} USDT ({rub:.0f} ₽) — {d.status}\n"
        if len(active_deals) > 5:
            active_text += f"… и ещё {len(active_deals) - 5}\n"

    # Current shift
    from datetime import date
    today = date.today().isoformat()
    sr_repo = ShiftReportRepository()
    report = sr_repo.find_by_manager_and_date(mgr_id, today)
    shift_text = ""
    if report:
        start_total = report.opening_balance + report.start_kb
        end_total = report.closing_balance + report.end_kb
        shift_text = (
            f"\n{TAG_PENCIL} <b>Смена {today}:</b>\n"
            f"Начало: {start_total:.0f} ₽ (П {report.opening_balance:.0f} + КБ {report.start_kb:.0f})\n"
        )
        if report.closing_balance > 0:
            shift_text += f"Конец: {end_total:.0f} ₽ (П {report.closing_balance:.0f} + КБ {report.end_kb:.0f})\n"
            shift_text += f"Доход: {report.system_profit:.0f} ₽\n"
        if report.is_locked:
            shift_text += "🔒 Закрыта админом\n"
    else:
        shift_text = f"\n{TAG_PENCIL} Смена {today}: не открыта\n"

    mgr_profit_usdt = mgr.profit / Decimal("84") if mgr.profit else Decimal("0")
    text = (
        f"{TAG_PROFILE} <b>{mgr.full_name or mgr.username or mgr.telegram_id}</b>\n\n"
        f"ID: <code>{mgr.telegram_id}</code>\n"
        f"Онлайн: <b>{'Да' if mgr.is_online else 'Нет'}</b>\n"
        f"Получает сделки: <b>{'Да' if mgr.can_receive_deals else 'Нет'}</b>\n\n"
        f"{TAG_CHART} Статистика:\n"
        f"• Сделок: <b>{mgr.deal_count}</b>\n"
        f"• Прибыль: <b>{mgr.profit:.2f} ₽</b> (~{mgr_profit_usdt:.2f} USDT)\n"
        f"• Отмен: <b>{mgr.cancel_count}</b>\n"
        f"• Оборот: <b>{mgr.total_volume:.2f} USDT</b> ({mgr_volume_rub:.0f} ₽)\n"
        f"{active_text}{shift_text}"
    )
    await safe_edit_text(callback, text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin_mgr_confirm_delete_"))
async def cb_admin_mgr_confirm_delete(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    mgr_id = int(parts[4])

    await safe_edit_text(callback, 
        f"{TAG_CROSS} <b>Подтвердите</b>\n\nВы уверены, что хотите удалить этого менеджера?",
        reply_markup=confirm_keyboard(
            f"admin_mgr_do_delete_{mgr_id}",
            f"admin_mgr_detail_{mgr_id}",
        ),
    )


@router.callback_query(F.data.startswith("admin_mgr_do_delete_"))
async def cb_admin_mgr_do_delete(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    mgr_id = int(parts[4])

    mgr_repo = ManagerRepository()
    mgr = mgr_repo.find_by_id(mgr_id)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("admin_managers"))
        return

    mgr_repo.soft_delete(mgr_id, actor_id=callback.from_user.id)

    audit = AuditService()
    audit.log(
        event_type="manager_deleted",
        actor_id=callback.from_user.id,
        object_type="manager",
        object_id=str(mgr_id),
        payload={"telegram_id": mgr.telegram_id, "username": mgr.username, "full_name": mgr.full_name},
    )

    await safe_edit_text(callback, 
        f"{TAG_CHECK} Менеджер удалён.",
        reply_markup=back_keyboard("admin_managers"),
    )


# ── Deals Admin ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_deals")
@router.callback_query(F.data.startswith("admin_deals_page_"))
async def cb_admin_deals(callback: CallbackQuery):
    await callback.answer()
    deal_repo = DealRepository()

    offset = 0
    if callback.data.startswith("admin_deals_page_"):
        offset = int(callback.data.replace("admin_deals_page_", ""))

    PAGE_SIZE = 10
    deals = deal_repo.list_recent(limit=PAGE_SIZE, offset=offset)
    total = deal_repo.count_all()

    items = ""
    extra = []
    if not deals:
        items += "Нет сделок."
    else:
        from bot.common import get_client_contact
        for d in deals:
            rub = d.amount_usdt * d.client_rate
            client = get_client_contact(d)
            status_ru = STATUS_RU.get(d.status, d.status)
            dt = d.created_at
            dt_str = dt.strftime("%d.%m %H:%M") if dt else "--.-- --:--"
            items += f"• {client} / {d.amount_usdt} USDT ({rub:.0f} ₽) — {status_ru}\n"
            extra.append([{"text": f"{dt_str} / {d.client_rate}₽ / {d.amount_usdt} USDT → {rub:.0f} ₽", "callback_data": f"admin_deal_detail_{d.id}"}])

    # Pagination
    if offset > 0:
        extra.append([{"text": "← Новее", "callback_data": f"admin_deals_page_{max(0, offset - PAGE_SIZE)}"}])
    if total > offset + len(deals):
        extra.append([{"text": "Старее →", "callback_data": f"admin_deals_page_{offset + PAGE_SIZE}"}])

    extra.append([{"text": "Назад", "callback_data": "admin_menu", "icon_custom_emoji_id": "5963103826075456248"}])

    page_info = f" (страница {offset // PAGE_SIZE + 1}/{(total + PAGE_SIZE - 1) // PAGE_SIZE})" if total > PAGE_SIZE else ""
    await tpl.edit_template(
        callback, "admin.deals",
        {"count": str(total) + page_info, "items": SafeHTML(items)},
        extra_buttons=extra,
    )


@router.callback_query(F.data.startswith("admin_deal_detail_"))
async def cb_admin_deal_detail(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("admin_deal_detail_", "")
    deal_repo = DealRepository()
    deal = deal_repo.find_by_id(deal_id)
    if not deal:
        await safe_edit_text(callback, "Сделка не найдена.", reply_markup=back_keyboard("admin_deals"))
        return

    from bot.common import get_client_contact
    client_contact = get_client_contact(deal)

    mgr_name = "—"
    if deal.manager_id:
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_id(deal.manager_id)
        if mgr:
            mgr_name = mgr.full_name or mgr.username or str(mgr.telegram_id)

    rub = deal.amount_usdt * deal.client_rate
    profit_usdt = deal.profit / deal.client_rate if deal.client_rate else Decimal("0")
    revenue_usdt = deal.revenue / deal.client_rate if deal.client_rate else Decimal("0")
    cost_usdt = deal.cost / deal.client_rate if deal.client_rate else Decimal("0")

    extra = []
    if deal.status not in ("cancelled", "closed"):
        extra.append([{"text": "Закрыть", "callback_data": f"admin_deal_close_{deal.id}", "icon_custom_emoji_id": "5870633910337015697"}])
        extra.append([{"text": "Отменить", "callback_data": f"admin_deal_confirm_cancel_{deal.id}", "icon_custom_emoji_id": "5870657884844462243"}])
        extra.append([{"text": "Передать менеджеру", "callback_data": f"admin_deal_transfer_{deal.id}", "icon_custom_emoji_id": "5870772616305839506"}])

    extra.append([{"text": "Назад", "callback_data": "admin_deals", "icon_custom_emoji_id": "5963103826075456248"}])

    created_at = deal.created_at.strftime("%d.%m.%Y %H:%M UTC") if deal.created_at else "—"
    await tpl.edit_template(
        callback,
        "admin.deal_detail",
        variables={
            "amount": str(deal.amount_usdt),
            "rate": str(deal.client_rate),
            "total": f"{rub:.0f}",
            "revenue": f"{deal.revenue:.2f}",
            "revenue_usdt": f"{revenue_usdt:.2f}",
            "cost": f"{deal.cost:.2f}",
            "cost_usdt": f"{cost_usdt:.2f}",
            "profit": f"{deal.profit:.2f}",
            "profit_usdt": f"{profit_usdt:.2f}",
            "status": deal.status.upper(),
            "user": client_contact,
            "manager": mgr_name,
            "deal_id": deal.id,
            "created_at": created_at,
        },
        extra_buttons=extra,
    )


@router.callback_query(F.data.startswith("admin_deal_confirm_cancel_"))
async def cb_admin_deal_confirm_cancel(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("admin_deal_confirm_cancel_", "")
    await safe_edit_text(callback, 
        f"{TAG_CROSS} <b>Подтвердите</b>\n\nВы уверены, что хотите отменить эту сделку?",
        reply_markup=confirm_keyboard(
            f"admin_deal_do_cancel_{deal_id}",
            f"admin_deal_detail_{deal_id}",
        ),
    )


@router.callback_query(F.data.startswith("admin_deal_do_cancel_"))
async def cb_admin_deal_do_cancel(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("admin_deal_do_cancel_", "")
    deal_service = DealService()
    try:
        await deal_service.cancel_deal(deal_id, actor_id=callback.from_user.id)
        await safe_edit_text(callback, 
            f"{TAG_CROSS} Сделка отменена.",
            reply_markup=back_keyboard("admin_deals"),
        )
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard("admin_deals"))


@router.callback_query(F.data.startswith("admin_deal_close_"))
async def cb_admin_deal_close(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("admin_deal_close_", "")
    deal_repo = DealRepository()
    deal = deal_repo.find_by_id(deal_id)
    if not deal:
        await safe_edit_text(callback, "Сделка не найдена.", reply_markup=back_keyboard("admin_deals"))
        return
    await safe_edit_text(
        callback,
        f"{TAG_CHECK} <b>Подтвердите закрытие</b>\n\nСделка #{deal.id[:8]}\nСумма: {deal.amount_usdt} USDT\n\nЗакрыть сделку?",
        reply_markup=confirm_keyboard(
            f"admin_deal_do_close_{deal_id}",
            f"admin_deal_detail_{deal_id}",
        ),
    )


@router.callback_query(F.data.startswith("admin_deal_do_close_"))
async def cb_admin_deal_do_close(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("admin_deal_do_close_", "")
    deal_service = DealService()
    try:
        await deal_service.close_deal(deal_id, actor_id=callback.from_user.id)
        await safe_edit_text(
            callback,
            f"{TAG_CHECK} Сделка #{deal_id[:8]} закрыта.",
            reply_markup=back_keyboard("admin_deals"),
        )
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard("admin_deals"))


@router.callback_query(F.data.startswith("admin_deal_transfer_"))
async def cb_admin_deal_transfer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    deal_id = callback.data.replace("admin_deal_transfer_", "")
    await state.update_data(admin_transfer_deal_id=deal_id)
    deal_repo = DealRepository()
    deal = deal_repo.find_by_id(deal_id)
    if not deal:
        await safe_edit_text(callback, "Сделка не найдена.", reply_markup=back_keyboard("admin_deals"))
        return

    mgr_repo = ManagerRepository()
    managers = mgr_repo.list_all_active()
    if not managers:
        await safe_edit_text(
            callback,
            f"{TAG_CROSS} Нет активных менеджеров для назначения.",
            reply_markup=back_keyboard(f"admin_deal_detail_{deal_id}"),
        )
        return

    extra = []
    for m in managers:
        name = m.full_name or m.username or f"ID:{m.telegram_id}"
        extra.append([{"text": name, "callback_data": f"admin_deal_assign_mgr_{m.id}"}])

    extra.append([{"text": "Назад", "callback_data": "admin_deals", "icon_custom_emoji_id": "5963103826075456248"}])

    tmpl = tpl.get_template("admin.transfer_manager_list", "ru")
    await tpl.edit_template(
        callback, "admin.transfer_manager_list",
        {"deal_id_short": deal_id[:8]},
        extra_buttons=extra,
    )


@router.callback_query(F.data.startswith("admin_deal_assign_mgr_"))
async def cb_admin_deal_assign_mgr(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    # format: admin_deal_assign_mgr_{mgr_id} (deal_id stored in FSM)
    match = re.match(r"^admin_deal_assign_mgr_(\d+)$", callback.data)
    if not match:
        await safe_edit_text(callback, "Ошибка.", reply_markup=back_keyboard("admin_deals"))
        return
    mgr_id = int(match.group(1))
    data = await state.get_data()
    deal_id = data.get("admin_transfer_deal_id")
    if not deal_id:
        await safe_edit_text(callback, "Ошибка: сделка не найдена в состоянии.", reply_markup=back_keyboard("admin_deals"))
        return

    deal_service = DealService()
    try:
        await deal_service.assign_manager(deal_id, mgr_id, actor_id=callback.from_user.id)
        await state.clear()
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_id(mgr_id)
        mgr_name = (mgr.full_name or mgr.username or f"ID:{mgr.telegram_id}") if mgr else "Unknown"
        await safe_edit_text(callback, f"{TAG_CHECK} Сделка передана: {escape_html(mgr_name)}", reply_markup=back_keyboard("admin_deals"))
    except ValueError as exc:
        await safe_edit_text(callback, f"{TAG_CROSS} {exc}", reply_markup=back_keyboard("admin_deals"))

@router.message(AdminStates.edit_rate)
async def process_edit_rate(message: Message, state: FSMContext):
    data = await state.get_data()
    rate_id = data.get("edit_rate_id")
    if not rate_id:
        await send_text(message, "Ошибка состояния.")
        await state.clear()
        return

    text = message.text.strip().replace(",", ".")
    rate_repo = RateRepository()
    rate = rate_repo.find_by_id(rate_id)
    if not rate:
        await send_text(message, "Курс не найден.", reply_markup=back_keyboard("admin_rates"))
        await state.clear()
        return

    try:
        if text.startswith(("+", "-")):
            delta = Decimal(text)
            new_rate = rate.rate + delta
        else:
            new_rate = Decimal(text)
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите число. Пример: 85.5 или +1")
        return

    rate_service = RateService()
    rate_service.update_rate(rate_id, new_rate, actor_id=message.from_user.id)
    await _sync_rapira_baseline()

    await send_text(message, f"{TAG_CHECK} Курс обновлён: {new_rate} ₽", reply_markup=back_keyboard("admin_rates"))
    await state.clear()

@router.callback_query(F.data == "admin_shift_reports")
async def cb_admin_shift_reports(callback: CallbackQuery):
    await callback.answer()
    from datetime import date, timedelta
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(7)]

    extra = []
    for d in days:
        extra.append([{"text": d, "callback_data": f"admin_shift_date_{d}"}])
    await tpl.edit_template(
        callback, "admin.shift_reports",
        {"date": today.isoformat(), "items": SafeHTML("Выберите дату:")},
        extra_buttons=extra,
    )

@router.callback_query(F.data.startswith("admin_shift_date_"))
async def cb_admin_shift_date(callback: CallbackQuery):
    await callback.answer()
    work_date = callback.data.replace("admin_shift_date_", "")
    service = ShiftReportService()
    reports = service.repo.list_by_date(work_date)

    extra = []
    items = ""
    mgr_repo = ManagerRepository()
    for r in reports:
        mgr = mgr_repo.find_by_id(r.manager_id)
        name = (mgr.full_name or mgr.username or f"ID:{mgr.telegram_id}") if mgr else "Unknown"
        salary = service.calculate_salary(r)
        items += f"• {escape_html(name)}: начало {r.opening_balance:.0f} → конец {r.closing_balance:.0f} | ЗП {salary:.0f} ₽\n"
        extra.append([{"text": f"{name} (подробнее)", "callback_data": f"admin_shift_report_{r.id}"}])

    if not reports:
        items = "Нет отчётов за эту дату.\n"

    # Auto-rank button
    extra.append([{"text": "Авто-ТОП по прибыли", "callback_data": f"admin_shift_autotop_{work_date}"}])
    extra.append([{"text": "Назад", "callback_data": "admin_shift_reports", "icon_custom_emoji_id": "5963103826075456248"}])

    tmpl = tpl.get_template("admin.shift_reports", "ru")
    text = tpl.render_text(tmpl, {"date": work_date, "items": SafeHTML(items)})
    kb = tpl.build_keyboard(tmpl.get("buttons", []), extra)
    await safe_edit_text(callback, text, reply_markup=kb)

@router.callback_query(F.data.startswith("admin_shift_report_"))
async def cb_admin_shift_report(callback: CallbackQuery):
    await callback.answer()
    report_id = int(callback.data.replace("admin_shift_report_", ""))
    service = ShiftReportService()
    report = service.repo.find_by_id(report_id)
    if not report:
        await safe_edit_text(callback, "Отчёт не найден.", reply_markup=back_keyboard("admin_shift_reports"))
        return

    mgr_repo = ManagerRepository()
    mgr = mgr_repo.find_by_id(report.manager_id)
    name = (mgr.full_name or mgr.username or f"ID:{mgr.telegram_id}") if mgr else "Unknown"
    salary = service.calculate_salary(report)

    extra = []
    if not report.is_locked:
        extra.append([{"text": "Закрыть (лок)", "callback_data": f"admin_shift_lock_{report.id}"}])
    if not report.is_top_fixed:
        extra.append([
            {"text": "ТОП-1", "callback_data": f"admin_shift_top_{report.id}_1"},
            {"text": "ТОП-2", "callback_data": f"admin_shift_top_{report.id}_2"},
            {"text": "ТОП-3", "callback_data": f"admin_shift_top_{report.id}_3"},
        ])
    extra.append([{"text": "Назад", "callback_data": f"admin_shift_date_{report.work_date}", "icon_custom_emoji_id": "5963103826075456248"}])

    start_total = report.opening_balance + report.start_kb
    end_total = report.closing_balance + report.end_kb
    await tpl.edit_template(
        callback, "admin.shift_report_detail",
        {
            "name": name,
            "date": report.work_date,
            "start_platform": f"{report.opening_balance:.0f}",
            "start_kb": f"{report.start_kb:.0f}",
            "start_total": f"{start_total:.0f}",
            "end_platform": f"{report.closing_balance:.0f}",
            "end_kb": f"{report.end_kb:.0f}",
            "end_total": f"{end_total:.0f}",
            "income": f"{report.system_profit:.0f}",
            "salary_percent": f"{report.salary_percent:.1f}",
            "salary": f"{salary:.2f}",
            "top_place": str(report.top_place) if report.top_place else "—",
            "top_bonus": f"{report.top_bonus:.0f}",
            "locked": "Да" if report.is_locked else "Нет",
            "admin_note": report.admin_note or "",
        },
        extra_buttons=extra,
    )

@router.callback_query(F.data.startswith("admin_shift_lock_"))
async def cb_admin_shift_lock(callback: CallbackQuery):
    await callback.answer()
    report_id = int(callback.data.replace("admin_shift_lock_", ""))
    service = ShiftReportService()
    try:
        service.lock_report(report_id, actor_id=callback.from_user.id)
        await safe_edit_text(callback, f"{TAG_LOCK} Отчёт закрыт (locked).", reply_markup=back_keyboard("admin_shift_reports"))
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard("admin_shift_reports"))

@router.callback_query(F.data.startswith("admin_shift_top_"))
async def cb_admin_shift_top(callback: CallbackQuery):
    await callback.answer()
    # format: admin_shift_top_{report_id}_{place}
    parts = callback.data.split("_")
    report_id = int(parts[3])
    place = int(parts[4])
    service = ShiftReportService()
    from twix_settings import get as settings_get
    bonus_key = {1: "manager.top_bonus_1", 2: "manager.top_bonus_2", 3: "manager.top_bonus_3"}[place]
    bonus_val = await settings_get(bonus_key)
    bonus = Decimal(str(bonus_val)) if bonus_val else Decimal("0")
    try:
        service.set_top_bonus(report_id, place, bonus, actor_id=callback.from_user.id)
        await safe_edit_text(callback, f"{TAG_CHECK} ТОП-{place} установлен (+{bonus:.0f} ₽).", reply_markup=back_keyboard("admin_shift_reports"))
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard("admin_shift_reports"))

@router.callback_query(F.data.startswith("admin_shift_autotop_"))
async def cb_admin_shift_autotop(callback: CallbackQuery):
    await callback.answer()
    work_date = callback.data.replace("admin_shift_autotop_", "")
    service = ShiftReportService()
    ranked = service.rank_managers_by_profit(work_date)
    from twix_settings import get as settings_get
    bonus_map = {
        1: "manager.top_bonus_1",
        2: "manager.top_bonus_2",
        3: "manager.top_bonus_3",
    }
    applied = []
    for i, row in enumerate(ranked[:3], 1):
        report = row["report"]
        if not report:
            continue
        bonus_val = await settings_get(bonus_map[i])
        bonus = Decimal(str(bonus_val)) if bonus_val else Decimal("0")
        service.set_top_bonus(report.id, i, bonus, actor_id=callback.from_user.id)
        applied.append(f"ТОП-{i}")
    await safe_edit_text(
        callback,
        f"{TAG_CHECK} Авто-ТОП применён: {', '.join(applied)}." if applied else f"{TAG_CROSS} Нет данных для ТОП.",
        reply_markup=back_keyboard("admin_shift_reports"),
    )

@router.callback_query(F.data == "admin_logs")
async def cb_admin_logs(callback: CallbackQuery):
    await callback.answer()
    audit = AuditService()
    logs = audit.get_all_recent(20)

    items = ""
    for log in logs:
        items += f"• {log.event_type} — {log.object_type} #{str(log.object_id)[:8]}\n"
    await tpl.edit_template(
        callback, "admin.logs",
        {"count": str(len(logs)), "items": SafeHTML(items)},
    )

@router.callback_query(F.data == "admin_tickets")
async def cb_admin_tickets(callback: CallbackQuery):
    await callback.answer()
    from repositories import TicketRepository
    from services import TicketService

    ticket_repo = TicketRepository()
    all_tickets = ticket_repo.list_all()

    user_repo = UserRepository()
    ticket_by_user: dict[int, int] = {}
    for t in all_tickets:
        if t.user_id not in ticket_by_user:
            ticket_by_user[t.user_id] = 0
        ticket_by_user[t.user_id] += 1

    items = ""
    for uid, count in ticket_by_user.items():
        u = user_repo.find_by_id(uid)
        name = (u.full_name or u.username or str(uid)) if u else str(uid)
        items += f"• {escape_html(name)}: <b>{count}</b>\n"
    extra = [
        [{"text": "Назад", "callback_data": "admin_menu", "icon_custom_emoji_id": "5963103826075456248"}],
    ]
    await tpl.edit_template(
        callback, "admin.tickets",
        {"count": str(len(all_tickets)), "items": SafeHTML(items)},
        extra_buttons=extra,
    )

@router.callback_query(F.data == "admin_ticket_draw")
async def cb_admin_ticket_draw(callback: CallbackQuery):
    await callback.answer()
    from services import TicketService
    ticket_service = TicketService()
    winner = ticket_service.draw_winner()

    if winner:
        user_repo = UserRepository()
        winner_user = user_repo.find_by_id(winner.user_id)
        name = ""
        uid = ""
        uname = ""
        if winner_user:
            name = winner_user.full_name or ""
            uname = f"@{winner_user.username}" if winner_user.username else ""
            uid = str(winner_user.telegram_id)
        else:
            uid = str(winner.user_id)

        contact_info = f"{uname} | ID: <code>{uid}</code>" if uname else f"ID: <code>{uid}</code>"
        tmpl = tpl.get_template("admin.lottery_winner", "ru")
        text = tpl.render_text(tmpl, {
            "ticket": winner.ticket_number,
            "name": name,
            "contact": contact_info,
        })
    else:
        tmpl = tpl.get_template("admin.lottery_empty", "ru")
        text = tpl.render_text(tmpl, {})

    await tpl.edit_template(
        callback,
        "admin.lottery_winner" if winner else "admin.lottery_empty",
        {"ticket": winner.ticket_number if winner else "", "name": name, "contact": contact_info} if winner else {},
    )

@router.callback_query(F.data == "admin_ticket_burn")
async def cb_admin_ticket_burn(callback: CallbackQuery):
    await callback.answer()
    from services import TicketService
    ticket_service = TicketService()
    count = ticket_service.clear_all(actor_id=callback.from_user.id)
    await tpl.edit_template(
        callback, "admin.tickets_burned",
        {"count": str(count)},
    )

@router.callback_query(F.data == "admin_top_managers")
async def cb_admin_top_managers(callback: CallbackQuery):
    await callback.answer()
    from services import StatsService
    stats_service = StatsService()
    top = stats_service.get_top_managers(limit=10)

    items = ""
    if top:
        for i, m in enumerate(top, 1):
            m_profit_usdt = Decimal(str(m['profit'])) / Decimal("84")
            items += (
                f"{i}. <b>{m['name']}</b>\n"
                f"   Прибыль: {m['profit']:.2f} ₽ (~{m_profit_usdt:.2f} USDT) | Сделок: {m['deals']} | Оборот: {m['volume']:.2f} USDT\n\n"
            )
    else:
        items += "Нет данных."
    await tpl.edit_template(
        callback, "admin.top_managers",
        {"items": SafeHTML(items)},
    )

@router.callback_query(F.data == "admin_top_users")
async def cb_admin_top_users(callback: CallbackQuery):
    await callback.answer()
    from services import StatsService
    stats_service = StatsService()
    top = stats_service.get_top_users(limit=10)

    items = ""
    if top:
        for i, u in enumerate(top, 1):
            u_vol_rub = Decimal(str(u['volume'])) * Decimal("84")
            items += (
                f"{i}. <b>{u['name']}</b>\n"
                f"   Оборот: {u['volume']:.2f} USDT (~{u_vol_rub:.0f} ₽) | Сделок: {u['deals']}\n\n"
            )
    else:
        items += "Нет данных."
    await tpl.edit_template(
        callback, "admin.top_users",
        {"items": SafeHTML(items)},
    )

@router.callback_query(F.data == "admin_weekly_stats")
async def cb_admin_weekly_stats(callback: CallbackQuery):
    await callback.answer()
    from services import StatsService
    stats_service = StatsService()
    weekly = stats_service.get_weekly_stats(weeks=8)

    items = ""
    if weekly:
        for row in weekly[:8]:
            w_profit_usdt = Decimal(str(row['profit'])) / Decimal("84")
            w_vol_rub = Decimal(str(row['volume'])) * Decimal("84")
            items += (
                f"{Decimal(str(row['profit'])):.0f} ₽ (~{w_profit_usdt:.1f} USDT) прибыли, "
                f"{Decimal(str(row['volume'])):.2f} USDT (~{w_vol_rub:.0f} ₽)\n"
            )
    else:
        items += "Нет данных."
    await tpl.edit_template(
        callback, "admin.weekly_stats",
        {"items": SafeHTML(items)},
    )

@router.callback_query(F.data == "admin_broadcast_rates")
async def cb_admin_broadcast_rates(callback: CallbackQuery):
    await callback.answer()
    rate_service = RateService()
    tiers = rate_service.get_tiers()

    tiers_text = ""
    if tiers:
        for t in tiers:
            tiers_text += f"• {t.name} → <b>{t.rate} ₽</b>\n"
    else:
        tiers_text += "Курсы не настроены."
    await tpl.edit_template(
        callback, "admin.broadcast_rates",
        {"tiers": SafeHTML(tiers_text)},
    )

@router.callback_query(F.data == "admin_broadcast_confirm")
async def cb_admin_broadcast_confirm(callback: CallbackQuery):
    await callback.answer()
    rate_service = RateService()
    tiers = rate_service.get_tiers()

    text = f"{TAG_EXCHANGE} <b>Актуальные курсы TWIX</b>\n\n"
    if tiers:
        for t in tiers:
            text += f"• {t.name} → <b>{t.rate} ₽</b>\n"

    import presentation as tpl
    footer_tmpl = tpl.get_template("rates.broadcast_footer", "ru")
    footer = tpl.render_text(footer_tmpl, {}).strip()
    if footer:
        text += "\n" + footer

    user_repo = UserRepository()
    users = user_repo.list_all(limit=10000)
    sent = 0
    failed = 0

    for u in users:
        if not u.telegram_id:
            continue
        try:
            await send_chat(callback.bot, u.telegram_id, text)
            sent += 1
        except Exception:
            failed += 1

    result_text = (
        f"{TAG_CHECK} <b>Рассылка завершена</b>\n\n"
        f"Отправлено: <b>{sent}</b>\n"
        f"Не удалось: <b>{failed}</b>"
    )
    tmpl_res = tpl.get_template("admin.more", "ru")
    kb = tpl.build_keyboard(tmpl_res.get("buttons", []))
    await safe_edit_text(callback, result_text, reply_markup=kb)

@router.callback_query(F.data.startswith("admin_mgr_edit_name_"))
async def cb_admin_mgr_edit_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    mgr_id = int(callback.data.replace("admin_mgr_edit_name_", ""))
    await state.set_state(AdminStates.edit_manager_name)
    await state.update_data(edit_mgr_id=mgr_id)
    await safe_edit_text(callback, 
        f"{TAG_PENCIL} <b>Редактирование имени</b>\n\n"
        f"Введите новое отображаемое имя для менеджера:"
    )

@router.message(AdminStates.edit_manager_name)
async def process_edit_manager_name(message: Message, state: FSMContext):
    data = await state.get_data()
    mgr_id = data.get("edit_mgr_id")
    if not mgr_id:
        await send_text(message, "Ошибка состояния.")
        await state.clear()
        return

    new_name = message.text.strip()
    mgr_repo = ManagerRepository()
    mgr = mgr_repo.find_by_id(mgr_id)
    if not mgr:
        await send_text(message, "Менеджер не найден.")
        await state.clear()
        return

    mgr.full_name = new_name
    mgr_repo.update(mgr)
    await send_text(message, 
        f"{TAG_CHECK} Имя обновлено: <b>{new_name}</b>",
        reply_markup=back_keyboard(f"admin_mgr_detail_{mgr_id}"),
    )
    await state.clear()

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    is_admin = IsAdmin(ADMIN_IDS)
    if not await is_admin(message):
        return
    await tpl.send_template(message, "admin.menu", {})


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:return
    await callback.answer();await state.clear()
    await state.set_state(AdminStates.broadcast_message)
    await tpl.edit_template(callback, "admin.broadcast", {})


@router.message(AdminStates.broadcast_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:return
    await state.update_data(broadcast_chat=message.chat.id,broadcast_message=message.message_id)
    await state.set_state(None)
    count=len(UserRepository().list_all(limit=10000))
    await tpl.send_template(message,"admin.broadcast_confirm",{"count":count})


@router.callback_query(F.data == "admin_broadcast_send")
async def cb_admin_broadcast_send(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:return
    await callback.answer()
    data=await state.get_data()
    if not data.get('broadcast_message'):
        await safe_edit_text(callback,'Нет сообщения для рассылки',reply_markup=back_keyboard('admin_tools'));return
    # Clear before network work: repeated confirmation cannot resend the batch.
    await state.clear()
    sent=failed=0
    for user in UserRepository().list_all(limit=10000):
        if not user.telegram_id:continue
        try:
            await callback.bot.copy_message(user.telegram_id,data['broadcast_chat'],data['broadcast_message'])
            sent+=1
        except Exception:failed+=1
    await safe_edit_text(callback,f'Рассылка завершена. Отправлено: {sent}. Ошибок: {failed}',reply_markup=back_keyboard('admin_tools'))


@router.callback_query(F.data == "admin_promocodes")
async def cb_admin_promocodes(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:return
    await callback.answer();await state.clear()
    import html
    rows=PromocodeService().list_all()
    items='\n'.join(f'<code>{html.escape(p.code)}</code>: {p.bonus_percent}%, использовано {p.used_count}/{p.max_activations or "безлимит"}' for p in rows) or 'Промокодов нет'
    extra=[[{'text':f'Удалить {p.code}','callback_data':f'admin_promocode_delete_{p.id}'}] for p in rows[:3]]
    extra.append([{'text':'Назад','callback_data':'admin_tools'}])
    await tpl.edit_template(callback,'admin.promocodes',{'items':SafeHTML(items)},extra_buttons=extra)


@router.callback_query(F.data == "admin_promocode_add")
async def cb_admin_promocode_add(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:return
    await callback.answer();await state.clear();await state.set_state(AdminStates.promocode_add)
    await tpl.edit_template(callback,'admin.promocode_add',{})


@router.message(AdminStates.promocode_add)
async def process_promocode_add(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:return
    from decimal import InvalidOperation
    try:
        code,percent,count=(message.text or '').split()
        bonus=Decimal(percent.replace(',','.'));count=int(count)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',code) or not bonus.is_finite() or not 0<bonus<=100 or count<0:
            raise ValueError('Некорректные параметры')
        if PromocodeService().repo.find_by_code(code):raise ValueError('Код уже существует')
        PromocodeService().create(code,bonus,count)
    except (ValueError,InvalidOperation) as exc:
        await send_text(message,f'Не удалось добавить промокод: {exc}');return
    await state.clear()
    await tpl.send_template(message,'admin.promocodes',{'items':'Промокод добавлен'})


@router.callback_query(F.data.startswith("admin_promocode_delete_"))
async def cb_admin_promocode_delete(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:return
    try:ident=int(callback.data.removeprefix('admin_promocode_delete_'))
    except ValueError:
        await callback.answer('Некорректный код');return
    PromocodeService().soft_delete(ident)
    await cb_admin_promocodes(callback,state)

