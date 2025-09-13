"""User handlers for employee functionality."""
import html
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from ..services import GoogleSheetsService
from ..states import AuthStates, ReportStates


user_router = Router()


@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, sheets_service: GoogleSheetsService):
    """Handle /start command."""
    # Check if user is already authenticated
    data = await state.get_data()
    if data.get("authenticated"):
        employee_data = data.get("employee_data", {})
        first_name = employee_data.get("Имя", "")
        await message.answer(
            f"Вы уже авторизованы, {first_name}! ✅\n\n"
            "Используйте /report для заполнения отчета или /logout для выхода из системы."
        )
        return
    
    await state.clear()
    
    welcome_text = (
        "Добро пожаловать в BiaminoFeedback! 🏢\n\n"
        "Пожалуйста, для авторизации введите ваши Фамилию и Имя через пробел.\n"
        "Например: <code>Иванов Иван</code>"
    )
    
    await message.answer(welcome_text, parse_mode="HTML")
    await state.set_state(AuthStates.waiting_for_name)


@user_router.message(AuthStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext, sheets_service: GoogleSheetsService):
    """Process employee name input."""
    try:
        name_parts = message.text.strip().split()
        
        if len(name_parts) != 2:
            await message.answer(
                "Пожалуйста, введите Фамилию и Имя через пробел.\n"
                "Например: <code>Иванов Иван</code>",
                parse_mode="HTML"
            )
            return
            
        last_name, first_name = name_parts
        
        # Check if employee exists
        employee_data = await sheets_service.get_employee_data(last_name, first_name)
        
        if not employee_data:
            await message.answer(
                "Сотрудник с такими данными не найден. "
                "Пожалуйста, проверьте Фамилию и Имя и попробуйте еще раз."
            )
            return
            
        # Store name data and ask for password
        await state.update_data(last_name=last_name, first_name=first_name)
        await message.answer("Теперь введите ваш пароль:")
        await state.set_state(AuthStates.waiting_for_password)
        
    except Exception as e:
        logger.error(f"Error processing name: {e}")
        await message.answer("Произошла ошибка. Попробуйте еще раз.")


@user_router.message(AuthStates.waiting_for_password)
async def process_password(message: Message, state: FSMContext, sheets_service: GoogleSheetsService):
    """Process password input and authenticate."""
    try:
        data = await state.get_data()
        last_name = data.get("last_name")
        first_name = data.get("first_name")
        password = message.text.strip()
        
        # Verify credentials
        employee_data = await sheets_service.verify_employee_password(last_name, first_name, password)
        
        if not employee_data:
            await message.answer(
                "Неверный пароль. Пожалуйста, попробуйте еще раз или введите /start для повторной авторизации."
            )
            return
            
        # Store employee data
        await state.update_data(
            employee_data=employee_data,
            employee_id=employee_data.get("ID", ""),
            authenticated=True
        )
        
        success_text = (
            f"Авторизация прошла успешно! ✅\n\n"
            f"Добро пожаловать, {first_name}!\n"
            f"Я напишу вам сегодня в 21:00 по МСК для сбора отчета.\n\n"
            f"Вы можете использовать команду /report для заполнения отчета вручную."
        )
        
        await message.answer(success_text)
        # Clear the auth state after successful authentication
        await state.clear()
        # Restore the authentication data without any specific state
        await state.update_data(
            employee_data=employee_data,
            employee_id=employee_data.get("ID", ""),
            authenticated=True
        )
        
        logger.info(f"User {first_name} {last_name} authenticated successfully")
        
    except Exception as e:
        logger.error(f"Error processing password: {e}")
        await message.answer("Произошла ошибка. Попробуйте еще раз.")


@user_router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext, sheets_service: GoogleSheetsService):
    """Handle /report command."""
    try:
        data = await state.get_data()
        
        if not data.get("authenticated"):
            await message.answer("Сначала необходимо авторизоваться. Используйте команду /start")
            return
            
        employee_id = data.get("employee_id", "")
        
        # Check if report already submitted today
        today = datetime.now().strftime("%d.%m.%Y")
        has_report = await sheets_service.check_report_submitted(employee_id, today)
        
        if has_report:
            await message.answer("Вы уже сдали отчет за сегодня! ✅")
            return
            
        await start_report_collection(message, state)
        
    except Exception as e:
        logger.error(f"Error handling report command: {e}")
        await message.answer("Произошла ошибка. Попробуйте еще раз.")


async def start_report_collection(message: Message, state: FSMContext):
    """Start the report collection process."""
    feedback_text = (
        "Заполнение отчета! 📝\n\n"
        "Расскажите, как вам работалось над сегодняшними задачами? "
        "Были ли они интересными, с какими нюансами столкнулись?"
    )
    
    await message.answer(feedback_text)
    await state.set_state(ReportStates.waiting_for_feedback)


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
        feedback = data.get("feedback", "")
        difficulties = data.get("difficulties", "")
        daily_report = data.get("daily_report", "")
        
        # Save to Google Sheets
        success = await sheets_service.save_daily_report(
            employee_id, feedback, difficulties, daily_report
        )
        
        if success:
            await callback.message.edit_text(
                "Ваш отчет успешно сохранен. Спасибо! ✅",
                reply_markup=None
            )
            logger.info(f"Report saved for employee {employee_id}")
        else:
            await callback.message.edit_text(
                "Произошла ошибка при сохранении отчета. Попробуйте еще раз.",
                reply_markup=None
            )
            
        # Clear only report-related data, preserve authentication
        employee_data = data.get("employee_data")
        employee_id = data.get("employee_id")
        authenticated = data.get("authenticated")
        
        await state.clear()
        await state.update_data(
            employee_data=employee_data,
            employee_id=employee_id,
            authenticated=authenticated
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
async def restart_report(callback: CallbackQuery, state: FSMContext):
    """Restart the report collection process."""
    await callback.message.edit_text(
        "Хорошо, давайте заполним отчет заново.",
        reply_markup=None
    )
    
    await start_report_collection(callback.message, state)
    await callback.answer()


@user_router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    help_text = (
        "Доступные команды:\n\n"
        "/start - Авторизация в системе\n"
        "/report - Заполнить отчет вручную\n"
        "/logout - Выйти из системы\n"
        "/help - Показать это сообщение\n\n"
        "Бот автоматически напомнит о заполнении отчета в 21:00 МСК."
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