"""Scheduler for automated triggers (21:00 and 24:00 MSK)."""
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from aiogram.fsm.storage.base import StorageKey
from loguru import logger
import pytz

from ..services import GoogleSheetsService


class BotScheduler:
    """Scheduler for automated bot tasks."""
    
    def __init__(self, bot: Bot, sheets_service: GoogleSheetsService):
        self.bot = bot
        self.sheets_service = sheets_service
        self.scheduler = AsyncIOScheduler(timezone=pytz.timezone('Europe/Moscow'))
        
    async def is_user_authorized(self, telegram_id: int) -> bool:
        """Check if user is authorized by checking FSM state."""
        try:
            storage = self.bot.session.middleware.storage
            storage_key = StorageKey(
                bot_id=self.bot.id,
                chat_id=telegram_id,
                user_id=telegram_id
            )
            
            # Get FSM data from storage
            data = await storage.get_data(key=storage_key)
            
            # Check if user has authenticated flag
            is_authenticated = data.get('authenticated', False)
            logger.debug(f"User {telegram_id} authorization status: {is_authenticated}")
            
            return is_authenticated
            
        except Exception as e:
            logger.error(f"Error checking authorization for user {telegram_id}: {e}")
            return False
        
    async def start(self):
        """Start the scheduler."""
        # Schedule report collection at 21:00 MSK
        self.scheduler.add_job(
            self.trigger_report_collection,
            CronTrigger(hour=21, minute=0, timezone=pytz.timezone('Europe/Moscow')),
            id='report_collection'
        )
        
        # Schedule reminders at 24:00 (00:00) MSK
        self.scheduler.add_job(
            self.send_reminders,
            CronTrigger(hour=0, minute=0, timezone=pytz.timezone('Europe/Moscow')),
            id='send_reminders'
        )
        
        self.scheduler.start()
        logger.info("Scheduler started with Moscow timezone")
        
    async def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")
        
    async def trigger_report_collection(self):
        """Trigger report collection for all employees."""
        logger.info("Starting automated report collection trigger")
        
        try:
            today = datetime.now().strftime("%d.%m.%Y")
            employees = await self.sheets_service.get_all_employees()
            
            triggered_count = 0
            skipped_count = 0
            
            for employee in employees:
                employee_id = employee.get("ID", "")
                telegram_ids_str = employee.get("TelegramID", "")
                
                if not employee_id or not telegram_ids_str:
                    continue
                    
                # Check if report already submitted
                has_report = await self.sheets_service.check_report_submitted(employee_id, today)
                
                if not has_report:
                    # Parse multiple Telegram IDs separated by commas
                    telegram_ids = [tid.strip() for tid in str(telegram_ids_str).split(',') if tid.strip()]
                    
                    for telegram_id in telegram_ids:
                        try:
                            # Check if user is authorized
                            is_authorized = await self.is_user_authorized(int(telegram_id))
                            
                            if not is_authorized:
                                skipped_count += 1
                                logger.warning(f"Skipping report trigger for unauthorized user {employee_id} (TG: {telegram_id})")
                                continue
                            
                            report_text = (
                                "Пришло время для отчета! 📝\n\n"
                                "Используйте команду /report для заполнения."
                            )
                            
                            await self.bot.send_message(int(telegram_id), report_text)
                            triggered_count += 1
                            logger.info(f"Triggered report collection for {employee_id} (TG: {telegram_id})")
                            
                            # Small delay to avoid hitting rate limits
                            await asyncio.sleep(0.5)
                            
                        except Exception as e:
                            logger.error(f"Failed to trigger report collection for {employee_id} (TG: {telegram_id}): {e}")
                        
            logger.info(f"Report collection triggered for {triggered_count} authorized employees, skipped {skipped_count} unauthorized")
            
        except Exception as e:
            logger.error(f"Error in trigger_report_collection: {e}")
            
    async def send_reminders(self):
        """Send reminders to employees who haven't submitted reports."""
        logger.info("Starting automated reminder sending")
        
        try:
            # Get yesterday's date (since this runs at midnight)
            yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday = yesterday.replace(day=yesterday.day - 1)
            date_str = yesterday.strftime("%d.%m.%Y")
            
            employees_without_reports = await self.sheets_service.get_employees_without_reports(date_str)
            employees = await self.sheets_service.get_all_employees()
            
            sent_count = 0
            
            for employee in employees:
                employee_id = employee.get("ID", "")
                telegram_id = employee.get("TelegramID")  # Updated to match your column name
                
                if employee_id in employees_without_reports and telegram_id:
                    try:
                        reminder_text = (
                            "Кажется, вы забыли заполнить отчет за вчера. "
                            "Пожалуйста, не забудьте это сделать! ⏰\n\n"
                            "Используйте команду /report для заполнения отчета."
                        )
                        
                        await self.bot.send_message(int(telegram_id), reminder_text)
                        sent_count += 1
                        logger.info(f"Sent reminder to {employee_id}")
                        
                        # Small delay to avoid hitting rate limits
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"Failed to send reminder to {employee_id}: {e}")
                        
            logger.info(f"Reminders sent to {sent_count} employees")
            
        except Exception as e:
            logger.error(f"Error in send_reminders: {e}")
            
    async def send_task_notifications(self):
        """Send task notifications (can be triggered manually by admin)."""
        logger.info("Starting task notifications")
        
        try:
            today = datetime.now().strftime("%d.%m.%Y")
            employees = await self.sheets_service.get_all_employees()
            
            sent_count = 0
            
            for employee in employees:
                employee_id = employee.get("ID", "")
                telegram_id = employee.get("TelegramID")  # Updated to match your column name
                
                if not employee_id or not telegram_id:
                    continue
                    
                tasks = await self.sheets_service.get_employee_tasks(employee_id, today)
                
                if tasks and tasks.strip():
                    try:
                        task_text = f"📋 У вас новые задачи на сегодня:\n\n{tasks}"
                        await self.bot.send_message(int(telegram_id), task_text)
                        sent_count += 1
                        logger.info(f"Sent tasks to {employee_id}")
                        
                        # Small delay to avoid hitting rate limits
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"Failed to send tasks to {employee_id}: {e}")
                        
            logger.info(f"Task notifications sent to {sent_count} employees")
            
        except Exception as e:
            logger.error(f"Error in send_task_notifications: {e}")