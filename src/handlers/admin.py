"""Admin handlers for administrator functionality."""
from datetime import datetime
from typing import List, Dict, Tuple
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from ..config_data import Config
from ..services import GoogleSheetsService
from ..states import AdminStates


admin_router = Router()

# Pagination settings
EMPLOYEES_PER_PAGE = 5


def is_admin(user_id: int, config: Config) -> bool:
    """Check if user is admin."""
    tg_bot = config.get_tg_bot()
    return user_id in tg_bot.admin_ids


async def get_employees_with_tasks(sheets_service: GoogleSheetsService, date: str) -> List[Dict]:
    """Get employees who have tasks for the specified date."""
    employees = await sheets_service.get_all_employees()
    employees_with_tasks = []
    
    for employee in employees:
        employee_id = employee.get("ID", "")
        if not employee_id:
            continue
            
        tasks = await sheets_service.get_employee_tasks(employee_id, date)
        if tasks and tasks.strip():
            employee['tasks'] = tasks
            employees_with_tasks.append(employee)
            
    return employees_with_tasks


def create_employee_selection_keyboard(employees: List[Dict], page: int = 0, selected: List[str] = None) -> InlineKeyboardMarkup:
    """Create keyboard for employee selection with pagination."""
    if selected is None:
        selected = []
        
    builder = InlineKeyboardBuilder()
    
    # Calculate pagination
    start_idx = page * EMPLOYEES_PER_PAGE
    end_idx = start_idx + EMPLOYEES_PER_PAGE
    page_employees = employees[start_idx:end_idx]
    
    # Add employee buttons
    for employee in page_employees:
        employee_id = employee.get("ID", "")
        name = f"{employee.get('Фамилия', '')} {employee.get('Имя', '')}".strip()
        
        if employee_id in selected:
            text = f"✅ {name}"
            callback_data = f"deselect_emp_{employee_id}"
        else:
            text = f"◻️ {name}"
            callback_data = f"select_emp_{employee_id}"
            
        builder.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    
    # Add pagination buttons
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page-1}"))
    if end_idx < len(employees):
        pagination_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"page_{page+1}"))
    
    if pagination_buttons:
        builder.row(*pagination_buttons)
    
    # Add control buttons
    control_buttons = []
    if len(selected) > 0:
        control_buttons.append(InlineKeyboardButton(text="📤 Отправить выбранным", callback_data="send_to_selected"))
    
    control_buttons.extend([
        InlineKeyboardButton(text="✅ Выбрать всех", callback_data="select_all"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task_selection")
    ])
    
    for i in range(0, len(control_buttons), 2):
        builder.row(*control_buttons[i:i+2])
    
    return builder.as_markup()


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, config: Config):
    """Handle /admin command."""
    if not is_admin(message.from_user.id, config):
        return  # Ignore if not admin
        
    await state.clear()
    
    admin_text = (
        "🔧 <b>Панель администратора</b>\n\n"
        "Выберите действие:"
    )
    
    # Create admin keyboard
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Отправить задачи", callback_data="admin_send_tasks")
    )
    builder.row(
        InlineKeyboardButton(text="⏰ Отчет (не сдавшим)", callback_data="admin_remind_pending"),
        InlineKeyboardButton(text="📢 Отчет (всем)", callback_data="admin_remind_all")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Отправить все задачи всем", callback_data="admin_send_all_tasks")
    )
    builder.row(
        InlineKeyboardButton(text="📡 Сделать рассылку", callback_data="admin_broadcast")
    )
    
    await message.answer(admin_text, parse_mode="HTML", reply_markup=builder.as_markup())


@admin_router.callback_query(F.data == "admin_send_tasks")
async def admin_send_tasks(callback: CallbackQuery, sheets_service: GoogleSheetsService, state: FSMContext):
    """Show employees with tasks for selection."""
    try:
        today = datetime.now().strftime("%d.%m.%Y")
        employees_with_tasks = await get_employees_with_tasks(sheets_service, today)
        
        if not employees_with_tasks:
            await callback.message.edit_text(
                f"На {today} нет сотрудников с задачами.",
                reply_markup=None
            )
            await callback.answer()
            return
            
        # Store employees data in state
        await state.update_data(
            employees_with_tasks=employees_with_tasks,
            selected_employees=[],
            current_page=0
        )
        await state.set_state(AdminStates.selecting_employees_for_tasks)
        
        keyboard = create_employee_selection_keyboard(employees_with_tasks, 0, [])
        
        text = (
            f"📋 <b>Отправка задач на {today}</b>\n\n"
            f"Найдено сотрудников с задачами: {len(employees_with_tasks)}\n"
            "Выберите, кому отправить задачи:"
        )
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in admin_send_tasks: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при загрузке списка сотрудников.",
            reply_markup=None
        )
        await callback.answer()


