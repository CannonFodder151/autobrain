"""Ownership Advisor deterministic helpers.

Five of the six Ownership Advisor modules are entirely deterministic. This
module owns the shared building blocks: odometer/condition adjustment on the
cached market median, comparable-listing search across the existing
``market_listing_cache`` table, and the well-known trade-in band (75-90% of
mid private-sale value).

No AI calls. No 9Router. Deterministic-first per the product rule and per
ADR 0001 (docs/adr/0001-ownership-advisor.md).
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.market_listing import MarketListingCache
from app.models.vehicle import Vehicle
from app.services.market_data import get_market_data

logger = get_logger(__name__)

# Realistic trade-in band as a fraction of the private-sale mid. Dealers
# typically pay 75-90% of private value; we surface three points across that
# band so the UI can show low / mid / high. Industry-standard, not invented.
TRADE_IN_LOW_RATIO = 0.75
TRADE_IN_MID_RATIO = 0.82
TRADE_IN_HIGH_RATIO = 0.90

# Condition multipliers applied to the market median. The existing
# vehicles.condition column is one of {excellent, good, fair, poor}; maps
# straight to a price adjustment that mirrors industry guides.
_CONDITION_MULTIPLIER: dict[str, float] = {
    "excellent": 1.05,
    "good": 1.00,
    "fair": 0.92,
    "poor": 0.82,
}

# Band clamp around the adjusted mid. Used so a single outlier listing
# can't blow the displayed range out to silly proportions.
BAND_LOW_RATIO = 0.92
BAND_HIGH_RATIO = 1.08

# Benchmark km-per-year for the odometer adjustment. A car driven less than
# this is worth a small premium; a car driven much more is worth less.
_BENCHMARK_KM_PER_YEAR = 15_000
_KM_ADJUSTMENT_PER_20K = 0.05  # 5% per 20,000 km off benchmark

# Comparables filter window (years either side of the vehicle's year).
COMPARABLES_YEAR_WINDOW = 3
COMPARABLES_MAX = 10

# Currency. AutoBrain is AU-only; one source of truth here keeps the
# response shape consistent.
CURRENCY = "AUD"

# Hard floor / ceiling for any computed value. Stops a junk input from
# emitting a $0 or $1B result on the screen.
_MIN_VALUE = 500.0
_MAX_VALUE = 5_000_000.0


def _safe(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return max(_MIN_VALUE, min(_MAX_VALUE, f))


def condition_multiplier(condition: str | None) -> float:
    """Map the existing Vehicle.condition enum to a price multiplier.

    Unknown values fall back to 1.0 (neutral) so the response stays
    sensible for legacy data with garbage in ``condition``.
    """
    if not condition:
        return 1.0
    return _CONDITION_MULTIPLIER.get(condition.strip().lower(), 1.0)


def km_adjustment(vehicle: Vehicle, odometer_km: int | None) -> float:
    """Return a multiplier in [~0.85, ~1.10] based on km vs benchmark.

    Uses the vehicle's model year and the user-supplied (or stored) odometer
    to decide whether the car is under- or over-driven for its age. Falls
    back to 1.0 (neutral) when the year is missing or in the future.
    """
    if odometer_km is None or odometer_km <= 0:
        odometer_km = vehicle.odometer_km or 0
    year = vehicle.year
    if not year:
        return 1.0
    age_years = max(0, date.today().year - int(year))
    if age_years == 0:
        # New car (year is current or next); trust the stored odo.
        return 1.0
    expected_km = _BENCHMARK_KM_PER_YEAR * age_years
    if expected_km <= 0:
        return 1.0
    delta = odometer_km - expected_km
    # 5% per 20,000 km off the benchmark, capped at ±10% so a 200,000 km
    # taxi doesn't read as worthless (or a 1,000 km garage queen as a gold bar).
    raw = -(delta / 20_000.0) * _KM_ADJUSTMENT_PER_20K
    return max(-0.10, min(0.10, raw)) + 1.0


def _band(mid: float) -> tuple[float, float]:
    low = max(_MIN_VALUE, round(mid * BAND_LOW_RATIO, 2))
    high = min(_MAX_VALUE, round(mid * BAND_HIGH_RATIO, 2))
    return low, high


async def compute_market_value(
    db: AsyncSession,
    vehicle: Vehicle,
    odometer_km: int | None = None,
) -> dict:
    """Deterministic market value for a vehicle.

    Anchors on the cached ``market_listing_cache`` median for the vehicle's
    (make, model, year). Applies a condition multiplier and an odometer
    adjustment, then derives a tight low/high band.

    Returns a dict that matches the ``AdvisorValueData`` schema (see
    schemas/advisor.py). If the cache has no data for the vehicle (or the
    provider is unconfigured) the function still returns a well-formed dict
    with ``median_price=None`` and a ``note`` explaining the gap, so the UI
    can render a graceful "no market data" state instead of crashing.
    """
    market = await get_market_data(
        db,
        vehicle.make or "",
        vehicle.model or "",
        vehicle.year,
        vehicle.vehicle_type or "car",
    )
    median = _safe(market.get("median_price"))
    cond_mult = condition_multiplier(vehicle.condition)
    km_mult = km_adjustment(vehicle, odometer_km)
    freshness = market.get("as_of")
    stale = bool(market.get("stale"))

    if median is None:
        return {
            "currency": CURRENCY,
            "low": None,
            "mid": None,
            "high": None,
            "source": market.get("source", "fallback"),
            "as_of": freshness,
            "stale": stale,
            "sample_size": int(market.get("sample_size") or 0),
            "condition_multiplier": round(cond_mult, 4),
            "km_multiplier": round(km_mult, 4),
            "comparable_count": 0,
            "comparable_window_years": COMPARABLES_YEAR_WINDOW,
            "note": market.get("note") or "no market listings available for this vehicle",
        }

    mid = round(median * cond_mult * km_mult, 2)
    low, high = _band(mid)
    return {
        "currency": CURRENCY,
        "low": low,
        "mid": mid,
        "high": high,
        "source": market.get("source", "fallback"),
        "as_of": freshness,
        "stale": stale,
        "sample_size": int(market.get("sample_size") or 0),
        "condition_multiplier": round(cond_mult, 4),
        "km_multiplier": round(km_mult, 4),
        "comparable_count": 0,
        "comparable_window_years": COMPARABLES_YEAR_WINDOW,
        "note": None,
    }


def _load_listings(row: MarketListingCache) -> list[dict]:
    try:
        if not row.listings:
            return []
        parsed = json.loads(row.listings)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


async def find_comparables(
    db: AsyncSession,
    vehicle: Vehicle,
    max_results: int = COMPARABLES_MAX,
) -> list[dict]:
    """Return comparable listings for the same make/model, year ±3.

    Walks ``market_listing_cache`` (rows already normalised by the
    market-data service) instead of re-scraping the provider. Cache TTL is
    24h (same as ``/valuation/market``) so comparables stay stable between
    visits.

    Listings are sorted by year DESC then price ASC and capped at
    ``max_results`` so the UI shows a tight comparison set.
    """
    make_l = (vehicle.make or "").strip().lower()
    model_l = (vehicle.model or "").strip().lower()
    year = vehicle.year
    if not make_l and not model_l:
        return []

    stmt = select(MarketListingCache).where(
        MarketListingCache.make == make_l,
        MarketListingCache.model == model_l,
    )
    if year is not None:
        stmt = stmt.where(
            MarketListingCache.year >= year - COMPARABLES_YEAR_WINDOW,
            MarketListingCache.year <= year + COMPARABLES_YEAR_WINDOW,
        )
    rows = list((await db.scalars(stmt)).all())

    out: list[dict] = []
    for row in rows:
        for listing in _load_listings(row):
            if not isinstance(listing, dict):
                continue
            if listing.get("price") is None:
                continue
            out.append({
                "title": listing.get("title", ""),
                "price": float(listing["price"]),
                "year": listing.get("year") or row.year,
                "odometer_km": listing.get("odometer_km"),
                "source": listing.get("source", row.source or ""),
                "url": listing.get("url", ""),
            })
    out.sort(key=lambda x: (-(x.get("year") or 0), x["price"]))
    return out[:max_results]


def trade_in_band(mid_value: float | None) -> dict:
    """Industry-standard trade-in band expressed as a fraction of mid private-sale value.

    75% / 82% / 90% of the private-sale mid. The deterministic band is the
    same shape across the whole industry (dealer trade-in sits below
    private sale; private-to-private is the ceiling); making it explicit
    here means the UI never has to invent numbers and AI never has to
    either.
    """
    if mid_value is None:
        return {"currency": CURRENCY, "low": None, "mid": None, "high": None, "ratios": {
            "low": TRADE_IN_LOW_RATIO, "mid": TRADE_IN_MID_RATIO, "high": TRADE_IN_HIGH_RATIO,
        }}
    mid = _safe(mid_value)
    if mid is None:
        return {"currency": CURRENCY, "low": None, "mid": None, "high": None, "ratios": {
            "low": TRADE_IN_LOW_RATIO, "mid": TRADE_IN_MID_RATIO, "high": TRADE_IN_HIGH_RATIO,
        }}
    return {
        "currency": CURRENCY,
        "low": round(mid * TRADE_IN_LOW_RATIO, 2),
        "mid": round(mid * TRADE_IN_MID_RATIO, 2),
        "high": round(mid * TRADE_IN_HIGH_RATIO, 2),
        "ratios": {"low": TRADE_IN_LOW_RATIO, "mid": TRADE_IN_MID_RATIO, "high": TRADE_IN_HIGH_RATIO},
    }
