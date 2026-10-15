# tpl/sender.py
"""Отправка и редактирование сообщений по шаблонам с поддержкой локалей."""

import re
import copy
from typing import Optional

from aiogram import Bot
from aiogram.types import (
    Message, CallbackQuery,
    InputMediaPhoto, InputMediaAnimation, InputMediaVideo,
)

from tpl.manager import get_template
from tpl.keyboards import build_keyboard, build_reply_keyboard
from tpl.locale import get_user_locale, get_default_locale
from tpl.types import ButtonData
from typing import Optional

# Глобальный fallback-bot для отправки по chat_id (int)
_default_bot: Optional[Bot] = None


def set_default_bot(bot: Bot):
    global _default_bot
    _default_bot = bot


def get_default_bot() -> Optional[Bot]:
    return _default_bot


def render_text(template: dict, variables: dict) -> str:
    text = template.get("text", "")
    try:
        return text.format(**variables)
    except (KeyError, IndexError, ValueError):
        class SafeDict(dict):
            def __missing__(self, k):
                return "{" + k + "}"
        return text.format_map(SafeDict(**variables))


def _render_str(s: str, variables: dict) -> str:
    """Render variables in any string (button text, callback_data, url)."""
    if not variables or not s or "{" not in s:
        return s
    try:
        return s.format(**variables)
    except (KeyError, IndexError, ValueError):
        class SafeDict(dict):
            def __missing__(self, k):
                return "{" + k + "}"
        return s.format_map(SafeDict(**variables))


def _render_buttons(buttons: list[list[ButtonData]], variables: dict) -> list[list[ButtonData]]:
    """Render variables in button texts, callback_data, and urls."""
    if not variables or not buttons:
        return buttons

    rendered = []
    for row in buttons:
        rendered_row = []
        for btn in row:
            new_btn = copy.deepcopy(btn)
            if "text" in new_btn:
                new_btn["text"] = _render_str(new_btn["text"], variables)
            if "callback_data" in new_btn:
                new_btn["callback_data"] = _render_str(new_btn["callback_data"], variables)
            if "url" in new_btn:
                new_btn["url"] = _render_str(new_btn["url"], variables)
            if "icon_custom_emoji_id" in new_btn:
                new_btn["icon_custom_emoji_id"] = _render_str(new_btn["icon_custom_emoji_id"], variables)
            rendered_row.append(new_btn)
        rendered.append(rendered_row)
    return rendered


def _resolve_chat_and_bot(target, bot):
    if isinstance(target, Message):
        return target.chat.id, bot or target.bot
    return target, bot


async def _resolve_locale(target, locale: str | None) -> str:
    if locale:
        return locale

    user_id = None
    if isinstance(target, Message):
        user_id = target.from_user.id if target.from_user else None
    elif isinstance(target, CallbackQuery):
        user_id = target.from_user.id
    elif isinstance(target, int):
        user_id = target

    if user_id:
        return await get_user_locale(user_id)

    return get_default_locale()