# Employee selection handlers
@admin_router.callback_query(F.data.startswith("select_emp_"), AdminStates.selecting_employees_for_tasks)
async def select_employee(callback: CallbackQuery, state: FSMContext):
    """Select an employee for task sending."""
    employee_id = callback.data.split("_", 2)[2]
    
    data = await state.get_data()
    selected_employees = data.get("selected_employees", [])
    employees_with_tasks = data.get("employees_with_tasks", [])
    current_page = data.get("current_page", 0)
    
    if employee_id not in selected_employees:
        selected_employees.append(employee_id)
        await state.update_data(selected_employees=selected_employees)
    
    keyboard = create_employee_selection_keyboard(employees_with_tasks, current_page, selected_employees)
    
    text = (
        f"📋 <b>Отправка задач</b>\n\n"
        f"Найдено сотрудников с задачами: {len(employees_with_tasks)}\n"
        f"Выбрано: {len(selected_employees)}\n"
        "Выберите, кому отправить задачи:"
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("deselect_emp_"), AdminStates.selecting_employees_for_tasks)
async def deselect_employee(callback: CallbackQuery, state: FSMContext):
    """Deselect an employee from task sending."""
    employee_id = callback.data.split("_", 2)[2]
    
    data = await state.get_data()
    selected_employees = data.get("selected_employees", [])
    employees_with_tasks = data.get("employees_with_tasks", [])
    current_page = data.get("current_page", 0)
    
    if employee_id in selected_employees:
        selected_employees.remove(employee_id)
        await state.update_data(selected_employees=selected_employees)
    
    keyboard = create_employee_selection_keyboard(employees_with_tasks, current_page, selected_employees)
    
    text = (
        f"📋 <b>Отправка задач</b>\n\n"
        f"Найдено сотрудников с задачами: {len(employees_with_tasks)}\n"
        f"Выбрано: {len(selected_employees)}\n"
        "Выберите, кому отправить задачи:"
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("page_"), AdminStates.selecting_employees_for_tasks)
async def change_page(callback: CallbackQuery, state: FSMContext):
    """Change page in employee selection."""
    page = int(callback.data.split("_")[1])
    
    data = await state.get_data()
    selected_employees = data.get("selected_employees", [])
    employees_with_tasks = data.get("employees_with_tasks", [])
    
    await state.update_data(current_page=page)
    
    keyboard = create_employee_selection_keyboard(employees_with_tasks, page, selected_employees)
    
    text = (
        f"📋 <b>Отправка задач</b>\n\n"
        f"Найдено сотрудников с задачами: {len(employees_with_tasks)}\n"
        f"Выбрано: {len(selected_employees)}\n"
        f"Страница: {page + 1}\n"
        "Выберите, кому отправить задачи:"
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@admin_router.callback_query(F.data == "select_all", AdminStates.selecting_employees_for_tasks)
async def select_all_employees(callback: CallbackQuery, state: FSMContext):
    """Select all employees with tasks."""
    data = await state.get_data()
    employees_with_tasks = data.get("employees_with_tasks", [])
    current_page = data.get("current_page", 0)
    
    selected_employees = [emp.get("ID", "") for emp in employees_with_tasks if emp.get("ID")]
    await state.update_data(selected_employees=selected_employees)
    
    keyboard = create_employee_selection_keyboard(employees_with_tasks, current_page, selected_employees)
    
    text = (
        f"📋 <b>Отправка задач</b>\n\n"
        f"Найдено сотрудников с задачами: {len(employees_with_tasks)}\n"
        f"Выбрано: {len(selected_employees)} (все)\n"
        "Выберите, кому отправить задачи:"
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@admin_router.callback_query(F.data == "send_to_selected", AdminStates.selecting_employees_for_tasks)
async def send_tasks_to_selected(callback: CallbackQuery, state: FSMContext, sheets_service: GoogleSheetsService, bot: Bot):
    """Send tasks to selected employees."""
    try:
        data = await state.get_data()
        selected_employees = data.get("selected_employees", [])
        employees_with_tasks = data.get("employees_with_tasks", [])
        
        if not selected_employees:
            await callback.answer("Не выбран ни один сотрудник!", show_alert=True)
            return
            
        sent_count = 0
        failed_count = 0
        
        # Create a lookup dict for faster access
        employees_dict = {emp.get("ID", ""): emp for emp in employees_with_tasks}
        
        for employee_id in selected_employees:
            employee = employees_dict.get(employee_id)
            if not employee:
                continue
                
            telegram_id = employee.get("TelegramID")
            tasks = employee.get("tasks", "")
            
            if telegram_id and tasks:
                try:
                    name = f"{employee.get('Фамилия', '')} {employee.get('Имя', '')}".strip()
                    task_text = f"📋 Привет, {name}!\n\nУ вас новые задачи на сегодня:\n\n{tasks}"
                    await bot.send_message(int(telegram_id), task_text)
                    sent_count += 1
                    logger.info(f"Sent tasks to {employee_id}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to send tasks to {employee_id}: {e}")
            else:
                failed_count += 1
                logger.warning(f"Employee {employee_id} missing telegram_id or tasks")
                
        result_text = (
            f"📤 <b>Отправка задач завершена!</b>\n\n"
            f"✅ Отправлено: {sent_count}\n"
            f"❌ Не удалось отправить: {failed_count}"
        )
        
        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=None)
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error sending tasks to selected employees: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при отправке задач.",
            reply_markup=None
        )
        await state.clear()
        await callback.answer()


