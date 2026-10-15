from __future__ import annotations
from twix_runtime import runtime


async def setting_display(key):
    return format_value_short(key,runtime().settings.get(key))


def format_value_short(key,value):
    if isinstance(value,bool):return 'Включено' if value else 'Выключено'
    return str(value)


async def setting_toggle_button(key):
    setting=runtime().schema.get(key)
    return {'text':f'{setting.title}: {await setting_display(key)}','callback_data':'admin_settings'}


async def setting_edit_button(key):
    return await setting_toggle_button(key)
