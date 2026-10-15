# settings/inline.py
"""API for embedding settings into any screen (not just auto-admin panel).

Usage:
    from settings.inline import (
        setting_toggle_button, setting_edit_button, setting_display,
        create_inline_router,
    )

    # Bool toggle button:
    toggle = await setting_toggle_button("tickets.enabled")
    # → {"text": "Выкл Начисление тикетов", "callback_data": "set:toggle:tickets.enabled"}

    # Edit button:
    edit = await setting_edit_button("tickets.threshold")
    # → {"text": "Сумма для 1 тикета (₽): 2000 ✏️", "callback_data": "set:edit:tickets.threshold"}

    # Display line:
    text = await setting_display("tickets.enabled")   # → "✅ Вкл"

Router: dp.include_router(create_inline_router(admin_ids))
In main.py call setup_inline_router() which creates and registers it.
"""
from __future__ import annotations

from decimal import Decimal
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Filter
from aiogram import F

from settings.schema import get_def
from settings.runtime import get, set as set_value, format_value_short
from settings.types import BoolSetting


class InlineSettingStates(StatesGroup):
    edit_value = State()


PREFIX_TOGGLE = "set:toggle:"
PREFIX_EDIT = "set:edit:"


# ── Display ─────────────────────────────────────────────────────────────────

async def setting_display(key: str) -> str:
    sd = get_def(key)
    if not sd:
        return "—"
    value = await get(key)
    return format_value_short(key, value)


# ── Buttons ─────────────────────────────────────────────────────────────────

async def setting_toggle_button(key: str) -> dict:
    sd = get_def(key)
    value = await get(key)
    current = bool(value)
    title = sd.title if sd else key
    action = "Выкл" if current else "Вкл"
    return {
        "text": f"{action} {title}",
        "callback_data": f"{PREFIX_TOGGLE}{key}",
    }


async def setting_edit_button(key: str) -> dict:
    sd = get_def(key)
    value = await get(key)
    title = sd.title if sd else key
    display = format_value_short(key, value)
    return {
        "text": f"{title}: {display} ✏️",
        "callback_data": f"{PREFIX_EDIT}{key}",
    }


# ── Router ──────────────────────────────────────────────────────────────────

def create_inline_router(admin_ids: list[int]) -> Router:
    router = Router(name="settings_inline")

    def _is_admin(user_id: int) -> bool:
        return user_id in admin_ids

    @router.callback_query(F.data.startswith(PREFIX_TOGGLE))
    async def handle_toggle(callback: CallbackQuery):
        key = callback.data[len(PREFIX_TOGGLE):]
        if not _is_admin(callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        value = await get(key)
        new_val = not bool(value)
        await set_value(key, new_val)
        await callback.answer(
            f"{'✅ Вкл' if new_val else '❌ Выкл'}", show_alert=False
        )

    @router.callback_query(F.data.startswith(PREFIX_EDIT))
    async def handle_edit_start(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        key = callback.data[len(PREFIX_EDIT):]
        if not _is_admin(callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        sd = get_def(key)
        if not sd:
            await callback.answer("Настройка не найдена", show_alert=True)
            return
        title = sd.title or key
        current = format_value_short(key, await get(key))
        hint = sd.description or ""
        await state.set_state(InlineSettingStates.edit_value)
        await state.update_data(edit_setting_key=key)
        lines = [f"<b>{title}</b>", f"Текущее: <b>{current}</b>"]
        if hint:
            lines.append(hint)
        lines.append("\nВведите новое значение:")
        await callback.message.answer("\n".join(lines), parse_mode="HTML")
        try:
            await callback.message.delete()
        except Exception:
            pass

    @router.message(InlineSettingStates.edit_value)
    async def handle_edit_value(message: Message, state: FSMContext):
        data = await state.get_data()
        key = data.get("edit_setting_key")
        if not key:
            await message.answer("Ошибка: ключ не найден.")
            await state.clear()
            return
        sd = get_def(key)
        if not sd:
            await message.answer("Ошибка: настройка не найдена.")
            await state.clear()
            return

        raw = message.text.strip()
        try:
            if isinstance(sd, BoolSetting):
                r = raw.lower()
                if r in ("вкл", "on", "true", "1", "yes", "да"):
                    parsed = True
                elif r in ("выкл", "off", "false", "0", "no", "нет"):
                    parsed = False
                else:
                    parsed = sd.parse(raw)
            else:
                parsed = sd.parse(raw)
            sd.validate(parsed)
        except (ValueError, TypeError) as e:
            await message.answer(f"❌ {e}")
            return

        await set_value(key, parsed)
        display = format_value_short(key, parsed)
        await message.answer(f"✅ {sd.title}: <b>{display}</b>")
        await state.clear()

    return router
