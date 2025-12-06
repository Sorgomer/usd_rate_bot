from aiogram.fsm.state import StatesGroup, State


class SettingsStates(StatesGroup):
    waiting_timezone = State()
    waiting_currency = State()
    waiting_time = State()