"""FSM states for report collection and authentication flows."""
from aiogram.fsm.state import State, StatesGroup


class AuthStates(StatesGroup):
    """States for employee authentication."""
    waiting_for_name = State()
    waiting_for_password = State()


class ReportStates(StatesGroup):
    """States for daily report collection."""
    waiting_for_feedback = State()
    waiting_for_difficulties = State()
    waiting_for_daily_report = State()
    waiting_for_confirmation = State()


class AdminStates(StatesGroup):
    """States for admin operations."""
    waiting_for_broadcast_message = State()
    waiting_for_task_assignment = State()
    selecting_employees_for_tasks = State()