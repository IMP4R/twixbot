# tpl/admin_handler.py
"""Роутер админки шаблонов — Premium Emoji + улучшенная компоновка текстов."""

import html as html_lib

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from tpl.manager import (
    get_template, update_template, update_button_at_index,
    remove_button_field, swap_button_action, get_flat_buttons,
    get_flat_reply_buttons, update_reply_button_at_index,
    remove_reply_button_field,
    reset_template, reset_template_all_locales, list_all_keys,
    get_template_locales,
)
from tpl.sender import send_template, render_text
from tpl.emoji import rebuild_text_with_emoji, extract_first_emoji_id
from tpl.locale import get_available_locales, get_default_locale
from tpl.admin_states import TplAdminStates
from tpl.admin_kb import (
    admin_main_kb, templates_list_kb, template_view_kb,
    locale_choice_kb, cancel_kb, btn_list_kb, btn_edit_kb, style_choice_kb,
    reply_btn_list_kb, reply_btn_edit_kb,
)
from tpl.admin_emoji import (
    TAG_SETTINGS, TAG_FOLDER, TAG_CROSS, TAG_PENCIL, TAG_TRASH, TAG_CHECK,
    TAG_EYE, TAG_LINK, TAG_CLIP, TAG_MEDIA_PHOTO,
    TAG_CHART_GROWTH, TAG_PROFILE, TAG_CODE, TAG_APPS, TAG_ADD_TEXT,
    TAG_LOADING, TAG_BELL, TAG_LOCK_CLOSED, TAG_LOCK_OPEN, TAG_CLOCK,
    TAG_BRUSH, TAG_BOX, TAG_INFO,
    ERR_CROSS, ERR_WARN,
)

E = html_lib.escape


# ══════════════════════════════════════════════════════════════════════
#  Info builders
# ══════════════════════════════════════════════════════════════════════

def _tmpl_info(key: str, locale: str = None) -> str:
    if locale is None:
        locale = get_default_locale()
    t = get_template(key, locale)
    mt = t.get("media_type", "none")
    has_media = mt != "none" and t.get("media_file_id")
    media_s = f"{TAG_CHECK} {mt}" if has_media else f"{TAG_CROSS} —"
    emoji_ids = t.get("custom_emoji_ids", [])
    emoji_s = f"{TAG_BOX} {len(emoji_ids)}" if emoji_ids else "—"
    locales = get_template_locales(key)
    locale_names = get_available_locales()
    lang_s = ", ".join(locale_names.get(l, l) for l in locales)

    # Inline buttons info
    flat = get_flat_buttons(key, locale)
    btn_lines = []
    for b in flat:
        style = b.get("style", "—")
        s_icon = {"primary": "🔵", "success": "🟢", "danger": "🔴"}.get(style, "⬜")
        ico = "✨" if b.get("icon_custom_emoji_id") else ""
        cb = b.get("callback_data") or b.get("url", "")
        btn_lines.append(f"  {s_icon}{ico} <b>{E(b['text'])}</b> → <code>{E(cb)}</code>")
    btn_text = "\n".join(btn_lines) if btn_lines else "  —"

    # Reply buttons info
    reply_flat = get_flat_reply_buttons(key, locale)
    reply_lines = []
    for b in reply_flat:
        action = b.get("action", "—")
        style = b.get("style", "—")
        s_icon = {"primary": "🔵", "success": "🟢", "danger": "🔴"}.get(style, "⬜")
        ico = "✨" if b.get("icon_custom_emoji_id") else ""
        reply_lines.append(f"  {s_icon}{ico} <b>{E(b['text'])}</b> → <code>{E(action)}</code>")
    reply_text = "\n".join(reply_lines) if reply_lines else ""

    raw_preview = t.get("text", "")[:300]
    if len(t.get("text", "")) > 300:
        raw_preview += "…"

    result = (
        f"{TAG_ADD_TEXT} <code>{E(key)}</code> [{E(locale)}]\n\n"
        f"{TAG_PENCIL} <b>Текст:</b>\n<pre>{E(raw_preview)}</pre>\n\n"
        f"{TAG_MEDIA_PHOTO} <b>Медиа:</b> {media_s}\n"
        f"{TAG_BOX} <b>Emoji:</b> {emoji_s}\n"
        f"🌐 <b>Языки:</b> {lang_s}\n"
        f"{TAG_CODE} <b>Inline кнопки ({len(flat)}):</b>\n{btn_text}"
    )
    if reply_text:
        result += f"\n{TAG_APPS} <b>Reply кнопки ({len(reply_flat)}):</b>\n{reply_text}"
    return result


