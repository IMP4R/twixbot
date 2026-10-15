# tpl/admin_kb.py
"""Клавиатуры админки — Premium Emoji и контактная компоновка."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from tpl.manager import list_all_keys, get_template, get_flat_buttons, get_flat_reply_buttons, get_template_locales
from tpl.locale import get_available_locales, get_default_locale
from tpl.tree import parent_key, get_tree_nodes
from tpl.admin_emoji import (
    FOLDER, HOME, CROSS, PENCIL, TRASH, CHECK,
    EYE, LINK, CLIP, CODE, MEDIA_PHOTO,
    CHART_GROWTH, CHART_STATS, BOX, APPS, ADD_TEXT,
    LOADING, BELL, LOCK_CLOSED, LOCK_OPEN, CLOCK,
    ARROW_UP, ARROW_DOWN, BRUSH as BRUSH_EMOJI,
)

ITEMS_PER_PAGE = 8

STYLE_OPTIONS = [
    ("default", "⬜ По умолчанию"),
    ("primary", "🔵 Primary"),
    ("success", "🟢 Success"),
    ("danger", "🔴 Danger"),
]

STYLE_ICON_EMOJI = {
    "primary": "🔵",
    "success": "🟢",
    "danger":  "🔴",
    "":         "⬜",
}


def _b(text: str, cb: str, icon: str | None = None) -> InlineKeyboardButton:
    """Фабрика кнопки с опциональным Premium-emoji иконкой."""
    kw = {"text": text, "callback_data": cb}
    if icon:
        kw["icon_custom_emoji_id"] = icon
    return InlineKeyboardButton(**kw)


def _row(*btns: InlineKeyboardButton) -> list[InlineKeyboardButton]:
    return list(btns)


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(_b("Шаблоны",     "tpl:tree::0",     icon=FOLDER)),
        _row(_b("Закрыть",     "tpl:close",        icon=CROSS)),
    ])


# ═══════════════════════════════════════════════════════════════
#  Tree / List
# ═══════════════════════════════════════════════════════════════

def templates_list_kb(page: int = 0, prefix: str | None = None) -> InlineKeyboardMarkup:
    all_keys = list_all_keys()
    folders, leaves = get_tree_nodes(all_keys, prefix)

    total = max(1, (len(leaves) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total - 1))
    start = page * ITEMS_PER_PAGE
    page_leaves = leaves[start:start + ITEMS_PER_PAGE]

    rows: list[list[InlineKeyboardButton]] = []

    # Папки
    for fname in folders:
        full = f"{prefix}.{fname}" if prefix else fname
        rows.append(_row(_b(fname, f"tpl:tree:{full}:0", icon=FOLDER)))

    # Листья
    for key in page_leaves:
        locales = get_template_locales(key)
        locale_count = len(locales)
        dl = get_default_locale()
        t = get_template(key, dl)
        has_media = t.get("media_type", "none") != "none" and t.get("media_file_id")
        has_emoji = bool(t.get("custom_emoji_ids"))
        has_reply = bool(t.get("reply_buttons"))

        if has_reply:
            icon = APPS
        elif has_media:
            icon = MEDIA_PHOTO
        elif has_emoji:
            icon = BOX
        else:
            icon = ADD_TEXT

        lang_badge = f" [{locale_count}]" if locale_count > 1 else ""
        short = key.split(".")[-1] if prefix else key
        rows.append(_row(_b(f"{short}{lang_badge}", f"tpl:view:{key}", icon=icon)))

    # Пагинация — стрелки по краям, номер в центре
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_b("←", f"tpl:tree:{prefix or ''}:{page - 1}", icon=ARROW_UP))
    else:
        nav.append(_b("·", "tpl:noop"))
    nav.append(_b(f"{page + 1}/{total}", "tpl:noop"))
    if page < total - 1:
        nav.append(_b("→", f"tpl:tree:{prefix or ''}:{page + 1}", icon=ARROW_DOWN))
    else:
        nav.append(_b("·", "tpl:noop"))
    rows.append(nav)

    # Навигация вверх/назад
    if prefix:
        parent = parent_key(prefix)
        if parent:
            rows.append(_row(_b("Вверх", f"tpl:tree:{parent}:0", icon=ARROW_UP)))
        else:
            rows.append(_row(_b("Назад", "tpl:back_main", icon=HOME)))
    else:
        rows.append(_row(_b("Назад", "tpl:back_main", icon=HOME)))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════════════════════════
#  Locale picker
# ═══════════════════════════════════════════════════════════════

def locale_choice_kb(key: str, action: str) -> InlineKeyboardMarkup:
    available = get_available_locales()
    existing = set(get_template_locales(key))
    dl = get_default_locale()

    rows: list[list[InlineKeyboardButton]] = []
    for code, label in available.items():
        marker = " ✅" if code in existing else " ➕"
        default_mark = " ★" if code == dl else ""
        rows.append(_row(_b(f"{label}{marker}{default_mark}", f"tpl:{action}:{key}:{code}")))
    rows.append(_row(_b("Назад", f"tpl:view:{key}", icon=HOME)))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════════════════════════
#  Template view  —  компактная 2-колоночная компоновка
# ═══════════════════════════════════════════════════════════════

def template_view_kb(key: str) -> InlineKeyboardMarkup:
    available = get_available_locales()
    has_multiple_locales = len(available) > 1
    dl = get_default_locale()
    t = get_template(key, dl)
    has_media = t.get("media_type", "none") != "none" and t.get("media_file_id")
    btn_count = sum(len(r) for r in t.get("buttons", []))
    reply_btn_count = sum(len(r) for r in t.get("reply_buttons", []))
    lc_prefix = "lc:" if has_multiple_locales else ""
    suffix = f":{key}" if has_multiple_locales else f":{key}:{dl}"

    rows: list[list[InlineKeyboardButton]] = []

    # ── Редактирование: текст + медиа в одной строке ──
    rows.append(_row(
        _b("Текст",     f"tpl:{lc_prefix}et{suffix}",   icon=PENCIL),
        _b("Медиа",     f"tpl:{lc_prefix}em{suffix}",   icon=MEDIA_PHOTO),
    ))

    # ── Предпросмотр ──
    rows.append(_row(
        _b("Предпросмотр", f"tpl:{lc_prefix}pv{suffix}", icon=EYE),
    ))

    # ── Управление кнопками (одной строкой, если оба типа есть) ──
    btn_row: list[InlineKeyboardButton] = []
    if btn_count > 0:
        btn_row.append(_b(f"Кнопки ({btn_count})", f"tpl:{lc_prefix}bl{suffix}", icon=CODE))
    if reply_btn_count > 0:
        btn_row.append(_b(f"Reply ({reply_btn_count})", f"tpl:{lc_prefix}rbl{suffix}", icon=APPS))
    if btn_row:
        rows.append(btn_row)

    # ── Удаление медиа (если есть) ──
    if has_media:
        rows.append(_row(
            _b("Убрать медиа", f"tpl:{lc_prefix}rm{suffix}", icon=TRASH),
        ))

    # ── Сброс: локаль + всё ──
    rows.append(_row(
        _b("Сбросить локаль", f"tpl:{lc_prefix}rs{suffix}", icon=CLOCK),
        _b("Сбросить всё",    f"tpl:rsa:{key}",            icon=TRASH),
    ))

    # ── Назад ──
    rows.append(_row(_b("К дереву", "tpl:tree::0", icon=HOME)))

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════════════════════════
#  Cancel
# ═══════════════════════════════════════════════════════════════

def cancel_kb(back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(_b("Отмена", back_cb, icon=CROSS)),
    ])


# ═══════════════════════════════════════════════════════════════
#  Inline Buttons
# ═══════════════════════════════════════════════════════════════

def btn_list_kb(key: str, locale: str) -> InlineKeyboardMarkup:
    flat = get_flat_buttons(key, locale)
    rows: list[list[InlineKeyboardButton]] = []
    for i, btn in enumerate(flat):
        style = btn.get("style", "")
        s_icon = STYLE_ICON_EMOJI.get(style, "⬜")
        emoji_icon = "✨" if btn.get("icon_custom_emoji_id") else ""
        rows.append(_row(_b(f"{s_icon}{emoji_icon} {btn['text']}", f"tpl:be:{key}:{locale}:{i}", icon=CODE)))
    rows.append(_row(_b("Назад", f"tpl:view:{key}", icon=HOME)))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def btn_edit_kb(key: str, locale: str, idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(_b("Текст",      f"tpl:bt:{key}:{locale}:{idx}", icon=PENCIL)),
        _row(_b("Стиль",      f"tpl:bs:{key}:{locale}:{idx}", icon=BRUSH_EMOJI)),
        _row(_b("Emoji",      f"tpl:bi:{key}:{locale}:{idx}", icon=BOX)),
        _row(_b("Callback/URL", f"tpl:bc:{key}:{locale}:{idx}", icon=LINK)),
        _row(_b("К кнопкам",  f"tpl:bl:{key}:{locale}", icon=HOME)),
    ])


# ═══════════════════════════════════════════════════════════════
#  Style picker (inline + reply)
# ═══════════════════════════════════════════════════════════════

def style_choice_kb(key: str, locale: str, idx: int, callback_prefix: str = "tpl:bss") -> InlineKeyboardMarkup:
    if callback_prefix == "tpl:bss":
        flat = get_flat_buttons(key, locale)
    else:
        flat = get_flat_reply_buttons(key, locale)

    current = flat[idx].get("style", "") if idx < len(flat) else ""
    rows: list[list[InlineKeyboardButton]] = []
    for val, label in STYLE_OPTIONS:
        active = " ✅" if (val == current or (val == "default" and not current)) else ""
        cb_val = val if val != "default" else ""
        rows.append(_row(_b(f"{label}{active}", f"{callback_prefix}:{key}:{locale}:{idx}:{cb_val}")))
    # Back
    if callback_prefix == "tpl:bss":
        rows.append(_row(_b("Назад", f"tpl:be:{key}:{locale}:{idx}", icon=HOME)))
    else:
        rows.append(_row(_b("Назад", f"tpl:rbe:{key}:{locale}:{idx}", icon=HOME)))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════════════════════════
#  Reply Buttons
# ═══════════════════════════════════════════════════════════════

def reply_btn_list_kb(key: str, locale: str) -> InlineKeyboardMarkup:
    flat = get_flat_reply_buttons(key, locale)
    rows: list[list[InlineKeyboardButton]] = []
    for i, btn in enumerate(flat):
        style = btn.get("style", "")
        s_icon = STYLE_ICON_EMOJI.get(style, "⬜")
        emoji_icon = "✨" if btn.get("icon_custom_emoji_id") else ""
        action = btn.get("action", "?")
        rows.append(_row(_b(f"{s_icon}{emoji_icon} {btn['text']} → {action}", f"tpl:rbe:{key}:{locale}:{i}", icon=APPS)))
    rows.append(_row(_b("Назад", f"tpl:view:{key}", icon=HOME)))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reply_btn_edit_kb(key: str, locale: str, idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(_b("Текст",  f"tpl:rbt:{key}:{locale}:{idx}", icon=PENCIL)),
        _row(_b("Стиль",  f"tpl:rbs:{key}:{locale}:{idx}", icon=("6050679691004612757"))),
        _row(_b("Emoji",  f"tpl:rbi:{key}:{locale}:{idx}", icon=BOX)),
        _row(_b("К reply кнопкам", f"tpl:rbl:{key}:{locale}", icon=HOME)),
    ])