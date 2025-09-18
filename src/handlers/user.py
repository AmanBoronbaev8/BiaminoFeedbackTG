"""User handlers for employee functionality."""
import html
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from ..config_data import Config
from ..services import GoogleSheetsService
from ..states import ReportStates
from ..utils.telegram_utils import parse_telegram_ids, is_admin


user_router = Router()


async def auto_authenticate_user(message: Message, state: FSMContext, sheets_service: GoogleSheetsService, config: Config = None) -> bool:
    """Automatically authenticate user based on TelegramID."""
    try:
        telegram_id = message.from_user.id
        
        # Check if user is admin first - admins don't need to be in employee database
        if config and is_admin(telegram_id, config):
            await state.update_data(
                employee_data={"ID": f"admin_{telegram_id}", "Имя": "Admin", "Фамилия": "User"},
                employee_id=f"admin_{telegram_id}",
                authenticated=True,
                is_admin=True
            )
            
            await message.answer(
                "Вы авторизированы как администратор! 👑\n\n"
                "Используйте /admin для доступа к панели управления."
            )
            logger.info(f"Admin {telegram_id} authenticated successfully")
            return True
        
        # Try to find employee by TelegramID
        employee_data = await sheets_service.get_employee_by_telegram_id(telegram_id)
        
        if employee_data:
            # Store employee data permanently
            await state.update_data(
                employee_data=employee_data,
                employee_id=employee_data.get(config.team_id_col if config else "ID", ""),
                authenticated=True,
                is_admin=False
            )
            
            # Get full name using config
            if config:
                first_name = employee_data.get(config.team_firstname_col, "")
                last_name = employee_data.get(config.team_lastname_col, "")
            else:
                first_name = employee_data.get("Имя", "")
                last_name = employee_data.get("Фамилия", "")
            full_name = f"{last_name} {first_name}".strip()
            
            # Send authentication success message
            auth_text = f"Вы авторизированы как {full_name}! ✅"
            await message.answer(auth_text)
            
            logger.info(f"User {telegram_id} authenticated as {full_name}")
            return True
        else:
            # User not found in the system
            await message.answer(
                "Ваш Telegram аккаунт не найден в системе. "
                "Обратитесь к администратору для добавления в систему."
            )
            logger.warning(f"Unknown user with TelegramID {telegram_id} tried to access the bot")
            return False
            
    except Exception as e:
        logger.error(f"Error in auto authentication: {e}")
        await message.answer("Произошла ошибка при авторизации. Попробуйте позже.")
        return False


@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, sheets_service: GoogleSheetsService, config: Config):
    """Handle /start command with automatic authentication."""
    # Check if user is already authenticated
    data = await state.get_data()
    if data.get("authenticated"):
        employee_data = data.get("employee_data", {})
        if data.get("is_admin"):
            await message.answer(
                "Вы уже авторизированы как администратор! 👑\n\n"
                "Используйте /admin для доступа к панели управления."
            )
        else:
            # Use config for field names
            if config:
                first_name = employee_data.get(config.team_firstname_col, "")
                last_name = employee_data.get(config.team_lastname_col, "")
            else:
                first_name = employee_data.get("Имя", "")
                last_name = employee_data.get("Фамилия", "")
            full_name = f"{last_name} {first_name}".strip()
            
            await message.answer(
                f"Вы уже авторизированы как {full_name}! ✅\n\n"
                "Используйте /report для заполнения отчета."
            )
        return
    
    # Auto-authenticate based on TelegramID
    await auto_authenticate_user(message, state, sheets_service, config)


@user_router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext, sheets_service: GoogleSheetsService):
    """Handle /report command."""
    try:
        data = await state.get_data()
        
        if not data.get("authenticated"):
            await message.answer("Сначала необходимо авторизоваться. Используйте команду /start")
            return
            
        employee_id = data.get("employee_id", "")
        
        # Get tasks that don't have reports for today
        tasks_without_reports = await sheets_service.get_tasks_without_reports_today(employee_id)
        
        if not tasks_without_reports:
            await message.answer("Вы уже сдали отчеты по всем активным задачам за сегодня! ✅")
            return
            
        await start_report_collection(message, state, sheets_service)
        
    except Exception as e:
        logger.error(f"Error handling report command: {e}")
        await message.answer("Произошла ошибка. Попробуйте еще раз.")


