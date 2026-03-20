from __future__ import annotations

from typing import Any

import httpx

from carousell_alert_bot.contracts import ReferencePriceQuote, ReferencePriceSnapshot
from carousell_alert_bot.utils import parse_price_to_cents


class SerpApiReferencePriceProvider:
    base_url = "https://serpapi.com/search.json"

    def __init__(self, *, api_key: str | None, timeout_seconds: float = 20.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def parse_quotes(payload: dict[str, Any]) -> list[ReferencePriceQuote]:
        quotes: list[ReferencePriceQuote] = []
        shopping_results = payload.get("shopping_results") or []
        for result in shopping_results:
            price_cents = parse_price_to_cents(result.get("price") or result.get("extracted_price"))
            if price_cents is None:
                continue
            quotes.append(
                ReferencePriceQuote(
                    source="serpapi",
                    merchant=result.get("source"),
                    title=result.get("title") or "Unknown",
                    url=result.get("link"),
                    price_cents=price_cents,
                    currency="SGD",
                )
            )
        return quotes

    async def lookup(self, query: str) -> ReferencePriceSnapshot:
        if not self.api_key:
            return ReferencePriceSnapshot.from_quotes(
                source="serpapi",
                status="disabled",
                query=query,
                quotes=[],
                error="SERPAPI_API_KEY is not configured.",
            )

        params = {
            "engine": "google_shopping",
            "q": query,
            "gl": "sg",
            "hl": "en",
            "location": "Singapore",
            "api_key": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return ReferencePriceSnapshot.from_quotes(
                source="serpapi",
                status="error",
                query=query,
                quotes=[],
                error=str(exc),
            )

        return ReferencePriceSnapshot.from_quotes(
            source="serpapi",
            status="ok",
            query=query,
            quotes=self.parse_quotes(payload),
        )

