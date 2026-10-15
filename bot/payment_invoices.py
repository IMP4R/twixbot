from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from aiogram import Router,F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State,StatesGroup
from tg_payments import PaymentError
from tg_templates import Button,Template

from payment_service import service
from presentation import message_ref
from twix_runtime import runtime

router=Router(name='manager_invoices')


class InvoiceStates(StatesGroup):
    client=State()
    amount=State()
    description=State()
    confirm=State()


async def send(target,template,variables=None):
    return await runtime().ui.send(target.chat.id,template,variables)


@router.callback_query(F.data=='mgr_invoice')
async def begin_callback(callback,state:FSMContext):
    try:service().require_manager(callback.from_user.id)
    except PermissionError:
        await callback.answer('Недоступно');return
    await callback.answer();await state.clear();await state.set_state(InvoiceStates.client)
    await runtime().ui.send(callback.message.chat.id,Template('<b>Новый счет</b>\nВведите Telegram ID клиента.\n/cancel — отмена'))


@router.message(Command('invoice'))
async def begin(message,state:FSMContext):
    try:service().require_manager(message.from_user.id)
    except PermissionError:return
    await state.clear();await state.set_state(InvoiceStates.client)
    await send(message,Template('<b>Новый счет</b>\nВведите Telegram ID клиента.\n/cancel — отмена'))


@router.message(Command('cancel'))
async def cancel(message,state:FSMContext):
    if (await state.get_state() or '').startswith('InvoiceStates:'):
        await state.clear();await send(message,Template('Создание счета отменено'))
    else:
        from aiogram.dispatcher.event.bases import UNHANDLED
        return UNHANDLED


@router.message(InvoiceStates.client)
async def client(message,state:FSMContext):
    try:
        service().require_manager(message.from_user.id)
        client_tg=int(message.text or '')
        if client_tg<=0 or not service().users(client_tg):raise ValueError('Клиент не найден. Он должен запустить бота')
    except (ValueError,PermissionError) as exc:
        await send(message,Template('{error}'),{'error':str(exc)});return
    await state.update_data(client=client_tg,key=str(uuid.uuid4()),currency=runtime().settings.get('payments.currency'),provider=runtime().settings.get('payments.provider'))
    await state.set_state(InvoiceStates.amount)
    await send(message,Template('Введите сумму счета в {currency}'),{'currency':(await state.get_data())['currency']})


@router.message(InvoiceStates.amount)
async def amount(message,state:FSMContext):
    try:
        service().require_manager(message.from_user.id)
        value=Decimal((message.text or '').replace(',','.'))
        if not value.is_finite() or value<=0 or value>runtime().settings.get('payments.max_amount'):raise ValueError('Недопустимая сумма')
    except (InvalidOperation,ValueError,PermissionError) as exc:
        await send(message,Template('Некорректная сумма: {error}'),{'error':str(exc)});return
    await state.update_data(amount=str(value));await state.set_state(InvoiceStates.description)
    await send(message,Template('Введите назначение платежа (до 400 символов)'))


@router.message(InvoiceStates.description)
async def description(message,state:FSMContext):
    text=(message.text or '').strip()
    if not 1<=len(text)<=400:
        await send(message,Template('Описание должно содержать от 1 до 400 символов'));return
    service().require_manager(message.from_user.id)
    await state.update_data(description=text);await state.set_state(InvoiceStates.confirm)
    data=await state.get_data()
    await send(message,Template('<b>Создать и отправить счет?</b>\nКлиент: {client}\nСумма: {amount} {currency}\n{description}',buttons=((Button('Создать счет',callback_data='invoice_confirm',style='success'),),(Button('Отмена',callback_data='invoice_cancel'),))),data)


@router.callback_query(F.data=='invoice_cancel')
async def cancel_callback(callback,state:FSMContext):
    service().require_manager(callback.from_user.id)
    await callback.answer();await state.clear()
    await runtime().ui.edit(message_ref(callback.message),Template('Создание счета отменено'))


