# tpl/admin_states.py
"""FSM-состояния админки шаблонов."""

from aiogram.fsm.state import State, StatesGroup


class TplAdminStates(StatesGroup):
    tpl_main = State()           # was: main
    tpl_viewing = State()        # was: viewing
    tpl_choosing_locale = State() # was: choosing_locale
    tpl_edit_text = State()       # was: edit_text
    tpl_edit_media = State()      # was: edit_media
    # Inline buttons
    tpl_btn_list = State()        # was: btn_list
    tpl_btn_edit_text = State()   # was: btn_edit_text
    tpl_btn_edit_style = State()  # was: btn_edit_style
    tpl_btn_edit_emoji = State() # was: btn_edit_emoji
    tpl_btn_edit_callback = State() # was: btn_edit_callback
    # Reply buttons
    tpl_reply_btn_list = State()       # was: reply_btn_list
    tpl_reply_btn_edit_text = State()  # was: reply_btn_edit_text
    tpl_reply_btn_edit_style = State() # was: reply_btn_edit_style
    tpl_reply_btn_edit_emoji = State() # was: reply_btn_edit_emoji