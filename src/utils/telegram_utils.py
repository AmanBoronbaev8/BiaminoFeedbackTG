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
    parse_mode: str = None,
    config = None
) -> Tuple[int, int]:
    """
    Send message to multiple employees with rate limiting and error handling.
    
    Args:
        bot: Bot instance
        employees: List of employee dictionaries with TelegramID field
        message: Message to send
        rate_limit_delay: Delay between messages in seconds
        parse_mode: Parse mode for message (optional)
        config: Config instance for field names
        
    Returns:
        Tuple of (successful_count, failed_count)
    """
    sent_count = 0
    failed_count = 0
    
    # Get column names from config or use defaults
    if config:
        id_col = config.team_id_col
        telegram_col = config.team_telegram_id_col
    else:
        id_col = "ID"
        telegram_col = "TelegramID"
    
    for employee in employees:
        employee_id = employee.get(id_col, "Unknown")
        telegram_ids = parse_telegram_ids(employee.get(telegram_col))
        
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
    rate_limit_delay: float = 0.5,
    config = None
) -> Tuple[int, int]:
    """
    Send tasks to employees with standardized message format.
    
    Args:
        bot: Bot instance
        employees_with_tasks: List of employee dicts with 'tasks' field (list of task dicts)
        rate_limit_delay: Delay between messages in seconds
        config: Config instance for field names
        
    Returns:
        Tuple of (successful_count, failed_count)
    """
    sent_count = 0
    failed_count = 0
    
    # Get column names from config or use defaults
    if config:
        id_col = config.team_id_col
        lastname_col = config.team_lastname_col
        firstname_col = config.team_firstname_col
        telegram_col = config.team_telegram_id_col
    else:
        id_col = "ID"
        lastname_col = "Фамилия"
        firstname_col = "Имя"
        telegram_col = "TelegramID"
    
    for employee in employees_with_tasks:
        employee_id = employee.get(id_col, "Unknown")
        tasks = employee.get("tasks", [])
        telegram_ids = parse_telegram_ids(employee.get(telegram_col))
        
        if not telegram_ids or not tasks:
            logger.debug(f"Skipping employee {employee_id}: no TelegramID or tasks")
            failed_count += 1
            continue
            
        # Format task message with multiple tasks
        name = f"{employee.get(lastname_col, '')} {employee.get(firstname_col, '')}".strip()
        
        if isinstance(tasks, list):
            # New format: list of task dictionaries
            task_lines = []
            for task in tasks:
                task_text = task.get('task', '')
                deadline = task.get('deadline', '')
                deadline_part = f" (до {deadline})" if deadline else ""
                formatted_task = format_task_name(task_text)
                task_lines.append(f"• {formatted_task}{deadline_part}")
            
            if task_lines:
                tasks_text = "\n".join(task_lines)
            else:
                logger.debug(f"No valid tasks for employee {employee_id}")
                failed_count += 1
                continue
        else:
            # Old format: tasks as string (backwards compatibility)
            tasks_text = str(tasks)
            
        if name.strip():
            task_message = f"📋 Привет, {name}!\n\nУ вас активные задачи:\n\n{tasks_text}"
        else:
            task_message = f"📋 У вас активные задачи:\n\n{tasks_text}"
            
        # Send to first available telegram ID
        employee_success = False
        for telegram_id in telegram_ids:
            success = await send_message_safe(bot, telegram_id, task_message, employee_id, "HTML")
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


def format_task_name(task_text: str, max_length: int = 50) -> str:
    """
    Format task name by truncating to max_length and adding ellipsis if needed.
    
    Args:
        task_text: Original task text
        max_length: Maximum length (default 50)
        
    Returns:
        Formatted task text
    """
    if not task_text:
        return ""
    
    task_text = task_text.strip()
    if len(task_text) <= max_length:
        return task_text
    
    return task_text[:max_length] + "..."


def is_admin(user_id: int, config) -> bool:
    """Check if user is admin."""
    return user_id in config.admin_ids_list