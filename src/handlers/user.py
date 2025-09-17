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
                employee_id=employee_data.get("ID", ""),
                authenticated=True,
                is_admin=False
            )
            
            # Get full name
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