from __future__ import annotations
from presentation import send_text, send_chat
"""Business message middleware for Telegram Business support.

Processes manager commands directly in business chat (client↔manager).
After each command:
1. Deletes the original command message
2. Sends a result message (no profit/revenue/cost shown to client)
3. Adds a deep-link button to open the deal inside TWIX bot.
"""

import re
from decimal import Decimal

from aiogram import BaseMiddleware
from aiogram.types import Update, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.deep_linking import create_start_link

from bot.emoji import (
    TAG_CHECK, TAG_CROSS, TAG_BELL, TAG_PIN, TAG_LOADING,
)


class BusinessCommandMiddleware(BaseMiddleware):
    """Intercept business messages and process manager commands inline."""

    async def __call__(self, handler, event: Update, data: dict):
        raw = event.model_dump(exclude_none=True)
        bus_msg = raw.get("business_message")

        if not bus_msg or not bus_msg.get("text"):
            return await handler(event, data)

        text = bus_msg["text"].strip()
        user_id = bus_msg.get("from_user", {}).get("id")
        chat_id = bus_msg.get("chat", {}).get("id")
        conn_id = bus_msg.get("business_connection_id")

        # Check if sender is a manager
        from repositories import ManagerRepository
        mgr_repo = ManagerRepository()
        mgr = mgr_repo.find_by_telegram_id(user_id)
        if not mgr or mgr.deleted_at is not None:
            return await handler(event, data)

        bot = data.get("bot")
        if not bot or not chat_id:
            return await handler(event, data)

        async def _reply(msg_text: str, deal_id: str | None = None):
            """Send text + optional deep-link button to open deal in TWIX bot."""
            try:
                kw = {"business_connection_id": conn_id} if conn_id else {}
                if deal_id:
                    link = await create_start_link(bot, f"deal_{deal_id}", encode=False)
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Открыть в TWIX", url=link)]
                    ])
                    kw["reply_markup"] = kb
                await send_chat(bot, chat_id, msg_text, **kw)
            except Exception:
                pass

        async def _delete_cmd():
            """Try to delete the original command message."""
            try:
                if event.business_message:
                    await event.business_message.delete()
            except Exception:
                pass

        from services import DealService, RateService
        from bot.common import post_service_channel
        from models import User
        from repositories import UserRepository, DealRepository

        def _get_current_deal(mgr_id: int, chat_tg_id: int):
            """Return the open deal for this client in the current business chat."""
            user_repo = UserRepository()
            user = user_repo.find_by_telegram_id(chat_tg_id)
            if user:
                deal_repo = DealRepository()
                deal = deal_repo.find_open_by_user(user.id)
                if deal and deal.manager_id == mgr_id:
                    return deal
            return None

        # ── +cr / +create ──
        match = re.match(r"^\+(cr|create)\s+(\d+(\.\d+)?)(?:\s+usdt)?(?:\s+(\d+(\.\d+)?))?$", text, re.IGNORECASE)
        if match:
            amount = Decimal(match.group(2))
            rate_service = RateService()

            custom_rate_str = match.group(4)
            if custom_rate_str:
                client_rate = Decimal(custom_rate_str)
            else:
                tier = rate_service.get_rate_for_amount(amount)
                if not tier:
                    await _reply(f"{TAG_CROSS} Нет курса для этой суммы.")
                    await _delete_cmd()
                    return
                client_rate = tier.rate

            from twix_settings import get as settings_get
            rapira_price = await settings_get("rates.rapira_last_price")
            if rapira_price and Decimal(str(rapira_price)) > 0:
                internal_rate = Decimal(str(rapira_price)) * (await settings_get('rates.coefficient'))
            else:
                internal_rate = client_rate / (await settings_get('rates.coefficient'))

            # Resolve target client: reply_to takes priority, then chat.id (private = client)
            target_user_id = None
            reply_to = bus_msg.get("reply_to_message")
            if reply_to:
                from_user = reply_to.get("from_user", {})
                reply_tg_id = from_user.get("id")
                if reply_tg_id:
                    user_repo = UserRepository()
                    reply_user = user_repo.find_by_telegram_id(reply_tg_id)
                    if not reply_user:
                        reply_user = user_repo.create(
                            User(
                                telegram_id=reply_tg_id,
                                username=from_user.get("username"),
                                full_name=from_user.get("full_name"),
                            )
                        )
                    target_user_id = reply_user.id

            # Fallback: in a private business chat, chat.id IS the client’s Telegram ID
            if not target_user_id and event.business_message and event.business_message.chat:
                chat = event.business_message.chat
                if getattr(chat, "type", None) == "private":
                    client_tg_id = chat.id
                    user_repo = UserRepository()
                    client_user = user_repo.find_by_telegram_id(client_tg_id)
                    if not client_user:
                        client_user = user_repo.create(
                            User(
                                telegram_id=client_tg_id,
                                username=getattr(chat, "username", None),
                                full_name=getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(client_tg_id),
                            )
                        )
                    target_user_id = client_user.id

            if not target_user_id:
                await _reply(f"{TAG_CROSS} Нужно ответить на сообщение клиента.")
                await _delete_cmd()
                return

            deal_service = DealService()
            try:
                deal = await deal_service.create_deal(
                    user_id=target_user_id,
                    amount_usdt=amount,
                    client_rate=client_rate,
                    internal_rate=internal_rate,
                    manager_id=mgr.id,
                    actor_id=mgr.id,
                )
                rub = amount * client_rate
                await _reply(
                    f"{TAG_CHECK} Сделка создана: {amount} USDT ({rub:.0f} ₽)",
                    deal_id=deal.id,
                )
                # Notify client in bot
                try:
                    from bot.common import notify_user_deal_assigned
                    await notify_user_deal_assigned(bot, deal)
                    print(f"[BUSINESS +cr] notified client user_id={target_user_id} deal={deal.id[:8]} mgr={deal.manager_id}")
                except Exception as e:
                    print(f"[BUSINESS +cr] notify_user_deal_assigned failed: {e}")
                    pass
            except ValueError as e:
                err_msg = str(e)
                if "already has an open deal" in err_msg.lower():
                    await _reply(f"{TAG_CROSS} У клиента уже есть открытая сделка.")
                else:
                    await _reply(f"{TAG_CROSS} {e}")
            await _delete_cmd()
            return

        # ── -d / -done ──
        d_match = re.match(r"^-(d|done)(?:\s+(\d+(?:\.\d+)?))?$", text, re.IGNORECASE)
        if d_match:
            deal_service = DealService()
            deal = _get_current_deal(mgr.id, chat_id)
            if not deal:
                await _reply(f"{TAG_CROSS} Нет активных сделок с этим клиентом.")
                await _delete_cmd()
                return
            actual_amount = None
            if d_match.group(2):
                actual_amount = Decimal(d_match.group(2))
            closed = await deal_service.close_deal(deal.id, actor_id=mgr.id, actual_amount=actual_amount)
            await post_service_channel(bot, closed)
            # Notify client
            try:
                from bot.common import notify_user_deal_status
                await notify_user_deal_status(bot, closed, "closed")
            except Exception:
                pass
            rub = closed.amount_usdt * closed.client_rate
            # NO profit/revenue/cost in business chat — client sees this too
            await _reply(
                f"{TAG_CHECK} Сделка #{closed.id[:8]} завершена!\n"
                f"Сумма: {closed.amount_usdt} USDT ({rub:.0f} ₽)\n"
                f"К получению: {rub:.2f} ₽ ({closed.amount_usdt} USDT)",
                deal_id=closed.id,
            )
            await _delete_cmd()
            return

        # ── -c / -cancel ──
        if re.match(r"^-(c|cancel)$", text, re.IGNORECASE):
            deal_service = DealService()
            deal = _get_current_deal(mgr.id, chat_id)
            if not deal:
                await _reply(f"{TAG_CROSS} Нет активных сделок с этим клиентом.")
                await _delete_cmd()
                return
            await deal_service.cancel_deal(deal.id, actor_id=mgr.id)
            # Notify client
            try:
                from bot.common import notify_user_deal_status
                await notify_user_deal_status(bot, deal, "cancelled")
            except Exception:
                pass
            await _reply(f"{TAG_CROSS} Сделка отменена.")
            await _delete_cmd()
            return

        # ── -r / -remind ──
        if re.match(r"^-(r|remind)$", text, re.IGNORECASE):
            deal_service = DealService()
            deal = _get_current_deal(mgr.id, chat_id)
            if not deal:
                await _reply(f"{TAG_CROSS} Нет активных сделок с этим клиентом.")
                await _delete_cmd()
                return
            try:
                user_repo = UserRepository()
                deal_user = user_repo.find_by_id(deal.user_id)
                if deal_user:
                    await send_chat(bot, 
                        deal_user.telegram_id,
                        f"Напоминание от менеджера по сделке #{deal.id[:8]}: пожалуйста, свяжитесь для завершения."
                    )
                await _reply(
                    f"{TAG_BELL} Напоминание отправлено клиенту.",
                    deal_id=deal.id,
                )
            except Exception as e:
                await _reply(f"{TAG_CROSS} Не удалось отправить: {e}")
            await _delete_cmd()
            return

        # ── +p / +pin ──
        if re.match(r"^\+(p|pin)$", text, re.IGNORECASE):
            deal_service = DealService()
            deal = _get_current_deal(mgr.id, chat_id)
            if not deal:
                await _reply(f"{TAG_CROSS} Нет активных сделок с этим клиентом.")
                await _delete_cmd()
                return
            await deal_service.pin_deal(deal.id, actor_id=mgr.id)
            await _reply(
                f"{TAG_PIN} Сделка закреплена.",
                deal_id=deal.id,
            )
            await _delete_cmd()
            return

        # ── -u / -unpin ──
        if re.match(r"^-(u|unpin)$", text, re.IGNORECASE):
            deal_service = DealService()
            deal = _get_current_deal(mgr.id, chat_id)
            if not deal or deal.status != "pinned":
                await _reply(f"{TAG_CROSS} Нет закреплённых сделок с этим клиентом.")
                await _delete_cmd()
                return
            await deal_service.unpin_deal(deal.id, actor_id=mgr.id)
            await _reply(
                f"{TAG_PIN} Сделка откреплена.",
                deal_id=deal.id,
            )
            await _delete_cmd()
            return

        # ── -transfer ──
        if re.match(r"^-transfer$", text, re.IGNORECASE):
            from services import QueueService
            deal_service = DealService()
            queue_service = QueueService()
            deal = _get_current_deal(mgr.id, chat_id)
            if not deal:
                await _reply(f"{TAG_CROSS} Нет активных сделок с этим клиентом.")
                await _delete_cmd()
                return
            try:
                updated = await deal_service.transfer_deal(deal.id, actor_id=mgr.id, queue_service=queue_service)
                print(f"[BUSINESS_TRANSFER] deal={deal.id[:8]} new_mgr={updated.manager_id if updated else None}")
                # Notify new manager and client if reassigned to someone else
                if updated and updated.manager_id and updated.manager_id != mgr.id:
                    from bot.common import notify_manager_new_deal, notify_user_deal_assigned
                    new_mgr = ManagerRepository().find_by_id(updated.manager_id)
                    if new_mgr:
                        try:
                            await notify_manager_new_deal(bot, new_mgr, updated)
                            print(f"[BUSINESS_TRANSFER] notified new_mgr={new_mgr.telegram_id}")
                        except Exception as e:
                            print(f"[BUSINESS_TRANSFER] notify manager failed: {e}")
                            pass
                    try:
                        await notify_user_deal_assigned(bot, updated)
                        print(f"[BUSINESS_TRANSFER] notified client user_id={updated.user_id}")
                    except Exception as e:
                        print(f"[BUSINESS_TRANSFER] notify client failed: {e}")
                        pass
                await _reply(
                    f"{TAG_LOADING} Сделка передана в общую очередь.",
                    deal_id=deal.id,
                )
            except ValueError as e:
                await _reply(f"{TAG_CROSS} {e}")
            await _delete_cmd()
            return

        return await handler(event, data)
