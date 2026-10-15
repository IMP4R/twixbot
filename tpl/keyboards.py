# tpl/keyboards.py
"""Построение клавиатур из шаблонных данных."""

from typing import Optional
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)

from tpl.types import ButtonData, ReplyButtonData

import copy


def _render_str(s: str, variables: dict | None) -> str:
    if not variables or not s or "{" not in s:
        return s
    try:
        return s.format(**variables)
    except (KeyError, IndexError, ValueError):
        class SafeDict(dict):
            def __missing__(self, k):
                return "{" + k + "}"
        return s.format_map(SafeDict(**variables))


def _render_buttons(buttons: list[list[ButtonData]], variables: dict | None) -> list[list[ButtonData]]:
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


def build_keyboard(
    buttons: list[list[ButtonData]],
    extra_buttons: list[list[ButtonData]] | None = None,
    variables: dict | None = None,
) -> Optional[InlineKeyboardMarkup]:
    all_buttons = _render_buttons(list(buttons), variables)
    if extra_buttons:
        all_buttons = all_buttons + _render_buttons(list(extra_buttons), variables)

    if not all_buttons:
        return None

    rows = []
    for row_data in all_buttons:
        row = []
        for b in row_data:
            kwargs = {"text": b.get("text", "?")}

            if "url" in b and b["url"]:
                kwargs["url"] = b["url"]
            else:
                kwargs["callback_data"] = b.get("callback_data", "noop")

            if b.get("style"):
                kwargs["style"] = b["style"]

            if b.get("icon_custom_emoji_id"):
                kwargs["icon_custom_emoji_id"] = b["icon_custom_emoji_id"]

            row.append(InlineKeyboardButton(**kwargs))
        rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_reply_keyboard(
    reply_buttons: list[list[ReplyButtonData]],
    filter_actions: list[str] | None = None,
    premium_active: bool = False,
) -> Optional[ReplyKeyboardMarkup]:
    if not reply_buttons:
        return None

    rows = []
    for row_data in reply_buttons:
        row = []
        for b in row_data:
            action = b.get("action", "")
            if filter_actions is not None and action not in filter_actions:
                continue

            text = b.get("text", "?")
            if action == "premium" and premium_active:
                text += " ✓"

            kwargs = {"text": text}

            if b.get("style"):
                kwargs["style"] = b["style"]

            if b.get("icon_custom_emoji_id"):
                kwargs["icon_custom_emoji_id"] = b["icon_custom_emoji_id"]

            row.append(KeyboardButton(**kwargs))
        if row:
            rows.append(row)

    if not rows:
        return None

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)