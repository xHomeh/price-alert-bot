from __future__ import annotations

from carousell_alert_bot.services.watch_service import (
    TelegramIdentity,
    WatchService,
    WatchValidationError,
)
from tests.support import create_test_session_factory, make_settings, run


def test_allowlist_enforcement() -> None:
    async def scenario() -> None:
        settings = make_settings(allowed_telegram_ids=[111], admin_telegram_ids=[111])
        session_factory, engine = await create_test_session_factory()
        try:
            async with session_factory() as session:
                service = WatchService(session, settings)
                user = await service.ensure_allowed_user(
                    TelegramIdentity(
                        telegram_user_id=999,
                        username="blocked",
                        full_name="Blocked User",
                    )
                )
                assert user is None
        finally:
            await engine.dispose()

    run(scenario())


def test_create_update_pause_resume_delete_watch_flow() -> None:
    async def scenario() -> None:
        settings = make_settings()
        session_factory, engine = await create_test_session_factory()
        try:
            async with session_factory() as session:
                service = WatchService(session, settings)
                user = await service.ensure_allowed_user(
                    TelegramIdentity(telegram_user_id=111, username="joel", full_name="Joel Tan"),
                    mark_onboarded=True,
                )
                assert user is not None and user.onboarding_complete is True

                watch = await service.create_watch(
                    user=user,
                    query="Sony WH-1000XM5",
                    max_price_raw="250",
                    cadence_raw="15",
                    alert_style="Only alert for exceptional deals.",
                )
                assert watch.query == "Sony WH-1000XM5"
                assert watch.max_price_cents == 25_000
                assert watch.cadence_minutes == 15

                user_watches = await service.list_watches(user)
                assert len(user_watches) == 1

                watch = await service.update_cadence(
                    user=user,
                    reference=watch.id[:8],
                    cadence_raw="60",
                )
                assert watch.cadence_minutes == 60

                watch = await service.update_style(
                    user=user,
                    reference=watch.id[:8],
                    alert_style="Slightly good deals are okay.",
                )
                assert watch.alert_style == "Slightly good deals are okay."

                watch = await service.pause_watch(user=user, reference=watch.id[:8])
                assert watch.status.value == "paused"

                watch = await service.resume_watch(user=user, reference=watch.id[:8])
                assert watch.status.value == "active"

                watch = await service.delete_watch(user=user, reference=watch.id[:8])
                assert watch.status.value == "deleted"
                assert await service.list_watches(user) == []
        finally:
            await engine.dispose()

    run(scenario())


def test_watch_validation_rejects_invalid_cadence() -> None:
    async def scenario() -> None:
        settings = make_settings()
        session_factory, engine = await create_test_session_factory()
        try:
            async with session_factory() as session:
                service = WatchService(session, settings)
                user = await service.ensure_allowed_user(
                    TelegramIdentity(telegram_user_id=111, username="joel", full_name="Joel Tan")
                )
                assert user is not None
                try:
                    await service.create_watch(
                        user=user,
                        query="Sony XM5",
                        max_price_raw="200",
                        cadence_raw="1",
                        alert_style="Only alert for huge deals.",
                    )
                except WatchValidationError as exc:
                    assert "Cadence must be between" in str(exc)
                else:
                    raise AssertionError("Expected WatchValidationError")
        finally:
            await engine.dispose()

    run(scenario())
