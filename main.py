"""TWIX entry point; unified settings/templates and separate invoice payments."""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from decimal import Decimal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import ADMIN_IDS, BOT_TOKEN, DATA_DIR, DB_PATH, DEFAULT_RATES
from database import init_db
from presentation import set_default_bot
from twix_runtime import configure, runtime

log=logging.getLogger(__name__)


def setup_tpl():
    return configure()


def setup_settings():
    return runtime().settings


def create_dispatcher():
    from bot import client,manager,admin
    from bot.business_middleware import BusinessCommandMiddleware
    from bot.configuration import create_router
    from bot.payment_invoices import router as payment_router
    dp=Dispatcher()
    dp.update.outer_middleware(BusinessCommandMiddleware())
    # Unified config/payment handlers precede business FSM handlers.
    dp.include_router(create_router())
    dp.include_router(payment_router)
    dp.include_router(client.router)
    dp.include_router(manager.router)
    dp.include_router(admin.router)
    return dp


async def backup_loop():
    import sqlite3
    while True:
        directory=DATA_DIR/'backups';directory.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        if runtime().settings.get('backup.enabled'):
            for label,path in [('twix',DB_PATH),('runtime',DATA_DIR/'runtime.sqlite'),('payments',DATA_DIR/'payments.sqlite')]:
                if not path.exists():continue
                source=sqlite3.connect(str(path));target=sqlite3.connect(str(directory/f'{label}-{stamp}.sqlite'))
                try:source.backup(target)
                finally:source.close();target.close()
        await asyncio.sleep(86400)


async def auto_cancel_loop(bot):
    from services import DealService, QueueService
    while True:
        try:
            from twix_settings import get
            service=DealService()
            cancelled=await QueueService().auto_cancel_expired(int(await get('timers.auto_cancel')),service)
            from repositories import UserRepository
            from tg_templates import Template
            for deal in cancelled:
                user=UserRepository().find_by_id(deal.user_id)
                if user:
                    try:await runtime().ui.send(user.telegram_id,Template('Сделка <code>{id}</code> автоматически отменена из-за неактивности'),{'id':deal.id[:8]})
                    except Exception:log.exception('Auto-cancel notification failed')
        except asyncio.CancelledError:raise
        except Exception:log.exception('auto_cancel iteration failed')
        await asyncio.sleep(60)


async def setup_rapira():
    """Seed baseline at startup/on-enable so disabled-period drift is not applied."""
    from twix_settings import get,set,on_change
    from rapira import RapiraClient
    async def seed():
        try:
            price=await asyncio.to_thread(RapiraClient().get_current_price,'USDT/RUB')
            if price is not None:
                await set('rates.rapira_last_price',str(price))
                await set('rates.rapira_baseline',str(price))
        except asyncio.CancelledError:raise
        except Exception:log.exception('Rapira baseline initialization failed')
    async def changed(key,old,new):
        if key=='rates.rapira_enabled' and new is True:await seed()
    on_change(changed)
    if await get('rates.rapira_enabled'):await seed()


async def rapira_poll_loop():
    from twix_settings import get,set
    from rapira import RapiraClient
    from services import RateService
    while True:
        try:
            if await get('rates.rapira_enabled'):
                price=await asyncio.to_thread(RapiraClient().get_current_price,'USDT/RUB')
                if price is not None:
                    await set('rates.rapira_last_price',str(price))
                    mode=await get('rates.mode')
                    baseline=await get('rates.rapira_baseline')
                    if mode=='rapira_percent':
                        RateService().recalculate_tiers_from_rapira(price)
                    elif await get('rates.auto_shift') and baseline>0:
                        delta=(price-baseline).quantize(Decimal('0.01'))
                        if delta:RateService().shift_all_rates(delta)
                    await set('rates.rapira_baseline',str(price))
            interval=int(await get('rates.rapira_poll_interval'))
        except asyncio.CancelledError:raise
        except Exception:
            log.exception('rapira iteration failed');interval=300
        await asyncio.sleep(max(5,interval))


async def reminder_loop(bot):
    from repositories import DealRepository,UserRepository,ManagerRepository
    from tg_templates import Template
    while True:
        try:
            interval=runtime().settings.get('timers.reminder_interval')
            now=datetime.now(timezone.utc)
            for deal in DealRepository().list_open():
                if deal.status not in ('created','queued') or not deal.created_at:continue
                age=(now-deal.created_at).total_seconds()
                if interval<=age<interval+60:
                    user=UserRepository().find_by_id(deal.user_id)
                    manager=ManagerRepository().find_by_id(deal.manager_id) if deal.manager_id else None
                    for recipient in [user,manager]:
                        if recipient:
                            await runtime().ui.send(recipient.telegram_id,Template('Напоминание: сделка <code>{id}</code> ожидает обработки'),{'id':deal.id[:8]})
        except asyncio.CancelledError:raise
        except Exception:log.exception('reminder iteration failed')
        await asyncio.sleep(60)


async def main():
    if not BOT_TOKEN:raise RuntimeError('BOT_TOKEN required')
    init_db()
    from repositories import RateRepository
    from models import Rate
    from decimal import Decimal
    repo=RateRepository()
    if not repo.list_active():
        for rate in DEFAULT_RATES:
            repo.create(Rate(name=rate['name'],min_amount=Decimal(rate['min']),max_amount=Decimal(rate['max']),rate=Decimal(rate['rate']),is_active=True))
    setup_tpl()
    bot=Bot(BOT_TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    set_default_bot(bot)
    from payment_service import configure_payments,payment_loop
    tasks=[]
    invoice_service=None
    try:
        invoice_service=configure_payments()
        await setup_rapira()
        tasks=[asyncio.create_task(auto_cancel_loop(bot)),asyncio.create_task(rapira_poll_loop()),asyncio.create_task(reminder_loop(bot)),asyncio.create_task(backup_loop()),asyncio.create_task(payment_loop())]
        await create_dispatcher().start_polling(bot,allowed_updates=['message','callback_query','business_message'])
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        try:
            await bot.session.close()
        finally:
            try:
                if invoice_service is not None:
                    try:invoice_service.db.close()
                    finally:invoice_service.payments.store.close()
            finally:runtime().close()


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
