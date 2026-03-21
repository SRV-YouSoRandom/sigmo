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

    # Postgres direct connection (used by APScheduler job store — bypasses pgbouncer)
    POSTGRES_DIRECT_HOST: str = "postgres"
    POSTGRES_DIRECT_PORT: int = 5432

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
    def scheduler_database_url(self) -> str:
        """Synchronous psycopg2 URL for APScheduler's SQLAlchemyJobStore.
        Must connect directly to postgres, not pgbouncer, because APScheduler
        uses SQLAlchemy core with a persistent connection."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_DIRECT_HOST}:{self.POSTGRES_DIRECT_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def telegram_api_url(self) -> str:
        return f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Timezone helper – display times in PHT (UTC+8)
# ---------------------------------------------------------------------------
from datetime import timedelta, timezone

PHT = timezone(timedelta(hours=8))


def to_pht(dt) -> "datetime":
    """Convert a naive-UTC datetime to PHT (UTC+8) for user-facing display."""
    from datetime import datetime as _dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PHT)


def pht_today_start_utc() -> datetime:
    """Return the start of today (PHT) as a naive UTC datetime for DB queries."""
    now_pht = to_pht(datetime.utcnow())
    return now_pht.replace(hour=0, minute=0, second=0, microsecond=0)\
                  .astimezone(timezone.utc).replace(tzinfo=None)