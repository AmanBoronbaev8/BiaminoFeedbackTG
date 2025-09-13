"""Configuration module for the bot."""
import os
from typing import List
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TgBot(BaseModel):
    """Telegram bot configuration."""
    token: SecretStr
    admin_ids: List[int]


class GoogleSheets(BaseModel):
    """Google Sheets configuration."""
    spreadsheet_id: str
    service_account_file: str = "service_account.json"


class Redis(BaseModel):
    """Redis configuration."""
    url: str


class Config(BaseSettings):
    """Main configuration class."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid"
    )
    
    # Use proper field names that match environment variables
    bot_token: SecretStr
    admin_ids: str
    spreadsheet_id: str
    service_account_file: str = "service_account.json"
    redis_url: str = "redis://localhost:6379/0"

    def get_tg_bot(self) -> TgBot:
        """Get TgBot configuration."""
        admin_ids_list = [int(id_.strip()) for id_ in self.admin_ids.split(",") if id_.strip()]
        return TgBot(
            token=self.bot_token,
            admin_ids=admin_ids_list
        )

    def get_google_sheets(self) -> GoogleSheets:
        """Get GoogleSheets configuration."""
        return GoogleSheets(
            spreadsheet_id=self.spreadsheet_id,
            service_account_file=self.service_account_file
        )

    def get_redis(self) -> Redis:
        """Get Redis configuration."""
        return Redis(url=self.redis_url)


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config()