# tpl/__init__.py
"""
tpl — мультиязычная библиотека шаблонов для Telegram-ботов (aiogram 3.25+)
"""

from tpl.defaults import set_defaults, get_defaults
from tpl.manager import (
    get_template,
    update_template,
    update_button_at_index,
    remove_button_field,
    swap_button_action,
    get_flat_buttons,
    get_flat_reply_buttons,
    update_reply_button_at_index,
    remove_reply_button_field,
    reset_template,
    reset_template_all_locales,
    list_all_keys,
    get_template_locales,
    set_data_file,
)
from tpl.sender import send_template, edit_template, answer_template, render_text, set_default_bot, get_default_bot
from tpl.keyboards import build_keyboard, build_reply_keyboard
from tpl.emoji import rebuild_text_with_emoji, extract_emoji_ids, extract_first_emoji_id
from tpl.locale import (
    set_default_locale,
    get_default_locale,
    set_available_locales,
    get_available_locales,
    set_user_locale_getter,
    set_user_locale_setter,
    get_user_locale,
    set_user_locale,
    set_locale_fallbacks,
    get_locale_fallbacks,
    resolve_fallback,
)
from tpl.admin_handler import create_router as _create_router
from tpl.admin_states import TplAdminStates
from tpl.admin_emoji import emoji_tag
from tpl.types import TemplateData, ButtonData, ReplyButtonData
from tpl.storage import set_backend, get_backend, JSONBackend, MemoryBackend
from tpl.tree import (
    normalize_key,
    key_to_callback,
    callback_to_key,
    build_tree,
    group_by_prefix,
    list_children,
    parent_key,
    is_in_namespace,
    get_tree_nodes,
)
from tpl.builder import KeyboardBuilder
from tpl.middleware import TplI18nMiddleware


def create_admin_router(
    admin_ids: list[int],
    command: str = "templates",
    preview_variables: dict | None = None,
):
    """Создать Router админки шаблонов."""
    return _create_router(admin_ids=admin_ids, command=command, preview_variables=preview_variables)


__all__ = [
    "set_defaults", "get_defaults",
    "set_default_locale", "get_default_locale",
    "set_available_locales", "get_available_locales",
    "set_user_locale_getter", "set_user_locale_setter",
    "get_user_locale", "set_user_locale",
    "set_locale_fallbacks", "get_locale_fallbacks", "resolve_fallback",
    "get_template", "update_template",
    "update_button_at_index", "remove_button_field", "swap_button_action",
    "get_flat_buttons", "get_flat_reply_buttons",
    "update_reply_button_at_index", "remove_reply_button_field",
    "reset_template", "reset_template_all_locales",
    "list_all_keys", "get_template_locales", "set_data_file",
    "send_template", "edit_template", "answer_template", "render_text",
    "set_default_bot", "get_default_bot",
    "build_keyboard", "build_reply_keyboard",
    "rebuild_text_with_emoji", "extract_emoji_ids", "extract_first_emoji_id",
    "create_admin_router", "TplAdminStates",
    "TemplateData", "ButtonData", "ReplyButtonData",
    "set_backend", "get_backend", "JSONBackend", "MemoryBackend",
    "normalize_key", "key_to_callback", "callback_to_key",
    "build_tree", "group_by_prefix", "list_children", "parent_key", "is_in_namespace",
    "get_tree_nodes",
    "TplI18nMiddleware",
]