from __future__ import annotations

from dataclasses import asdict, replace

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from tg_templates import Button, MessageRef, SafeHTML, Template, template_from_dict
from twix_runtime import runtime


def set_default_bot(bot):return runtime().attach_bot(bot)
def get_default_bot():return runtime().bot

def build_keyboard(rows,extra_buttons=None):
    from aiogram.types import InlineKeyboardMarkup,InlineKeyboardButton
    all_rows=[*(rows or []),*(extra_buttons or [])]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(**{k:v for k,v in b.items() if v is not None}) if isinstance(b,dict) else b for b in row] for row in all_rows]) if all_rows else None


def literal_template(text,reply_markup=None):
    # Already rendered application text must not be interpreted as a SECOND
    # format string: client names can legally contain literal braces.
    return Template(text.replace('{','{{').replace('}','}}'),buttons=buttons(reply_markup))


def get_template(key,locale=None):
    template=runtime().catalog.get(key,locale)
    data=asdict(template)
    media=data.pop('media')
    data.update(media_type=media['kind'] if media else 'none',media_file_id=media['source'] if media else '')
    return data


def buttons(markup):
    if markup is None:return ()
    rows=markup.inline_keyboard if hasattr(markup,'inline_keyboard') else markup
    result=[]
    for row in rows:
        result.append(tuple(b if isinstance(b,Button) else Button(**(b.model_dump(exclude_none=True) if hasattr(b,'model_dump') else b)) for b in row))
    return tuple(result)


def message_ref(message):
    kind=next((k for k in ['animation','photo','video','audio','document'] if getattr(message,k,None)),'text')
    return MessageRef(message.chat.id,message.message_id,kind,getattr(message,'business_connection_id',None))


def render_text(template,variables):
    # Existing business strings include trusted assembled HTML tables. Callers
    # explicitly mark those with SafeHTML; raw names remain escaped.
    return runtime().ui.renderer.format(template.get('text',''),variables or {},html=template.get('parse_mode','HTML')=='HTML')


async def _result(ref):
    bot=runtime().bot
    data={'message_id':ref.message_id,'date':0,'chat':{'id':ref.chat_id,'type':'private'},'business_connection_id':ref.business_connection_id}
    # UI returns MessageRef, not Telegram's complete Message. Preserve its kind
    # so follow-up compatibility edits choose caption/media, not editMessageText.
    # Synthetic file metadata is identity-only; never use it for resending media.
    media={'file_id':'identity-only','file_unique_id':'identity-only'}
    if ref.kind=='photo':data['photo']=[{**media,'width':1,'height':1}]
    elif ref.kind in {'video','animation'}:data[ref.kind]={**media,'width':1,'height':1,'duration':0}
    elif ref.kind=='audio':data['audio']={**media,'duration':0}
    elif ref.kind=='document':data['document']=media
    return Message.model_validate(data,context={'bot':bot})


async def send_template(target,key,variables=None,bot=None,extra_buttons=None,locale=None,reply_markup=None):
    ui=runtime().ui
    if ui is None:raise RuntimeError('Bot not attached')
    chat_id=target.chat.id if hasattr(target,'chat') else target
    template=runtime().catalog.get(key,locale)
    if reply_markup is not None:template=replace(template,buttons=buttons(reply_markup))
    options={}
    if getattr(target,'business_connection_id',None):options['business_connection_id']=target.business_connection_id
    ref=await ui.send(chat_id,template,variables,extra_buttons=buttons(extra_buttons),**options)
    return await _result(ref)


async def edit_template(target,key,variables=None,bot=None,extra_buttons=None,locale=None,reply_markup=None):
    message=target.message if hasattr(target,'message') else target
    template=runtime().catalog.get(key,locale)
    if reply_markup is not None:template=replace(template,buttons=buttons(reply_markup))
    try:ref=await runtime().ui.edit(message_ref(message),template,variables,extra_buttons=buttons(extra_buttons))
    except TelegramBadRequest as exc:
        if 'message is not modified' in exc.message:return message
        raise
    return await _result(ref)


async def answer_template(callback,key,variables=None,**kwargs):
    return await runtime().ui.answer(callback.id,runtime().catalog.get(key),variables,**kwargs)


async def safe_edit_text(callback,text,reply_markup=None):
    try:return await runtime().ui.edit(message_ref(callback.message),literal_template(text,reply_markup))
    except TelegramBadRequest as exc:
        if 'message is not modified' in exc.message:return message_ref(callback.message)
        raise


async def send_text(message,text,reply_markup=None,**options):
    if getattr(message,'business_connection_id',None):options['business_connection_id']=message.business_connection_id
    ref=await runtime().ui.send(message.chat.id,literal_template(text,reply_markup),**options)
    return await _result(ref)


async def send_chat(bot,chat_id,text,reply_markup=None,**options):
    return await _result(await runtime().ui.send(chat_id,literal_template(text,reply_markup),**options))
