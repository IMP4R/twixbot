from __future__ import annotations

import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from settings.admin_emoji import (
    SETTINGS, FOLDER, HOME, PENCIL, CHECK, CROSS, TRASH,
    ARROW_UP, ARROW_DOWN, BOX, PROFILE, MONEY,
    BELL, CLOCK, CODE, PEOPLE, INFO, LINK,
    FORMAT, CLIP, SEND,
)


def _safe_icon(raw: str | None) -> str | None:
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return raw
    m = re.search(r'emoji-id="(\d+)"', raw)
    if m:
        return m.group(1)
    return None


CATEGORY_NAMES: dict[str, str] = {
    "rates":         "Курсы",
    "deals":         "Сделки",
    "tickets":       "Тикеты",
    "timers":        "Таймеры",
    "notifications": "Уведомления",
    "loyalty":       "Лояльность",
    "system":        "Система",
    "general":       "Общие",
}

CATEGORY_ICONS: dict[str, str] = {
    "rates":         MONEY,
    "deals":         CLIP,
    "tickets":       BOX,
    "timers":        CLOCK,
    "notifications": BELL,
    "loyalty":       PROFILE,
    "system":        CODE,
    "general":       SETTINGS,
}


def _b(text: str, cb: str, icon: str | None = None) -> InlineKeyboardButton:
    safe = _safe_icon(icon)
    if safe:
        return InlineKeyboardButton(text=text, callback_data=cb, icon_custom_emoji_id=safe)
    return InlineKeyboardButton(text=text, callback_data=cb)


def categories_kb(categories: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        icon = _safe_icon(CATEGORY_ICONS.get(cat, SETTINGS))
        display = CATEGORY_NAMES.get(cat, cat.capitalize())
        if icon:
            builder.button(text=display, callback_data=f"set_cat:{cat}", icon_custom_emoji_id=icon)
        else:
            builder.button(text=display, callback_data=f"set_cat:{cat}")
    builder.adjust(2)
    builder.row(*[
        _b("Назад", "admin_menu", ARROW_UP),
    ])
    return builder.as_markup()


def settings_list_kb(
    category: str,
    settings_defs: list,
    values: dict[str, str],
    page: int = 0,
    per_page: int = 10,
) -> InlineKeyboardMarkup:
    total = len(settings_defs)
    start = page * per_page
    end = min(start + per_page, total)
    page_items = settings_defs[start:end]

    builder = InlineKeyboardBuilder()
    for sd in page_items:
        val_text = values.get(sd.key, "—")
        btn_text = f"{sd.title}: {val_text}"
        icon = _safe_icon(CATEGORY_ICONS.get(sd.category, SETTINGS))
        kw: dict = {"text": btn_text, "callback_data": f"set_view:{sd.key}"}
        if icon:
            kw["icon_custom_emoji_id"] = icon
        builder.button(**kw)

    builder.adjust(1)

    nav_buttons = []
    if total > per_page:
        if page > 0:
            nav_buttons.append(
                _b("Назад", f"set_cat:{category}:{page - 1}", ARROW_UP),
            )
        if end < total:
            nav_buttons.append(
                _b("Вперёд", f"set_cat:{category}:{page + 1}", ARROW_DOWN),
            )

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(*[
        _b("Категории", "set_main", HOME),
        _b("Админка", "admin_menu", SETTINGS),
    ])
    return builder.as_markup()


def view_setting_kb(key: str, setting_def, current_value: str) -> InlineKeyboardMarkup:
    from settings.types import (
        BoolSetting, IntSetting, FloatSetting, DecimalSetting,
        StrSetting, EnumSetting, TierSetting, DurationSetting,
        JsonSetting, ListSetting,
    )

    builder = InlineKeyboardBuilder()

    if isinstance(setting_def, BoolSetting):
        val = current_value == "True" or current_value == "true"
        new_val = not val
        toggle_text = "Вкл" if not val else "Выкл"
        builder.button(
            text=toggle_text, callback_data=f"set_toggle:{key}:{str(new_val).lower()}",
            icon_custom_emoji_id=CHECK,
        )
    elif isinstance(setting_def, (IntSetting, FloatSetting, DecimalSetting, StrSetting)):
        builder.button(
            text="Изменить", callback_data=f"set_input:{key}",
            icon_custom_emoji_id=PENCIL,
        )
    elif isinstance(setting_def, EnumSetting):
        for opt in setting_def.options:
            icon = CHECK if opt == current_value else CROSS
            builder.button(
                text=opt, callback_data=f"set_enum:{key}:{opt}",
                icon_custom_emoji_id=icon,
            )
    elif isinstance(setting_def, DurationSetting):
        builder.button(
            text="Изменить (сек)", callback_data=f"set_input:{key}",
            icon_custom_emoji_id=PENCIL,
        )
    elif isinstance(setting_def, TierSetting):
        builder.button(
            text="Редактировать", callback_data=f"set_input:{key}",
            icon_custom_emoji_id=PENCIL,
        )
    elif isinstance(setting_def, (JsonSetting, ListSetting)):
        builder.button(
            text="Изменить JSON", callback_data=f"set_input:{key}",
            icon_custom_emoji_id=PENCIL,
        )

    builder.adjust(1)
    builder.row(*[
        _b("Сбросить к default", f"set_reset:{key}", TRASH),
    ])
    builder.row(*[
        _b("Назад", f"set_cat:{setting_def.category}", ARROW_UP),
        _b("Категории", "set_main", HOME),
        _b("Админка", "admin_menu", SETTINGS),
    ])
    return builder.as_markup()
