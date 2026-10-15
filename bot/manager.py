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

from bot.common import get_manager, get_or_create_user, IsManager, safe_edit_text
from bot.keyboards import (
    manager_menu_keyboard,
    manager_deals_keyboard,
    deal_action_keyboard,
    back_keyboard,
)
from bot.emoji import (
    TAG_PROFILE, TAG_RECEIPT, TAG_MONEY, TAG_CHART, TAG_PIN,
    TAG_LOADING, TAG_CROSS, TAG_CHECK, TAG_SETTINGS, TAG_DOWNLOAD,
    TAG_ARROW_UP, TAG_BELL, TAG_LOCK, TAG_EXCHANGE, ARROW_UP,
    TAG_MONEY_SEND, TAG_INFO, TAG_PENCIL, BOX,
    CHECK, CROSS, LOADING,
)
import presentation as tpl


def _safe_icon(raw: str | None) -> str | None:
    import re
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return raw
    m = re.search(r'emoji-id="(\d+)"', raw)
    if m:
        return m.group(1)
    return None
from services import DealService, QueueService, NotificationService, ShiftReportService, RateService
from repositories import ManagerRepository, DealRepository, UserRepository
from models import Manager

router = Router()


class ManagerStates(StatesGroup):
    shift_open_platform = State()   # площадка начало
    shift_open_kb = State()        # КБ начало
    shift_open_confirm = State()    # подтверждение открытия
    shift_edit_platform = State()   # редактирование площадка
    shift_edit_kb = State()         # редактирование КБ
    shift_close_platform = State() # площадка конец
    shift_close_kb = State()      # КБ конец
    shift_close_confirm = State()   # подтверждение закрытия


# ── Manager Menu ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "manager_menu")
async def cb_manager_menu(callback: CallbackQuery):
    await callback.answer()
    await tpl.edit_template(callback, "manager.menu", {}, extra_buttons=[[{"text":"Создать счет","callback_data":"mgr_invoice"}]])


@router.callback_query(F.data == "mgr_rates")
async def cb_mgr_rates(callback: CallbackQuery):
    await callback.answer()
    rate_service = RateService()
    tiers = rate_service.get_tiers()

    tiers_text = ""
    if tiers:
        for t in tiers:
            tiers_text += f"• {t.name} — <b>{t.rate} ₽</b>\n"
    else:
        tiers_text = "Нет активных курсов.\n"

    await tpl.edit_template(
        callback, "manager.rates",
        {"tiers": SafeHTML(tiers_text)},
    )


# ── Manager History (finished deals) ──────────────────────────────────────

_DEAL_STATUS_ICON_MGR = {
    "closed": CHECK,
    "cancelled": CROSS,
}
_DEFAULT_STATUS_ICON_MGR = LOADING


@router.callback_query(F.data == "mgr_history")
async def cb_mgr_history(callback: CallbackQuery):
    await _show_mgr_history(callback, page=0)


@router.callback_query(F.data.startswith("mgr_history_page_"))
async def cb_mgr_history_page(callback: CallbackQuery):
    page = int(callback.data.replace("mgr_history_page_", ""))
    await _show_mgr_history(callback, page=page)


async def _show_mgr_history(callback: CallbackQuery, page: int = 0):
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("home"))
        return

    deal_repo = DealRepository()
    all_deals = deal_repo.list_by_manager(mgr.id)
    # Sort: active first, then by created_at desc
    all_deals = sorted(
        all_deals,
        key=lambda d: (0 if d.status in ("created", "queued", "active", "pinned") else 1, d.created_at or ""),
        reverse=True,
    )
    per_page = 10
    total = len(all_deals)
    start = page * per_page
    end = start + per_page
    deals = all_deals[start:end]

    extra = []
    for d in deals:
        icon = _DEAL_STATUS_ICON_MGR.get(d.status, _DEFAULT_STATUS_ICON_MGR)
        rub = d.amount_usdt * d.client_rate
        dt = d.created_at
        if dt:
            dt_str = dt.strftime("%d.%m %H:%M")
        else:
            dt_str = "--.-- --:--"
        row = [{
            "text": f"{dt_str} / {d.client_rate}₽ / {d.amount_usdt} USDT → {rub:.0f} ₽",
            "callback_data": f"mgr_deal_{d.id}",
            "icon_custom_emoji_id": icon,
        }]
        # Allow cancel for active deals from history too
        if d.status in ("created", "queued", "active", "pinned"):
            row.append({
                "text": "Отменить",
                "callback_data": f"deal_cancel_{d.id}",
            })
        extra.append(row)

    # Pagination
    nav = []
    if page > 0:
        nav.append({"text": "← Назад", "callback_data": f"mgr_history_page_{page - 1}", "icon_custom_emoji_id": ARROW_UP})
    if end < total:
        nav.append({"text": "Вперёд →", "callback_data": f"mgr_history_page_{page + 1}", "icon_custom_emoji_id": ARROW_UP})
    if nav:
        extra.append(nav)

    extra.append([{"text": "Назад", "callback_data": "home", "icon_custom_emoji_id": ARROW_UP}])

    active_count = len([d for d in all_deals if d.status in ("created", "queued", "active", "pinned")])
    finished_count = total - active_count
    info = f"Всего: {total} (активных: {active_count}, завершённых: {finished_count})   Страница {page + 1}/{(total // per_page) + (1 if total % per_page else 0)}" if total else "Нет сделок."
    await safe_edit_text(
        callback,
        f"{TAG_RECEIPT} <b>История сделок</b>\n\n{info}",
        reply_markup=tpl.build_keyboard([], extra),
    )


