from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from carousell_alert_bot.config import Settings
from carousell_alert_bot.db.models import User, Watch, WatchStatus
from carousell_alert_bot.repositories.user_repository import UserRepository
from carousell_alert_bot.repositories.watch_repository import WatchRepository
from carousell_alert_bot.utils import next_scan_at, normalize_query, parse_price_to_cents, utc_now


class WatchValidationError(ValueError):
    """Raised when a watch request is invalid."""


@dataclass(slots=True)
class TelegramIdentity:
    telegram_user_id: int
    username: str | None
    full_name: str | None


class WatchService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.user_repo = UserRepository(session)
        self.watch_repo = WatchRepository(session)

    async def ensure_allowed_user(
        self,
        identity: TelegramIdentity,
        *,
        mark_onboarded: bool = False,
    ) -> User | None:
        is_admin = identity.telegram_user_id in self.settings.admin_telegram_ids
        is_allowed = identity.telegram_user_id in self.settings.all_allowed_telegram_ids
        if not (is_admin or is_allowed):
            return None

        user = await self.user_repo.get_by_telegram_id(identity.telegram_user_id)
        if user is None:
            user = User(
                telegram_user_id=identity.telegram_user_id,
                username=identity.username,
                full_name=identity.full_name,
                is_admin=is_admin,
                is_allowed=True,
                onboarding_complete=mark_onboarded,
            )
            self.session.add(user)
        else:
            user.username = identity.username
            user.full_name = identity.full_name
            user.is_admin = is_admin
            user.is_allowed = True
            if mark_onboarded:
                user.onboarding_complete = True

        await self.session.commit()
        await self.session.refresh(user)
        return user

    def validate_query(self, query: str) -> str:
        normalized = " ".join(query.split())
        if len(normalized) < 3:
            raise WatchValidationError("Search query must be at least 3 characters long.")
        if len(normalized) > 255:
            raise WatchValidationError("Search query must be shorter than 256 characters.")
        return normalized

    def validate_max_price_cents(self, raw_value: str | int | float) -> int:
        cents = parse_price_to_cents(raw_value)
        if cents is None or cents <= 0:
            raise WatchValidationError("Max price must be a positive amount.")
        return cents

    def validate_cadence_minutes(self, raw_value: str | int) -> int:
        try:
            minutes = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise WatchValidationError("Cadence must be a whole number of minutes.") from exc
        if not (
            self.settings.min_watch_cadence_minutes
            <= minutes
            <= self.settings.max_watch_cadence_minutes
        ):
            raise WatchValidationError(
                f"Cadence must be between {self.settings.min_watch_cadence_minutes} and "
                f"{self.settings.max_watch_cadence_minutes} minutes."
            )
        return minutes

    def validate_alert_style(self, style: str) -> str:
        normalized = " ".join(style.split())
        if len(normalized) < 8:
            raise WatchValidationError(
                "Alert style should be a short sentence describing deal quality."
            )
        return normalized

    async def create_watch(
        self,
        *,
        user: User,
        query: str,
        max_price_raw: str | int | float,
        cadence_raw: str | int,
        alert_style: str,
    ) -> Watch:
        watch = Watch(
            user_id=user.id,
            query=self.validate_query(query),
            normalized_query=normalize_query(query),
            max_price_cents=self.validate_max_price_cents(max_price_raw),
            cadence_minutes=self.validate_cadence_minutes(cadence_raw),
            alert_style=self.validate_alert_style(alert_style),
            region=self.settings.marketplace_region,
            status=WatchStatus.ACTIVE,
            next_scan_at=next_scan_at(
                self.validate_cadence_minutes(cadence_raw),
                from_time=utc_now(),
            ),
        )
        self.session.add(watch)
        await self.session.commit()
        await self.session.refresh(watch)
        return watch

    async def list_watches(self, user: User) -> list[Watch]:
        return await self.watch_repo.list_for_user(user.id)

    async def resolve_watch(self, *, user: User, reference: str) -> Watch:
        try:
            watch = await self.watch_repo.resolve_for_user(user.id, reference)
        except ValueError as exc:
            raise WatchValidationError(str(exc)) from exc
        if watch is None:
            raise WatchValidationError("Watch not found.")
        return watch

    async def pause_watch(self, *, user: User, reference: str) -> Watch:
        watch = await self.resolve_watch(user=user, reference=reference)
        watch.status = WatchStatus.PAUSED
        watch.leased_until = None
        await self.session.commit()
        await self.session.refresh(watch)
        return watch

    async def resume_watch(self, *, user: User, reference: str) -> Watch:
        watch = await self.resolve_watch(user=user, reference=reference)
        watch.status = WatchStatus.ACTIVE
        watch.next_scan_at = utc_now()
        watch.leased_until = None
        await self.session.commit()
        await self.session.refresh(watch)
        return watch

    async def delete_watch(self, *, user: User, reference: str) -> Watch:
        watch = await self.resolve_watch(user=user, reference=reference)
        watch.status = WatchStatus.DELETED
        watch.leased_until = None
        await self.session.commit()
        await self.session.refresh(watch)
        return watch

    async def update_cadence(
        self,
        *,
        user: User,
        reference: str,
        cadence_raw: str | int,
    ) -> Watch:
        watch = await self.resolve_watch(user=user, reference=reference)
        watch.cadence_minutes = self.validate_cadence_minutes(cadence_raw)
        watch.next_scan_at = next_scan_at(watch.cadence_minutes, from_time=utc_now())
        await self.session.commit()
        await self.session.refresh(watch)
        return watch

    async def update_style(self, *, user: User, reference: str, alert_style: str) -> Watch:
        watch = await self.resolve_watch(user=user, reference=reference)
        watch.alert_style = self.validate_alert_style(alert_style)
        await self.session.commit()
        await self.session.refresh(watch)
        return watch
