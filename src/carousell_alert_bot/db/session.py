from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from carousell_alert_bot.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, future=True, pool_pre_ping=True)


def create_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_engine(settings)
    return async_sessionmaker(engine, expire_on_commit=False)