# ── My Deals ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "mgr_deals")
async def cb_mgr_deals(callback: CallbackQuery):
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("home"))
        return

    deal_service = DealService()
    all_deals = deal_service.get_manager_deals(mgr.id)

    current_deal = all_deals[0] if all_deals else None
    queued_deals = all_deals[1:] if len(all_deals) > 1 else []

    if not all_deals:
        await tpl.edit_template(callback, "manager.deals_empty", {})
    else:
        current_text = ""
        if current_deal:
            rub = current_deal.amount_usdt * current_deal.client_rate
            current_text = f"<b>Текущая:</b> {current_deal.amount_usdt} USDT ({rub:.0f} ₽)\n"
        queue_text = ""
        for i, d in enumerate(queued_deals, 1):
            rub = d.amount_usdt * d.client_rate
            queue_text += f"В очереди: {d.amount_usdt} USDT ({rub:.0f} ₽)\n"
        extra = []
        if current_deal:
            rub = current_deal.amount_usdt * current_deal.client_rate
            dt = current_deal.created_at
            dt_str = dt.strftime("%d.%m %H:%M") if dt else "--.-- --:--"
            extra.append([{"text": f"{dt_str} / {current_deal.client_rate}₽ / {current_deal.amount_usdt} USDT → {rub:.0f} ₽", "callback_data": f"mgr_deal_{current_deal.id}"}])
        for d in queued_deals:
            rub = d.amount_usdt * d.client_rate
            dt = d.created_at
            dt_str = dt.strftime("%d.%m %H:%M") if dt else "--.-- --:--"
            extra.append([{"text": f"{dt_str} / {d.client_rate}₽ / {d.amount_usdt} USDT → {rub:.0f} ₽", "callback_data": f"mgr_deal_{d.id}"}])
        extra.append([{"text": "Назад", "callback_data": "home", "icon_custom_emoji_id": ARROW_UP}])
        await tpl.edit_template(
            callback, "manager.deals",
            {
                "count": str(len(all_deals)),
                "current": current_text,
                "queue": queue_text,
            },
            extra_buttons=extra,
        )


@router.callback_query(F.data.startswith("mgr_deal_"))
async def cb_mgr_deal_detail(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("mgr_deal_", "")
    deal_service = DealService()
    deal = deal_service.deals.find_by_id(deal_id)

    if not deal:
        await safe_edit_text(callback, "Сделка не найдена.", reply_markup=back_keyboard("mgr_deals"))
        return

    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("mgr_deals"))
        return

    all_deals = deal_service.get_manager_deals(mgr.id)
    is_current = len(all_deals) > 0 and all_deals[0].id == deal.id

    rub = deal.amount_usdt * deal.client_rate
    profit_usdt = deal.profit / deal.client_rate if deal.client_rate else Decimal("0")
    pinned_text = ""
    if deal.is_pinned:
        pinned_text = f"{TAG_PIN} <b>ЗАКРЕПЛЕНА</b>\n"
    current_status_text = ""
    if is_current:
        current_status_text = "\n<b>Это ваша текущая сделка</b>"
    else:
        current_status_text = "\n<b>В очереди</b>"

    from twix_settings import get as settings_get
    show_profit = await settings_get("manager.show_deal_profit")
    profit_section = ""
    if show_profit:
        profit_section = (
            f"<tg-emoji emoji-id='5870930636742595124'>📈</tg-emoji> Прибыль: <b>{deal.profit:.2f} ₽</b> ({profit_usdt:.2f} USDT)\n"
        )

    extra = []
    if deal.is_pinned:
        extra.append([{"text": "Открепить", "callback_data": f"deal_unpin_{deal.id}", "icon_custom_emoji_id": "6042011682497106307"}])
    else:
        extra.append([{"text": "Закрепить", "callback_data": f"deal_pin_{deal.id}", "icon_custom_emoji_id": "6042011682497106307"}])
    if not is_current:
        extra.append([{"text": "Сделать текущей", "callback_data": f"deal_promote_{deal.id}", "icon_custom_emoji_id": "5963103826075456248"}])

    profit_toggle_label = "Скрыть прибыль" if show_profit else "Показать прибыль"
    extra.append([{"text": profit_toggle_label, "callback_data": "mgr_toggle_profit"}])
    extra.append([{"text": "Назад", "callback_data": "mgr_deals", "icon_custom_emoji_id": "5963103826075456248"}])

    from bot.common import get_client_contact
    client_contact = get_client_contact(deal)
    created_at = deal.created_at.strftime("%d.%m.%Y %H:%M UTC") if deal.created_at else "—"
    await tpl.edit_template(
        callback,
        "manager.deal_detail",
        variables={
            "amount": str(deal.amount_usdt),
            "rate": str(deal.client_rate),
            "total": f"{rub:.0f}",
            "profit_section": profit_section,
            "status": deal.status.upper(),
            "pinned": pinned_text,
            "current_status": current_status_text,
            "deal_id": deal.id,
            "client": client_contact,
            "created_at": created_at,
        },
        extra_buttons=extra,
    )


