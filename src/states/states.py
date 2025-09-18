"""FSM states for report collection flows."""
from aiogram.fsm.state import State, StatesGroup


class ReportStates(StatesGroup):
    """States for daily report collection."""
    selecting_task = State()
    waiting_for_feedback = State()
    waiting_for_difficulties = State()
    waiting_for_daily_report = State()
    waiting_for_confirmation = State()


class AdminStates(StatesGroup):
    """States for admin operations."""
    waiting_for_broadcast_message = State()
    waiting_for_task_assignment = State()
    selecting_employees_for_tasks = State()