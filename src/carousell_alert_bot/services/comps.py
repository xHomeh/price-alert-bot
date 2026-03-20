from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from carousell_alert_bot.contracts import ComparisonSnapshot, CompStats
from carousell_alert_bot.db.models import Watch
from carousell_alert_bot.repositories.listing_repository import ListingRepository


class ComparisonService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ListingRepository(session)

    async def build_snapshot(
        self,
        *,
        watch: Watch,
        exclude_listing_id: str | None = None,
    ) -> ComparisonSnapshot:
        same_watch_prices = await self.repo.prices_for_watch(
            watch_id=watch.id,
            exclude_listing_id=exclude_listing_id,
        )
        same_query_prices = await self.repo.prices_for_normalized_query(
            normalized_query=watch.normalized_query,
            exclude_listing_id=exclude_listing_id,
        )
        return ComparisonSnapshot(
            same_watch=CompStats.from_prices(same_watch_prices),
            same_query=CompStats.from_prices(same_query_prices),
        )
