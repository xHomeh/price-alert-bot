from __future__ import annotations

from carousell_alert_bot.config import Settings


def test_settings_accept_single_numeric_telegram_ids() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="test-token",
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@postgres:5432/carousell_alert_bot",
        ALLOWED_TELEGRAM_IDS=1530569197,
        ADMIN_TELEGRAM_IDS=1530569197,
    )

    assert settings.allowed_telegram_ids == [1530569197]
    assert settings.admin_telegram_ids == [1530569197]