@admin_router.callback_query(F.data == "cancel_task_selection", AdminStates.selecting_employees_for_tasks)
async def cancel_task_selection(callback: CallbackQuery, state: FSMContext):
    """Cancel task selection and return to admin menu."""
    await state.clear()
    await callback.message.edit_text(
        "Отправка задач отменена.",
        reply_markup=None
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_remind_pending")
async def admin_remind_pending(callback: CallbackQuery, sheets_service: GoogleSheetsService, bot: Bot):
    """Remind employees who haven't submitted reports."""
    try:
        today = datetime.now().strftime("%d.%m.%Y")
        employees_without_reports = await sheets_service.get_employees_without_reports(today)
        employees = await sheets_service.get_all_employees()
        
        sent_count = 0
        
        for employee in employees:
            employee_id = employee.get("ID", "")
            telegram_ids_str = employee.get("TelegramID", "")
            
            if employee_id in employees_without_reports and telegram_ids_str:
                # Parse multiple Telegram IDs separated by commas
                telegram_ids = [tid.strip() for tid in str(telegram_ids_str).split(',') if tid.strip()]
                
                for telegram_id in telegram_ids:
                    try:
                        reminder_text = (
                            "Кажется, вы забыли заполнить отчет за сегодня. "
                            "Пожалуйста, не забудьте это сделать! ⏰"
                        )
                        await bot.send_message(int(telegram_id), reminder_text)
                        sent_count += 1
                        logger.info(f"Sent reminder to {employee_id} (TG: {telegram_id})")
                    except Exception as e:
                        logger.error(f"Failed to send reminder to {employee_id} (TG: {telegram_id}): {e}")
                    
        await callback.message.edit_text(
            f"Напоминания отправлены {sent_count} сотрудникам, которые не сдали отчет.",
            reply_markup=None
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error sending reminders: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при отправке напоминаний.",
            reply_markup=None
        )
        await callback.answer()


@admin_router.callback_query(F.data == "admin_remind_all")
async def admin_remind_all(callback: CallbackQuery, sheets_service: GoogleSheetsService, bot: Bot):
    """Remind all employees about reports."""
    try:
        employees = await sheets_service.get_all_employees()
        sent_count = 0
        
        for employee in employees:
            telegram_id = employee.get("TelegramID")  # Updated to match your column name
            
            if telegram_id:
                try:
                    reminder_text = (
                        "Коллеги, просьба срочно заполнить отчет и фидбек за сегодня! 📝"
                    )
                    await bot.send_message(int(telegram_id), reminder_text)
                    sent_count += 1
                    logger.info(f"Sent reminder to {employee.get('ID', '')}")
                except Exception as e:
                    logger.error(f"Failed to send reminder to {employee.get('ID', '')}: {e}")
                    
        await callback.message.edit_text(
            f"Напоминания отправлены всем {sent_count} сотрудникам.",
            reply_markup=None
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error sending reminders to all: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при отправке напоминаний.",
            reply_markup=None
        )
        await callback.answer()


@admin_router.callback_query(F.data == "admin_send_all_tasks")
async def admin_send_all_tasks(callback: CallbackQuery, sheets_service: GoogleSheetsService, bot: Bot):
    """Send all tasks to all employees who have them."""
    try:
        today = datetime.now().strftime("%d.%m.%Y")
        employees = await sheets_service.get_all_employees()
        
        sent_count = 0
        
        for employee in employees:
            employee_id = employee.get("ID", "")
            telegram_id = employee.get("TelegramID")  # Updated to match your column name
            
            if not employee_id or not telegram_id:
                logger.debug(f"Skipping employee {employee_id}: missing telegram_id={telegram_id}")
                continue
                
            tasks = await sheets_service.get_employee_tasks(employee_id, today)
            
            if tasks and tasks.strip():
                try:
                    task_text = f"📋 Ваши задачи на сегодня:\n\n{tasks}"
                    await bot.send_message(int(telegram_id), task_text)
                    sent_count += 1
                    logger.info(f"Sent all tasks to {employee_id}")
                except Exception as e:
                    logger.error(f"Failed to send all tasks to {employee_id}: {e}")
                    
        await callback.message.edit_text(
            f"Все задачи повторно отправлены {sent_count} сотрудникам.",
            reply_markup=None
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error sending all tasks: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при отправке всех задач.",
            reply_markup=None
        )
        await callback.answer()


@admin_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Start broadcast message process."""
    await callback.message.edit_text(
        "Отправьте сообщение для рассылки всем пользователям (текст или медиа):",
        reply_markup=None
    )
    await state.set_state(AdminStates.waiting_for_broadcast_message)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_broadcast_message)
async def process_broadcast_message(message: Message, state: FSMContext, sheets_service: GoogleSheetsService, bot: Bot, config: Config):
    """Process and send broadcast message."""
    if not is_admin(message.from_user.id, config):
        return
        
    try:
        employees = await sheets_service.get_all_employees()
        logger.info(f"Found {len(employees)} employees for broadcast")
        sent_count = 0
        failed_count = 0
        
        for employee in employees:
            telegram_id = employee.get("TelegramID")  # Updated to match your column name
            employee_id = employee.get("ID", "Unknown")
            
            logger.debug(f"Processing employee {employee_id} with telegram_id: {telegram_id}")
            
            if telegram_id:
                try:
                    # Copy the message to each user
                    if message.text:
                        await bot.send_message(int(telegram_id), message.text)
                    elif message.photo:
                        await bot.send_photo(
                            int(telegram_id), 
                            message.photo[-1].file_id,
                            caption=message.caption
                        )
                    elif message.video:
                        await bot.send_video(
                            int(telegram_id), 
                            message.video.file_id,
                            caption=message.caption
                        )
                    elif message.document:
                        await bot.send_document(
                            int(telegram_id), 
                            message.document.file_id,
                            caption=message.caption
                        )
                    # Add more media types as needed
                    
                    sent_count += 1
                    logger.info(f"Sent broadcast to {employee.get('ID', '')}")
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to send broadcast to {employee.get('ID', '')}: {e}")
            else:
                logger.debug(f"Skipping employee {employee_id}: no telegram_id")
                    
        result_text = (
            f"Рассылка завершена!\n"
            f"✅ Отправлено: {sent_count}\n"
            f"❌ Не удалось отправить: {failed_count}"
        )
        
        await message.answer(result_text)
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error processing broadcast: {e}")
        await message.answer("Произошла ошибка при рассылке.")
        await state.clear()


@admin_router.message(Command("stats"))
async def cmd_stats(message: Message, config: Config, sheets_service: GoogleSheetsService):
    """Show statistics for admins."""
    if not is_admin(message.from_user.id, config):
        return
        
    try:
        today = datetime.now().strftime("%d.%m.%Y")
        employees = await sheets_service.get_all_employees()
        employees_without_reports = await sheets_service.get_employees_without_reports(today)
        
        total_employees = len(employees)
        reports_submitted = total_employees - len(employees_without_reports)
        
        stats_text = (
            f"📊 <b>Статистика на {today}</b>\n\n"
            f"👥 Всего сотрудников: {total_employees}\n"
            f"✅ Сдали отчет: {reports_submitted}\n"
            f"⏳ Не сдали отчет: {len(employees_without_reports)}\n\n"
        )
        
        if employees_without_reports:
            stats_text += "<b>Не сдали отчет:</b>\n"
            for emp_id in employees_without_reports:
                stats_text += f"• {emp_id}\n"
                
        await message.answer(stats_text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await message.answer("Произошла ошибка при получении статистики.")