@router.callback_query(InvoiceStates.confirm,F.data=='invoice_confirm')
async def confirm(callback,state:FSMContext):
    await callback.answer()
    data=await state.get_data()
    key=data.get('key')
    created=False
    try:
        key,invoice=await service().create(callback.from_user.id,data['client'],Decimal(data['amount']),data['description'],request_id=data['key'],expected_currency=data['currency'],expected_provider=data['provider'])
        created=True
        await service().deliver(key,callback.from_user.id)
    except (PermissionError,ValueError) as exc:
        await runtime().ui.send(callback.message.chat.id,Template('Счет не отправлен: {error}'),{'error':str(exc)});return
    except PaymentError as exc:
        await runtime().ui.send(callback.message.chat.id,Template('Исход создания не подтвержден: {error}\nНомер: <code>{key}</code>\nНе создавайте новый счет до сверки провайдера. Администратор: /invoice_reconcile {key} ID_CryptoPay'),{'error':str(exc),'key':key or ''});return
    except Exception:
        if not created:
            await runtime().ui.send(callback.message.chat.id,Template('Исход создания счета не подтвержден. Номер: <code>{key}</code>. Не создавайте новый счет до проверки провайдера.'),{'key':key or ''})
            return
        # Network failure after provider creation: retry delivery of the SAME
        # persisted invoice, not creation with a new key.
        await state.clear()
        await runtime().ui.send(callback.message.chat.id,Template('Счет создан, доставка не подтверждена.\nНомер: <code>{key}</code>\nПовторите доставку существующего счета.',buttons=((Button('Повторить доставку',callback_data=f"pay_retry:{key}"),),)),{'key':key})
        return
    await state.clear()
    await runtime().ui.edit(message_ref(callback.message),Template('Счет <code>{key}</code> отправлен клиенту'),{'key':key})


@router.callback_query(F.data.startswith('pay_retry:'))
async def retry_delivery(callback):
    await callback.answer()
    key=callback.data.split(':',1)[1]
    try:await service().retry_delivery(key,callback.from_user.id)
    except (PermissionError,PaymentError,KeyError) as exc:
        await runtime().ui.send(callback.message.chat.id,Template('Доставка недоступна: {error}'),{'error':str(exc)});return
    except Exception:
        await runtime().ui.send(callback.message.chat.id,Template('Доставка снова не подтверждена. Используйте ту же кнопку, не создавайте новый счет.'));return
    await runtime().ui.edit(message_ref(callback.message),Template('Счет <code>{key}</code> доставлен'),{'key':key})


@router.message(Command('invoice_retry'))
async def retry_command(message):
    parts=(message.text or '').split()
    if len(parts)!=2:
        await send(message,Template('Формат: /invoice_retry UUID'));return
    try:await service().retry_delivery(parts[1],message.from_user.id)
    except (PermissionError,PaymentError,KeyError) as exc:
        await send(message,Template('Повторная доставка недоступна: {error}'),{'error':str(exc)});return
    except Exception:
        await send(message,Template('Доставка не подтверждена. Повторите эту же команду после устранения ошибки.'));return
    await send(message,Template('Существующий счет доставлен'))


@router.message(Command('invoice_reconcile'))
async def reconcile_command(message):
    from config import ADMIN_IDS
    if message.from_user.id not in ADMIN_IDS:return
    parts=(message.text or '').split()
    if len(parts)!=3:
        await send(message,Template('Формат: /invoice_reconcile UUID ID_CryptoPay. Используйте ID из панели провайдера; сверка проверит payload, сумму и валюту.'));return
    try:await service().reconcile(parts[1],parts[2],message.from_user.id,admin_ids=ADMIN_IDS)
    except (PermissionError,ValueError,PaymentError) as exc:
        await send(message,Template('Сверка не выполнена: {error}'),{'error':str(exc)});return
    await send(message,Template('Существующий счет подтвержден провайдером. Автор счета может выполнить /invoice_retry {key}'),{'key':parts[1]})


@router.callback_query(F.data.startswith('pay_check:'))
async def check(callback):
    await callback.answer()
    try:template,variables=await service().check(callback.data.split(':',1)[1],callback.from_user.id)
    except (PermissionError,PaymentError) as exc:
        await runtime().ui.send(callback.message.chat.id,Template('{error}'),{'error':str(exc)});return
    await runtime().ui.edit(message_ref(callback.message),template,variables)
