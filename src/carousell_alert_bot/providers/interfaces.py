from __future__ import annotations

from typing import Protocol

from carousell_alert_bot.contracts import (
    ComparisonSnapshot,
    ListingSummary,
    LLMEvaluationResult,
    NotificationDelivery,
    ReferencePriceSnapshot,
    ScrapedListing,
)


class ScraperProvider(Protocol):
    async def search(self, query: str, *, region: str, limit: int) -> list[ListingSummary]: ...

    async def fetch_detail(self, summary: ListingSummary) -> ScrapedListing: ...

    async def close(self) -> None: ...


class ReferencePriceProvider(Protocol):
    async def lookup(self, query: str) -> ReferencePriceSnapshot: ...


class LLMProvider(Protocol):
    async def evaluate_candidate(
        self,
        *,
        listing: ScrapedListing,
        user_alert_style: str,
        max_price_cents: int,
        comparison_snapshot: ComparisonSnapshot,
        reference_snapshot: ReferencePriceSnapshot,
    ) -> LLMEvaluationResult: ...


class Notifier(Protocol):
    async def send_deal_alert(
        self,
        *,
        telegram_user_id: int,
        watch_query: str,
        watch_max_price_cents: int,
        listing: ScrapedListing,
        evaluation: LLMEvaluationResult,
        reference_snapshot: ReferencePriceSnapshot,
    ) -> NotificationDelivery: ...

    async def close(self) -> None: ...

