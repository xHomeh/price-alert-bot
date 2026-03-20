from aiogram.fsm.state import State, StatesGroup


class AddWatchStates(StatesGroup):
    query = State()
    max_price = State()
    cadence = State()
    alert_style = State()


class EditWatchStates(StatesGroup):
    cadence = State()
    style = State()

