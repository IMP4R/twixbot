# tpl/builder.py
"""Keyboard builder API — clean inline keyboard construction.

Usage:
    from tpl.builder import KeyboardBuilder

    kb = KeyboardBuilder()
    kb.add("Отключить", callback="toggle", icon="5870982283724328568")
    kb.add("Изменить", callback="edit")
    kb.add_back("admin_tickets")
    rows = kb.build()  # → [[{...}], [{...}], [{...}]]

    # Pass to edit_template:
    await tpl.edit_template(callback, "admin.tickets", {}, extra_buttons=kb.build())
"""
from __future__ import annotations


class KeyboardBuilder:
    """Fluent builder for inline keyboard button rows."""

    def __init__(self):
        self._rows: list[list[dict]] = [[]]

    def add(
        self,
        text: str,
        *,
        callback: str = "",
        url: str = "",
        icon: str = "",
        new_row: bool = True,
    ) -> KeyboardBuilder:
        """Add a button. If new_row=True (default), starts a new row."""
        btn = {"text": text}
        if callback:
            btn["callback_data"] = callback
        if url:
            btn["url"] = url
        if icon:
            btn["icon_custom_emoji_id"] = icon

        if new_row or not self._rows[-1]:
            self._rows.append([btn])
        else:
            self._rows[-1].append(btn)
        return self

    def add_same_row(
        self,
        text: str,
        *,
        callback: str = "",
        url: str = "",
        icon: str = "",
    ) -> KeyboardBuilder:
        """Add a button in the same row as the previous one."""
        return self.add(text, callback=callback, url=url, icon=icon, new_row=False)

    def add_back(self, callback_data: str, icon: str = "5963103826075456248") -> KeyboardBuilder:
        """Add a 'Назад' button in its own row."""
        return self.add("Назад", callback=callback_data, icon=icon, new_row=True)

    def build(self) -> list[list[dict]]:
        """Return built button rows (empty rows filtered out)."""
        return [row for row in self._rows if row]

    def as_markup(self):
        """Return aiogram InlineKeyboardMarkup."""
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        ib = InlineKeyboardBuilder()
        for row in self.build():
            for btn in row:
                kwargs = {"text": btn["text"]}
                if "callback_data" in btn:
                    kwargs["callback_data"] = btn["callback_data"]
                if "url" in btn:
                    kwargs["url"] = btn["url"]
                if "icon_custom_emoji_id" in btn:
                    kwargs["icon_custom_emoji_id"] = btn["icon_custom_emoji_id"]
                ib.button(**kwargs)
            ib.adjust(len(row))
        return ib.as_markup()
