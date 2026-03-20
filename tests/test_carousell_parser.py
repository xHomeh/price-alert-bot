from __future__ import annotations

from carousell_alert_bot.providers.carousell import (
    parse_listing_detail_html,
    parse_search_results_html,
)
from tests.support import fixture_path


def test_parse_search_results_and_detect_change() -> None:
    html = fixture_path("search_results.html").read_text()
    updated_html = fixture_path("search_results_updated.html").read_text()

    listings = parse_search_results_html(html)
    updated_listings = parse_search_results_html(updated_html)

    assert len(listings) == 2
    assert listings[0].external_id == "123456789"
    assert listings[0].price_cents == 25_000
    assert updated_listings[0].external_id == "123456789"
    assert updated_listings[0].price_cents == 22_000
    assert listings[0].summary_hash != updated_listings[0].summary_hash


def test_parse_listing_detail_page() -> None:
    html = fixture_path("detail_page.html").read_text()
    summary = parse_search_results_html(fixture_path("search_results.html").read_text())[0]
    detail = parse_listing_detail_html(html, summary=summary)

    assert detail.external_id == "123456789"
    assert detail.title == "Sony WH-1000XM5 Headphones"
    assert detail.price_cents == 25_000
    assert detail.seller_name == "Joel Seller"
    assert len(detail.image_urls) >= 2