@router.callback_query(F.data == "mgr_toggle_profit")
async def cb_mgr_toggle_profit(callback: CallbackQuery):
    await callback.answer()
    from twix_settings import get as settings_get, set as settings_set
    current = await settings_get("manager.show_deal_profit")
    await settings_set("manager.show_deal_profit", not current)
    await safe_edit_text(
        callback,
        f"{TAG_CHECK} Обновлено: прибыль {'видна' if not current else 'скрыта'}.",
        reply_markup=back_keyboard("mgr_deals"),
    )


# ── Deal Actions ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("deal_close_"))
async def cb_deal_close(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    deal_id = callback.data.replace("deal_close_", "")
    deal_service = DealService()
    deal = deal_service.deals.find_by_id(deal_id)
    if not deal:
        await safe_edit_text(callback, "Сделка не найдена.", reply_markup=back_keyboard("mgr_deals"))
        return

    mgr = await get_manager(callback)
    closed = await deal_service.close_deal(deal_id, actor_id=mgr.id if mgr else 0)

    from bot.common import post_service_channel, notify_user_deal_status
    bot = callback.bot
    await post_service_channel(bot, closed)

    # Notify client
    try:
        await notify_user_deal_status(bot, closed, "closed")
    except Exception:
        pass

    profit_usdt = closed.profit / closed.client_rate if closed.client_rate else Decimal("0")
    tmpl = tpl.get_template("manager.deal_closed", "ru")
    text = tpl.render_text(tmpl, {
        "profit": f"{closed.profit:.2f}",
        "profit_usdt": f"{profit_usdt:.2f}",
    })
    await safe_edit_text(callback, 
        text,
        reply_markup=back_keyboard("mgr_deals"),
    )
    await state.clear()


@router.callback_query(F.data.startswith("deal_cancel_"))
async def cb_deal_cancel(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("deal_cancel_", "")

    mgr = await get_manager(callback)
    deal_service = DealService()
    await deal_service.cancel_deal(deal_id, actor_id=mgr.id if mgr else 0)

    deal = deal_service.deals.find_by_id(deal_id)
    if deal:
        from bot.common import notify_user_deal_status
        try:
            await notify_user_deal_status(callback.bot, deal, "cancelled")
        except Exception:
            pass

    tmpl = tpl.get_template("client.cancelled", "ru")
    text = tpl.render_text(tmpl, {})
    await safe_edit_text(callback, 
        text,
        reply_markup=back_keyboard("mgr_deals"),
    )


@router.callback_query(F.data.startswith("deal_pin_"))
async def cb_deal_pin(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("deal_pin_", "")
    deal_service = DealService()
    mgr = await get_manager(callback)
    await deal_service.pin_deal(deal_id, actor_id=mgr.id if mgr else 0)
    await safe_edit_text(callback, 
        f"{TAG_PIN} Сделка закреплена.",
        reply_markup=back_keyboard("mgr_deals"),
    )


@router.callback_query(F.data.startswith("deal_unpin_"))
async def cb_deal_unpin(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("deal_unpin_", "")
    deal_service = DealService()
    mgr = await get_manager(callback)
    await deal_service.unpin_deal(deal_id, actor_id=mgr.id if mgr else 0)
    await safe_edit_text(callback, 
        f"{TAG_PIN} Сделка откреплена.",
        reply_markup=back_keyboard("mgr_deals"),
    )


@router.callback_query(F.data.startswith("deal_promote_"))
async def cb_deal_promote(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("deal_promote_", "")
    deal_service = DealService()
    mgr = await get_manager(callback)
    try:
        await deal_service.promote_deal(deal_id, actor_id=mgr.id if mgr else 0)
        await safe_edit_text(callback, 
            f"{TAG_ARROW_UP} Сделка теперь текущая!",
            reply_markup=back_keyboard("mgr_deals"),
        )
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard("mgr_deals"))


@router.callback_query(F.data.startswith("deal_transfer_"))
async def cb_deal_transfer(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("deal_transfer_", "")
    deal_service = DealService()
    from services import QueueService
    queue_service = QueueService()
    mgr = await get_manager(callback)
    try:
        deal = await deal_service.transfer_deal(deal_id, actor_id=mgr.id if mgr else 0, queue_service=queue_service)

        # Notify new manager and client only if deal was reassigned to someone else
        if deal and deal.manager_id and deal.manager_id != (mgr.id if mgr else None):
            from bot.common import notify_manager_new_deal, notify_user_deal_assigned
            new_mgr = ManagerRepository().find_by_id(deal.manager_id)
            if new_mgr:
                try:
                    await notify_manager_new_deal(callback.bot, new_mgr, deal)
                    print(f"[TRANSFER_CB] notified new_mgr={new_mgr.telegram_id}")
                except Exception as e:
                    print(f"[TRANSFER_CB] notify_manager_new_deal failed: {e}")
                    pass
            try:
                await notify_user_deal_assigned(callback.bot, deal)
                print(f"[TRANSFER_CB] notified client user_id={deal.user_id}")
            except Exception as e:
                print(f"[TRANSFER_CB] notify client failed: {e}")
                pass

        # Refresh manager deals view
        all_deals = deal_service.get_manager_deals(mgr.id if mgr else 0)
        current_deal = all_deals[0] if all_deals else None
        queued_deals = all_deals[1:] if len(all_deals) > 1 else []
        if not all_deals:
            await tpl.edit_template(callback, "manager.deals_empty", {})
        else:
            current_text = ""
            if current_deal:
                rub = current_deal.amount_usdt * current_deal.client_rate
                current_text = f"<b>Текущая:</b> {current_deal.amount_usdt} USDT ({rub:.0f} ₽)\n"
            queue_text = ""
            for i, d in enumerate(queued_deals, 1):
                rub = d.amount_usdt * d.client_rate
                queue_text += f"В очереди: {d.amount_usdt} USDT ({rub:.0f} ₽)\n"
            extra = []
            if current_deal:
                rub = current_deal.amount_usdt * current_deal.client_rate
                extra.append([{"text": f"Текущая: {current_deal.amount_usdt} USDT ({rub:.0f} ₽)", "callback_data": f"mgr_deal_{current_deal.id}"}])
            for d in queued_deals:
                rub = d.amount_usdt * d.client_rate
                extra.append([{"text": f"В очереди: {d.amount_usdt} USDT ({rub:.0f} ₽)", "callback_data": f"mgr_deal_{d.id}"}])
            await tpl.edit_template(
                callback, "manager.deals",
                {
                    "count": str(len(all_deals)),
                    "current": current_text,
                    "queue": queue_text,
                },
                extra_buttons=extra,
            )
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard("mgr_deals"))


# ── Manager Stats ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "mgr_stats")
async def cb_mgr_stats(callback: CallbackQuery):
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("home"))
        return

    mgr_profit_usdt = mgr.profit / Decimal("84") if mgr.profit else Decimal("0")
    mgr_vol_rub = mgr.total_volume * Decimal("84")
    await tpl.edit_template(
        callback, "manager.stats",
        {
            "name": mgr.full_name or mgr.username or "Не указано",
            "volume": str(mgr.total_volume),
            "volume_rub": f"{mgr_vol_rub:.0f}",
            "profit": f"{mgr.profit:.2f}",
            "profit_usdt": f"{mgr_profit_usdt:.2f}",
            "deals": SafeHTML(str(mgr.deal_count)),
            "cancels": str(mgr.cancel_count),
        },
    )


# ── Manager Settings ──────────────────────────────────────────────────────

@router.callback_query(F.data == "mgr_settings")
async def cb_mgr_settings(callback: CallbackQuery):
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("home"))
        return

    online = "Онлайн" if mgr.is_online else "Офлайн"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Офлайн" if mgr.is_online else "Онлайн",
        callback_data=f"mgr_toggle_online_{mgr.id}_{0 if mgr.is_online else 1}"
    )
    builder.button(text="Смена", callback_data="mgr_shift_status")
    builder.button(text="Назад", callback_data="home", icon_custom_emoji_id=_safe_icon(ARROW_UP))
    builder.adjust(1)

    await tpl.edit_template(
        callback, "manager.settings",
        {"online": online,"status":"Принимает сделки" if mgr.can_receive_deals else "Прием остановлен"},
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("mgr_toggle_online_"))
async def cb_mgr_toggle_online(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    mgr_id = int(parts[3])
    new_state = int(parts[4])

    mgr_repo = ManagerRepository()
    mgr = mgr_repo.find_by_id(mgr_id)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("home"))
        return

    mgr.is_online = bool(new_state)
    mgr.can_receive_deals = bool(new_state)  # sync: online = can receive
    mgr_repo.update(mgr)

    status = "Онлайн" if mgr.is_online else "Офлайн"
    await safe_edit_text(callback,
        f"{TAG_CHECK} Обновлено!\n\nСтатус: <b>{status}</b>",
        reply_markup=back_keyboard("home"),
    )


# ── Shift Status ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "mgr_shift_status")
async def cb_mgr_shift_status(callback: CallbackQuery):
    print(f"[DEBUG] cb_mgr_shift_status called by user={callback.from_user.id}", flush=True)
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("home"))
        return

    from datetime import date
    today = date.today().isoformat()
    service = ShiftReportService()
    report = service.repo.find_by_manager_and_date(mgr.id, today)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from datetime import timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    builder = InlineKeyboardBuilder()
    if report and report.closing_balance > 0:
        builder.button(text="Смена закрыта", callback_data="mgr_shift_status")
    elif report and report.is_locked:
        builder.button(text="Смена закрыта админом", callback_data="mgr_shift_status")
    elif report:
        builder.button(text="Закрыть смену", callback_data="mgr_shift_close")
        builder.button(text="Редактировать", callback_data="mgr_shift_edit")
    else:
        builder.button(text="Открыть смену", callback_data="mgr_shift_open")
        builder.button(text=f"Открыть за {tomorrow}", callback_data="mgr_shift_open_tomorrow")
    builder.button(text="Назад", callback_data="home", icon_custom_emoji_id=_safe_icon(ARROW_UP))
    builder.adjust(1)

    start_total = report.opening_balance + report.start_kb if report else Decimal("0")
    end_total = report.closing_balance + report.end_kb if report else Decimal("0")
    await tpl.edit_template(
        callback, "manager.shift_status",
        {
            "date": today,
            "start_platform": f"{report.opening_balance:.0f}" if report else "—",
            "start_kb": f"{report.start_kb:.0f}" if report else "—",
            "start_total": f"{start_total:.0f}" if report else "—",
            "end_platform": f"{report.closing_balance:.0f}" if report and report.closing_balance else "—",
            "end_kb": f"{report.end_kb:.0f}" if report and report.end_kb else "—",
            "end_total": f"{end_total:.0f}" if report and report.closing_balance else "—",
            "income": f"{report.system_profit:.0f}" if report and report.closing_balance else "—",
            "locked": "Да" if report and report.is_locked else "Нет",
        },
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "mgr_shift_edit")
async def cb_mgr_shift_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("mgr_shift_status"))
        return

    from datetime import date
    today = date.today().isoformat()
    service = ShiftReportService()
    report = service.repo.find_by_manager_and_date(mgr.id, today)
    if not report:
        await safe_edit_text(callback, "Сначала откройте смену.", reply_markup=back_keyboard("mgr_shift_status"))
        return
    if report.is_locked:
        await safe_edit_text(callback, "Смена закрыта администратором.", reply_markup=back_keyboard("mgr_shift_status"))
        return

    await state.update_data(shift_edit_date=today)
    await state.set_state(ManagerStates.shift_edit_platform)
    await safe_edit_text(
        callback,
        f"{TAG_PENCIL} <b>Редактирование смены</b>\n\nТекущий баланс Площадки: <b>{report.opening_balance:.0f} ₽</b>\n\nВведите новый баланс <b>Площадки</b>:",
        reply_markup=back_keyboard("mgr_shift_status"),
    )


