from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ListingSummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str
    url: HttpUrl
    title: str
    price_cents: int
    seller_location: str | None = None
    image_url: HttpUrl | None = None
    summary_hash: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ScrapedListing(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str
    url: HttpUrl
    title: str
    description: str | None = None
    price_cents: int
    currency: str = "SGD"
    seller_name: str | None = None
    seller_location: str | None = None
    listed_at: datetime | None = None
    image_urls: list[HttpUrl] = Field(default_factory=list)
    summary_hash: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ReferencePriceQuote(BaseModel):
    source: str
    merchant: str | None = None
    title: str
    url: HttpUrl | None = None
    price_cents: int
    currency: str = "SGD"


class ReferencePriceSnapshot(BaseModel):
    source: str
    status: str
    query: str
    quotes: list[ReferencePriceQuote] = Field(default_factory=list)
    median_price_cents: int | None = None
    min_price_cents: int | None = None
    max_price_cents: int | None = None
    error: str | None = None

    @classmethod
    def from_quotes(
        cls,
        *,
        source: str,
        status: str,
        query: str,
        quotes: list[ReferencePriceQuote],
        error: str | None = None,
    ) -> ReferencePriceSnapshot:
        prices = [quote.price_cents for quote in quotes]
        return cls(
            source=source,
            status=status,
            query=query,
            quotes=quotes,
            median_price_cents=int(median(prices)) if prices else None,
            min_price_cents=min(prices) if prices else None,
            max_price_cents=max(prices) if prices else None,
            error=error,
        )


class CompStats(BaseModel):
    sample_size: int = 0
    min_price_cents: int | None = None
    avg_price_cents: int | None = None
    median_price_cents: int | None = None
    max_price_cents: int | None = None

    @classmethod
    def from_prices(cls, prices: list[int]) -> CompStats:
        if not prices:
            return cls()
        ordered = sorted(prices)
        return cls(
            sample_size=len(ordered),
            min_price_cents=ordered[0],
            avg_price_cents=int(sum(ordered) / len(ordered)),
            median_price_cents=int(median(ordered)),
            max_price_cents=ordered[-1],
        )


class ComparisonSnapshot(BaseModel):
    same_watch: CompStats = Field(default_factory=CompStats)
    same_query: CompStats = Field(default_factory=CompStats)


class LLMEvaluationResult(BaseModel):
    normalized_brand: str | None = None
    normalized_model: str | None = None
    condition_grade: str
    condition_notes: str
    estimated_fair_price_min_cents: int
    estimated_fair_price_max_cents: int
    deal_score: float
    should_alert: bool
    alert_reason: str
    confidence: float


class NotificationDelivery(BaseModel):
    status: str
    telegram_message_id: int | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

