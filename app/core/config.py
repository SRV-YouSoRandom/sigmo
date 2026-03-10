"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""

    # Database
    POSTGRES_HOST: str = "pgbouncer"
    POSTGRES_PORT: int = 6432
    POSTGRES_DB: str = "sigmo"
    POSTGRES_USER: str = "sigmo"
    POSTGRES_PASSWORD: str = ""

    # Webhook
    SECRET_WEBHOOK_PATH: str = "/webhook"

    # App
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def telegram_api_url(self) -> str:
        return f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
