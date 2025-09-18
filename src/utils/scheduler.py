"""Scheduler for automated triggers (21:00 and 24:00 MSK)."""
import asyncio
from datetime import datetime
from typing import List, Dict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from loguru import logger
import pytz

from ..services import GoogleSheetsService, NotionService, TaskSyncService
from .telegram_utils import broadcast_to_employees, send_tasks_to_employees, parse_telegram_ids

current_timezone = pytz.timezone('Europe/Moscow')

class BotScheduler:
    """Scheduler for automated bot tasks."""
    
    def __init__(self, bot: Bot, sheets_service: GoogleSheetsService, config = None):
        self.bot = bot
        self.sheets_service = sheets_service
        self.config = config
        self.scheduler = AsyncIOScheduler(timezone=current_timezone)
        
        # Initialize Notion services
        self.notion_service = NotionService(config)
        self.task_sync_service = TaskSyncService(self.notion_service, sheets_service, config)
        
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
        
        # Schedule deadline reminders every hour
        self.scheduler.add_job(
            self.send_deadline_reminders,
            CronTrigger(minute=0, timezone=current_timezone),  # Every hour
            id='deadline_reminders'
        )
        
        # Schedule Notion task sync every 15 minutes
        self.scheduler.add_job(
            self.sync_notion_tasks,
            CronTrigger(minute='*/15', timezone=current_timezone),  # Every 15 minutes
            id='notion_task_sync'
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
                self.bot, employees_without_reports, report_text, config=self.config
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
                self.bot, employees_with_telegram, reminder_text, config=self.config
            )
                        
            logger.info(f"Reminders sent to {sent_count} employees")
            
        except Exception as e:
            logger.error(f"Error in send_reminders: {e}")
            
    async def send_task_notifications(self):
        """Send task notifications (can be triggered manually by admin)."""
        logger.info("Starting task notifications")
        
        try:
            employees_with_tasks = await self.sheets_service.get_employees_with_tasks_batch()
            
            sent_count, failed_count = await send_tasks_to_employees(self.bot, employees_with_tasks, config=self.config)
                        
            logger.info(f"Task notifications sent to {sent_count} employees")
            
        except Exception as e:
            logger.error(f"Error in send_task_notifications: {e}")
            
    async def send_deadline_reminders(self):
        """Send reminders for tasks with deadlines in 12 hours."""
        logger.info("Checking for deadline reminders")
        
        try:
            from datetime import timedelta
            
            # Calculate 12 hours from now
            now = datetime.now(current_timezone)
            twelve_hours_later = now + timedelta(hours=12)
            deadline_date = twelve_hours_later.strftime("%d.%m.%Y")
            
            logger.info(f"Checking for deadlines on: {deadline_date}")
            
            # Get all employees
            employees = await self.sheets_service.get_all_employees_cached()
            
            reminder_count = 0
            checked_employees = 0
            employees_with_tasks = 0
            
            for employee in employees:
                employee_id = employee.get(self.config.team_id_col if self.config else "ID", "")
                if not employee_id:
                    continue
                    
                checked_employees += 1
                
                try:
                    # Get tasks with deadlines for this date
                    tasks_with_deadlines = await self.sheets_service.get_tasks_with_deadline(employee_id, deadline_date)
                    
                    if tasks_with_deadlines:
                        employees_with_tasks += 1
                        logger.info(f"Employee {employee_id} has {len(tasks_with_deadlines)} tasks with deadline {deadline_date}")
                        
                        telegram_ids = parse_telegram_ids(employee.get(
                            self.config.team_telegram_id_col if self.config else "TelegramID"
                        ))
                        
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
                                    await self.bot.send_message(
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
                                
            logger.info(f"Deadline reminders completed: {reminder_count} sent, {checked_employees} checked, {employees_with_tasks} with tasks")
            
        except Exception as e:
            logger.error(f"Error in send_deadline_reminders: {e}", exc_info=True)
            
    async def sync_notion_tasks(self):
        """Sync tasks from Notion databases to Google Sheets."""
        logger.info("Starting Notion task synchronization")
        
        try:
            stats = await self.task_sync_service.sync_tasks_from_notion()
            
            logger.info(
                f"Notion sync completed - "
                f"Tasks: {stats['total_tasks']}, "
                f"Workers: {stats['processed_workers']}, "
                f"Updated sheets: {stats['updated_sheets']}, "
                f"Errors: {stats['errors']}"
            )
            
        except Exception as e:
            logger.error(f"Error in sync_notion_tasks: {e}", exc_info=True)