def _btn_info(key: str, locale: str, idx: int) -> str:
    flat = get_flat_buttons(key, locale)
    if idx >= len(flat):
        return f"{ERR_CROSS} Не найдена"
    b = flat[idx]
    style = b.get("style") or "default"
    s_icon = {"primary": "🔵", "success": "🟢", "danger": "🔴"}.get(style, "⬜")
    ico = b.get("icon_custom_emoji_id") or "—"
    cb = b.get("callback_data") or b.get("url", "—")
    locale_name = get_available_locales().get(locale, locale)
    return (
        f"{TAG_CODE} <b>Кнопка #{idx + 1}</b> [{E(locale_name)}]\n\n"
        f"{TAG_PENCIL} Текст: <b>{E(b['text'])}</b>\n"
        f"{TAG_BRUSH} Стиль: {s_icon} <b>{E(style)}</b>\n"
        f"{TAG_BOX} Emoji: <code>{E(ico)}</code>\n"
        f"{TAG_LINK} Action: <code>{E(cb)}</code>"
    )


def _reply_btn_info(key: str, locale: str, idx: int) -> str:
    flat = get_flat_reply_buttons(key, locale)
    if idx >= len(flat):
        return f"{ERR_CROSS} Не найдена"
    b = flat[idx]
    style = b.get("style") or "default"
    s_icon = {"primary": "🔵", "success": "🟢", "danger": "🔴"}.get(style, "⬜")
    ico = b.get("icon_custom_emoji_id") or "—"
    locale_name = get_available_locales().get(locale, locale)
    return (
        f"{TAG_APPS} <b>Reply кнопка #{idx + 1}</b> [{E(locale_name)}]\n\n"
        f"{TAG_PENCIL} Текст: <b>{E(b['text'])}</b>\n"
        f"{TAG_BRUSH} Стиль: {s_icon} <b>{E(style)}</b>\n"
        f"{TAG_BOX} Emoji: <code>{E(ico)}</code>\n"
        f"🎯 Action: <code>{E(b.get('action', '—'))}</code>"
    )


# ══════════════════════════════════════════════════════════════════════
#  Preview variables
# ══════════════════════════════════════════════════════════════════════

_PREVIEW_VARS = {
    "name": "Тест", "user_id": "0", "balance": "100.00",
    "result_text": "Тестовый результат", "action": "Тест",
    "balance_text": "💰 100$ | 💎 50$",
}


