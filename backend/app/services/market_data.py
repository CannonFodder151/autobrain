"""Used-car market data: live CarsGuide/CarSales listings + aggregates.

Primary path: a self-hosted market-data API configured via MARKET_DATA_URL +
MARKET_DATA_API_KEY (same pattern as rego lookup — never hardcode). It POSTs
/search and returns scraped listings from CarsGuide/CarSales.

Results are cached in ``market_listing_cache`` keyed by make/model/year for 24h
so repeated valuations return the SAME market numbers (this is what stops the
estimate from wobbling between runs). When the provider is unconfigured or
fails, a deterministic fallback is returned with sample_size=0 so the
valuation pipeline still completes end-to-end offline.
"""

import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.market_listing import MarketListingCache

logger = get_logger(__name__)

CACHE_TTL_HOURS = 24


def _dig(obj, key: str):
    """Depth-first search for a key (case-insensitive) in nested JSON."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() == key.lower():
                return v
            found = _dig(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _dig(item, key)
            if found is not None:
                return found
    return None


def _first(data, aliases: list[str]):
    for alias in aliases:
        val = _dig(data, alias)
        if val not in (None, "", [], "N/A", "n/a", "-"):
            return val
    return None


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _to_int(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _map_listing(raw) -> dict | None:
    """Normalise one provider listing onto our schema (alias-resilient)."""
    if not isinstance(raw, dict):
        return None
    price = _to_float(_first(raw, ["price", "price_aud", "asking_price", "price_value", "sale_price"]))
    year = _to_int(_first(raw, ["year", "model_year", "vehicle_year", "build_year"]))
    title = str(_first(raw, ["title", "name", "ad_title", "heading", "model_name"]) or "")
    if not title and year:
        title = f"{year} {_first(raw, ['make']) or ''} {_first(raw, ['model']) or ''}".strip()
    listing = {
        "title": title,
        "price": price,
        "year": year,
        "odometer_km": _to_int(_first(raw, ["odometer_km", "km", "odometer", "kms"])),
        "source": str(_first(raw, ["source", "portal", "provider"]) or "").lower(),
        "url": str(_first(raw, ["url", "link", "listing_url"]) or ""),
    }
    return listing if title or price is not None else None


def _parse_provider_response(data) -> dict:
    """Extract listings + source from a provider response."""
    raw_listings = data.get("listings") if isinstance(data, dict) else None
    if not isinstance(raw_listings, list):
        raw_listings = None
        for key in ("listings", "results", "items", "data", "cars", "vehicles"):
            candidate = _dig(data, key)
            if isinstance(candidate, list):
                raw_listings = candidate
                break
    listings = []
    if isinstance(raw_listings, list):
        for raw in raw_listings:
            listing = _map_listing(raw)
            if listing is not None:
                listings.append(listing)
    source = str(_first(data, ["source", "provider"]) or "provider").lower()
    return {"listings": listings, "source": source or "provider"}


def _aggregate(listings: list[dict]) -> dict:
    prices = sorted(p["price"] for p in listings if p.get("price") is not None)
    n = len(prices)
    if n == 0:
        return {"median_price": None, "low_price": None, "high_price": None, "sample_size": 0}
    mid = n // 2
    median = prices[mid] if n % 2 else (prices[mid - 1] + prices[mid]) / 2
    return {
        "median_price": round(median, 2),
        "low_price": prices[0],
        "high_price": prices[-1],
        "sample_size": n,
    }


async def _fetch_provider(query: str, make: str, model: str, year: int | None) -> dict | None:
    """POST /search to the self-hosted market-data API. None on any failure."""
    if not settings.MARKET_DATA_URL:
        return None
    url = settings.MARKET_DATA_URL.rstrip("/") + "/search"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                json={"query": query, "make": make, "model": model, "year": year},
                headers={"X-API-Key": settings.MARKET_DATA_API_KEY} if settings.MARKET_DATA_API_KEY else {},
            )
            resp.raise_for_status()
            return _parse_provider_response(resp.json())
    except Exception as exc:
        logger.warning("market_provider_failed_falling_back", error=str(exc), query=query)
        return None


async def get_market_data(
    db: AsyncSession,
    make: str,
    model: str,
    year: int | None = None,
    refresh: bool = False,
) -> dict:
    """Cached market data for a make/model/year. Always returns a dict."""
    make_l = (make or "").strip().lower()
    model_l = (model or "").strip().lower()
    query = " ".join(x for x in (make_l, model_l) if x) or "car"

    if not refresh:
        row = await db.scalar(select(MarketListingCache).where(
            MarketListingCache.make == make_l,
            MarketListingCache.model == model_l,
            MarketListingCache.year == year,
        ))
        if row is not None and _fresh(row):
            return _serialise(row, stale=False)

    provider = await _fetch_provider(query, make_l, model_l, year)
    data = _build(provider)
    await _store(db, make_l, model_l, year, data)
    return data


async def search_market(db: AsyncSession, q: str, refresh: bool = False) -> dict:
    """Live search across CarsGuide/CarSales listings for an arbitrary query."""
    query = (q or "").strip()
    if not query:
        return _fallback("empty query")
    if not refresh:
        row = await db.scalar(select(MarketListingCache).where(
            MarketListingCache.make == query.lower(),
            MarketListingCache.model == "",
            MarketListingCache.year.is_(None),
        ))
        if row is not None and _fresh(row):
            return _serialise(row, stale=False)

    provider = await _fetch_provider(query, query, "", None)
    data = _build(provider)
    await _store(db, query.lower(), "", None, data)
    return data


def _build(provider: dict | None) -> dict:
    if provider and provider.get("listings"):
        data = {"source": provider.get("source", "provider"), "listings": provider["listings"]}
        data.update(_aggregate(provider["listings"]))
        return data
    return _fallback("no live data available")


def _fallback(reason: str) -> dict:
    return {
        "source": "fallback",
        "listings": [],
        "median_price": None,
        "low_price": None,
        "high_price": None,
        "sample_size": 0,
        "note": reason,
    }


async def _store(db: AsyncSession, make: str, model: str, year: int | None, data: dict) -> None:
    row = await db.scalar(select(MarketListingCache).where(
        MarketListingCache.make == make,
        MarketListingCache.model == model,
        MarketListingCache.year == year,
    ))
    if row is None:
        row = MarketListingCache(make=make, model=model, year=year)
        db.add(row)
    row.source = data.get("source", "fallback")
    row.listings = json.dumps(data.get("listings", []))
    row.median_price = data.get("median_price")
    row.low_price = data.get("low_price")
    row.high_price = data.get("high_price")
    row.sample_size = data.get("sample_size", 0)
    row.fetched_at = datetime.now(timezone.utc)
    await db.commit()


def _fresh(row: MarketListingCache) -> bool:
    fetched = row.fetched_at
    if fetched is None:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched < timedelta(hours=CACHE_TTL_HOURS)


def _serialise(row: MarketListingCache, *, stale: bool) -> dict:
    try:
        listings = json.loads(row.listings) if row.listings else []
    except (TypeError, ValueError):
        listings = []
    return {
        "source": row.source,
        "listings": listings,
        "median_price": row.median_price,
        "low_price": row.low_price,
        "high_price": row.high_price,
        "sample_size": row.sample_size,
        "as_of": row.fetched_at.isoformat() if row.fetched_at else None,
        "stale": stale,
    }


async def clear_market_cache(db: AsyncSession, make: str, model: str, year: int | None = None) -> None:
    await db.execute(delete(MarketListingCache).where(
        MarketListingCache.make == make.lower(),
        MarketListingCache.model == model.lower(),
        MarketListingCache.year == year,
    ))
    await db.commit()
