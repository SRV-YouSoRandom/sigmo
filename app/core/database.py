"""Async SQLAlchemy database engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def _build_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)


def _build_session_factory(eng):
    return async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


# Lazy globals – only created when first accessed at runtime, not at import time
_engine = None
_async_session = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_async_session():
    global _async_session
    if _async_session is None:
        _async_session = _build_session_factory(get_engine())
    return _async_session


# Convenience aliases for non-test code
@property
def engine():
    return get_engine()


async_session = property(lambda self: get_async_session())


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """Dependency that yields an async DB session."""
    factory = get_async_session()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Create tables (used for dev/testing; production uses Alembic)."""
    eng = get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine connection pool."""
    eng = get_engine()
    await eng.dispose()
