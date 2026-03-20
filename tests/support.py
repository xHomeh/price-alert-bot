from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from carousell_alert_bot.config import Settings
from carousell_alert_bot.db.base import Base


def fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / "carousell" / name


def make_settings(**overrides) -> Settings:
    defaults = {
        "telegram_bot_token": "test-token",
        "database_url": "sqlite+aiosqlite://",
        "openai_api_key": "test-openai-key",
        "openai_model": "gpt-5.2",
        "serpapi_api_key": "test-serp-key",
        "allowed_telegram_ids": [111, 222],
        "admin_telegram_ids": [111],
        "scan_batch_size": 5,
        "scan_loop_seconds": 1,
        "watch_lease_seconds": 30,
        "listing_scan_limit": 10,
        "min_confidence_to_alert": 0.7,
    }
    defaults.update(overrides)
    return Settings(**defaults)


async def create_test_session_factory() -> tuple[async_sessionmaker, object]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def run(coro):
    return asyncio.run(coro)