async def send_template(
    target: Message | int,
    key: str,
    variables: dict | None = None,
    bot: Bot | None = None,
    extra_buttons: list[list[ButtonData]] | None = None,
    locale: str | None = None,
    reply_markup=None,  # <--- ДОБАВИТЬ ЭТОТ ПАРАМЕТР
) -> Message:
    loc = await _resolve_locale(target, locale)
    tmpl = get_template(key, loc)
    variables = variables or {}
    text = render_text(tmpl, variables)
    pm = tmpl.get("parse_mode", "HTML")

    rendered_btns = _render_buttons(tmpl.get("buttons", []), variables)
    reply_btns = tmpl.get("reply_buttons", [])

    if reply_markup is not None:
        kb = reply_markup
    elif reply_btns:
        kb = build_reply_keyboard(reply_btns)
    else:
        kb = build_keyboard(rendered_btns, extra_buttons)

    mt = tmpl.get("media_type", "none")
    mf = tmpl.get("media_file_id", "")

    # Получаем chat_id и bot
    if isinstance(target, Message):
        cid = target.chat.id
        _bot = bot or target.bot
    elif isinstance(target, int):
        cid = target
        _bot = bot or get_default_bot()
        if _bot is None:
            raise ValueError("bot is required when target is int. Use set_default_bot(bot) or pass bot explicitly.")
    else:
        raise ValueError(f"Invalid target type: {type(target)}")

    if mt != "none" and mf:
        media_methods = {
            "photo": ("send_photo", "photo"),
            "animation": ("send_animation", "animation"),
            "video": ("send_video", "video"),
        }
        method_name, kwarg_name = media_methods.get(mt, ("send_photo", "photo"))
        method = getattr(_bot, method_name)
        try:
            return await method(
                chat_id=cid, **{kwarg_name: mf},
                caption=text, parse_mode=pm, reply_markup=kb,
            )
        except Exception as exc:
            # Fallback: media file_id invalid or Telegram error → send text-only
            import logging
            logging.getLogger("tpl.sender").warning(
                "Media send failed (%s %s), falling back to text: %s", mt, kwarg_name, exc
            )

    return await _bot.send_message(chat_id=cid, text=text, parse_mode=pm, reply_markup=kb)

async def edit_template(
    target: Message | CallbackQuery,
    key: str,
    variables: dict | None = None,
    bot: Bot | None = None,
    locale: str | None = None,
    extra_buttons: list[list[ButtonData]] | None = None,
    reply_markup=None,
) -> Message:
    loc = await _resolve_locale(target, locale)
    tmpl = get_template(key, loc)
    variables = variables or {}
    text = render_text(tmpl, variables)
    pm = tmpl.get("parse_mode", "HTML")

    # Рендерим кнопки с переменными
    rendered_btns = _render_buttons(tmpl.get("buttons", []), variables)
    kb = build_keyboard(rendered_btns, extra_buttons) if reply_markup is None else reply_markup
    
    mt = tmpl.get("media_type", "none")
    mf = tmpl.get("media_file_id", "")

    msg = target.message if isinstance(target, CallbackQuery) else target
    _bot = bot or msg.bot

    has_media = mt != "none" and mf
    old_has_media = bool(msg.photo or msg.animation or msg.video)

    if not has_media and not old_has_media:
        try:
            return await msg.edit_text(text=text, parse_mode=pm, reply_markup=kb)
        except Exception:
            return await msg.answer(text=text, parse_mode=pm, reply_markup=kb)

    if has_media and old_has_media:
        media_cls = {
            "photo": InputMediaPhoto,
            "animation": InputMediaAnimation,
            "video": InputMediaVideo,
        }.get(mt, InputMediaPhoto)
        try:
            await msg.edit_media(
                media=media_cls(media=mf, caption=text, parse_mode=pm),
                reply_markup=kb,
            )
            return msg
        except Exception as exc:
            import logging
            logging.getLogger("tpl.sender").warning(
                "Media edit failed (%s), falling back to delete+send: %s", mt, exc
            )
            # Fallback: delete old + send new as text-only
            try:
                await msg.delete()
            except Exception:
                pass
            return await _bot.send_message(chat_id=msg.chat.id, text=text, parse_mode=pm, reply_markup=kb)

    cid = msg.chat.id
    try:
        await msg.delete()
    except Exception:
        pass
    return await send_template(cid, key, variables, bot=_bot, locale=loc, extra_buttons=extra_buttons)


async def answer_template(
    callback: CallbackQuery,
    key: str,
    show_alert: bool = False,
    variables: dict | None = None,
    locale: str | None = None,
):
    loc = await _resolve_locale(callback, locale)
    tmpl = get_template(key, loc)
    text = render_text(tmpl, variables or {})
    clean = re.sub(r'<[^>]+>', '', text)
    await callback.answer(clean[:200], show_alert=show_alert)