@router.message(ManagerStates.shift_edit_platform)
async def process_shift_edit_platform(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount < 0:
            raise ValueError
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите положительное число.")
        return
    await state.update_data(edit_platform=amount)
    await state.set_state(ManagerStates.shift_edit_kb)
    await send_text(message, 
        f"{TAG_PENCIL} <b>Редактирование смены</b>\n\nВведите новый баланс <b>КБ</b>:"
    )


@router.message(ManagerStates.shift_edit_kb)
async def process_shift_edit_kb(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount < 0:
            raise ValueError
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите положительное число.")
        return

    data = await state.get_data()
    edit_platform = data.get("edit_platform", Decimal("0"))
    edit_date = data.get("shift_edit_date")

    mgr = await get_manager(message)
    if not mgr:
        await send_text(message, "Менеджер не найден.")
        await state.clear()
        return

    service = ShiftReportService()
    report = service.repo.find_by_manager_and_date(mgr.id, edit_date)
    if not report:
        await send_text(message, "Смена не найдена.")
        await state.clear()
        return
    if report.is_locked:
        await send_text(message, "Смена закрыта администратором.")
        await state.clear()
        return

    report.opening_balance = Decimal(edit_platform)
    report.start_kb = Decimal(amount)
    service.repo.update(report)

    total = report.opening_balance + report.start_kb
    await send_text(message, 
        f"{TAG_CHECK} Смена обновлена ({edit_date})!\n\n"
        f"Площадка: <b>{report.opening_balance:.0f} ₽</b>\n"
        f"КБ: <b>{report.start_kb:.0f} ₽</b>\n"
        f"Общий: <b>{total:.0f} ₽</b>",
        reply_markup=back_keyboard("mgr_shift_status"),
    )
    await state.clear()


@router.callback_query(F.data == "mgr_shift_open")
async def cb_mgr_shift_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("home"))
        return

    from datetime import date
    await state.update_data(shift_work_date=date.today().isoformat())
    await state.set_state(ManagerStates.shift_open_platform)
    await safe_edit_text(
        callback,
        f"{TAG_PENCIL} <b>Открытие смены</b>\n\nВведите баланс <b>Площадки</b> на начало дня:",
        reply_markup=back_keyboard("mgr_shift_status"),
    )


@router.callback_query(F.data == "mgr_shift_open_tomorrow")
async def cb_mgr_shift_open_tomorrow(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    await state.update_data(shift_work_date=tomorrow)
    await state.set_state(ManagerStates.shift_open_platform)
    await safe_edit_text(
        callback,
        f"{TAG_PENCIL} <b>Открытие смены за {tomorrow}</b>\n\nВведите баланс <b>Площадки</b> на начало дня:",
        reply_markup=back_keyboard("mgr_shift_status"),
    )


@router.message(ManagerStates.shift_open_platform)
async def process_shift_open_platform(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount < 0:
            raise ValueError
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите положительное число.")
        return
    await state.update_data(start_platform=amount)
    await state.set_state(ManagerStates.shift_open_kb)
    await send_text(message, 
        f"{TAG_PENCIL} <b>Открытие смены</b>\n\nВведите баланс <b>КБ</b> на начало дня:"
    )


@router.message(ManagerStates.shift_open_kb)
async def process_shift_open_kb(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount < 0:
            raise ValueError
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите положительное число.")
        return

    await state.update_data(start_kb=amount)
    await state.set_state(ManagerStates.shift_open_confirm)

    data = await state.get_data()
    start_platform = data.get("start_platform", Decimal("0"))
    work_date = data.get("shift_work_date")
    if not work_date:
        from datetime import date
        work_date = date.today().isoformat()

    total = Decimal(start_platform) + amount
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить", callback_data="mgr_shift_confirm_open")
    builder.button(text="Отменить", callback_data="mgr_shift_cancel_open")
    builder.adjust(2)

    await send_text(message, 
        f"{TAG_PENCIL} <b>Подтвердите открытие смены</b> ({work_date})\n\n"
        f"Площадка: <b>{Decimal(start_platform):.0f} ₽</b>\n"
        f"КБ: <b>{amount:.0f} ₽</b>\n"
        f"Общий: <b>{total:.0f} ₽</b>",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "mgr_shift_confirm_open")
async def cb_mgr_shift_confirm_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    start_platform = data.get("start_platform", Decimal("0"))
    start_kb = data.get("start_kb", Decimal("0"))
    work_date = data.get("shift_work_date")
    if not work_date:
        from datetime import date
        work_date = date.today().isoformat()

    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("mgr_shift_status"))
        await state.clear()
        return

    service = ShiftReportService()
    try:
        report = await service.open_shift(mgr.id, work_date, Decimal(start_platform), Decimal(start_kb))
        total = report.opening_balance + report.start_kb
        await safe_edit_text(
            callback,
            f"{TAG_CHECK} Смена открыта ({work_date})!\n\n"
            f"Площадка: <b>{report.opening_balance:.0f} ₽</b>\n"
            f"КБ: <b>{report.start_kb:.0f} ₽</b>\n"
            f"Общий: <b>{total:.0f} ₽</b>",
            reply_markup=back_keyboard("mgr_shift_status"),
        )
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard("mgr_shift_status"))
    await state.clear()


@router.callback_query(F.data == "mgr_shift_cancel_open")
async def cb_mgr_shift_cancel_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(callback, f"{TAG_CROSS} Открытие смены отменено.", reply_markup=back_keyboard("mgr_shift_status"))


@router.callback_query(F.data == "mgr_shift_close")
async def cb_mgr_shift_close(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("mgr_shift_status"))
        return

    from datetime import date
    today = date.today().isoformat()
    service = ShiftReportService()
    report = service.repo.find_by_manager_and_date(mgr.id, today)
    if not report:
        await safe_edit_text(callback, "Сначала откройте смену.", reply_markup=back_keyboard("mgr_shift_status"))
        return
    if report.is_locked:
        await safe_edit_text(callback, "Смена закрыта администратором.", reply_markup=back_keyboard("mgr_shift_status"))
        return

    await state.set_state(ManagerStates.shift_close_platform)
    await safe_edit_text(
        callback,
        f"{TAG_PENCIL} <b>Закрытие смены</b>\n\nВведите баланс <b>Площадки</b> на конец дня:",
        reply_markup=back_keyboard("mgr_shift_status"),
    )


@router.message(ManagerStates.shift_close_platform)
async def process_shift_close_platform(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount < 0:
            raise ValueError
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите положительное число.")
        return
    await state.update_data(end_platform=amount)
    await state.set_state(ManagerStates.shift_close_kb)
    await send_text(message, 
        f"{TAG_PENCIL} <b>Закрытие смены</b>\n\nВведите баланс <b>КБ</b> на конец дня:"
    )


@router.message(ManagerStates.shift_close_kb)
async def process_shift_close_kb(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount < 0:
            raise ValueError
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите положительное число.")
        return

    await state.update_data(end_kb=amount)
    await state.set_state(ManagerStates.shift_close_confirm)

    data = await state.get_data()
    end_platform = data.get("end_platform", Decimal("0"))

    end_total = Decimal(end_platform) + amount
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить", callback_data="mgr_shift_confirm_close")
    builder.button(text="Отменить", callback_data="mgr_shift_cancel_close")
    builder.adjust(2)

    await send_text(message, 
        f"{TAG_PENCIL} <b>Подтвердите закрытие смены</b>\n\n"
        f"Площадка конец: <b>{Decimal(end_platform):.0f} ₽</b>\n"
        f"КБ конец: <b>{amount:.0f} ₽</b>\n"
        f"Общий конец: <b>{end_total:.0f} ₽</b>",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "mgr_shift_confirm_close")
async def cb_mgr_shift_confirm_close(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    end_platform = data.get("end_platform", Decimal("0"))
    end_kb = data.get("end_kb", Decimal("0"))

    mgr = await get_manager(callback)
    if not mgr:
        await safe_edit_text(callback, "Менеджер не найден.", reply_markup=back_keyboard("mgr_shift_status"))
        await state.clear()
        return

    from datetime import date
    today = date.today().isoformat()
    service = ShiftReportService()
    try:
        report = await service.close_shift(mgr.id, today, Decimal(end_platform), Decimal(end_kb))
        end_total = report.closing_balance + report.end_kb
        start_total = report.opening_balance + report.start_kb
        income = report.system_profit
        await safe_edit_text(
            callback,
            f"{TAG_CHECK} Смена закрыта!\n\n"
            f"Площадка: <b>{report.closing_balance:.0f} ₽</b>\n"
            f"КБ: <b>{report.end_kb:.0f} ₽</b>\n"
            f"Общий: <b>{end_total:.0f} ₽</b>\n\n"
            f"Доход: <b>{income:.0f} ₽</b>",
            reply_markup=back_keyboard("mgr_shift_status"),
        )
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard("mgr_shift_status"))
    await state.clear()


@router.callback_query(F.data == "mgr_shift_cancel_close")
async def cb_mgr_shift_cancel_close(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(callback, f"{TAG_CROSS} Закрытие смены отменено.", reply_markup=back_keyboard("mgr_shift_status"))


# ── Commands Help (cheat sheet for business chat) ─────────────────────────

@router.callback_query(F.data == "mgr_commands_help")
async def cb_mgr_commands_help(callback: CallbackQuery):
    await callback.answer()
    await tpl.edit_template(callback, "manager.commands_help", {})


# ── Quick shift shortcuts (from manager home panel) ────────────────────────

@router.callback_query(F.data == "mgr_shift_start")
async def cb_mgr_shift_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    mgr = await get_manager(callback)
    if mgr:
        mgr_repo = ManagerRepository()
        mgr.is_online = True
        mgr.can_receive_deals = True
        mgr_repo.update(mgr)
    await cb_mgr_shift_open(callback, state)


@router.callback_query(F.data == "mgr_shift_end")
async def cb_mgr_shift_end(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await cb_mgr_shift_close(callback, state)


# ── Business Commands (direct message commands) ───────────────────────────

@router.message(F.text.regexp(r"^\+(cr|create)\s+(\d+(\.\d+)?)(?:\s+usdt)?(?:\s+(\d+(\.\d+)?))?$"))
async def cmd_create_deal(message: Message):
    mgr = await get_manager(message)
    if not mgr:
        return

    match = re.match(r"^\+(cr|create)\s+(\d+(\.\d+)?)(?:\s+usdt)?(?:\s+(\d+(\.\d+)?))?$", message.text, re.IGNORECASE)
    amount = Decimal(match.group(2))

    from services import RateService
    rate_service = RateService()

    custom_rate_str = match.group(4)
    if custom_rate_str:
        client_rate = Decimal(custom_rate_str)
    else:
        tier = rate_service.get_rate_for_amount(amount)
        if not tier:
            await send_text(message, f"{TAG_CROSS} Нет курса для этой суммы.")
            return
        client_rate = tier.rate

    from twix_settings import get as settings_get
    rapira_price = await settings_get("rates.rapira_last_price")
    if rapira_price and Decimal(str(rapira_price)) > 0:
        internal_rate = Decimal(str(rapira_price)) * (await settings_get('rates.coefficient'))
    else:
        internal_rate = client_rate / (await settings_get('rates.coefficient'))

    user_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user_repo = UserRepository()
        reply_user = user_repo.find_by_telegram_id(message.reply_to_message.from_user.id)
        if not reply_user:
            from models import User
            reply_user = user_repo.create(
                User(
                    telegram_id=message.reply_to_message.from_user.id,
                    username=message.reply_to_message.from_user.username,
                    full_name=message.reply_to_message.from_user.full_name,
                )
            )
        user_id = reply_user.id

    if not user_id:
        await send_text(message, f"{TAG_CROSS} Нужно ответить на сообщение клиента.")
        return

    deal_service = DealService()
    try:
        deal = await deal_service.create_deal(
            user_id=user_id,
            amount_usdt=amount,
            client_rate=client_rate,
            internal_rate=internal_rate,
            manager_id=mgr.id,
            actor_id=mgr.id,
        )
        rub = amount * client_rate
        await send_text(message, f"{TAG_CHECK} Сделка создана: {amount} USDT ({rub:.0f} ₽)")
        try:
            await message.delete()
        except Exception:
            pass
    except ValueError as e:
        await send_text(message, f"{TAG_CROSS} {e}")


@router.message(F.text.regexp(r"^-(d|done)(?:\s+(\d+(?:\.\d+)?))?$"))
async def cmd_done_deal(message: Message):
    mgr = await get_manager(message)
    if not mgr:
        return

    match = re.match(r"^-(d|done)(?:\s+(\d+(?:\.\d+)?))?$", message.text or "", re.IGNORECASE)
    actual_amount = None
    if match and match.group(2):
        actual_amount = Decimal(match.group(2))

    deal_service = DealService()
    deals = deal_service.get_manager_deals(mgr.id)
    if not deals:
        await send_text(message, f"{TAG_CROSS} Нет активных сделок.")
        return

    deal = deals[0]
    closed = await deal_service.close_deal(deal.id, actor_id=mgr.id, actual_amount=actual_amount)

    from bot.common import post_service_channel
    await post_service_channel(message.bot, closed)

    profit_usdt = closed.profit / closed.client_rate if closed.client_rate else Decimal("0")
    await send_text(message, f"{TAG_CHECK} Сделка завершена! Прибыль: {closed.profit:.2f} ₽ ({profit_usdt:.2f} USDT)")
    try:
        await message.delete()
    except Exception:
        pass


@router.message(F.text.regexp(r"^-(r|remind)$"))
async def cmd_remind(message: Message):
    mgr = await get_manager(message)
    if not mgr:
        return

    deal_service = DealService()
    deals = deal_service.get_manager_deals(mgr.id)
    if not deals:
        await send_text(message, f"{TAG_CROSS} Нет активных сделок.")
        try:
            await message.delete()
        except Exception:
            pass
        return

    deal = deals[0]
    try:
        from repositories import UserRepository
        user_repo = UserRepository()
        deal_user = user_repo.find_by_id(deal.user_id)
        if deal_user:
            await send_chat(message.bot, 
                deal_user.telegram_id,
                f"Напоминание от менеджера по сделке #{deal.id[:8]}: пожалуйста, свяжитесь для завершения."
            )
        await send_text(message, f"{TAG_BELL} Напоминание отправлено клиенту.")
    except Exception as e:
        await send_text(message, f"{TAG_CROSS} Не удалось отправить: {e}")

    try:
        await message.delete()
    except Exception:
        pass


@router.message(F.text.regexp(r"^-(c|cancel)$"))
async def cmd_cancel_deal(message: Message):
    mgr = await get_manager(message)
    if not mgr:
        return

    deal_service = DealService()
    deals = deal_service.get_manager_deals(mgr.id)
    if not deals:
        await send_text(message, f"{TAG_CROSS} Нет активных сделок.")
        return

    deal = deals[0]
    await deal_service.cancel_deal(deal.id, actor_id=mgr.id)
    await send_text(message, f"{TAG_CROSS} Сделка отменена.")
    try:
        await message.delete()
    except Exception:
        pass


@router.message(F.text.regexp(r"^\+(p|pin)$"))
async def cmd_pin_deal(message: Message):
    mgr = await get_manager(message)
    if not mgr:
        return

    deal_service = DealService()
    deals = deal_service.get_manager_deals(mgr.id)
    if not deals:
        await send_text(message, f"{TAG_CROSS} Нет активных сделок для закрепления.")
        return

    deal = deals[0]
    await deal_service.pin_deal(deal.id, actor_id=mgr.id)
    await send_text(message, f"{TAG_PIN} Сделка закреплена.")
    try:
        await message.delete()
    except Exception:
        pass


@router.message(F.text.regexp(r"^-(u|unpin)$"))
async def cmd_unpin_deal(message: Message):
    mgr = await get_manager(message)
    if not mgr:
        return

    deal_service = DealService()
    deals = deal_service.get_manager_deals(mgr.id)
    pinned = [d for d in deals if d.status == "pinned"]
    if not pinned:
        await send_text(message, f"{TAG_CROSS} Нет закреплённых сделок.")
        return

    deal = pinned[0]
    await deal_service.unpin_deal(deal.id, actor_id=mgr.id)
    await send_text(message, f"{TAG_PIN} Сделка откреплена.")
    try:
        await message.delete()
    except Exception:
        pass


@router.message(F.text.regexp(r"^-transfer$"))
async def cmd_transfer_deal(message: Message):
    mgr = await get_manager(message)
    if not mgr:
        return

    deal_service = DealService()
    deals = deal_service.get_manager_deals(mgr.id)
    if not deals:
        await send_text(message, f"{TAG_CROSS} Нет активных сделок.")
        return

    deal = deals[0]
    try:
        await deal_service.transfer_deal(deal.id, actor_id=mgr.id)
        await send_text(message, f"{TAG_LOADING} Сделка передана в общую очередь.")
    except ValueError as e:
        await send_text(message, f"{TAG_CROSS} {e}")
    try:
        await message.delete()
    except Exception:
        pass


# ── Notifications ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "mgr_notifications")
async def cb_mgr_notifications(callback: CallbackQuery):
    await callback.answer()
    mgr = await get_manager(callback)
    if not mgr:
        return

    from services import NotificationService
    notif_service = NotificationService()
    notifications = notif_service.get_unread_for_manager(mgr.id)

    if not notifications:
        await tpl.edit_template(callback, "manager.notifications_empty", {})
    else:
        items = ""
        for n in notifications:
            items += f"• {n.message}\n"
            notif_service.mark_read(n.id)
        await tpl.edit_template(
            callback, "manager.notifications",
            {"count": str(len(notifications)), "items": SafeHTML(items)},
        )
