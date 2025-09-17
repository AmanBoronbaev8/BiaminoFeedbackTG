"""Configuration module for the bot."""
import os
from typing import List
from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Main configuration class with direct field access."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid"
    )
    
    bot_token: SecretStr
    admin_ids: str
    spreadsheet_id: str
    service_account_file: str = "service_account.json"
    redis_url: str = "redis://localhost:6379/0"

    @field_validator('admin_ids')
    @classmethod
    def validate_admin_ids(cls, v):
        if not v or not v.strip():
            raise ValueError("admin_ids cannot be empty")
        return v

    @property
    def admin_ids_list(self) -> List[int]:
        """Get admin IDs as list of integers."""
        return [int(id_.strip()) for id_ in self.admin_ids.split(",") if id_.strip()]


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config()