def create_router(admin_ids: list[int], command: str = "templates", preview_variables: dict | None = None) -> Router:
    router = Router()
    pv = {**_PREVIEW_VARS, **(preview_variables or {})}

    def _is_admin(uid: int) -> bool:
        return uid in admin_ids

    # ── Базовая точка входа ──

    @router.message(Command(command))
    async def cmd_tpl(msg: Message, state: FSMContext):
        if not _is_admin(msg.from_user.id): return
        await state.clear()
        await state.set_state(TplAdminStates.tpl_main)
        await msg.answer(
            f"{TAG_SETTINGS} <b>Управление шаблонами</b>",
            parse_mode="HTML",
            reply_markup=admin_main_kb(),
        )

    @router.callback_query(F.data == "tpl:close")
    async def tpl_close(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        await state.clear()
        await cb.message.edit_text(f"{TAG_CHECK} Закрыто.")
        await cb.answer()

    @router.callback_query(F.data == "tpl:noop")
    async def tpl_noop(cb: CallbackQuery):
        await cb.answer()

    @router.callback_query(F.data == "tpl:back_main")
    async def tpl_back_main(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        await state.set_state(TplAdminStates.tpl_main)
        await cb.message.edit_text(
            f"{TAG_SETTINGS} <b>Управление шаблонами</b>",
            parse_mode="HTML",
            reply_markup=admin_main_kb(),
        )
        await cb.answer()

    # ── Дерево / Список ──

    @router.callback_query(F.data.startswith("tpl:list:"))
    async def tpl_list(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        page = int(cb.data.split(":")[2])
        await state.set_state(TplAdminStates.tpl_main)
        total = len(list_all_keys())
        await cb.message.edit_text(
            f"{TAG_FOLDER} <b>Шаблоны</b> ({total})",
            parse_mode="HTML",
            reply_markup=templates_list_kb(page),
        )
        await cb.answer()

    @router.callback_query(F.data.startswith("tpl:tree:"))
    async def tpl_tree(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        page = int(parts[-1])
        prefix = parts[2] if len(parts) > 3 else ""
        await state.set_state(TplAdminStates.tpl_main)
        title_prefix = f" [<code>{E(prefix)}</code>]" if prefix else ""
        await cb.message.edit_text(
            f"{TAG_FOLDER} <b>Дерево шаблонов</b>{title_prefix}",
            parse_mode="HTML",
            reply_markup=templates_list_kb(page, prefix=prefix or None),
        )
        await cb.answer()

    # ── Просмотр шаблона ──

    @router.callback_query(F.data.startswith("tpl:view:"))
    async def tpl_view(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        key = cb.data.split(":", 2)[2]
        dl = get_default_locale()
        await state.set_state(TplAdminStates.tpl_viewing)
        await state.update_data(tpl_key=key, tpl_locale=dl)
        await cb.message.edit_text(
            _tmpl_info(key, dl),
            parse_mode="HTML",
            reply_markup=template_view_kb(key),
        )
        await cb.answer()

    # ── Выбор локали ──

    @router.callback_query(F.data.startswith("tpl:lc:"))
    async def tpl_locale_choice(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        await state.update_data(tpl_key=parts[3])
        await cb.message.edit_text(
            f"🌐 <b>Выберите язык</b>\n\n{TAG_ADD_TEXT} <code>{E(parts[3])}</code>",
            parse_mode="HTML",
            reply_markup=locale_choice_kb(parts[3], parts[2]),
        )
        await cb.answer()

    # ── Предпросмотр ──

    @router.callback_query(F.data.startswith("tpl:pv:"))
    async def tpl_preview(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id):
            return
        parts = cb.data.split(":")
        key = parts[2]
        locale = parts[3] if len(parts) > 3 else get_default_locale()

        test_vars = {
            "name": "Тестовый товар",
            "description": "Тестовое описание",
            "price": "99.99",
            "amount": "99.99",
            "discount": "10",
            "discount_line": "🎯 Скидка: 10%\n",
            "final_price": "89.99",
            "original_price": "99.99",
            "order_id": "12345",
            "product_id": "123",
            "user_id": "0",
            "total_orders": "5",
            "total_spent": "499.95",
            "premium_status": "active",
            "premium_discount": "20",
            "premium_end_date": "2024-12-31",
            "referrals_count": "3",
            "earned": "50.00",
            "available": "25.00",
            "ref_link": "https://t.me/test_bot?start=ref_0",
            "language": "Русский",
            "balance": "100.00",
            "details": "Тестовые реквизиты",
            "withdrawals_list": "✅ $10.00 — 2024-01-01\n⏳ $5.00 — 2024-01-02",
            "orders_list": "\nТовар 1 — $10.00\nТовар 2 — $20.00",
            "cblink": "https://t.me/cryptobot?start=test",
            "pay_url": "https://t.me/cryptobot?start=test",
            "ton_link": "ton://transfer/test",
            "back_callback": "main_menu",
            "timeout_minutes": "60",
            "comment": "Test comment",
            "ton_amount": "0.0136",
            "usd_amount": "0.02",
            "days": "30",
            "until": "2024-12-31",
            "days_left": "5",
            "category": "Тестовая категория",
        }

        await cb.answer(f"{TAG_EYE} Превью...")
        try:
            local_vars = {
                **test_vars,
                "name": cb.from_user.full_name,
                "user_id": str(cb.from_user.id),
            }
            await send_template(cb.message, key, local_vars, locale=locale)
        except Exception as ex:
            await cb.message.answer(f"{ERR_CROSS} {ex}")

    # ── Сброс ──

    @router.callback_query(F.data.startswith("tpl:rs:"))
    async def tpl_reset_ask(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale = parts[2], parts[3] if len(parts) > 3 else get_default_locale()
        ln = get_available_locales().get(locale, locale)
        await cb.message.edit_text(
            f"{TAG_TRASH} <b>Сбросить</b> <code>{E(key)}</code> [{E(ln)}]?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"Только {ln}",
                    callback_data=f"tpl:rsc:{key}:{locale}",
                )],
                [InlineKeyboardButton(
                    text="Все языки",
                    callback_data=f"tpl:rsa:{key}",
                )],
                [InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"tpl:view:{key}",
                )],
            ]),
        )
        await cb.answer()

    @router.callback_query(F.data.startswith("tpl:rsc:"))
    async def tpl_reset_one(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale = parts[2], parts[3]
        reset_template(key, locale)
        await cb.message.edit_text(
            f"{TAG_CHECK} [{E(locale)}]\n\n{_tmpl_info(key, locale)}",
            parse_mode="HTML",
            reply_markup=template_view_kb(key),
        )
        await cb.answer(f"{TAG_CHECK}")

    @router.callback_query(F.data.startswith("tpl:rsa:"))
    async def tpl_reset_all(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id): return
        key = cb.data.split(":")[2]
        reset_template_all_locales(key)
        dl = get_default_locale()
        await cb.message.edit_text(
            f"{TAG_CHECK} Все языки\n\n{_tmpl_info(key, dl)}",
            parse_mode="HTML",
            reply_markup=template_view_kb(key),
        )
        await cb.answer(f"{TAG_CHECK}")

    # ── Edit text ──

    @router.callback_query(F.data.startswith("tpl:et:"))
    async def tpl_edit_text(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale = parts[2], parts[3] if len(parts) > 3 else get_default_locale()
        t = get_template(key, locale)
        ln = get_available_locales().get(locale, locale)
        await state.set_state(TplAdminStates.tpl_edit_text)
        await state.update_data(tpl_key=key, tpl_locale=locale)
        await cb.message.edit_text(
            f"{TAG_PENCIL} <b>{E(key)}</b> [{E(ln)}]\n\n"
            f"<pre>{E(t.get('text', '')[:800])}</pre>\n\n"
            f"Отправьте новый текст.\n"
            f"{TAG_INFO} Premium emoji поддерживаются.",
            parse_mode="HTML",
            reply_markup=cancel_kb(f"tpl:view:{key}"),
        )
        await cb.answer()

    @router.message(TplAdminStates.tpl_edit_text)
    async def tpl_text_input(msg: Message, state: FSMContext):
        if not _is_admin(msg.from_user.id): return
        if not (msg.text or msg.caption):
            await msg.answer(f"{ERR_CROSS} Нужен текст.")
            return
        data = await state.get_data()
        key, locale = data["tpl_key"], data["tpl_locale"]
        update_template(key, locale=locale, text=rebuild_text_with_emoji(msg))
        eids = get_template(key, locale).get("custom_emoji_ids", [])
        note = f"\n{TAG_BOX} Custom emoji: {len(eids)}" if eids else ""
        await state.set_state(TplAdminStates.tpl_viewing)
        await msg.answer(
            f"{TAG_CHECK}{note}\n\n{_tmpl_info(key, locale)}",
            parse_mode="HTML",
            reply_markup=template_view_kb(key),
        )

    # ── Edit media ──

    @router.callback_query(F.data.startswith("tpl:em:"))
    async def tpl_edit_media(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale = parts[2], parts[3] if len(parts) > 3 else get_default_locale()
        ln = get_available_locales().get(locale, locale)
        await state.set_state(TplAdminStates.tpl_edit_media)
        await state.update_data(tpl_key=key, tpl_locale=locale)
        await cb.message.edit_text(
            f"{TAG_MEDIA_PHOTO} <b>{E(key)}</b> [{E(ln)}]\n\n"
            f"Отправьте фото, GIF или видео.",
            parse_mode="HTML",
            reply_markup=cancel_kb(f"tpl:view:{key}"),
        )
        await cb.answer()

    @router.message(TplAdminStates.tpl_edit_media)
    async def tpl_media_input(msg: Message, state: FSMContext):
        if not _is_admin(msg.from_user.id): return
        data = await state.get_data()
        key, locale = data["tpl_key"], data["tpl_locale"]
        if msg.photo:
            update_template(key, locale=locale, media_type="photo", media_file_id=msg.photo[-1].file_id)
            label = "Фото"
        elif msg.animation:
            update_template(key, locale=locale, media_type="animation", media_file_id=msg.animation.file_id)
            label = "GIF"
        elif msg.video:
            update_template(key, locale=locale, media_type="video", media_file_id=msg.video.file_id)
            label = "Видео"
        else:
            await msg.answer(
                f"{ERR_CROSS} Фото, GIF или видео.",
                reply_markup=cancel_kb(f"tpl:view:{key}"),
            )
            return
        if msg.caption:
            update_template(key, locale=locale, text=rebuild_text_with_emoji(msg))
        await state.set_state(TplAdminStates.tpl_viewing)
        await msg.answer(
            f"{TAG_CHECK} {label}!\n\n{_tmpl_info(key, locale)}",
            parse_mode="HTML",
            reply_markup=template_view_kb(key),
        )

    @router.callback_query(F.data.startswith("tpl:rm:"))
    async def tpl_remove_media(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale = parts[2], parts[3] if len(parts) > 3 else get_default_locale()
        update_template(key, locale=locale, media_type="none", media_file_id="")
        await cb.message.edit_text(
            f"{TAG_CHECK} Медиа удалено!\n\n{_tmpl_info(key, locale)}",
            parse_mode="HTML",
            reply_markup=template_view_kb(key),
        )
        await cb.answer(f"{TAG_CHECK}")

    # ══════════════════════════════════════════
    #  INLINE BUTTONS
    # ══════════════════════════════════════════

    @router.callback_query(F.data.startswith("tpl:bl:"))
    async def tpl_btn_list(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale = parts[2], parts[3] if len(parts) > 3 else get_default_locale()
        if not get_flat_buttons(key, locale):
            await cb.answer("Нет кнопок!", show_alert=True)
            return
        await state.set_state(TplAdminStates.tpl_btn_list)
        await state.update_data(tpl_key=key, tpl_locale=locale)
        ln = get_available_locales().get(locale, locale)
        await cb.message.edit_text(
            f"{TAG_CODE} <b>Inline кнопки:</b> <code>{E(key)}</code> [{E(ln)}]",
            parse_mode="HTML",
            reply_markup=btn_list_kb(key, locale),
        )
        await cb.answer()

    @router.callback_query(F.data.startswith("tpl:be:"))
    async def tpl_btn_view(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        await state.update_data(tpl_key=key, tpl_locale=locale, tpl_btn_idx=idx)
        await cb.message.edit_text(
            _btn_info(key, locale, idx),
            parse_mode="HTML",
            reply_markup=btn_edit_kb(key, locale, idx),
        )
        await cb.answer()

    # button text
    @router.callback_query(F.data.startswith("tpl:bt:"))
    async def tpl_btn_text_start(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        flat = get_flat_buttons(key, locale)
        await state.set_state(TplAdminStates.tpl_btn_edit_text)
        await state.update_data(tpl_key=key, tpl_locale=locale, tpl_btn_idx=idx)
        await cb.message.edit_text(
            f"{TAG_PENCIL} Текущий: <b>{E(flat[idx]['text'])}</b>\n\nВведите новый:",
            parse_mode="HTML",
            reply_markup=cancel_kb(f"tpl:be:{key}:{locale}:{idx}"),
        )
        await cb.answer()

    @router.message(TplAdminStates.tpl_btn_edit_text)
    async def tpl_btn_text_input(msg: Message, state: FSMContext):
        if not _is_admin(msg.from_user.id): return
        if not msg.text:
            await msg.answer(f"{ERR_CROSS} Нужен текст.")
            return
        data = await state.get_data()
        key, locale, idx = data["tpl_key"], data["tpl_locale"], data["tpl_btn_idx"]
        update_button_at_index(key, idx, locale=locale, text=msg.text.strip())
        await state.set_state(TplAdminStates.tpl_btn_list)
        await msg.answer(
            f"{TAG_CHECK}\n\n{_btn_info(key, locale, idx)}",
            parse_mode="HTML",
            reply_markup=btn_edit_kb(key, locale, idx),
        )

    # button style
    @router.callback_query(F.data.startswith("tpl:bs:"))
    async def tpl_btn_style(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        await cb.message.edit_text(
            f"{TAG_BRUSH} <b>Стиль inline #{idx + 1}</b>",
            parse_mode="HTML",
            reply_markup=style_choice_kb(key, locale, idx, "tpl:bss"),
        )
        await cb.answer()

    @router.callback_query(F.data.startswith("tpl:bss:"))
    async def tpl_btn_style_set(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        style = parts[5] if len(parts) > 5 and parts[5] else ""
        if style:
            update_button_at_index(key, idx, locale=locale, style=style)
        else:
            remove_button_field(key, idx, "style", locale=locale)
        await cb.answer(f"{TAG_CHECK} {style or 'default'}", show_alert=True)
        await cb.message.edit_text(
            _btn_info(key, locale, idx),
            parse_mode="HTML",
            reply_markup=btn_edit_kb(key, locale, idx),
        )

    # button emoji icon
    @router.callback_query(F.data.startswith("tpl:bi:"))
    async def tpl_btn_emoji_start(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        flat = get_flat_buttons(key, locale)
        current = flat[idx].get("icon_custom_emoji_id", "") if idx < len(flat) else ""
        await state.set_state(TplAdminStates.tpl_btn_edit_emoji)
        await state.update_data(tpl_key=key, tpl_locale=locale, tpl_btn_idx=idx)
        await cb.message.edit_text(
            f"{TAG_BOX} <b>Emoji inline #{idx + 1}</b>\n\n"
            f"Текущий: <code>{E(current or '—')}</code>\n\n"
            f"Отправьте Premium emoji или ID.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Убрать",
                    callback_data=f"tpl:bir:{key}:{locale}:{idx}",
                )],
                [InlineKeyboardButton(
                    text="Назад",
                    callback_data=f"tpl:be:{key}:{locale}:{idx}",
                )],
            ]),
        )
        await cb.answer()

    @router.callback_query(F.data.startswith("tpl:bir:"))
    async def tpl_btn_emoji_remove(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        remove_button_field(key, idx, "icon_custom_emoji_id", locale=locale)
        await cb.answer(f"{TAG_CHECK}", show_alert=True)
        await state.set_state(TplAdminStates.tpl_btn_list)
        await cb.message.edit_text(
            _btn_info(key, locale, idx),
            parse_mode="HTML",
            reply_markup=btn_edit_kb(key, locale, idx),
        )

    @router.message(TplAdminStates.tpl_btn_edit_emoji)
    async def tpl_btn_emoji_input(msg: Message, state: FSMContext):
        if not _is_admin(msg.from_user.id): return
        data = await state.get_data()
        key, locale, idx = data["tpl_key"], data["tpl_locale"], data["tpl_btn_idx"]
        emoji_id = extract_first_emoji_id(msg)
        if not emoji_id and msg.text and msg.text.strip().isdigit():
            emoji_id = msg.text.strip()
        if not emoji_id:
            await msg.answer(f"{ERR_CROSS} Отправьте Premium emoji или ID.")
            return
        update_button_at_index(key, idx, locale=locale, icon_custom_emoji_id=emoji_id)
        await state.set_state(TplAdminStates.tpl_btn_list)
        await msg.answer(
            f"{TAG_CHECK} <code>{E(emoji_id)}</code>\n\n{_btn_info(key, locale, idx)}",
            parse_mode="HTML",
            reply_markup=btn_edit_kb(key, locale, idx),
        )

    # button callback_data / url
    @router.callback_query(F.data.startswith("tpl:bc:"))
    async def tpl_btn_cb_start(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        b = get_flat_buttons(key, locale)[idx]
        await state.set_state(TplAdminStates.tpl_btn_edit_callback)
        await state.update_data(tpl_key=key, tpl_locale=locale, tpl_btn_idx=idx)
        await cb.message.edit_text(
            f"{TAG_LINK} <b>#{idx + 1}</b>\n\n"
            f"Callback: <code>{E(b.get('callback_data', '—'))}</code>\n"
            f"URL: <code>{E(b.get('url', '—'))}</code>\n\n"
            f"<code>my:callback</code> → callback\n"
            f"<code>https://...</code> → URL",
            parse_mode="HTML",
            reply_markup=cancel_kb(f"tpl:be:{key}:{locale}:{idx}"),
        )
        await cb.answer()

    @router.message(TplAdminStates.tpl_btn_edit_callback)
    async def tpl_btn_cb_input(msg: Message, state: FSMContext):
        if not _is_admin(msg.from_user.id): return
        if not msg.text:
            await msg.answer(f"{ERR_CROSS} Нужен текст.")
            return
        data = await state.get_data()
        key, locale, idx = data["tpl_key"], data["tpl_locale"], data["tpl_btn_idx"]
        swap_button_action(key, idx, msg.text.strip(), locale=locale)
        await state.set_state(TplAdminStates.tpl_btn_list)
        await msg.answer(
            f"{TAG_CHECK}\n\n{_btn_info(key, locale, idx)}",
            parse_mode="HTML",
            reply_markup=btn_edit_kb(key, locale, idx),
        )

    # ══════════════════════════════════════════
    #  REPLY BUTTONS
    # ══════════════════════════════════════════

    @router.callback_query(F.data.startswith("tpl:rbl:"))
    async def tpl_reply_btn_list(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale = parts[2], parts[3] if len(parts) > 3 else get_default_locale()
        if not get_flat_reply_buttons(key, locale):
            await cb.answer("Нет reply кнопок!", show_alert=True)
            return
        await state.set_state(TplAdminStates.tpl_reply_btn_list)
        await state.update_data(tpl_key=key, tpl_locale=locale)
        ln = get_available_locales().get(locale, locale)
        await cb.message.edit_text(
            f"{TAG_APPS} <b>Reply кнопки:</b> <code>{E(key)}</code> [{E(ln)}]",
            parse_mode="HTML",
            reply_markup=reply_btn_list_kb(key, locale),
        )
        await cb.answer()

    @router.callback_query(F.data.startswith("tpl:rbe:"))
    async def tpl_reply_btn_view(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        await state.update_data(tpl_key=key, tpl_locale=locale, tpl_reply_btn_idx=idx)
        await cb.message.edit_text(
            _reply_btn_info(key, locale, idx),
            parse_mode="HTML",
            reply_markup=reply_btn_edit_kb(key, locale, idx),
        )
        await cb.answer()

    # reply text
    @router.callback_query(F.data.startswith("tpl:rbt:"))
    async def tpl_reply_btn_text_start(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        flat = get_flat_reply_buttons(key, locale)
        await state.set_state(TplAdminStates.tpl_reply_btn_edit_text)
        await state.update_data(tpl_key=key, tpl_locale=locale, tpl_reply_btn_idx=idx)
        await cb.message.edit_text(
            f"{TAG_PENCIL} Текущий: <b>{E(flat[idx]['text'])}</b>\n\nВведите новый текст:",
            parse_mode="HTML",
            reply_markup=cancel_kb(f"tpl:rbe:{key}:{locale}:{idx}"),
        )
        await cb.answer()

    @router.message(TplAdminStates.tpl_reply_btn_edit_text)
    async def tpl_reply_btn_text_input(msg: Message, state: FSMContext):
        if not _is_admin(msg.from_user.id): return
        if not msg.text:
            await msg.answer(f"{ERR_CROSS} Нужен текст.")
            return
        data = await state.get_data()
        key, locale, idx = data["tpl_key"], data["tpl_locale"], data["tpl_reply_btn_idx"]
        update_reply_button_at_index(key, idx, locale=locale, text=msg.text.strip())
        await state.set_state(TplAdminStates.tpl_reply_btn_list)
        await msg.answer(
            f"{TAG_CHECK}\n\n{_reply_btn_info(key, locale, idx)}"
            f"\n\n{TAG_INFO} Изменения видны после следующей отправки шаблона.",
            parse_mode="HTML",
            reply_markup=reply_btn_edit_kb(key, locale, idx),
        )

    # reply style
    @router.callback_query(F.data.startswith("tpl:rbs:"))
    async def tpl_reply_btn_style(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        await cb.message.edit_text(
            f"{TAG_BRUSH} <b>Стиль reply #{idx + 1}</b>",
            parse_mode="HTML",
            reply_markup=style_choice_kb(key, locale, idx, "tpl:rbss"),
        )
        await cb.answer()

    @router.callback_query(F.data.startswith("tpl:rbss:"))
    async def tpl_reply_btn_style_set(cb: CallbackQuery):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        style = parts[5] if len(parts) > 5 and parts[5] else ""
        if style:
            update_reply_button_at_index(key, idx, locale=locale, style=style)
        else:
            remove_reply_button_field(key, idx, "style", locale=locale)
        await cb.answer(f"{TAG_CHECK} {style or 'default'}", show_alert=True)
        await cb.message.edit_text(
            _reply_btn_info(key, locale, idx),
            parse_mode="HTML",
            reply_markup=reply_btn_edit_kb(key, locale, idx),
        )

    # reply emoji
    @router.callback_query(F.data.startswith("tpl:rbi:"))
    async def tpl_reply_btn_emoji_start(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        flat = get_flat_reply_buttons(key, locale)
        current = flat[idx].get("icon_custom_emoji_id", "") if idx < len(flat) else ""
        await state.set_state(TplAdminStates.tpl_reply_btn_edit_emoji)
        await state.update_data(tpl_key=key, tpl_locale=locale, tpl_reply_btn_idx=idx)
        await cb.message.edit_text(
            f"{TAG_BOX} <b>Emoji reply #{idx + 1}</b>\n\n"
            f"Текущий: <code>{E(current or '—')}</code>\n\n"
            f"Отправьте Premium emoji или ID.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Убрать",
                    callback_data=f"tpl:rbir:{key}:{locale}:{idx}",
                )],
                [InlineKeyboardButton(
                    text="Назад",
                    callback_data=f"tpl:rbe:{key}:{locale}:{idx}",
                )],
            ]),
        )
        await cb.answer()

    @router.callback_query(F.data.startswith("tpl:rbir:"))
    async def tpl_reply_btn_emoji_remove(cb: CallbackQuery, state: FSMContext):
        if not _is_admin(cb.from_user.id): return
        parts = cb.data.split(":")
        key, locale, idx = parts[2], parts[3], int(parts[4])
        remove_reply_button_field(key, idx, "icon_custom_emoji_id", locale=locale)
        await cb.answer(f"{TAG_CHECK}", show_alert=True)
        await state.set_state(TplAdminStates.tpl_reply_btn_list)
        await cb.message.edit_text(
            _reply_btn_info(key, locale, idx),
            parse_mode="HTML",
            reply_markup=reply_btn_edit_kb(key, locale, idx),
        )

    @router.message(TplAdminStates.tpl_reply_btn_edit_emoji)
    async def tpl_reply_btn_emoji_input(msg: Message, state: FSMContext):
        if not _is_admin(msg.from_user.id): return
        data = await state.get_data()
        key, locale, idx = data["tpl_key"], data["tpl_locale"], data["tpl_reply_btn_idx"]
        emoji_id = extract_first_emoji_id(msg)
        if not emoji_id and msg.text and msg.text.strip().isdigit():
            emoji_id = msg.text.strip()
        if not emoji_id:
            await msg.answer(f"{ERR_CROSS} Отправьте Premium emoji или ID.")
            return
        update_reply_button_at_index(key, idx, locale=locale, icon_custom_emoji_id=emoji_id)
        await state.set_state(TplAdminStates.tpl_reply_btn_list)
        await msg.answer(
            f"{TAG_CHECK} <code>{E(emoji_id)}</code>\n\n{_reply_btn_info(key, locale, idx)}"
            f"\n\n{TAG_INFO} Изменения видны после следующей отправки шаблона.",
            parse_mode="HTML",
            reply_markup=reply_btn_edit_kb(key, locale, idx),
        )

    return router