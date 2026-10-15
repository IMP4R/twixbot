from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from tg_payments import CryptoPayProvider, XRocketProvider, Payments, Money, SQLiteStore, Status, PaymentError
from tg_templates import Button, Template
from twix_runtime import runtime

log=logging.getLogger(__name__)
_service=None


class InvoiceService:
    """Separate invoices, never implicitly close USDT deals or credit balances."""
    def __init__(self,payments,db_path,*,manager_lookup,user_lookup):
        self.payments=payments
        self.managers,self.users=manager_lookup,user_lookup
        self.db=sqlite3.connect(str(db_path))
        self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS manager_invoices(id TEXT PRIMARY KEY, manager_tg INTEGER NOT NULL, client_tg INTEGER NOT NULL, amount TEXT NOT NULL, currency TEXT NOT NULL, description TEXT NOT NULL, provider TEXT NOT NULL, created_at TEXT NOT NULL, sent_message INTEGER, manager_notified INTEGER DEFAULT 0, client_notified INTEGER DEFAULT 0, deleted_at TEXT)')
        self.db.commit()
        self._delivery_locks={}
        self._notify_lock=asyncio.Lock()

    def require_manager(self,actor):
        manager=self.managers(actor)
        if not manager:raise PermissionError('Только действующий менеджер может создавать счета')
        return manager

    async def create(self,actor,client_tg,amount,description,*,request_id=None,expected_currency=None,expected_provider=None):
        self.require_manager(actor)
        settings=runtime().settings
        if not settings.get('payments.enabled'):raise ValueError('Оплата отключена администратором')
        if not self.users(client_tg):raise ValueError('Клиент должен сначала запустить бота')
        if not isinstance(amount,Decimal) or not amount.is_finite() or amount<=0 or amount>settings.get('payments.max_amount'):raise ValueError('Недопустимая сумма счета')
        if not description.strip() or len(description)>400:raise ValueError('Описание: от 1 до 400 символов')
        provider=settings.get('payments.provider');currency=settings.get('payments.currency')
        if (expected_currency is not None and currency!=expected_currency) or (expected_provider is not None and provider!=expected_provider):
            raise ValueError('Настройки оплаты изменились. Начните новый черновик счета и подтвердите валюту/провайдера заново')
        if provider not in self.payments.providers:raise ValueError('Для провайдера не задан токен. Обратитесь к администратору')
        configured_provider=self.payments.providers[provider]
        if isinstance(configured_provider,CryptoPayProvider):
            actual_testnet=configured_provider.base=='https://testnet-pay.crypt.bot/api'
            if actual_testnet!=settings.get('payments.testnet'):
                raise ValueError('Режим testnet изменен. Нужен контролируемый перезапуск до создания счетов')
        key=request_id or str(uuid.uuid4())
        with self.db:
            existing=self.db.execute('SELECT * FROM manager_invoices WHERE id=?',(key,)).fetchone()
            if existing:
                if (existing['manager_tg'],existing['client_tg'],Decimal(existing['amount']),existing['description'],existing['provider'],existing['currency'])!=(actor,client_tg,amount,description,provider,currency):raise ValueError('Конфликт повторного счета')
            else:
                self.db.execute('INSERT INTO manager_invoices(id,manager_tg,client_tg,amount,currency,description,provider,created_at) VALUES(?,?,?,?,?,?,?,?)',(key,actor,client_tg,str(amount),currency,description,provider,datetime.now(timezone.utc).isoformat()))
        invoice=await self.payments.create(provider,Money(amount,currency),idempotency_key=key)
        return key,invoice

    def record(self,key,actor):
        row=self.db.execute('SELECT * FROM manager_invoices WHERE id=? AND deleted_at IS NULL',(key,)).fetchone()
        if row is None or actor not in {row['manager_tg'],row['client_tg']}:raise PermissionError('Счет недоступен')
        if actor==row['manager_tg']:self.require_manager(actor)
        return row

    def screen(self,key,row,invoice):
        buttons=[]
        if invoice.status==Status.PENDING:
            buttons.append((Button('Оплатить',url=invoice.pay_url,style='success'),))
            buttons.append((Button('Проверить оплату',callback_data=f'pay_check:{key}'),))
        return Template('<b>Счет на оплату</b>\n{description}\n\nСумма: <b>{amount} {currency}</b>\nСтатус: {status}\nНомер: <code>{key}</code>',buttons=tuple(buttons)),{'description':row['description'],'amount':invoice.money.amount,'currency':invoice.money.currency,'status':invoice.status.value,'key':key}

    async def deliver(self,key,actor):
        async with self._delivery_locks.setdefault(key,asyncio.Lock()):
            return await self._deliver(key,actor)

    async def _deliver(self,key,actor):
        row=self.record(key,actor)
        if actor!=row['manager_tg']:raise PermissionError('Только автор счета может повторить доставку')
        invoice=self.payments.store.get(self.payments.scope,key)
        if row['sent_message'] is not None:return row['sent_message']
        template,variables=self.screen(key,row,invoice)
        ref=await runtime().ui.send(row['client_tg'],template,variables)
        with self.db:self.db.execute('UPDATE manager_invoices SET sent_message=? WHERE id=?',(ref.message_id,key))
        return ref.message_id

    async def retry_delivery(self,key,actor):
        # Never creates or reissues a provider invoice: durable ready record only.
        return await self.deliver(key,actor)

    async def reconcile(self,key,provider_invoice_id,actor,*,admin_ids):
        if actor not in admin_ids:raise PermissionError('Сверка доступна только администратору')
        row=self.db.execute('SELECT * FROM manager_invoices WHERE id=? AND deleted_at IS NULL',(key,)).fetchone()
        if row is None:raise ValueError('Неизвестный счет')
        if row['provider']!='cryptobot':raise ValueError('Автоматическая сверка поддерживается только для CryptoPay')
        provider=self.payments.providers.get('cryptobot')
        if provider is None:raise ValueError('CryptoPay не настроен')
        if not str(provider_invoice_id).isdigit():raise ValueError('ID провайдера должен быть числом')
        # Authenticated provider lookup and payload binding are mandatory:
        # matching money alone must never attach someone else's invoice.
        result=await provider._request('GET','getInvoices',params={'invoice_ids':str(provider_invoice_id)})
        matches=[item for item in result.get('items',[]) if str(item.get('invoice_id'))==str(provider_invoice_id) and item.get('payload')==key]
        if len(matches)!=1:raise ValueError('Счет провайдера не связан с этим запросом (payload)')
        invoice=provider._invoice(matches[0])
        if invoice.money!=Money(Decimal(row['amount']),row['currency']):raise ValueError('Сумма или валюта не совпадают')
        # Library repeats authenticated status/identity validation, then resolves
        # only an existing ambiguous reservation; it cannot create an invoice.
        return await self.payments.reconcile_creation(key,invoice)

    async def check(self,key,actor):
        row=self.record(key,actor)
        invoice=await self.payments.check(key)
        await self.notify_paid()
        return self.screen(key,row,invoice)

    async def notify_paid(self):
        async with self._notify_lock:
            await self._notify_paid()

    async def _notify_paid(self):
        for event_id,invoice in self.payments.paid_events():
            rows=self.db.execute('SELECT * FROM manager_invoices WHERE provider=? AND deleted_at IS NULL',(invoice.provider,)).fetchall()
            row=None
            for candidate in rows:
                try:stored=self.payments.store.get(self.payments.scope,candidate['id'])
                except (KeyError,PaymentError):continue
                if stored.id==invoice.id:
                    row=candidate;break
            if row is None:continue
            complete=True
            for flag,recipient in [('manager_notified',row['manager_tg']),('client_notified',row['client_tg'])]:
                if not row[flag]:
                    try:
                        await runtime().ui.send(recipient,Template('<b>Счет оплачен</b>\n{description}\n{amount} {currency}\nНомер: <code>{key}</code>'),{'description':row['description'],'amount':invoice.money.amount,'currency':invoice.money.currency,'key':row['id']})
                        with self.db:self.db.execute(f'UPDATE manager_invoices SET {flag}=1 WHERE id=?',(row['id'],))
                    except asyncio.CancelledError:raise
                    except Exception:
                        complete=False
                        log.exception('Paid notification failed for %s / %s',row['id'],flag)
            if complete:self.payments.acknowledge(event_id)


