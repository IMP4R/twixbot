from __future__ import annotations
from presentation import send_text, send_chat
from tg_templates import SafeHTML

import re

from aiogram import Router, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal

from bot.common import get_or_create_user, IsAdmin, IsManager, safe_edit_text
from bot.keyboards import (
    manager_home_keyboard,
    client_menu_keyboard,
    back_keyboard,
)
from bot.emoji import (
    TAG_RECEIPT, TAG_CHECK, TAG_CROSS, TAG_EXCHANGE,
    TAG_MONEY, TAG_CHART, TAG_PROFILE, TAG_LOADING, TAG_PIN,
    TAG_HOME, TAG_BELL, TAG_GIFT, TAG_INFO, TAG_RATE, TAG_DOWNLOAD,
    TAG_BOX, TAG_ARROW_UP, TAG_SEND, TAG_MEDIA_PHOTO, TAG_MONEY_SEND,
    TAG_LOCK, TAG_LAVA, TAG_CLOCK, SETTINGS, ADD_TEXT,
    LOCK_CLOSED, LOCK_OPEN,
    CROSS, CHECK, LOADING, DOWNLOAD, ARROW_UP, BOX, LINK,
)
import presentation as tpl
from config import ADMIN_IDS, DEFAULT_RATES
from twix_settings import get_sync
from database import init_db
from models import User
from repositories import UserRepository, RateRepository, ManagerRepository
from services import DealService, RateService, NotificationService, PromocodeService

router = Router()


class ClientStates(StatesGroup):
    accept_tos = State()
    enter_amount = State()
    enter_promocode = State()
    confirm_deal = State()


STATUS_RU = {
    "created": "Создана",
    "queued": "В очереди",
    "active": "Активна",
    "pinned": "Закреплена",
    "closed": "Завершена",
    "cancelled": "Отменена",
}


# ══════════════════════════════════════════════════════════════════════
#  TERMS OF SERVICE
# ══════════════════════════════════════════════════════════════════════

async def _send_home(message: Message, user: User):
    is_mgr = IsManager()
    is_admin = IsAdmin(ADMIN_IDS)
    manager_flag = await is_mgr(message)
    admin_flag = await is_admin(message)

    extra = []
    if manager_flag:
        extra.append([{"text": "Менеджер", "callback_data": "manager_menu", "icon_custom_emoji_id": "5870994129244131212"}])
    if admin_flag:
        extra.append([{"text": "Админка", "callback_data": "admin_menu", "icon_custom_emoji_id": "5870982283724328568"}])

    # Manager gets their own home screen
    if manager_flag:
        from repositories import ManagerRepository
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_telegram_id(message.from_user.id)
        if mgr:
            from services import DealService
            deal_service = DealService()
            all_deals = deal_service.get_manager_deals(mgr.id)
            current = all_deals[0] if all_deals else None
            queued = len(all_deals) - 1 if len(all_deals) > 1 else 0
            status_online = 'Онлайн' if mgr.is_online else 'Офлайн'
            status_receive = 'Да' if mgr.can_receive_deals else 'Нет'
            # Build manager home panel buttons
            mgr_extra = []
            # Unified online toggle: controls both is_online and can_receive_deals
            online_text = 'Онлайн' if mgr.is_online else 'Офлайн'
            online_icon = CHECK if mgr.is_online else CROSS
            mgr_extra.append([{"text": online_text, "callback_data": f"mgr_toggle_online_{mgr.id}_{0 if mgr.is_online else 1}", "icon_custom_emoji_id": online_icon}])
            if mgr.is_online:
                mgr_extra.append([{"text": "Завершить смену", "callback_data": "mgr_shift_end", "icon_custom_emoji_id": CROSS}])
            else:
                mgr_extra.append([{"text": "Начать смену", "callback_data": "mgr_shift_start", "icon_custom_emoji_id": CHECK}])
            if current:
                rub = current.amount_usdt * current.client_rate
                mgr_extra.append([{"text": f"Текущая: {current.amount_usdt} USDT ({rub:.0f} ₽)", "callback_data": f"mgr_deal_{current.id}"}])
            else:
                mgr_extra.append([{"text": "Нет текущей сделки", "callback_data": "mgr_deals", "icon_custom_emoji_id": LOADING}])
            if queued:
                mgr_extra.append([{"text": f"Очередь: {queued} сделок", "callback_data": "mgr_deals", "icon_custom_emoji_id": DOWNLOAD}])
            else:
                mgr_extra.append([{"text": "Очередь пуста", "callback_data": "mgr_deals", "icon_custom_emoji_id": DOWNLOAD}])
            mgr_extra.append([{"text": "Курсы", "callback_data": "mgr_rates", "icon_custom_emoji_id": LINK}])
            mgr_extra.append([{"text": "История", "callback_data": "mgr_history", "icon_custom_emoji_id": BOX}])
            if admin_flag:
                mgr_extra.append([{"text": "Админка", "callback_data": "admin_menu", "icon_custom_emoji_id": SETTINGS}])
            await tpl.send_template(
                message, "manager.home",
                {"status_online": status_online, "status_receive": status_receive},
                extra_buttons=mgr_extra,
            )
            return

    await tpl.send_template(
        message, "main.greeting",
        {"name": user.full_name or "друг"},
        extra_buttons=extra,
    )


