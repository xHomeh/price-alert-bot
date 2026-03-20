from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from random import uniform
from typing import Any

from bs4 import BeautifulSoup

from carousell_alert_bot.contracts import ListingSummary, ScrapedListing
from carousell_alert_bot.utils import (
    absolute_url,
    build_carousell_search_url,
    compute_hash,
    extract_listing_id,
    parse_datetime,
    parse_price_to_cents,
)


def _extract_text(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return " ".join(value.split())
    return None


def parse_search_results_html(
    html: str,
    *,
    base_url: str = "https://www.carousell.sg",
) -> list[ListingSummary]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("[data-testid='listing-card'], article, div[data-listing-id]")
    results: list[ListingSummary] = []
    seen: set[str] = set()

    for card in cards:
        anchor = card.select_one("a[href]")
        if anchor is None:
            continue
        href = absolute_url(base_url, anchor.get("href"))
        if href is None or "/p/" not in href:
            continue
        external_id = (
            card.get("data-listing-id")
            or anchor.get("data-listing-id")
            or extract_listing_id(href)
        )
        if not external_id or external_id in seen:
            continue
        title = _extract_text(
            anchor.get("title"),
            (card.select_one("[data-testid='listing-title']") or anchor).get_text(" ", strip=True),
        )
        price_node = card.select_one("[data-testid='listing-price'], .price")
        price_text = _extract_text(
            price_node.get_text(" ", strip=True) if price_node else None,
            card.get_text(" ", strip=True),
        )
        price_cents = parse_price_to_cents(price_text)
        if not title or price_cents is None:
            continue
        location_node = card.select_one("[data-testid='listing-location'], .location")
        location = _extract_text(
            location_node.get_text(" ", strip=True) if location_node else None
        )
        image_tag = card.select_one("img")
        image_url = absolute_url(
            base_url,
            image_tag.get("src") or image_tag.get("data-src") if image_tag else None,
        )
        summary_hash = compute_hash(title, price_cents, location, image_url, href)
        results.append(
            ListingSummary(
                external_id=str(external_id),
                url=href,
                title=title,
                price_cents=price_cents,
                seller_location=location,
                image_url=image_url,
                summary_hash=summary_hash,
                raw_payload={
                    "source": "search_results",
                    "title": title,
                    "price_text": price_text,
                    "location": location,
                },
            )
        )
        seen.add(str(external_id))

    return results


def parse_listing_detail_html(
    html: str,
    *,
    summary: ListingSummary,
    base_url: str = "https://www.carousell.sg",
) -> ScrapedListing:
    soup = BeautifulSoup(html, "html.parser")
    ld_json_nodes: list[dict[str, Any]] = []
    for script in soup.select("script[type='application/ld+json']"):
        if not script.string:
            continue
        try:
            parsed = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            ld_json_nodes.extend(node for node in parsed if isinstance(node, dict))
        elif isinstance(parsed, dict):
            ld_json_nodes.append(parsed)

    product_node = next(
        (
            node
            for node in ld_json_nodes
            if node.get("@type") in {"Product", "Offer"} or node.get("name")
        ),
        {},
    )

    title = _extract_text(
        product_node.get("name"),
        soup.select_one("meta[property='og:title']")
        and soup.select_one("meta[property='og:title']").get("content"),
        soup.select_one("h1") and soup.select_one("h1").get_text(" ", strip=True),
        summary.title,
    )
    description = _extract_text(
        product_node.get("description"),
        soup.select_one("meta[property='og:description']")
        and soup.select_one("meta[property='og:description']").get("content"),
        soup.select_one("[data-testid='listing-description']")
        and soup.select_one("[data-testid='listing-description']").get_text(" ", strip=True),
    )
    offers = product_node.get("offers") if isinstance(product_node.get("offers"), dict) else {}
    price_cents = (
        parse_price_to_cents(offers.get("price"))
        or parse_price_to_cents(product_node.get("price"))
        or parse_price_to_cents(
            soup.select_one("meta[property='product:price:amount']")
            and soup.select_one("meta[property='product:price:amount']").get("content")
        )
        or summary.price_cents
    )

    image_candidates: list[str] = []
    product_images = product_node.get("image")
    if isinstance(product_images, str):
        image_candidates.append(product_images)
    elif isinstance(product_images, list):
        image_candidates.extend(str(item) for item in product_images)

    for image_tag in soup.select("img"):
        image_src = image_tag.get("src") or image_tag.get("data-src")
        if image_src:
            image_candidates.append(image_src)

    deduped_images: list[str] = []
    for image in image_candidates:
        absolute = absolute_url(base_url, image)
        if absolute and absolute not in deduped_images:
            deduped_images.append(absolute)

    seller_name = _extract_text(
        soup.select_one("[data-testid='listing-seller-name']")
        and soup.select_one("[data-testid='listing-seller-name']").get_text(" ", strip=True),
        soup.select_one(".seller-name")
        and soup.select_one(".seller-name").get_text(" ", strip=True),
    )
    seller_location = _extract_text(
        soup.select_one("[data-testid='listing-location']")
        and soup.select_one("[data-testid='listing-location']").get_text(" ", strip=True),
        summary.seller_location,
    )
    listed_at = parse_datetime(
        soup.select_one("time") and soup.select_one("time").get("datetime")
    )

    return ScrapedListing(
        external_id=summary.external_id,
        url=str(summary.url),
        title=title or summary.title,
        description=description,
        price_cents=price_cents,
        seller_name=seller_name,
        seller_location=seller_location,
        listed_at=listed_at,
        image_urls=deduped_images[:8],
        summary_hash=summary.summary_hash,
        raw_payload={
            "source": "detail_page",
            "ld_json_nodes": ld_json_nodes,
            "summary_payload": summary.raw_payload,
        },
    )


@dataclass
class _BrowserState:
    playwright: Any
    browser: Any
    context: Any


class PlaywrightCarousellScraper:
    def __init__(self, *, headless: bool = True, storage_state_path: str | None = None) -> None:
        self._headless = headless
        self._storage_state_path = storage_state_path
        self._browser_state: _BrowserState | None = None

    async def _ensure_browser(self) -> _BrowserState:
        if self._browser_state is not None:
            return self._browser_state

        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=self._headless)
        context_kwargs: dict[str, Any] = {"locale": "en-SG"}
        if self._storage_state_path:
            context_kwargs["storage_state"] = self._storage_state_path
        context = await browser.new_context(**context_kwargs)
        self._browser_state = _BrowserState(
            playwright=playwright,
            browser=browser,
            context=context,
        )
        return self._browser_state

    async def _human_pause(self) -> None:
        await asyncio.sleep(uniform(0.5, 1.3))

    async def search(self, query: str, *, region: str, limit: int) -> list[ListingSummary]:
        state = await self._ensure_browser()
        page = await state.context.new_page()
        await page.goto(build_carousell_search_url(query), wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await self._human_pause()
        html = await page.content()
        await page.close()
        return parse_search_results_html(html)[:limit]

    async def fetch_detail(self, summary: ListingSummary) -> ScrapedListing:
        state = await self._ensure_browser()
        page = await state.context.new_page()
        await page.goto(str(summary.url), wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await self._human_pause()
        html = await page.content()
        await page.close()
        return parse_listing_detail_html(html, summary=summary)

    async def close(self) -> None:
        if self._browser_state is None:
            return
        await self._browser_state.context.close()
        await self._browser_state.browser.close()
        await self._browser_state.playwright.stop()
        self._browser_state = None
