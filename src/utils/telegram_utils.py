"""Telegram utility functions for consistent message sending and TelegramID handling."""
import asyncio
from typing import List, Union, Optional, Tuple
from aiogram import Bot
from loguru import logger


def parse_telegram_ids(telegram_id_field: Union[str, int, None]) -> List[int]:
    """
    Parse TelegramID field and return list of valid telegram IDs.
    
    Args:
        telegram_id_field: TelegramID value from Google Sheets (can be string with commas, int, or None)
        
    Returns:
        List of valid telegram IDs as integers
    """
    if not telegram_id_field:
        return []
    
    try:
        # Convert to string and handle comma-separated values
        telegram_ids_str = str(telegram_id_field).strip()
        if not telegram_ids_str:
            return []
            
        # Split by comma and clean up
        telegram_ids = []
        for tid in telegram_ids_str.split(','):
            tid = tid.strip()
            if tid:
                try:
                    telegram_ids.append(int(tid))
                except ValueError:
                    logger.warning(f"Invalid TelegramID format: '{tid}'")
                    
        return telegram_ids
        
    except Exception as e:
        logger.error(f"Error parsing TelegramID field '{telegram_id_field}': {e}")
        return []


async def send_message_safe(
    bot: Bot, 
    telegram_id: int, 
    message: str, 
    employee_id: str = None,
    parse_mode: str = None
) -> bool:
    """
    Send message to user with error handling and logging.
    
    Args:
        bot: Bot instance
        telegram_id: Target telegram ID
        message: Message to send
        employee_id: Employee ID for logging (optional)
        parse_mode: Parse mode for message (optional)
        
    Returns:
        True if message was sent successfully, False otherwise
    """
    try:
        await bot.send_message(telegram_id, message, parse_mode=parse_mode)
        if employee_id:
            logger.info(f"Message sent successfully to employee {employee_id} (TG: {telegram_id})")
        else:
            logger.info(f"Message sent successfully to TelegramID {telegram_id}")
        return True
        
    except Exception as e:
        if employee_id:
            logger.error(f"Failed to send message to employee {employee_id} (TG: {telegram_id}): {e}")
        else:
            logger.error(f"Failed to send message to TelegramID {telegram_id}: {e}")
        return False


async def broadcast_to_employees(
    bot: Bot, 
    employees: List[dict], 
    message: str,
    rate_limit_delay: float = 0.5,
    parse_mode: str = None
) -> Tuple[int, int]:
    """
    Send message to multiple employees with rate limiting and error handling.
    
    Args:
        bot: Bot instance
        employees: List of employee dictionaries with TelegramID field
        message: Message to send
        rate_limit_delay: Delay between messages in seconds
        parse_mode: Parse mode for message (optional)
        
    Returns:
        Tuple of (successful_count, failed_count)
    """
    sent_count = 0
    failed_count = 0
    
    for employee in employees:
        employee_id = employee.get("ID", "Unknown")
        telegram_ids = parse_telegram_ids(employee.get("TelegramID"))
        
        if not telegram_ids:
            logger.debug(f"Skipping employee {employee_id}: no valid TelegramID")
            failed_count += 1
            continue
            
        # Send to all telegram IDs for this employee
        employee_success = False
        for telegram_id in telegram_ids:
            success = await send_message_safe(
                bot, telegram_id, message, employee_id, parse_mode
            )
            if success:
                employee_success = True
                # If one ID works, don't send to others for same employee
                break
            
            # Rate limiting between attempts
            await asyncio.sleep(rate_limit_delay)
            
        if employee_success:
            sent_count += 1
        else:
            failed_count += 1
            
        # Rate limiting between employees
        await asyncio.sleep(rate_limit_delay)
        
    return sent_count, failed_count


async def send_tasks_to_employees(
    bot: Bot,
    employees_with_tasks: List[dict],
    rate_limit_delay: float = 0.5
) -> Tuple[int, int]:
    """
    Send tasks to employees with standardized message format.
    
    Args:
        bot: Bot instance
        employees_with_tasks: List of employee dicts with 'tasks' field
        rate_limit_delay: Delay between messages in seconds
        
    Returns:
        Tuple of (successful_count, failed_count)
    """
    sent_count = 0
    failed_count = 0
    
    for employee in employees_with_tasks:
        employee_id = employee.get("ID", "Unknown")
        tasks = employee.get("tasks", "")
        telegram_ids = parse_telegram_ids(employee.get("TelegramID"))
        
        if not telegram_ids or not tasks.strip():
            logger.debug(f"Skipping employee {employee_id}: no TelegramID or tasks")
            failed_count += 1
            continue
            
        # Format task message
        name = f"{employee.get('Фамилия', '')} {employee.get('Имя', '')}".strip()
        if name.strip():
            task_message = f"📋 Привет, {name}!\n\nУ вас новые задачи на сегодня:\n\n{tasks}"
        else:
            task_message = f"📋 У вас новые задачи на сегодня:\n\n{tasks}"
            
        # Send to first available telegram ID
        employee_success = False
        for telegram_id in telegram_ids:
            success = await send_message_safe(bot, telegram_id, task_message, employee_id)
            if success:
                employee_success = True
                break
            await asyncio.sleep(rate_limit_delay)
            
        if employee_success:
            sent_count += 1
        else:
            failed_count += 1
            
        await asyncio.sleep(rate_limit_delay)
        
    return sent_count, failed_count


def is_admin(user_id: int, config) -> bool:
    """Check if user is admin."""
    return user_id in config.admin_ids_list