async def start_report_collection(message: Message, state: FSMContext, sheets_service: GoogleSheetsService = None):
    """Start the report collection process with task selection."""
    if not sheets_service:
        # Get sheets_service from state if not provided (for callback scenarios)
        await message.answer("Произошла ошибка. Попробуйте команду /report еще раз.")
        return
        
    data = await state.get_data()
    employee_id = data.get("employee_id", "")
    
    # Get tasks that don't have reports for today
    tasks_without_reports = await sheets_service.get_tasks_without_reports_today(employee_id)
    
    if not tasks_without_reports:
        await message.answer(
            "У вас нет задач, по которым нужно сдать отчет за сегодня.\n\n"
            "Либо вы уже сдали отчеты по всем активным задачам, либо нет активных задач."
        )
        return
        
    # Create task selection keyboard
    builder = InlineKeyboardBuilder()
    
    for task in tasks_without_reports:
        task_id = task.get('task_id', '')
        task_text = task.get('task', '')
        task_preview = task_text[:30] + '...' if len(task_text) > 30 else task_text
        
        builder.row(
            InlineKeyboardButton(
                text=f"🔸 {task_id}: {task_preview}", 
                callback_data=f"select_task_{task_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_report")
    )
    
    # Store tasks in state for later use
    await state.update_data(available_tasks=tasks_without_reports)
    
    task_text = (
        "Выберите задачу для создания отчета:\n\n"
        "📋 <b>Задачи, по которым нужно сдать отчет:</b>\n"
    )
    
    for i, task in enumerate(tasks_without_reports, 1):
        deadline = task.get('deadline', '')
        deadline_text = f" (до {deadline})" if deadline else ""
        task_text += f"{i}. <b>{task.get('task_id', '')}:</b> {task.get('task', '')}{deadline_text}\n"
    
    await message.answer(task_text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(ReportStates.selecting_task)


@user_router.callback_query(F.data.startswith("select_task_"), ReportStates.selecting_task)
async def select_task_for_report(callback: CallbackQuery, state: FSMContext):
    """Handle task selection for report."""
    try:
        task_id = callback.data.split("_", 2)[2]
        
        # Get task details from stored available tasks
        data = await state.get_data()
        available_tasks = data.get("available_tasks", [])
        
        selected_task = None
        for task in available_tasks:
            if task.get('task_id') == task_id:
                selected_task = task
                break
                
        if not selected_task:
            await callback.answer("Задача не найдена!", show_alert=True)
            return
            
        # Store selected task
        await state.update_data(selected_task=selected_task)
        
        # Show task details and start feedback collection
        task_details = (
            f"Выбрана задача: <b>{task_id}</b>\n\n"
            f"<b>Описание:</b> {selected_task.get('task', '')}\n"
        )
        
        if selected_task.get('deadline'):
            task_details += f"<b>Дедлайн:</b> {selected_task.get('deadline')}\n"
            
        task_details += (
            "\n🔹 Расскажите, как вам работалось над этой задачей? "
            "Была ли она интересной, с какими нюансами столкнулись?"
        )
        
        await callback.message.edit_text(
            task_details, 
            parse_mode="HTML", 
            reply_markup=None
        )
        await state.set_state(ReportStates.waiting_for_feedback)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in task selection: {e}")
        await callback.answer("Произошла ошибка!", show_alert=True)


@user_router.callback_query(F.data == "cancel_report", ReportStates.selecting_task)
async def cancel_report_selection(callback: CallbackQuery, state: FSMContext):
    """Cancel report creation."""
    await callback.message.edit_text(
        "Создание отчета отменено.", 
        reply_markup=None
    )
    
    # Clear only report-related data, preserve authentication
    data = await state.get_data()
    employee_data = data.get("employee_data")
    employee_id = data.get("employee_id")
    authenticated = data.get("authenticated")
    is_admin = data.get("is_admin")
    
    await state.clear()
    await state.update_data(
        employee_data=employee_data,
        employee_id=employee_id,
        authenticated=authenticated,
        is_admin=is_admin
    )
    await callback.answer()


@user_router.message(ReportStates.waiting_for_feedback)
async def process_feedback(message: Message, state: FSMContext):
    """Process feedback input."""
    feedback_text = message.text or message.caption or ""
    
    if not feedback_text.strip():
        await message.answer("Пожалуйста, введите ваш фидбек.")
        return
        
    await state.update_data(feedback=feedback_text)
    
    difficulties_text = (
        "Спасибо! 👍\n\n"
        "Теперь расскажите о сложностях. С чем столкнулись, "
        "что не получилось, где нужна помощь?"
    )
    
    await message.answer(difficulties_text)
    await state.set_state(ReportStates.waiting_for_difficulties)


@user_router.message(ReportStates.waiting_for_difficulties)
async def process_difficulties(message: Message, state: FSMContext):
    """Process difficulties input."""
    difficulties_text = message.text or message.caption or ""
    
    if not difficulties_text.strip():
        await message.answer("Пожалуйста, расскажите о сложностях или напишите 'Нет сложностей'.")
        return
        
    await state.update_data(difficulties=difficulties_text)
    
    daily_report_text = (
        "Отлично! 👌\n\n"
        "И последнее: опишите, что было сделано за день. "
        "Можете приложить ссылки на результаты."
    )
    
    await message.answer(daily_report_text)
    await state.set_state(ReportStates.waiting_for_daily_report)


@user_router.message(ReportStates.waiting_for_daily_report)
async def process_daily_report(message: Message, state: FSMContext):
    """Process daily report input."""
    daily_report_text = message.text or message.caption or ""
    
    if not daily_report_text.strip():
        await message.answer("Пожалуйста, опишите, что было сделано за день.")
        return
        
    await state.update_data(daily_report=daily_report_text)
    
    # Show confirmation
    data = await state.get_data()
    feedback = data.get("feedback", "")
    difficulties = data.get("difficulties", "")
    daily_report = data.get("daily_report", "")
    
    confirmation_text = (
        "Ваш отчет за сегодня:\n\n"
        f"<b>Фидбек:</b>\n{html.escape(feedback)}\n\n"
        f"<b>Сложности:</b>\n{html.escape(difficulties)}\n\n"
        f"<b>Отчет за день:</b>\n{html.escape(daily_report)}\n\n"
        "Отправляем?"
    )
    
    # Create confirmation keyboard
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Да, отправить ✅", callback_data="confirm_report"),
        InlineKeyboardButton(text="Заполнить заново 🔄", callback_data="restart_report")
    )
    
    await message.answer(confirmation_text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(ReportStates.waiting_for_confirmation)


@user_router.callback_query(F.data == "confirm_report", ReportStates.waiting_for_confirmation)
async def confirm_report(callback: CallbackQuery, state: FSMContext, sheets_service: GoogleSheetsService):
    """Confirm and save the report."""
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id", "")
        selected_task = data.get("selected_task", {})
        task_id = selected_task.get("task_id", "")
        feedback = data.get("feedback", "")
        difficulties = data.get("difficulties", "")
        daily_report = data.get("daily_report", "")
        
        if not task_id:
            await callback.message.edit_text(
                "Ошибка: не выбрана задача. Попробуйте заново.",
                reply_markup=None
            )
            await state.clear()
            await callback.answer()
            return
        
        # Save to Google Sheets with task_id
        success = await sheets_service.save_daily_report(
            employee_id, task_id, feedback, difficulties, daily_report
        )
        
        if success:
            await callback.message.edit_text(
                f"Ваш отчет по задаче <b>{task_id}</b> успешно сохранен. Спасибо! ✅",
                parse_mode="HTML",
                reply_markup=None
            )
            logger.info(f"Report saved for employee {employee_id}, task {task_id}")
        else:
            await callback.message.edit_text(
                "Произошла ошибка при сохранении отчета. Попробуйте еще раз.",
                reply_markup=None
            )
            
        # Clear only report-related data, preserve authentication
        employee_data = data.get("employee_data")
        employee_id_stored = data.get("employee_id")
        authenticated = data.get("authenticated")
        is_admin = data.get("is_admin")
        
        await state.clear()
        await state.update_data(
            employee_data=employee_data,
            employee_id=employee_id_stored,
            authenticated=authenticated,
            is_admin=is_admin
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error confirming report: {e}")
        await callback.message.edit_text(
            "Произошла ошибка. Попробуйте еще раз.",
            reply_markup=None
        )
        await callback.answer()


@user_router.callback_query(F.data == "restart_report", ReportStates.waiting_for_confirmation)
async def restart_report(callback: CallbackQuery, state: FSMContext, sheets_service: GoogleSheetsService):
    """Restart the report collection process."""
    await callback.message.edit_text(
        "Хорошо, давайте заполним отчет заново.",
        reply_markup=None
    )
    
    await start_report_collection(callback.message, state, sheets_service)
    await callback.answer()


@user_router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    help_text = (
        "Доступные команды:\n\n"
        "/start - Первый запуск бота\n"
        "/report - Заполнить отчет вручную\n"
        "/help - Показать это сообщение\n\n"
        "Бот автоматически напомнит о заполнении отчета в 21:00 МСК.\n\n"
        "Авторизация происходит автоматически по вашему Telegram ID."
    )
    
    await message.answer(help_text)


@user_router.message(Command("logout"))
async def cmd_logout(message: Message, state: FSMContext):
    """Handle /logout command."""
    await state.clear()
    await message.answer(
        "Вы успешно вышли из системы. \n\n"
        "Для повторной авторизации используйте команду /start"
    )


@user_router.message(~F.text.startswith('/'))
async def handle_any_message(message: Message, state: FSMContext, sheets_service: GoogleSheetsService, config: Config):
    """Handle any message - authenticate user if not already authenticated."""
    data = await state.get_data()
    
    if not data.get("authenticated"):
        # User not authenticated, try to authenticate them
        authenticated = await auto_authenticate_user(message, state, sheets_service, config)
        if not authenticated:
            return  # Authentication failed, user was notified
        
        # Get updated state data after authentication
        data = await state.get_data()
        
        # Show available commands after successful authentication
        if data.get("is_admin", False):
            await message.answer(
                "Доступные команды:\n\n"
                "/admin - Панель администратора\n"
                "/help - Показать справку"
            )
        else:
            await message.answer(
                "Доступные команды:\n\n"
                "/report - Заполнить отчет\n"
                "/help - Показать справку\n\n"
                "Бот автоматически напомнит о заполнении отчета в 21:00 МСК."
            )
    else:
        # User is authenticated but sent an unknown command/message
        if data.get("is_admin", False):
            await message.answer(
                "Не понимаю вас. Используйте:\n\n"
                "/admin - Панель администратора\n"
                "/help - Показать справку"
            )
        else:
            await message.answer(
                "Не понимаю вас. Используйте:\n\n"
                "/report - Заполнить отчет\n"
                "/help - Показать справку"
            )