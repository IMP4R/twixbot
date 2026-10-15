from __future__ import annotations

import secrets
import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from tg_settings import SettingsUI, TemplateEditor, ValidationError, ConflictError, HookError
from tg_templates import Button, Media, Template

from config import ADMIN_IDS
from presentation import message_ref, send_text
from twix_runtime import runtime


class CompactSettingsUI(SettingsUI):
    def _categories(self,session):
        session.key,session.awaiting,session.has_pending=None,False,False
        return self._category_page(session,0)

    def _category_page(self,session,page):
        categories=self.settings.schema.categories()
        pages=max(1,(len(categories)+2)//3);page=max(0,min(page,pages-1))
        session.actions.clear()
        rows=[[self._button(session,category,('category',category,0))] for category in categories[page*3:(page+1)*3]]
        if page:rows.append([self._button(session,'Назад',('category_page',page-1))])
        if page+1<pages:rows.append([self._button(session,'Далее',('category_page',page+1))])
        return self._page(session,'categories',buttons=rows)

    async def handle(self,actor,callback_data):
        await self._authorized(actor)
        self._expire()
        action_token=callback_data.removeprefix('set:')
        for session in self.sessions.values():
            action=session.actions.get(action_token)
            if session.actor==actor and action and action[0]=='category_page':
                session.actions.pop(action_token)
                return self._category_page(session,action[1])
        return await super().handle(actor,callback_data)

    def __init__(self,*args,**kwargs):
        self._category_pages={}
        super().__init__(*args,**kwargs)


class ConfigStates(StatesGroup):
    editing=State()


def create_router():
    router=Router(name='unified_configuration')
    sessions={}
    actions={}
    admin=CompactSettingsUI(runtime().settings,authorize=lambda actor:actor in ADMIN_IDS,ui=runtime().ui,page_size=2)

    async def deliver(target,screen):
        template,variables=screen
        if hasattr(target,'message'):return await runtime().ui.edit(message_ref(target.message),template,variables)
        return await runtime().ui.send(target.chat.id,template,variables)

    async def open_settings(target,state):
        actor=target.from_user.id
        if actor not in ADMIN_IDS:return
        token,t,v=await admin.open(actor)
        sessions[actor]=(admin,token)
        await state.set_state(ConfigStates.editing)
        await deliver(target,(t,v))

    @router.message(Command('settings'))
    async def command_settings(message,state:FSMContext):await open_settings(message,state)

    @router.callback_query(F.data=='admin_settings')
    async def settings_callback(callback,state:FSMContext):
        await callback.answer();await open_settings(callback,state)

    async def template_menu(target,state,page=0):
        actor=target.from_user.id
        if actor not in ADMIN_IDS:return
        for token,entry in list(actions.items()):
            if entry[0]==actor or entry[2]<time.monotonic():actions.pop(token,None)
        keys=runtime().catalog.keys();page=max(0,min(page,max(0,(len(keys)-1)//3)))
        rows=[]
        for key in keys[page*3:(page+1)*3]:
            token=secrets.token_urlsafe(9);actions[token]=(actor,key,time.monotonic()+900)
            rows.append((Button(key,callback_data=f'cfg_tpl:{token}'),))
        nav=[]
        if page:nav.append(Button('Назад',callback_data=f'cfg_page:{page-1}'))
        if (page+1)*3<len(keys):nav.append(Button('Далее',callback_data=f'cfg_page:{page+1}'))
        if nav:rows.append(tuple(nav))
        if sum(len(row) for row in rows)<5:rows.append((Button('Настройки',callback_data='admin_settings'),))
        sessions.pop(actor,None)
        await state.clear()
        await deliver(target,(Template('<b>Шаблоны</b>\nВыберите экран',buttons=tuple(rows)),{}))

    @router.message(Command('templates'))
    async def command_templates(message,state:FSMContext):await template_menu(message,state)

    @router.callback_query(F.data=='admin_templates')
    async def templates_callback(callback,state:FSMContext):
        await callback.answer();await template_menu(callback,state)

    @router.callback_query(F.data.startswith('cfg_page:'))
    async def template_page(callback,state:FSMContext):
        await callback.answer();await template_menu(callback,state,int(callback.data.split(':')[1]))

    @router.callback_query(F.data.startswith('cfg_tpl:'))
    async def template_open(callback,state:FSMContext):
        await callback.answer()
        token=callback.data.split(':')[1];entry=actions.get(token)
        if callback.from_user.id not in ADMIN_IDS or entry is None or entry[0]!=callback.from_user.id or entry[2]<time.monotonic():return
        actions.pop(token,None)
        editor=TemplateEditor(runtime().catalog,entry[1],locale='ru',authorize=lambda actor:actor in ADMIN_IDS,ui=runtime().ui)
        session,t,v=await editor.open(callback.from_user.id)
        sessions[callback.from_user.id]=(editor.controller,session)
        await state.set_state(ConfigStates.editing)
        await deliver(callback,(t,v))

    @router.callback_query(F.data.startswith('set:'))
    async def setting_action(callback,state:FSMContext):
        await callback.answer()
        actor=callback.from_user.id
        if actor not in ADMIN_IDS:return
        if actor not in sessions:
            await open_settings(callback,state);return
        controller,token=sessions[actor]
        try:screen=await controller.handle(actor,callback.data)
        except (PermissionError,ValidationError,ConflictError,HookError) as exc:
            await runtime().ui.send(callback.message.chat.id,Template('{error}'),{'error':str(exc)})
            await open_settings(callback,state);return
        await deliver(callback,screen)

    @router.message(ConfigStates.editing,Command('cancel'))
    async def cancel_editor(message,state:FSMContext):
        sessions.pop(message.from_user.id,None)
        await state.clear()
        await deliver(message,(Template('Редактор закрыт. Изменения без сохранения не применены.'),{}))

    @router.callback_query(ConfigStates.editing,F.data.in_({'home','admin_menu','manager_menu'}))
    async def leave_editor(callback,state:FSMContext):
        from aiogram.dispatcher.event.bases import UNHANDLED
        sessions.pop(callback.from_user.id,None)
        await state.clear()
        return UNHANDLED

    @router.message(ConfigStates.editing)
    async def setting_input(message,state:FSMContext):
        actor=message.from_user.id
        if actor not in ADMIN_IDS:return
        controller,token=sessions.get(actor,(None,None))
        if controller is None:
            await open_settings(message,state);return
        if message.photo:raw=Media('photo',message.photo[-1].file_id)
        else:
            kind=next((k for k in ['video','animation','audio','document'] if getattr(message,k,None)),None)
            raw=Media(kind,getattr(message,kind).file_id) if kind else message.text
        try:screen=await controller.input(actor,token,raw)
        except (PermissionError,ValidationError,ConflictError,HookError) as exc:
            await runtime().ui.send(message.chat.id,Template('{error}'),{'error':str(exc)});return
        await deliver(message,screen)

    # Old inline buttons are links into the SAME controller, never own storage.
    @router.callback_query(F.data.startswith('set_inline_'))
    async def old_settings_link(callback,state:FSMContext):
        await callback.answer();await open_settings(callback,state)

    return router
