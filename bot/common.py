from __future__ import annotations
from presentation import send_text, send_chat
"""TWIX Bot — common utilities and middleware."""

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import BaseFilter

import presentation as tpl
from database import init_db
from repositories import UserRepository, ManagerRepository
from models import User, Manager


class IsAdmin(BaseFilter):
    """Filter for admin users."""

    def __init__(self, admin_ids: list[int]):
        self.admin_ids = admin_ids

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id if event.from_user else None
        return user_id in self.admin_ids


class IsManager(BaseFilter):
    """Filter for registered managers."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return False
        repo = ManagerRepository()
        mgr = repo.find_by_telegram_id(user_id)
        return mgr is not None and mgr.deleted_at is None


async def get_or_create_user(message: Message) -> User:
    """Get existing user or create new one from Telegram message."""
    repo = UserRepository()
    user = repo.find_by_telegram_id(message.from_user.id)
    if user:
        # Update username/full_name if changed
        if user.username != message.from_user.username or user.full_name != message.from_user.full_name:
            user.username = message.from_user.username
            user.full_name = message.from_user.full_name
            repo.update(user)
        return user

    new_user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    return repo.create(new_user)


async def get_manager(event: Message | CallbackQuery) -> Manager | None:
    """Get manager by telegram ID from Message or CallbackQuery."""
    user_id = event.from_user.id if event.from_user else None
    if not user_id:
        return None
    repo = ManagerRepository()
    return repo.find_by_telegram_id(user_id)


def format_amount(amount) -> str:
    """Format Decimal for display."""
    from decimal import Decimal
    d = Decimal(str(amount))
    return f"{d:.2f}"


def get_client_contact(deal) -> str:
    """Return client contact string (@username or ID:tg_id) from deal snapshot or DB fallback."""
    if deal.user_username:
        return f"@{deal.user_username}"
    if deal.user_telegram_id:
        return f"ID:{deal.user_telegram_id}"
    # Fallback to DB lookup
    user_repo = UserRepository()
    user = user_repo.find_by_id(deal.user_id)
    if user:
        if user.username:
            return f"@{user.username}"
        return f"ID:{user.telegram_id}"
    return "неизвестен"


async def post_service_channel(bot: Bot, deal):
    """Post deal completion to service channel if not anonymous."""
    from twix_settings import get
    channel_id = await get("system.channel_id")
    if not channel_id:
        return
    from repositories import UserRepository
    user_repo = UserRepository()
    user = user_repo.find_by_id(deal.user_id)
    if user and user.is_anonymous:
        return
    name = "Аноним"
    if user:
        name = user.username or user.full_name or "Аноним"
    me = await bot.get_me()
    bot_username = f"@{me.username}" if me.username else ""
    tmpl = tpl.get_template("service.channel_post", "ru")
    text = tpl.render_text(tmpl, {
        "amount": str(deal.amount_usdt),
        "rate": str(deal.client_rate),
        "name": name,
        "bot_username": bot_username,
    })
    try:
        await send_chat(bot, int(channel_id), text)
    except Exception:
        pass


async def notify_user_deal_status(bot: Bot, deal, status: str):
    """Notify client in bot about deal status change (closed/cancelled)."""
    from repositories import UserRepository
    from bot.emoji import TAG_CHECK, TAG_CROSS, TAG_RECEIPT, TAG_MONEY, TAG_MONEY_SEND
    user_repo = UserRepository()
    user = user_repo.find_by_id(deal.user_id)
    if not user:
        return
    if status == "closed":
        rub = deal.amount_usdt * deal.client_rate
        text = (
            f"{TAG_CHECK} <b>Сделка #{deal.id[:8]} завершена!</b>\n\n"
            f"{TAG_MONEY} Сумма: <b>{deal.amount_usdt} USDT</b>\n"
            f"К получению: <b>{rub:.2f} ₽</b>\n\n"
            f"Спасибо за использование TWIX."
        )
    elif status == "cancelled":
        text = (
            f"{TAG_CROSS} <b>Сделка #{deal.id[:8]} отменена</b>\n\n"
            f"Вы можете создать новую сделку в любое время."
        )
    else:
        text = f"{TAG_RECEIPT} Сделка #{deal.id[:8]}: статус изменён на {status}."
    try:
        await send_chat(bot, user.telegram_id, text)
    except Exception:
        pass


async def notify_user_deal_assigned(bot: Bot, deal):
    """Notify client that a manager has been assigned to their deal."""
    from repositories import UserRepository, ManagerRepository
    from bot.emoji import TAG_BELL, TAG_PROFILE, TAG_MONEY, TAG_CHART
    user_repo = UserRepository()
    user = user_repo.find_by_id(deal.user_id)
    if not user:
        return
    mgr_repo = ManagerRepository()
    mgr = mgr_repo.find_by_id(deal.manager_id) if deal.manager_id else None
    # Refresh manager username from Telegram if missing
    if mgr and not mgr.username:
        try:
            chat = await bot.get_chat(mgr.telegram_id)
            if chat.username:
                mgr.username = chat.username
                mgr_repo.update(mgr)
                print(f"[NOTIFY_ASSIGNED] refreshed mgr={mgr.id} username -> @{mgr.username}")
        except Exception as e:
            print(f"[NOTIFY_ASSIGNED] get_chat failed for mgr={mgr.id} tg={mgr.telegram_id}: {e}")
            pass
    mgr_contact = ""
    if mgr:
        mgr_contact = f"@{mgr.username}" if mgr.username else (mgr.full_name or f"ID {mgr.telegram_id}")
    rub = deal.amount_usdt * deal.client_rate
    text = (
        f"{TAG_BELL} <b>Менеджер назначен!</b>\n\n"
        f"{TAG_MONEY} Сумма: <b>{deal.amount_usdt} USDT</b>\n"
        f"{TAG_CHART} Курс: <b>{deal.client_rate} ₽</b>\n"
        f"К получению: <b>{rub:.2f} ₽</b>\n\n"
    )
    if mgr_contact:
        text += f"{TAG_PROFILE} Ваш менеджер: <b>{mgr_contact}</b>\nНапишите ему для проведения сделки."
    else:
        text += "Ожидайте, менеджер скоро свяжется с вами."
    try:
        await send_chat(bot, user.telegram_id, text)
        print(f"[NOTIFY_ASSIGNED] sent to user={user.telegram_id} mgr_contact={mgr_contact}")
    except Exception as e:
        print(f"[NOTIFY_ASSIGNED] send_message failed to user={user.telegram_id}: {e}")
        pass


from presentation import safe_edit_text


async def notify_manager_new_deal(bot: Bot, manager: Manager, deal):
    """Notify manager in bot about a new assigned deal."""
    from bot.emoji import TAG_BELL, TAG_MONEY, TAG_CHART, TAG_MONEY_SEND, TAG_PROFILE
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from repositories import UserRepository
    rub = deal.amount_usdt * deal.client_rate
    user_repo = UserRepository()
    user = user_repo.find_by_id(deal.user_id)
    client_contact = ""
    if user:
        if user.username:
            client_contact = f"@{user.username}"
        else:
            client_contact = f"ID:{user.telegram_id}"
    text = (
        f"{TAG_BELL} <b>Новая сделка!</b>\n\n"
        f"{TAG_MONEY} Сумма: <b>{deal.amount_usdt} USDT</b>\n"
        f"{TAG_CHART} Курс: <b>{deal.client_rate} ₽</b>\n"
        f"{TAG_MONEY_SEND} К получению: <b>{rub:.2f} ₽</b>\n"
    )
    if client_contact:
        text += f"{TAG_PROFILE} Клиент: <b>{client_contact}</b>\n"
    print(f"[NOTIFY_MGR] mgr_id={manager.id} tg={manager.telegram_id} deal={deal.id[:8]} client={client_contact}")
    try:
        from aiogram.utils.deep_linking import create_start_link
        link = await create_start_link(bot, f"deal_{deal.id}", encode=False)
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="Открыть в TWIX", url=link))
        await send_chat(bot, manager.telegram_id, text, reply_markup=kb.as_markup())
        print(f"[NOTIFY_MGR] sent with deep-link to mgr={manager.telegram_id}")
    except Exception as e:
        print(f"[NOTIFY_MGR] deep-link failed ({e}), fallback plain text")
        # Fallback without deep-link button
        try:
            await send_chat(bot, manager.telegram_id, text)
            print(f"[NOTIFY_MGR] sent plain text to mgr={manager.telegram_id}")
        except Exception as e2:
            print(f"[NOTIFY_MGR] plain text also failed: {e2}")
            pass
