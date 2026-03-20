from __future__ import annotations

from carousell_alert_bot.contracts import ReferencePriceSnapshot
from carousell_alert_bot.providers.reference_price import SerpApiReferencePriceProvider


def test_serpapi_quote_parsing_and_snapshot() -> None:
    payload = {
        "shopping_results": [
            {"title": "Sony Headphones", "price": "S$499", "source": "Sony Store", "link": "https://sony.example"},
            {"title": "Sony Headphones", "price": "S$479", "source": "Best Denki", "link": "https://best.example"},
        ]
    }
    quotes = SerpApiReferencePriceProvider.parse_quotes(payload)
    assert len(quotes) == 2
    snapshot = ReferencePriceSnapshot.from_quotes(
        source="serpapi",
        status="ok",
        query="Sony WH-1000XM5",
        quotes=quotes,
    )
    assert snapshot.min_price_cents == 47_900
    assert snapshot.max_price_cents == 49_900
    assert snapshot.median_price_cents == 48_900

