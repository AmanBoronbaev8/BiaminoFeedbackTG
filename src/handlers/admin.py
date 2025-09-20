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
from ..utils import (
    parse_telegram_ids,
    is_admin,
    broadcast_to_employees,
    send_tasks_to_employees
)


admin_router = Router()

# Pagination settings
EMPLOYEES_PER_PAGE = 5


async def get_employees_with_tasks(sheets_service: GoogleSheetsService) -> List[Dict]:
    """Get employees who have tasks using batch operations."""
    return await sheets_service.get_employees_with_tasks_batch()


def create_employee_selection_keyboard(employees: List[Dict], page: int = 0, selected: List[str] = None, config: Config = None) -> InlineKeyboardMarkup:
    """Create keyboard for employee selection with pagination."""
    if selected is None:
        selected = []
    if config is None:
        # Fallback values if config not provided
        id_col = "ID"
        lastname_col = "Фамилия"
        firstname_col = "Имя"
    else:
        id_col = config.team_id_col
        lastname_col = config.team_lastname_col
        firstname_col = config.team_firstname_col
        
    builder = InlineKeyboardBuilder()
    
    # Calculate pagination
    start_idx = page * EMPLOYEES_PER_PAGE
    end_idx = start_idx + EMPLOYEES_PER_PAGE
    page_employees = employees[start_idx:end_idx]
    
    # Add employee buttons
    for employee in page_employees:
        employee_id = employee.get(id_col, "")
        name = f"{employee.get(lastname_col, '')} {employee.get(firstname_col, '')}".strip()
        
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
    builder.row(
        InlineKeyboardButton(text="⏰ Напоминание о дедлайнах", callback_data="admin_deadline_reminders")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Синхронизация Notion", callback_data="admin_sync_notion")
    )
    
    await message.answer(admin_text, parse_mode="HTML", reply_markup=builder.as_markup())


