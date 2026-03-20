from __future__ import annotations

from functools import cached_property
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.2", alias="OPENAI_MODEL")
    serpapi_api_key: str | None = Field(default=None, alias="SERPAPI_API_KEY")

    allowed_telegram_ids: list[int] = Field(default_factory=list, alias="ALLOWED_TELEGRAM_IDS")
    admin_telegram_ids: list[int] = Field(default_factory=list, alias="ADMIN_TELEGRAM_IDS")

    bot_polling_timeout: int = Field(default=20, alias="BOT_POLLING_TIMEOUT")
    scan_batch_size: int = Field(default=5, alias="SCAN_BATCH_SIZE")
    scan_loop_seconds: int = Field(default=30, alias="SCAN_LOOP_SECONDS")
    watch_lease_seconds: int = Field(default=300, alias="WATCH_LEASE_SECONDS")
    listing_scan_limit: int = Field(default=15, alias="LISTING_SCAN_LIMIT")
    min_confidence_to_alert: float = Field(default=0.7, alias="MIN_CONFIDENCE_TO_ALERT")
    playwright_headless: bool = Field(default=True, alias="PLAYWRIGHT_HEADLESS")
    playwright_storage_state_path: str | None = Field(
        default=None,
        alias="PLAYWRIGHT_STORAGE_STATE_PATH",
    )

    marketplace_region: str = "SG"
    marketplace_currency: str = "SGD"
    min_watch_cadence_minutes: int = 5
    max_watch_cadence_minutes: int = 1440

    @field_validator("allowed_telegram_ids", "admin_telegram_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: Any) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            return [int(item) for item in value]
        if isinstance(value, tuple | set):
            return [int(item) for item in value]
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        raise TypeError("Telegram ID list must be a comma-separated string or list.")

    @cached_property
    def all_allowed_telegram_ids(self) -> set[int]:
        return set(self.allowed_telegram_ids) | set(self.admin_telegram_ids)