def configure_payments():
    global _service
    from config import DATA_DIR
    from repositories import ManagerRepository,UserRepository
    providers=[]
    if os.getenv('CRYPTOPAY_TOKEN'):providers.append(CryptoPayProvider(os.environ['CRYPTOPAY_TOKEN'],testnet=runtime().settings.get('payments.testnet')))
    if os.getenv('XROCKET_TOKEN'):providers.append(XRocketProvider(os.environ['XROCKET_TOKEN']))
    payments=Payments(*providers,store=SQLiteStore(str(DATA_DIR/'payments.sqlite')),scope='twix')
    _service=InvoiceService(payments,DATA_DIR/'payments.sqlite',manager_lookup=ManagerRepository().find_by_telegram_id,user_lookup=UserRepository().find_by_telegram_id)
    return _service


def service():
    if _service is None:raise RuntimeError('Payments not configured')
    return _service


async def payment_loop():
    while True:
        try:
            s=service()
            # One unavailable invoice/provider must not starve other invoices
            # or already persisted paid notifications in the outbox.
            for key,_ in s.payments.store.pending(s.payments.scope):
                try:await s.payments.check(key)
                except asyncio.CancelledError:raise
                except Exception:log.exception('Invoice status check failed for %s',key)
            await s.notify_paid()
        except asyncio.CancelledError:raise
        except Exception:log.exception('Invoice polling failed')
        await asyncio.sleep(runtime().settings.get('payments.poll_interval'))