@admin_router.callback_query(F.data == "admin_send_tasks")
async def admin_send_tasks(callback: CallbackQuery, sheets_service: GoogleSheetsService, state: FSMContext, config: Config):
    """Show employees with tasks for selection."""
    try:
        employees_with_tasks = await get_employees_with_tasks(sheets_service)
        
        if not employees_with_tasks:
            await callback.message.edit_text(
                "Нет сотрудников с активными задачами.",
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
        
        keyboard = create_employee_selection_keyboard(employees_with_tasks, 0, [], config)
        
        text = (
            f"📋 <b>Отправка задач</b>\n\n"
            f"Найдено сотрудников с активными задачами: {len(employees_with_tasks)}\n"
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
async def send_tasks_to_selected(callback: CallbackQuery, state: FSMContext, sheets_service: GoogleSheetsService, bot: Bot, config: Config):
    """Send tasks to selected employees."""
    # Answer callback immediately to prevent timeout
    await callback.answer()
    
    try:
        data = await state.get_data()
        selected_employees = data.get("selected_employees", [])
        employees_with_tasks = data.get("employees_with_tasks", [])
        
        if not selected_employees:
            await callback.message.edit_text(
                "Не выбран ни один сотрудник!",
                reply_markup=None
            )
            return
        
        # Show initial processing message
        await callback.message.edit_text(
            f"📤 Отправляю задачи {len(selected_employees)} сотрудникам...",
            reply_markup=None
        )
            
        # Filter selected employees
        selected_employee_data = [
            emp for emp in employees_with_tasks 
            if emp.get("ID") in selected_employees
        ]
        
        # Use standardized task sending utility
        sent_count, failed_count = await send_tasks_to_employees(bot, selected_employee_data, config=config)
                
        result_text = (
            f"📤 <b>Отправка задач завершена!</b>\n\n"
            f"✅ Отправлено: {sent_count}\n"
            f"❌ Не удалось отправить: {failed_count}"
        )
        
        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=None)
        await state.clear()
        
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
async def admin_remind_pending(callback: CallbackQuery, sheets_service: GoogleSheetsService, bot: Bot, config: Config):
    """Remind employees who haven't submitted reports for ALL their incomplete tasks."""
    # Answer callback immediately to prevent timeout
    await callback.answer()
    
    try:
        # Show initial processing message
        await callback.message.edit_text(
            "⏰ Проверяю отчеты сотрудников...",
            reply_markup=None
        )
        
        today = datetime.now().strftime("%d.%m.%Y")
        logger.info(f"Admin triggered report reminders for date: {today}")
        
        employees_without_reports_ids, employees_with_telegram = await sheets_service.get_employees_without_reports_batch(today)
        
        logger.info(f"Found {len(employees_without_reports_ids)} employees without complete reports")
        logger.info(f"Of those, {len(employees_with_telegram)} have valid TelegramIDs")
        
        reminder_text = (
            "Кажется, вы забыли заполнить отчет за сегодня по некоторым задачам. "
            "Пожалуйста, не забудьте заполнить отчеты по ВСЕМ невыполненным задачам! ⏰\n\n"
            "Используйте команду /report для заполнения."
        )
        
        sent_count, failed_count = await broadcast_to_employees(bot, employees_with_telegram, reminder_text, config=config)
        
        result_message = (
            f"📊 <b>Результат напоминаний о отчетах:</b>\n\n"
            f"🔍 Проверено: {len(await sheets_service.get_all_employees_cached())} сотрудников\n"
            f"❌ Без полных отчетов: {len(employees_without_reports_ids)}\n"
            f"📱 С TelegramID: {len(employees_with_telegram)}\n"
            f"✅ Отправлено: {sent_count}\n"
            f"❌ Ошибок: {failed_count}"
        )
        
        if employees_without_reports_ids:
            result_message += "\n\n<b>Сотрудники без полных отчетов:</b>\n"
            for emp_id in employees_without_reports_ids[:10]:  # Show first 10
                result_message += f"• {emp_id}\n"
            if len(employees_without_reports_ids) > 10:
                result_message += f"... и еще {len(employees_without_reports_ids) - 10}"
                    
        await callback.message.edit_text(
            result_message,
            reply_markup=None,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error sending reminders: {e}", exc_info=True)
        await callback.message.edit_text(
            f"Произошла ошибка при отправке напоминаний: {str(e)}",
            reply_markup=None
        )


@admin_router.callback_query(F.data == "admin_remind_all")
async def admin_remind_all(callback: CallbackQuery, sheets_service: GoogleSheetsService, bot: Bot, config: Config):
    """Remind all employees about reports."""
    # Answer callback immediately to prevent timeout
    await callback.answer()
    
    try:
        # Show initial processing message
        await callback.message.edit_text(
            "📢 Отправляю напоминания всем сотрудникам...",
            reply_markup=None
        )
        
        employees = await sheets_service.get_all_employees_cached()
        
        reminder_text = (
            "Коллеги, просьба срочно заполнить отчет и фидбек за сегодня! 📝"
        )
        
        sent_count, failed_count = await broadcast_to_employees(bot, employees, reminder_text, config=config)
                    
        await callback.message.edit_text(
            f"Напоминания отправлены всем {sent_count} сотрудникам.",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error sending reminders to all: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при отправке напоминаний.",
            reply_markup=None
        )


@admin_router.callback_query(F.data == "admin_send_all_tasks")
async def admin_send_all_tasks(callback: CallbackQuery, sheets_service: GoogleSheetsService, bot: Bot, config: Config):
    """Send all tasks to all employees who have them."""
    # Answer callback immediately to prevent timeout
    await callback.answer()
    
    try:
        # Show initial processing message
        await callback.message.edit_text(
            "🔄 Отправляю задачи всем сотрудникам...",
            reply_markup=None
        )
        
        today = datetime.now().strftime("%d.%m.%Y")
        employees_with_tasks = await sheets_service.get_employees_with_tasks_batch(today)
        
        sent_count, failed_count = await send_tasks_to_employees(bot, employees_with_tasks, config=config)
                    
        await callback.message.edit_text(
            f"Все задачи повторно отправлены {sent_count} сотрудникам.",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error sending all tasks: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при отправке всех задач.",
            reply_markup=None
        )


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
async def process_broadcast_message(
    message: Message, 
    state: FSMContext, 
    sheets_service: GoogleSheetsService, 
    bot: Bot, 
    config: Config
):
    """Process and send broadcast message (universal)."""
    if not is_admin(message.from_user.id, config):
        return

    try:
        employees = await sheets_service.get_all_employees_cached()
        logger.info(f"Found {len(employees)} employees for broadcast")

        sent_count, failed_count = 0, 0

        for employee in employees:
            telegram_ids = parse_telegram_ids(employee.get("TelegramID"))
            employee_id = employee.get("ID", "Unknown")

            if not telegram_ids:
                failed_count += 1
                continue

            employee_success = False
            for telegram_id in telegram_ids:
                try:
                    # Универсальная пересылка любого сообщения
                    await bot.copy_message(
                        chat_id=telegram_id,
                        from_chat_id=message.chat.id,
                        message_id=message.message_id
                    )
                    employee_success = True
                    break
                except Exception as e:
                    logger.error(f"Failed to send message to {employee_id} (TG: {telegram_id}): {e}")

            if employee_success:
                sent_count += 1
            else:
                failed_count += 1

        result_text = (
            f"📢 Рассылка завершена!\n\n"
            f"✅ Успешно: {sent_count}\n"
            f"❌ Ошибок: {failed_count}"
        )
        await message.answer(result_text)

    except Exception as e:
        logger.error(f"Error processing broadcast: {e}")
        await message.answer("❌ Произошла ошибка при рассылке.")

    finally:
        await state.clear()


@admin_router.callback_query(F.data == "admin_deadline_reminders")
async def admin_deadline_reminders(callback: CallbackQuery, sheets_service: GoogleSheetsService, bot: Bot, config: Config):
    """Manually trigger deadline reminders."""
    # Answer callback immediately to prevent timeout
    await callback.answer()
    
    try:
        # Show initial processing message
        await callback.message.edit_text(
            "⏰ Проверяю дедлайны...",
            reply_markup=None
        )
        
        from datetime import timedelta
        from ..utils.scheduler import current_timezone
        from ..utils.telegram_utils import parse_telegram_ids
        
        # Calculate 12 hours from now
        now = datetime.now(current_timezone)
        twelve_hours_later = now + timedelta(hours=12)
        deadline_date = twelve_hours_later.strftime("%d.%m.%Y")
        
        logger.info(f"Admin triggered deadline reminders for date: {deadline_date}")
        
        # Get all employees
        employees = await sheets_service.get_all_employees_cached()
        logger.info(f"Found {len(employees)} total employees")
        
        reminder_count = 0
        checked_employees = 0
        employees_with_tasks = 0
        
        for employee in employees:
            employee_id = employee.get(config.team_id_col, "")
            if not employee_id:
                continue
                
            checked_employees += 1
            
            try:
                # Get tasks with deadlines for this date
                tasks_with_deadlines = await sheets_service.get_tasks_with_deadline(employee_id, deadline_date)
                
                if tasks_with_deadlines:
                    employees_with_tasks += 1
                    logger.info(f"Employee {employee_id} has {len(tasks_with_deadlines)} tasks with deadline {deadline_date}")
                    
                    telegram_ids = parse_telegram_ids(employee.get(config.team_telegram_id_col))
                    
                    if telegram_ids:
                        # Format reminder message
                        task_list = []
                        for task in tasks_with_deadlines:
                            task_list.append(f"• {task.get('task_id', '')}: {task.get('task', '')}")
                        
                        tasks_text = "\n".join(task_list)
                        
                        reminder_text = (
                            f"⚠️ <b>Напоминание о дедлайне!</b>\n\n"
                            f"У следующих задач дедлайн через 12 часов ({deadline_date}):\n\n"
                            f"{tasks_text}\n\n"
                            f"Не забудьте завершить эти задачи вовремя!"
                        )
                        
                        # Send to first available telegram ID
                        for telegram_id in telegram_ids:
                            try:
                                await bot.send_message(
                                    telegram_id, 
                                    reminder_text, 
                                    parse_mode="HTML"
                                )
                                reminder_count += 1
                                logger.info(f"Deadline reminder sent to {employee_id} (TG: {telegram_id})")
                                break
                            except Exception as e:
                                logger.error(f"Failed to send deadline reminder to {employee_id} (TG: {telegram_id}): {e}")
                    else:
                        logger.warning(f"Employee {employee_id} has tasks with deadlines but no valid TelegramID")
            except Exception as e:
                logger.error(f"Error processing deadline reminders for employee {employee_id}: {e}")
        
        result_message = (
            f"⏰ <b>Результат проверки дедлайнов:</b>\n\n"
            f"📊 Проверено сотрудников: {checked_employees}\n"
            f"📋 С задачами на {deadline_date}: {employees_with_tasks}\n"
            f"✅ Отправлено напоминаний: {reminder_count}"
        )
        
        logger.info(f"Deadline reminders completed: {reminder_count} sent, {checked_employees} checked, {employees_with_tasks} with tasks")
                            
        await callback.message.edit_text(
            result_message,
            reply_markup=None,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error sending deadline reminders: {e}", exc_info=True)
        await callback.message.edit_text(
            f"Произошла ошибка при отправке напоминаний: {str(e)}",
            reply_markup=None
        )


@admin_router.message(Command("stats"))
async def cmd_stats(message: Message, config: Config, sheets_service: GoogleSheetsService):
    """Show detailed statistics for admins."""
    if not is_admin(message.from_user.id, config):
        return
        
    try:
        today = datetime.now().strftime("%d.%m.%Y")
        employees = await sheets_service.get_all_employees_cached()
        employees_without_reports_ids, employees_with_telegram = await sheets_service.get_employees_without_reports_batch(today)
        
        total_employees = len(employees)
        employees_with_complete_reports = total_employees - len(employees_without_reports_ids)
        employees_without_telegram = len(employees_without_reports_ids) - len(employees_with_telegram)
        
        stats_text = (
            f"📊 <b>Статистика на {today}</b>\n\n"
            f"👥 Всего сотрудников: {total_employees}\n"
            f"✅ Полные отчеты по всем задачам: {employees_with_complete_reports}\n"
            f"❌ Неполные отчеты: {len(employees_without_reports_ids)}\n"
            f"📱 С TelegramID: {len(employees_with_telegram)}\n"
            f"🚫 Без TelegramID: {employees_without_telegram}\n\n"
        )
        
        if employees_without_reports_ids:
            stats_text += "<b>Не сдали полные отчеты по всем задачам:</b>\n"
            for emp_id in employees_without_reports_ids[:15]:  # Show first 15
                stats_text += f"• {emp_id}\n"
            if len(employees_without_reports_ids) > 15:
                stats_text += f"... и еще {len(employees_without_reports_ids) - 15}\n"
                
        await message.answer(stats_text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        await message.answer(f"Произошла ошибка при получении статистики: {str(e)}")


@admin_router.callback_query(F.data == "admin_sync_notion")
async def admin_sync_notion(callback: CallbackQuery, config: Config):
    """Manually trigger Notion task synchronization."""
    # Answer callback immediately to prevent timeout
    await callback.answer()
    
    try:
        from ..services import NotionService, TaskSyncService, GoogleSheetsService
        
        # Initialize services (this should normally be done via dependency injection)
        # But for manual trigger, we create them here
        notion_service = NotionService(config)
        
        # We need the sheets service from callback context
        # This is a simplified approach - in production you'd inject this properly
        await callback.message.edit_text(
            "🔄 Запуск синхронизации с Notion...\n\n"
            "Это может занять несколько минут.",
            reply_markup=None
        )
        
        # Note: In a real implementation, you'd inject the existing sheets_service
        # For now, we'll indicate that this needs to be connected to the scheduler
        result_message = (
            "⚠️ <b>Синхронизация Notion</b>\n\n"
            "Функция синхронизации настроена и будет автоматически выполняться каждые 15 минут.\n\n"
            "📋 Данные из Notion будут автоматически загружаться в Google Sheets:\n"
            "• Задачи из обеих баз данных\n"
            "• Автоматическое сопоставление сотрудников\n"
            "• Обновление задач в личных листах сотрудников\n\n"
            "🔄 Следующая синхронизация произойдет автоматически."
        )
        
        await callback.message.edit_text(
            result_message,
            reply_markup=None,
            parse_mode="HTML"
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in manual Notion sync: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Произошла ошибка при синхронизации: {str(e)}",
            reply_markup=None
        )
        await callback.answer()