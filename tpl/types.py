# tpl/types.py
"""Типы данных шаблонов."""

from typing import TypedDict


class ButtonData(TypedDict, total=False):
    text: str
    callback_data: str
    url: str
    style: str
    icon_custom_emoji_id: str


class ReplyButtonData(TypedDict, total=False):
    text: str
    action: str
    style: str
    icon_custom_emoji_id: str


class TemplateData(TypedDict, total=False):
    text: str
    media_type: str
    media_file_id: str
    parse_mode: str
    buttons: list[list[ButtonData]]
    reply_buttons: list[list[ReplyButtonData]]
    custom_emoji_ids: list[str]