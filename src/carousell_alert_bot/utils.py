from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus, urljoin

PRICE_PATTERN = re.compile(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)")
LISTING_ID_PATTERN = re.compile(r"(?:-|\b)(\d{5,})/?$")


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def normalize_query(value: str) -> str:
    return " ".join(value.casefold().split())


def format_sgd(cents: int | None) -> str:
    if cents is None:
        return "N/A"
    return f"S${cents / 100:,.2f}"


def parse_price_to_cents(raw_value: str | int | float | None) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return raw_value * 100 if raw_value < 10_000_000 else raw_value
    if isinstance(raw_value, float):
        return int(round(raw_value * 100))

    match = PRICE_PATTERN.search(raw_value.replace("$", "").replace("S", ""))
    if not match:
        return None
    try:
        return int((Decimal(match.group(1).replace(",", "")) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def parse_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    normalized = raw_value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def compute_hash(*parts: object) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part or "").encode("utf-8"))
        digest.update(b"|")
    return digest.hexdigest()


def extract_listing_id(url: str) -> str | None:
    match = LISTING_ID_PATTERN.search(url)
    if match:
        return match.group(1)
    return None


def build_carousell_search_url(query: str) -> str:
    encoded = quote_plus(query)
    return (
        "https://www.carousell.sg/search/products"
        f"?addRecent=false&canChangeKeyword=true&includeSuggestions=false&query={encoded}"
    )


def absolute_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base_url, href)


def next_scan_at(minutes: int, *, from_time: datetime | None = None) -> datetime:
    baseline = from_time or utc_now()
    return baseline + timedelta(minutes=minutes)

