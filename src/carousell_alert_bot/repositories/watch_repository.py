from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from carousell_alert_bot.db.models import Watch, WatchStatus


class WatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: str) -> list[Watch]:
        result = await self.session.execute(
            select(Watch)
            .options(selectinload(Watch.user))
            .where(Watch.user_id == user_id, Watch.status != WatchStatus.DELETED)
            .order_by(Watch.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, watch_id: str) -> Watch | None:
        result = await self.session.execute(
            select(Watch).options(selectinload(Watch.user)).where(Watch.id == watch_id)
        )
        return result.scalar_one_or_none()

    async def resolve_for_user(self, user_id: str, reference: str) -> Watch | None:
        ref = reference.strip().lower()
        result = await self.session.execute(
            select(Watch)
            .options(selectinload(Watch.user))
            .where(
                Watch.user_id == user_id,
                Watch.status != WatchStatus.DELETED,
                or_(Watch.id == ref, Watch.id.like(f"{ref}%")),
            )
            .order_by(Watch.created_at.desc())
        )
        matches = list(result.scalars().all())
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError("Watch reference is ambiguous; use a longer ID prefix.")
        return matches[0]

    async def claim_due_watches(
        self,
        *,
        limit: int,
        lease_seconds: int,
        now: datetime,
    ) -> list[Watch]:
        candidate_ids = (
            await self.session.execute(
                select(Watch.id)
                .where(
                    Watch.status == WatchStatus.ACTIVE,
                    Watch.next_scan_at <= now,
                    or_(Watch.leased_until.is_(None), Watch.leased_until < now),
                )
                .order_by(Watch.next_scan_at.asc())
                .limit(limit)
            )
        ).scalars()

        claimed: list[Watch] = []
        lease_until = now + timedelta(seconds=lease_seconds)
        for watch_id in candidate_ids:
            updated = await self.session.execute(
                update(Watch)
                .where(
                    Watch.id == watch_id,
                    Watch.status == WatchStatus.ACTIVE,
                    Watch.next_scan_at <= now,
                    or_(Watch.leased_until.is_(None), Watch.leased_until < now),
                )
                .values(leased_until=lease_until)
                .returning(Watch.id)
            )
            claimed_id = updated.scalar_one_or_none()
            if not claimed_id:
                continue
            watch = await self.get_by_id(claimed_id)
            if watch is not None:
                claimed.append(watch)

        await self.session.commit()
        return claimed
