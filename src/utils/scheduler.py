"""Scheduler for automated triggers (21:00 and 24:00 MSK)."""
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from loguru import logger
import pytz

from ..services import GoogleSheetsService
from .telegram_utils import broadcast_to_employees, send_tasks_to_employees

current_timezone = pytz.timezone('Europe/Moscow')

class BotScheduler:
    """Scheduler for automated bot tasks."""
    
    def __init__(self, bot: Bot, sheets_service: GoogleSheetsService):
        self.bot = bot
        self.sheets_service = sheets_service
        self.scheduler = AsyncIOScheduler(timezone=current_timezone)
        
    async def start(self):
        """Start the scheduler."""
        # Schedule report collection at 21:00 MSK
        self.scheduler.add_job(
            self.trigger_report_collection,
            CronTrigger(hour=21, minute=0, timezone=current_timezone),
            id='report_collection'
        )
        
        # Schedule reminders at 24:00 (00:00) MSK
        self.scheduler.add_job(
            self.send_reminders,
            CronTrigger(hour=0, minute=0, timezone=current_timezone),
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
            _, employees_without_reports = await self.sheets_service.get_employees_without_reports_batch(today)
            
            report_text = (
                "Пришло время для отчета! 📝\n\n"
                "Используйте команду /report для заполнения."
            )
            
            triggered_count, failed_count = await broadcast_to_employees(
                self.bot, employees_without_reports, report_text
            )
                        
            logger.info(f"Report collection triggered for {triggered_count} employees")
            
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
            
            _, employees_with_telegram = await self.sheets_service.get_employees_without_reports_batch(date_str)
            
            reminder_text = (
                "Кажется, вы забыли заполнить отчет за вчера. "
                "Пожалуйста, не забудьте это сделать! ⏰\n\n"
                "Используйте команду /report для заполнения отчета."
            )
            
            sent_count, failed_count = await broadcast_to_employees(
                self.bot, employees_with_telegram, reminder_text
            )
                        
            logger.info(f"Reminders sent to {sent_count} employees")
            
        except Exception as e:
            logger.error(f"Error in send_reminders: {e}")
            
    async def send_task_notifications(self):
        """Send task notifications (can be triggered manually by admin)."""
        logger.info("Starting task notifications")
        
        try:
            today = datetime.now().strftime("%d.%m.%Y")
            employees_with_tasks = await self.sheets_service.get_employees_with_tasks_batch(today)
            
            sent_count, failed_count = await send_tasks_to_employees(self.bot, employees_with_tasks)
                        
            logger.info(f"Task notifications sent to {sent_count} employees")
            
        except Exception as e:
            logger.error(f"Error in send_task_notifications: {e}")