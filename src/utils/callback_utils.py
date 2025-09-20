"""Utility functions for handling callback queries and preventing timeouts."""
import asyncio
from typing import Callable, Any, Awaitable
from aiogram.types import CallbackQuery
from loguru import logger


async def handle_long_operation(
    callback: CallbackQuery,
    operation: Callable[[], Awaitable[Any]],
    processing_message: str = "⏳ Обрабатываю запрос...",
    success_message_template: str = "✅ Операция завершена успешно!",
    error_message: str = "❌ Произошла ошибка при выполнении операции."
) -> Any:
    """
    Handle long-running operations to prevent callback timeout errors.
    
    Args:
        callback: CallbackQuery object
        operation: Async function to execute
        processing_message: Message to show while processing
        success_message_template: Template for success message (can use {result} placeholder)
        error_message: Message to show on error
        
    Returns:
        Result of the operation or None if error occurred
    """
    # Answer callback immediately to prevent timeout
    await callback.answer()
    
    try:
        # Show processing message
        await callback.message.edit_text(
            processing_message,
            reply_markup=None
        )
        
        # Execute the long operation
        result = await operation()
        
        # Show success message
        if "{result}" in success_message_template:
            success_message = success_message_template.format(result=result)
        else:
            success_message = success_message_template
            
        await callback.message.edit_text(
            success_message,
            reply_markup=None,
            parse_mode="HTML"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in long operation: {e}", exc_info=True)
        await callback.message.edit_text(
            f"{error_message}\n\nОшибка: {str(e)}",
            reply_markup=None
        )
        return None


async def with_progress_updates(
    callback: CallbackQuery,
    operation: Callable[[Callable[[str], Awaitable[None]]], Awaitable[Any]],
    initial_message: str = "⏳ Начинаю обработку..."
) -> Any:
    """
    Handle operations with progress updates.
    
    Args:
        callback: CallbackQuery object
        operation: Async function that accepts an update_progress callback
        initial_message: Initial message to show
        
    Returns:
        Result of the operation or None if error occurred
    """
    # Answer callback immediately to prevent timeout
    await callback.answer()
    
    try:
        # Show initial message
        await callback.message.edit_text(
            initial_message,
            reply_markup=None
        )
        
        async def update_progress(message: str):
            """Update progress message."""
            try:
                await callback.message.edit_text(
                    message,
                    reply_markup=None,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Failed to update progress: {e}")
        
        # Execute operation with progress updates
        result = await operation(update_progress)
        return result
        
    except Exception as e:
        logger.error(f"Error in operation with progress: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Произошла ошибка при выполнении операции.\n\nОшибка: {str(e)}",
            reply_markup=None
        )
        return None


class CallbackTimeout:
    """Context manager to handle callback timeouts."""
    
    def __init__(self, callback: CallbackQuery, timeout_seconds: int = 25):
        self.callback = callback
        self.timeout_seconds = timeout_seconds
        self.answered = False
        
    async def __aenter__(self):
        # Start timeout timer
        self.timeout_task = asyncio.create_task(self._timeout_handler())
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Cancel timeout task
        if not self.timeout_task.done():
            self.timeout_task.cancel()
        
        # Answer callback if not already answered
        if not self.answered:
            try:
                await self.callback.answer()
            except Exception as e:
                logger.warning(f"Failed to answer callback on exit: {e}")
                
    async def answer(self, text: str = None, show_alert: bool = False):
        """Answer the callback query."""
        if not self.answered:
            await self.callback.answer(text, show_alert=show_alert)
            self.answered = True
            
    async def _timeout_handler(self):
        """Handle timeout by answering the callback."""
        try:
            await asyncio.sleep(self.timeout_seconds)
            if not self.answered:
                await self.callback.answer()
                self.answered = True
                logger.warning(f"Auto-answered callback due to timeout after {self.timeout_seconds}s")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in timeout handler: {e}")