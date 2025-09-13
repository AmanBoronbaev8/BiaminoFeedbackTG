"""Bot middlewares."""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from ..services import GoogleSheetsService
from ..config_data import Config


class DependencyInjectionMiddleware(BaseMiddleware):
    """Middleware to inject dependencies into handlers."""
    
    def __init__(self, sheets_service: GoogleSheetsService, config: Config):
        self.sheets_service = sheets_service
        self.config = config
        
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        data['sheets_service'] = self.sheets_service
        data['config'] = self.config
        return await handler(event, data)