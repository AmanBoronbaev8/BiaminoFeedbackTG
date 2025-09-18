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
    
    # Bot settings
    bot_token: SecretStr
    admin_ids: str
    spreadsheet_id: str
    service_account_file: str = "service_account.json"
    redis_url: str = "redis://localhost:6379/0"
    
    # Notion API settings
    notion_api_token: SecretStr
    notion_database_id_1: str
    notion_database_id_2: str
    
    # Team sheet settings
    team_sheet_name: str = "Команда"
    
    # Team sheet column names
    team_id_col: str = "ID"
    team_lastname_col: str = "Фамилия"
    team_firstname_col: str = "Имя"
    team_department_col: str = "Департамент"
    team_section_col: str = "Отдел"
    team_position_col: str = "Должность"
    team_telegram_id_col: str = "TelegramID"
    
    # Tasks table column names
    tasks_date_col: str = "Дата"
    tasks_id_col: str = "Task ID"
    tasks_task_col: str = "Задача"
    tasks_deadline_col: str = "Дедлайн"
    tasks_completed_col: str = "Выполнено"
    
    # Reports table column names
    reports_date_col: str = "Date"
    reports_task_id_col: str = "Task ID"
    reports_feedback_col: str = "Фидбек по задачам"
    reports_difficulties_col: str = "Сложности по задачам"
    reports_daily_report_col: str = "Отчет за день"
    
    # Table positioning settings
    tasks_table_start_row: int = 1
    tasks_table_start_col: str = "A"
    reports_table_start_row: int = 1
    reports_table_start_col: str = "H"

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