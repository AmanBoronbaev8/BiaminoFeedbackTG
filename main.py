"""Main module for BiaminoFeedbackTG bot."""
import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from loguru import logger

from src.config_data import load_config
from src.utils import setup_logging, BotScheduler
from src.services import GoogleSheetsService
from src.handlers import user_router, admin_router
from src.middlewares import DependencyInjectionMiddleware


async def main():
    """Main function to run the bot."""
    # Setup logging
    setup_logging()
    logger.info("Starting BiaminoFeedbackTG bot")
    
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Initialize bot with default properties
        bot = Bot(
            token=config.bot_token.get_secret_value(),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        
        # Initialize dispatcher with Redis storage
        try:
            storage = RedisStorage.from_url(config.redis_url)
            dp = Dispatcher(storage=storage)
            logger.info(f"Redis storage initialized: {config.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            logger.warning("Falling back to memory storage")
            from aiogram.fsm.storage.memory import MemoryStorage
            dp = Dispatcher(storage=MemoryStorage())
        
        # Initialize Google Sheets service
        sheets_service = GoogleSheetsService(
            service_account_file=config.service_account_file,
            spreadsheet_id=config.spreadsheet_id,
            config=config
        )
        await sheets_service.initialize()
        logger.info("Google Sheets service initialized")
        
        # Initialize scheduler
        scheduler = BotScheduler(bot, sheets_service, config)
        
        # Register middleware to pass dependencies to handlers
        middleware = DependencyInjectionMiddleware(sheets_service, config)
        dp.message.middleware(middleware)
        dp.callback_query.middleware(middleware)
        
        # Include routers - admin router first to handle admin commands
        dp.include_router(admin_router)
        dp.include_router(user_router)
        
        logger.info("Routers registered successfully")
        
        # Start scheduler
        await scheduler.start()
        
        # Skip webhook updates and start polling
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Bot started successfully")
        
        # Start polling
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise
    finally:
        if 'scheduler' in locals():
            await scheduler.stop()
        if 'storage' in locals() and hasattr(storage, 'close'):
            await storage.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