async def _edit_home(callback: CallbackQuery, user: User):
    is_mgr = IsManager()
    is_admin = IsAdmin(ADMIN_IDS)
    manager_flag = await is_mgr(callback)
    admin_flag = await is_admin(callback)

    extra = []
    if manager_flag:
        extra.append([{"text": "Менеджер", "callback_data": "manager_menu", "icon_custom_emoji_id": "5870994129244131212"}])
    if admin_flag:
        extra.append([{"text": "Админка", "callback_data": "admin_menu", "icon_custom_emoji_id": "5870982283724328568"}])

    # Manager gets their own home screen
    if manager_flag:
        from repositories import ManagerRepository
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_telegram_id(callback.from_user.id)
        if mgr:
            from services import DealService
            deal_service = DealService()
            all_deals = deal_service.get_manager_deals(mgr.id)
            current = all_deals[0] if all_deals else None
            queued = len(all_deals) - 1 if len(all_deals) > 1 else 0
            status_online = 'Онлайн' if mgr.is_online else 'Офлайн'
            status_receive = 'Да' if mgr.can_receive_deals else 'Нет'
            # Build manager home panel buttons
            mgr_extra = []
            # Unified online toggle: controls both is_online and can_receive_deals
            online_text = 'Онлайн' if mgr.is_online else 'Офлайн'
            online_icon = CHECK if mgr.is_online else CROSS
            mgr_extra.append([{"text": online_text, "callback_data": f"mgr_toggle_online_{mgr.id}_{0 if mgr.is_online else 1}", "icon_custom_emoji_id": online_icon}])
            if mgr.is_online:
                mgr_extra.append([{"text": "Завершить смену", "callback_data": "mgr_shift_end", "icon_custom_emoji_id": CROSS}])
            else:
                mgr_extra.append([{"text": "Начать смену", "callback_data": "mgr_shift_start", "icon_custom_emoji_id": CHECK}])
            if current:
                rub = current.amount_usdt * current.client_rate
                mgr_extra.append([{"text": f"Текущая: {current.amount_usdt} USDT ({rub:.0f} ₽)", "callback_data": f"mgr_deal_{current.id}"}])
            else:
                mgr_extra.append([{"text": "Нет текущей сделки", "callback_data": "mgr_deals", "icon_custom_emoji_id": LOADING}])
            if queued:
                mgr_extra.append([{"text": f"Очередь: {queued} сделок", "callback_data": "mgr_deals", "icon_custom_emoji_id": DOWNLOAD}])
            else:
                mgr_extra.append([{"text": "Очередь пуста", "callback_data": "mgr_deals", "icon_custom_emoji_id": DOWNLOAD}])
            mgr_extra.append([{"text": "Курсы", "callback_data": "mgr_rates", "icon_custom_emoji_id": LINK}])
            mgr_extra.append([{"text": "История", "callback_data": "mgr_history", "icon_custom_emoji_id": BOX}])
            if admin_flag:
                mgr_extra.append([{"text": "Админка", "callback_data": "admin_menu", "icon_custom_emoji_id": SETTINGS}])
            await tpl.edit_template(
                callback, "manager.home",
                {"status_online": status_online, "status_receive": status_receive},
                extra_buttons=mgr_extra,
            )
            return

    await tpl.edit_template(
        callback, "main.greeting",
        {"name": user.full_name or "друг"},
        extra_buttons=extra,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    await state.clear()

    # Deep link: /start deal_{id}  → open deal details
    if command.args and command.args.startswith("deal_"):
        deal_id = command.args.replace("deal_", "")
        deal_service = DealService()
        deal = deal_service.deals.find_by_id(deal_id)
        if not deal:
            tmpl = tpl.get_template("common.error_deal_not_found", "ru")
            text = tpl.render_text(tmpl, {})
            await send_text(message, text, reply_markup=back_keyboard("home"))
            return

        # Access control: only deal participants or admins
        user_repo = UserRepository()
        user = user_repo.find_by_telegram_id(message.from_user.id)
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_telegram_id(message.from_user.id)

        is_participant = (user and user.id == deal.user_id) or (mgr and mgr.id == deal.manager_id)
        is_admin = message.from_user.id in ADMIN_IDS

        if not is_participant and not is_admin:
            tmpl = tpl.get_template("client.access_denied", "ru")
            text = tpl.render_text(tmpl, {})
            await send_text(message, 
                text,
                reply_markup=back_keyboard("home")
            )
            return

        is_client = user and user.id == deal.user_id
        is_manager = mgr and mgr.id == deal.manager_id
        is_admin = message.from_user.id in ADMIN_IDS
        is_privileged = is_manager or is_admin

        rub_amount = deal.amount_usdt * deal.client_rate
        status_ru = STATUS_RU.get(deal.status, deal.status)
        created_at = deal.created_at.strftime("%d.%m.%Y %H:%M UTC") if deal.created_at else "—"

        text = (
            f"{TAG_RECEIPT} <b>Сделка #{deal.id[:8]}</b>\n\n"
            f"{TAG_MONEY} Сумма: <b>{deal.amount_usdt} USDT</b>\n"
            f"{TAG_CHART} Курс: <b>{deal.client_rate} ₽/USDT</b>\n"
            f"{TAG_MONEY_SEND} К получению: <b>{rub_amount:.2f} ₽</b>\n"
            f"{TAG_PIN} Статус: <b>{status_ru}</b>\n"
            f"{TAG_CLOCK} Создана: <b>{created_at}</b>\n"
        )

        from bot.common import get_client_contact
        client_contact = get_client_contact(deal)
        if is_privileged:
            text += f"\n{TAG_PROFILE} Клиент: <b>{client_contact}</b>"

        mgr_repo = ManagerRepository()
        if deal.manager_id:
            mgr_deal = mgr_repo.find_by_id(deal.manager_id)
            if mgr_deal:
                mgr_contact = f"@{mgr_deal.username}" if mgr_deal.username else (mgr_deal.full_name or f"ID: {mgr_deal.telegram_id}")
                text += f"\n{TAG_PROFILE} Менеджер: <b>{mgr_contact}</b>"

        # Manager/Admin see profit — client does not
        if is_privileged and deal.profit:
            text += (
                f"\n{TAG_CHART} <b>Финансы</b>\n"
                f"Выручка: {deal.revenue:.2f} ₽\n"
                f"Себестоимость: {deal.cost:.2f} ₽\n"
                f"Прибыль: {deal.profit:.2f} ₽\n"
            )

        await send_text(message, 
            text,
            reply_markup=back_keyboard("home")
        )
        return

    user = await get_or_create_user(message)

    try:
        from twix_settings import get as settings_get
        tos_enabled = await settings_get("tos.enabled")
        if isinstance(tos_enabled, str):
            tos_enabled = tos_enabled.lower() in ("true", "1", "yes")
    except Exception:
        tos_enabled = True

    if tos_enabled and not user.tos_accepted:
        await state.set_state(ClientStates.accept_tos)
        tos_tmpl = tpl.get_template("main.tos", "ru")
        await tpl.send_template(message, "main.tos", {})
        return

    await _send_home(message, user)


@router.callback_query(ClientStates.accept_tos, F.data == "accept_tos")
async def cb_accept_tos(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if user:
        user.tos_accepted = True
        user_repo.update(user)

    await _edit_home(callback, user)


# ══════════════════════════════════════════════════════════════════════
#  HOME
# ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "home")
async def cb_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()

    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer("Пользователь не найден.", reply_markup=back_keyboard())
        return

    await _edit_home(callback, user)


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await cb_home(callback, state)


# ══════════════════════════════════════════════════════════════════════
#  CLIENT MENU
# ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "client_menu")
async def cb_client_menu(callback: CallbackQuery, state: FSMContext):
    """Legacy: redirect to profile (old menu merged into profile)."""
    await state.clear()
    await callback.answer()
    await cb_profile(callback)


# ══════════════════════════════════════════════════════════════════════
#  MY DEAL (текущая сделка клиента)
# ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_deal")
async def cb_my_deal(callback: CallbackQuery):
    await callback.answer()

    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user:
        await safe_edit_text(callback, "Пользователь не найден.", reply_markup=back_keyboard("home"))
        return

    deal_service = DealService()
    deal = deal_service.get_user_active_deal(user.id)

    if not deal:
        await tpl.edit_template(callback, "client.no_deal", {})
        return

    status_ru = STATUS_RU.get(deal.status, deal.status)
    rub_amount = deal.amount_usdt * deal.client_rate

    mgr_section = ""
    if deal.manager_id:
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_id(deal.manager_id)
        if mgr:
            mgr_contact = f"@{mgr.username}" if mgr.username else (mgr.full_name or f"ID: {mgr.telegram_id}")
            mgr_section = f"\n{TAG_PROFILE} Менеджер: <b>{mgr_contact}</b>"
    else:
        mgr_section = "\nОжидайте назначения менеджера..."

    created_at = deal.created_at.strftime("%d.%m.%Y %H:%M UTC") if deal.created_at else "—"
    await tpl.edit_template(
        callback, "client.my_deal",
        {
            "amount": str(deal.amount_usdt),
            "rate": str(deal.client_rate),
            "total": f"{rub_amount:.2f}",
            "status": status_ru,
            "manager_section": SafeHTML(mgr_section),
            "created_at": created_at,
        },
    )


@router.callback_query(F.data == "client_cancel_deal")
async def cb_client_cancel_deal(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user:
        await safe_edit_text(callback, "Пользователь не найден.", reply_markup=back_keyboard())
        return

    deal_service = DealService()
    deal = deal_service.get_user_active_deal(user.id)
    if not deal:
        await safe_edit_text(
            callback,
            f"{TAG_CROSS} У вас нет активной сделки.",
            reply_markup=back_keyboard()
        )
        return

    try:
        await deal_service.cancel_deal(deal.id, actor_id=user.id)
    except ValueError:
        pass

    tmpl = tpl.get_template("client.cancelled", "ru")
    text = tpl.render_text(tmpl, {})
    await safe_edit_text(
        callback,
        text,
        reply_markup=back_keyboard()
    )


# ══════════════════════════════════════════════════════════════════════
#  RATES
# ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "rates")
async def cb_rates(callback: CallbackQuery):
    await callback.answer()

    rate_service = RateService()
    tiers = rate_service.get_tiers()

    if not tiers:
        for t in DEFAULT_RATES:
            rate_service.create_tier(
                name=t["name"],
                min_amount=Decimal(t["min"]),
                max_amount=Decimal(t["max"]),
                rate=Decimal(t["rate"]),
            )
        tiers = rate_service.get_tiers()

    try:
        from twix_settings import get as settings_get
        min_amount = await settings_get("deals.min_amount")
        min_text = f"{min_amount}" if min_amount else "3000"
    except Exception:
        min_text = "3000"

    tmpl = tpl.get_template("client.rates", "ru")
    tiers_text = "\n".join([f"• {t.name} — {t.rate} ₽" for t in tiers])
    await tpl.edit_template(
        callback, "client.rates",
        {"tiers": SafeHTML(tiers_text), "min_amount": min_text},
    )


# ══════════════════════════════════════════════════════════════════════
#  SELL USDT FLOW
# ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "sell_usdt")
async def cb_sell_usdt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer("Пользователь не найден.", reply_markup=back_keyboard())
        return

    deal_service = DealService()
    existing = deal_service.get_user_active_deal(user.id)
    if existing:
        status_ru = STATUS_RU.get(existing.status, existing.status)
        rub_amount = existing.amount_usdt * existing.client_rate
        await tpl.edit_template(
            callback, "client.already_has_deal",
            {
                "amount": str(existing.amount_usdt),
                "rate": str(existing.client_rate),
                "total": f"{rub_amount:.2f}",
                "status": status_ru,
            },
        )
        return

    await state.set_state(ClientStates.enter_amount)

    await tpl.edit_template(callback, "client.sell_prompt", {})


@router.message(ClientStates.enter_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except Exception:
        await send_text(message, f"{TAG_CROSS} Введите корректное число. Пример: 250")
        return

    rate_service = RateService()
    tier = rate_service.get_rate_for_amount(amount)
    if not tier:
        await send_text(message, f"{TAG_CROSS} Нет доступного курса для этой суммы. Попробуйте другую.")
        return

    user = await get_or_create_user(message)
    client_rate = rate_service.apply_loyalty_bonus(
        tier.rate, user.total_volume, [(t['max'],t['rate']) for t in get_sync('loyalty.tiers')]
    )

    from twix_settings import get as settings_get
    rapira_price = await settings_get("rates.rapira_last_price")
    if rapira_price and Decimal(str(rapira_price)) > 0:
        internal_rate = Decimal(str(rapira_price)) * get_sync('rates.coefficient')
    else:
        internal_rate = client_rate / get_sync('rates.coefficient')
    rub_amount = amount * client_rate

    try:
        min_amount_setting = await settings_get("deals.min_amount")
        min_amount = Decimal(str(min_amount_setting)) if min_amount_setting else Decimal("3000")
    except Exception:
        min_amount = Decimal("3000")

    if rub_amount < min_amount:
        await send_text(message, 
            f"{TAG_CROSS} Минимальная сумма сделки — <b>{min_amount} ₽</b>.\n"
            f"Вы ввели {amount} USDT (≈ {rub_amount:.2f} ₽).\n"
            f"Введите бо́льшую сумму."
        )
        return

    await state.update_data(
        amount=str(amount),
        base_client_rate=str(client_rate),
        client_rate=str(client_rate),
        internal_rate=str(internal_rate),
        tier_id=tier.id,
        promocode_code="",
    )
    await state.set_state(ClientStates.enter_promocode)

    await send_text(message, 
        f"{TAG_GIFT} <b>Промокод</b>\n\n"
        f"Введите промокод для бонуса к курсу, или отправьте <code>-</code> для пропуска."
    )


@router.message(ClientStates.enter_promocode)
async def process_promocode(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    data = await state.get_data()
    amount = Decimal(data["amount"])
    base_rate = Decimal(data["base_client_rate"])

    if text == "-":
        final_rate = base_rate
        promo_info = ""
        await state.update_data(client_rate=str(final_rate), promocode_code="")
    else:
        pc_service = PromocodeService()
        pc = pc_service.validate(text.upper())
        if not pc:
            await send_text(message, 
                f"{TAG_CROSS} Промокод не найден или истёк.\n"
                f"Попробуйте другой или отправьте <code>-</code> для пропуска."
            )
            return
        final_rate, applied_pc = pc_service.apply(text.upper(), base_rate)
        promo_info = f"\n{TAG_CHECK} Промокод <b>{applied_pc.code}</b>: +{applied_pc.bonus_percent}% к курсу"
        await state.update_data(client_rate=str(final_rate), promocode_code=applied_pc.code)

    rub_amount = amount * final_rate
    await state.set_state(ClientStates.confirm_deal)

    tmpl = tpl.get_template("deal.confirm", "ru")
    render_data = {
        "amount": str(amount),
        "rate": str(final_rate),
        "total": f"{rub_amount:.2f}",
    }
    text = tpl.render_text(tmpl, render_data) + promo_info
    kb = tpl.build_keyboard(tmpl.get("buttons", []))
    await send_text(message, text, reply_markup=kb)


@router.callback_query(ClientStates.confirm_deal, F.data == "confirm_deal")
async def cb_confirm_deal(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    amount = Decimal(data["amount"])
    client_rate = Decimal(data["client_rate"])
    internal_rate = Decimal(data["internal_rate"])

    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user:
        await safe_edit_text(callback, "Пользователь не найден.", reply_markup=back_keyboard())
        await state.clear()
        return

    deal_service = DealService()

    try:
        deal = await deal_service.create_deal(
            user_id=user.id,
            amount_usdt=amount,
            client_rate=client_rate,
            internal_rate=internal_rate,
            actor_id=user.id,
            promocode_code=data.get("promocode_code") or None,
        )
    except ValueError as e:
        await safe_edit_text(callback, f"{TAG_CROSS} {e}", reply_markup=back_keyboard())
        await state.clear()
        return

    from services import QueueService
    queue_service = QueueService()
    new_mgr_id = await queue_service.distribute_new_deal(deal.id)
    if new_mgr_id:
        deal = await deal_service.assign_manager(deal.id, new_mgr_id)

    await state.clear()

    rub_amount = amount * client_rate
    mgr_contact = ""
    if deal and deal.manager_id:
        from bot.common import notify_manager_new_deal
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_id(deal.manager_id)
        print(f"[CLIENT_CONFIRM] deal={deal.id[:8]} mgr_id={deal.manager_id} mgr_obj={mgr}")
        if mgr:
            # Refresh manager username from Telegram if missing
            if not mgr.username:
                try:
                    chat = await callback.bot.get_chat(mgr.telegram_id)
                    if chat.username:
                        mgr.username = chat.username
                        mgr_repo.update(mgr)
                        print(f"[CLIENT_CONFIRM] refreshed mgr username -> @{mgr.username}")
                except Exception as e:
                    print(f"[CLIENT_CONFIRM] get_chat failed for mgr={mgr.id}: {e}")
                    pass
            try:
                await notify_manager_new_deal(callback.bot, mgr, deal)
                print(f"[CLIENT_CONFIRM] notify_manager_new_deal sent to mgr={mgr.telegram_id}")
            except Exception as e:
                print(f"[CLIENT_CONFIRM] notify_manager_new_deal FAILED: {e}")
                pass
        mgr_contact = f"@{mgr.username}" if mgr and mgr.username else (mgr.full_name if mgr and mgr.full_name else (f"ID: {mgr.telegram_id}" if mgr else "неизвестен"))
        tmpl = tpl.get_template("client.deal_created_with_manager", "ru")
        text = tpl.render_text(tmpl, {
            "amount": str(amount),
            "rate": str(client_rate),
            "total": f"{rub_amount:.2f}",
            "manager": mgr_contact,
        })
    else:
        tmpl = tpl.get_template("client.deal_created_no_manager", "ru")
        text = tpl.render_text(tmpl, {
            "amount": str(amount),
            "rate": str(client_rate),
            "total": f"{rub_amount:.2f}",
        })

    kb = tpl.build_keyboard(tmpl.get("buttons", []))
    await safe_edit_text(callback, text, reply_markup=kb)


@router.callback_query(ClientStates.confirm_deal, F.data == "cancel_deal")
async def cb_cancel_deal(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Сделка отменена")
    await state.clear()
    tmpl = tpl.get_template("client.cancelled", "ru")
    text = tpl.render_text(tmpl, {})
    kb = tpl.build_keyboard(tmpl.get("buttons", []))
    await safe_edit_text(callback, text, reply_markup=kb)


# ══════════════════════════════════════════════════════════════════════
#  PROFILE / HISTORY / TICKETS
# ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    await callback.answer()
    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer("Профиль не найден.", reply_markup=back_keyboard("home"))
        return

    from services import TicketService
    ticket_service = TicketService()
    ticket_count = ticket_service.get_ticket_count(user.id)

    from services import RateService
    rate_service = RateService()
    loyalty_bonus = rate_service.apply_loyalty_bonus(Decimal("0"), user.total_volume, [(t['max'],t['rate']) for t in get_sync('loyalty.tiers')])

    bonus_section = ""
    if loyalty_bonus > 0:
        bonus_section = f"\n{TAG_CHECK} Бонус лояльности: <b>+{loyalty_bonus} ₽</b> к курсу"

    from twix_settings import get as settings_get
    tickets_enabled = await settings_get("tickets.enabled")
    tickets_line = str(ticket_count)
    if not tickets_enabled:
        tickets_line = "отключены"

    tmpl = tpl.get_template("client.profile", "ru")
    text = tpl.render_text(tmpl, {
        "name": user.full_name or "Не указано",
        "volume": str(user.total_volume),
        "volume_rub": f"{user.total_volume_rub:.0f}",
        "deals": SafeHTML(str(user.deal_count)),
        "tickets": tickets_line,
        "bonus_section": bonus_section,
    })
    anon_icon = LOCK_CLOSED if user.is_anonymous else LOCK_OPEN
    anon_text = "Вкл" if user.is_anonymous else "Выкл"
    extra = [
        [{"text": "Мои сделки", "callback_data": "my_deals", "icon_custom_emoji_id": "5884479287171485878"}],
    ]
    if tickets_enabled:
        extra.append([{"text": "Тикеты", "callback_data": "tickets", "icon_custom_emoji_id": "6032644646587338669"}])
    extra.extend([
        [{"text": f"Анонимность: {anon_text}", "callback_data": "profile_toggle_anonymous", "icon_custom_emoji_id": anon_icon}],
        [{"text": "Назад", "callback_data": "home", "icon_custom_emoji_id": "5963103826075456248"}],
    ])
    await tpl.edit_template(
        callback, "client.profile",
        {
            "name": user.full_name or "Не указано",
            "volume": str(user.total_volume),
            "volume_rub": f"{user.total_volume_rub:.0f}",
            "deals": SafeHTML(str(user.deal_count)),
            "tickets": tickets_line,
            "bonus_section": bonus_section,
        },
        extra_buttons=extra,
    )


@router.callback_query(F.data == "profile_toggle_anonymous")
async def cb_profile_toggle_anonymous(callback: CallbackQuery):
    await callback.answer()
    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user:
        await safe_edit_text(callback, "Пользователь не найден.", reply_markup=back_keyboard("home"))
        return
    user.is_anonymous = not user.is_anonymous
    user_repo.update(user)
    status = "включена" if user.is_anonymous else "выключена"
    await safe_edit_text(
        callback,
        f"{TAG_CHECK} Анонимность {status}.",
        reply_markup=back_keyboard("home")
    )


# ── Deal status → Premium emoji icon for list buttons ──
_DEAL_STATUS_ICON = {
    "closed": "5870633910337015697",     # ✅ CHECK
    "cancelled": "5870657884844462243",  # ❌ CROSS
}
_DEFAULT_STATUS_ICON = "5983150113483134607"  # ⏰ CLOCK (created, queued, active, pinned)


@router.callback_query(F.data == "my_deals")
async def cb_my_deals(callback: CallbackQuery):
    await _show_my_deals(callback, page=0)


@router.callback_query(F.data.startswith("my_deals_page_"))
async def cb_my_deals_page(callback: CallbackQuery):
    page = int(callback.data.replace("my_deals_page_", ""))
    await _show_my_deals(callback, page=page)


async def _show_my_deals(callback: CallbackQuery, page: int = 0):
    import traceback
    try:
        await callback.answer()
        user_repo = UserRepository()
        user = user_repo.find_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.answer("Сделки недоступны.", reply_markup=back_keyboard("profile"))
            return

        deal_service = DealService()
        all_deals = deal_service.get_user_history(user.id)
        per_page = 10
        total = len(all_deals)
        start = page * per_page
        end = start + per_page
        deals = all_deals[start:end]

        extra = []
        for d in deals:
            icon = _DEAL_STATUS_ICON.get(d.status, _DEFAULT_STATUS_ICON)
            rub = d.amount_usdt * d.client_rate
            dt = d.created_at
            if dt:
                dt_str = dt.strftime("%d.%m %H:%M")
            else:
                dt_str = "--.-- --:--"
            extra.append([{
                "text": f"{dt_str} / {d.client_rate}₽ / {d.amount_usdt} USDT → {rub:.0f} ₽",
                "callback_data": f"client_deal_{d.id}",
                "icon_custom_emoji_id": icon,
            }])

        # Pagination
        nav = []
        if page > 0:
            nav.append({"text": "← Назад", "callback_data": f"my_deals_page_{page - 1}", "icon_custom_emoji_id": "5963103826075456248"})
        if end < total:
            nav.append({"text": "Вперёд →", "callback_data": f"my_deals_page_{page + 1}", "icon_custom_emoji_id": "5963103826075456248"})
        if nav:
            extra.append(nav)

        extra.append([{"text": "Назад", "callback_data": "profile", "icon_custom_emoji_id": "5963103826075456248"}])

        info = f"Всего: {total}   Страница {page + 1}/{(total // per_page) + (1 if total % per_page else 0)}" if total else "Нет сделок."
        await tpl.edit_template(
            callback, "client.my_deals",
            {"info": info},
            extra_buttons=extra,
        )
    except Exception as e:
        with open('/tmp/deals_debug.log', 'a') as f:
            f.write(f'[my_deals ERROR] {e}\n')
            f.write(traceback.format_exc())
            f.write('\n')
        raise


@router.callback_query(F.data.startswith("client_deal_"))
async def cb_client_deal_detail(callback: CallbackQuery):
    await callback.answer()
    deal_id = callback.data.replace("client_deal_", "")
    deal_service = DealService()
    deal = deal_service.deals.find_by_id(deal_id)
    if not deal:
        await callback.message.answer("Сделка не найдена.", reply_markup=back_keyboard("my_deals"))
        return

    # Access control
    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user or user.id != deal.user_id:
        await callback.message.answer("Нет доступа.", reply_markup=back_keyboard("my_deals"))
        return

    status_ru = STATUS_RU.get(deal.status, deal.status)
    rub_amount = deal.amount_usdt * deal.client_rate

    mgr_section = ""
    if deal.manager_id:
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_id(deal.manager_id)
        if mgr:
            mgr_contact = f"@{mgr.username}" if mgr.username else (mgr.full_name or f"ID: {mgr.telegram_id}")
            mgr_section = f"\n{TAG_PROFILE} Менеджер: <b>{mgr_contact}</b>"

    created_at = deal.created_at.strftime("%d.%m.%Y %H:%M UTC") if deal.created_at else "—"
    await tpl.edit_template(
        callback, "client.deal_detail_client",
        {
            "deal_id_short": deal.id[:8],
            "amount": str(deal.amount_usdt),
            "rate": str(deal.client_rate),
            "total": f"{rub_amount:.2f}",
            "status": status_ru,
            "manager_section": SafeHTML(mgr_section),
            "created_at": created_at,
        },
    )


@router.callback_query(F.data == "tickets")
async def cb_tickets(callback: CallbackQuery):
    await callback.answer()
    from twix_settings import get as settings_get
    tickets_enabled = await settings_get("tickets.enabled")
    if not tickets_enabled:
        await tpl.edit_template(callback, "client.tickets_disabled", {})
        return

    user_repo = UserRepository()
    user = user_repo.find_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer("Тикеты недоступны.", reply_markup=back_keyboard("profile"))
        return

    from services import TicketService
    ticket_service = TicketService()
    count = ticket_service.get_ticket_count(user.id)

    threshold = Decimal("2000")
    rub_volume = user.total_volume_rub
    progress = rub_volume % threshold
    next_needed = threshold - progress

    # Graphical progress bar — лавовая лампа стиль
    total_blocks = 10
    filled = int((progress / threshold) * total_blocks)
    filled = min(filled, total_blocks)
    empty = total_blocks - filled
    bar = "".join([TAG_LAVA for _ in range(filled)]) + "·" * empty

    await tpl.edit_template(
        callback, "client.tickets",
        {
            "count": str(count),
            "progress_bar": bar,
            "progress": f"{progress:.0f}",
            "next_needed": f"{next_needed:.0f}",
        },
    )


# ══════════════════════════════════════════════════════════════════════
#  ERROR HANDLER
# ══════════════════════════════════════════════════════════════════════

@router.errors()
async def handle_error(event):
    print(f"[Client error] {event.exception}")
