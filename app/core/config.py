from typing import Literal

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "ChefLink"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: PostgresDsn
    DATABASE_SYNC_URL: str

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_URL: str | None = None

    # LLM Configuration
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    LLM_PROVIDER: Literal["openai", "anthropic"] = "anthropic"
    LLM_MODEL: str = "claude-opus-4-20250514"
    LLM_THINKING_ENABLED: bool = True
    LLM_THINKING_BUDGET: int = 8000


    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str
    INVITATION_CODE_LENGTH: int = 8

    # Meal Plan Settings
    MEAL_PLAN_LOCK_HOUR: int = 20
    MEAL_PLAN_LOCK_TIMEZONE: str = "UTC"

    @field_validator("DATABASE_URL")
    def validate_postgres_db(cls, v: PostgresDsn) -> PostgresDsn:
        return v


settings = Settings()