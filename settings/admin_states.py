from aiogram.fsm.state import State, StatesGroup


class SetAdminStates(StatesGroup):
    set_main = State()
    set_category = State()
    set_editing = State()
    set_input_value = State()