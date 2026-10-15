from __future__ import annotations
import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from settings.admin_states import SetAdminStates
from settings.admin_kb import (
    categories_kb, settings_list_kb, view_setting_kb,
)
from settings.admin_emoji import (
    TAG_SETTINGS, TAG_CHECK, ERR_CROSS, TAG_INFO,
)
from settings.schema import get_categories, get_by_category, get_def
from settings.runtime import get, set, reset, format_value_short


def create_admin_router(
    admin_ids: list[int],
    command: str = "settings",
) -> Router:
    router = Router(name="settings_admin")

    def is_admin(user_id: int) -> bool:
        return user_id in admin_ids

    # ── Entry ──

    @router.message(Command(command))
    async def entry(msg: Message, state: FSMContext):
        if not is_admin(msg.from_user.id):
            await msg.answer(f"{ERR_CROSS} Нет доступа.")
            return
        await state.set_state(SetAdminStates.set_main)
        cats = get_categories()
        await msg.answer(
            f"{TAG_SETTINGS} <b>Настройки</b>\nВыберите категорию:",
            reply_markup=categories_kb(cats),
        )

    # ── Back to categories ──

    @router.callback_query(F.data == "set_main", SetAdminStates.set_category)
    @router.callback_query(F.data == "set_main", SetAdminStates.set_editing)
    async def go_main(cb: CallbackQuery, state: FSMContext):
        await state.set_state(SetAdminStates.set_main)
        cats = get_categories()
        await cb.message.edit_text(
            f"{TAG_SETTINGS} <b>Настройки</b>\nВыберите категорию:",
            reply_markup=categories_kb(cats),
        )
        await cb.answer()

    # ── Open category ──

    @router.callback_query(F.data.startswith("set_cat:"), SetAdminStates.set_main)
    @router.callback_query(F.data.startswith("set_cat:"), SetAdminStates.set_category)
    @router.callback_query(F.data.startswith("set_cat:"), SetAdminStates.set_editing)
    async def open_category(cb: CallbackQuery, state: FSMContext):
        parts = cb.data.split(":", 2)
        category = parts[1]
        page = int(parts[2]) if len(parts) > 2 else 0

        await state.set_state(SetAdminStates.set_category)
        defs = get_by_category(category)
        values = {}
        for sd in defs:
            v = await get(sd.key)
            values[sd.key] = format_value_short(sd.key, v)

        await cb.message.edit_text(
            f"{TAG_SETTINGS} <b>{category.capitalize()}</b>\nНастроек: {len(defs)}",
            reply_markup=settings_list_kb(category, defs, values, page),
        )
        await cb.answer()

    # ── View / edit setting ──

    @router.callback_query(F.data.startswith("set_view:"), SetAdminStates.set_category)
    async def view_setting(cb: CallbackQuery, state: FSMContext):
        key = cb.data.split(":", 1)[1]
        sd = get_def(key)
        if not sd:
            await cb.answer(f"{ERR_CROSS} Не найдено.", show_alert=True)
            return

        await state.set_state(SetAdminStates.set_editing)
        await state.update_data(edit_key=key)

        value = await get(key)
        val_text = format_value_short(key, value)

        text = (
            f"{TAG_INFO} <b>{sd.title}</b>\n"
            f"<i>{sd.description}</i>\n\n"
            f"Текущее значение: <code>{val_text}</code>"
        )
        await cb.message.edit_text(text, reply_markup=view_setting_kb(key, sd, str(value)))
        await cb.answer()

    # ── Toggle bool ──

    @router.callback_query(F.data.startswith("set_toggle:"), SetAdminStates.set_editing)
    async def toggle_bool(cb: CallbackQuery, state: FSMContext):
        _, key, raw = cb.data.split(":", 2)
        new_val = raw == "true"
        try:
            await set(key, new_val)
        except ValueError as e:
            await cb.answer(f"{ERR_CROSS} {e}", show_alert=True)
            return

        sd = get_def(key)
        value = await get(key)
        val_text = format_value_short(key, value)
        text = (
            f"{TAG_INFO} <b>{sd.title}</b>\n"
            f"<i>{sd.description}</i>\n\n"
            f"Текущее значение: <code>{val_text}</code>"
        )
        await cb.message.edit_text(text, reply_markup=view_setting_kb(key, sd, str(value)))
        await cb.answer(f"{TAG_CHECK} Сохранено!")

    # ── Enum select ──

    @router.callback_query(F.data.startswith("set_enum:"), SetAdminStates.set_editing)
    async def select_enum(cb: CallbackQuery, state: FSMContext):
        _, key, opt = cb.data.split(":", 2)
        try:
            await set(key, opt)
        except ValueError as e:
            await cb.answer(f"{ERR_CROSS} {e}", show_alert=True)
            return

        sd = get_def(key)
        value = await get(key)
        val_text = format_value_short(key, value)
        text = (
            f"{TAG_INFO} <b>{sd.title}</b>\n"
            f"<i>{sd.description}</i>\n\n"
            f"Текущее значение: <code>{val_text}</code>"
        )
        await cb.message.edit_text(text, reply_markup=view_setting_kb(key, sd, str(value)))
        await cb.answer(f"{TAG_CHECK} Сохранено!")

    # ── Prompt for input ──

    @router.callback_query(F.data.startswith("set_input:"), SetAdminStates.set_editing)
    async def prompt_input(cb: CallbackQuery, state: FSMContext):
        key = cb.data.split(":", 1)[1]
        await state.set_state(SetAdminStates.set_input_value)
        await state.update_data(edit_key=key)
        await cb.message.answer(
            f"{TAG_SETTINGS} Введите новое значение для <b>{key}</b>:"
        )
        await cb.answer()

    # ── Receive input value ──

    @router.message(SetAdminStates.set_input_value)
    async def receive_input(msg: Message, state: FSMContext):
        data = await state.get_data()
        key = data.get("edit_key")
        if not key:
            await msg.answer(f"{ERR_CROSS} Ошибка состояния.")
            await state.clear()
            return

        sd = get_def(key)
        raw = msg.text.strip()

        from settings.types import (
            BoolSetting, IntSetting, FloatSetting, DecimalSetting,
            StrSetting, JsonSetting, ListSetting, TierSetting, DurationSetting,
        )

        parsed = raw
        if isinstance(sd, IntSetting):
            try:
                parsed = int(raw)
            except ValueError:
                await msg.answer(f"{ERR_CROSS} Введите целое число.")
                return
        elif isinstance(sd, FloatSetting):
            try:
                parsed = float(raw)
            except ValueError:
                await msg.answer(f"{ERR_CROSS} Введите число.")
                return
        elif isinstance(sd, DecimalSetting):
            try:
                from decimal import Decimal as D
                parsed = D(raw)
            except Exception:
                await msg.answer(f"{ERR_CROSS} Введите число (Decimal).")
                return
        elif isinstance(sd, DurationSetting):
            try:
                parsed = int(raw)
            except ValueError:
                await msg.answer(f"{ERR_CROSS} Введите количество секунд (число).")
                return
        elif isinstance(sd, TierSetting):
            import json as _json
            parsed = None
            # Try display format first: "500→0.2, 1000→0.4"
            try:
                items = []
                for part in raw.split(","):
                    part = part.strip()
                    if "→" in part:
                        max_str, rate_str = part.split("→", 1)
                    elif ":" in part:
                        max_str, rate_str = part.split(":", 1)
                    else:
                        continue
                    items.append({"max": int(max_str.strip()), "rate": float(rate_str.strip())})
                if items:
                    parsed = items
            except Exception:
                pass
            if parsed is None:
                try:
                    parsed = _json.loads(raw)
                except _json.JSONDecodeError:
                    await msg.answer(f"{ERR_CROSS} Введите JSON-список с полями max и rate, или формат: 500→0.2, 1000→0.4")
                    return
            if not isinstance(parsed, list):
                await msg.answer(f"{ERR_CROSS} Должен быть список.")
                return
        elif isinstance(sd, (JsonSetting, ListSetting)):
            import json as _json
            try:
                parsed = _json.loads(raw)
            except _json.JSONDecodeError:
                await msg.answer(f"{ERR_CROSS} Введите валидный JSON.")
                return

        try:
            await set(key, parsed)
        except ValueError as e:
            await msg.answer(f"{ERR_CROSS} {e}")
            return

        await state.set_state(SetAdminStates.set_editing)
        value = await get(key)
        val_text = format_value_short(key, value)
        text = (
            f"{TAG_INFO} <b>{sd.title}</b>\n"
            f"<i>{sd.description}</i>\n\n"
            f"Текущее значение: <code>{val_text}</code>"
        )
        await msg.answer(text, reply_markup=view_setting_kb(key, sd, str(value)))
        await msg.answer(f"{TAG_CHECK} Сохранено!")
        await msg.delete()

    # ── Reset setting ──

    @router.callback_query(F.data.startswith("set_reset:"), SetAdminStates.set_editing)
    async def reset_setting(cb: CallbackQuery, state: FSMContext):
        key = cb.data.split(":", 1)[1]
        await reset(key)

        sd = get_def(key)
        if not sd:
            await cb.answer(f"{ERR_CROSS} Не найдено.", show_alert=True)
            return

        value = await get(key)
        val_text = format_value_short(key, value)
        text = (
            f"{TAG_INFO} <b>{sd.title}</b>\n"
            f"<i>{sd.description}</i>\n\n"
            f"Текущее значение: <code>{val_text}</code>"
        )
        await cb.message.edit_text(text, reply_markup=view_setting_kb(key, sd, str(value)))
        await cb.answer(f"{TAG_CHECK} Сброшено к default.")

    return router