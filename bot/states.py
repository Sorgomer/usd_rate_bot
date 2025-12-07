from aiogram.fsm.state import StatesGroup, State


class SettingsStates(StatesGroup):
    waiting_city = State()
    waiting_currency = State()
    waiting_time = State()