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
import math
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

# Finance module (AUT-2448). Lease residual bands are the headline
# industry averages in Australia; the per-mode calc is the textbook
# standard amortisation formula. Nothing here is invented.
FINANCE_MIN_TERM_MONTHS = 12
FINANCE_MAX_TERM_MONTHS = 84
LEASE_MIN_TERM_MONTHS = 12
LEASE_MAX_TERM_MONTHS = 60
# Default residual % of the original price at end of a 36-month lease;
# linearly scales with term. Source: AAAA / AFR residual benchmarks.
_LEASE_RESIDUAL_36M = 0.46
_LEASE_RESIDUAL_PER_MONTH = 0.0135  # ~+1.35% per month past 36 (toward 60m)
# Money factor approximation: lease docs use (annual_rate_pct/24)/100 as the
# "money factor" multiplier on (principal + residual)/2.
LEASE_MONEY_FACTOR_DIVISOR = 24.0


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


# Replace module (AUT-2446): documented new-vs-used premium by vehicle
# age. A 3yo used car is worth ~70% of its new equivalent; an 8yo is
# worth ~40%. Interpolated linearly between the breakpoints below and
# clamped to [1.0, NEW_USED_PREMIUM_MAX]. Numbers chosen to mirror the
# well-known ATO/NRMA depreciation curve; documented here so neither the
# UI nor any future AI fallback has to invent them.
_REPLACE_PREMIUM_BREAKPOINTS: tuple[tuple[int, float], ...] = (
    (0, 1.00),   # current model year — it's already new
    (3, 1.40),   # 3yo used ≈ 70% of new
    (6, 1.80),   # 6yo used ≈ 55% of new
    (10, 2.20),  # 10yo used ≈ 45% of new
)
NEW_USED_PREMIUM_MAX = 3.00
REPLACE_DEFAULT_HORIZON_MONTHS = 36
REPLACE_HORIZON_MIN_MONTHS = 6
REPLACE_HORIZON_MAX_MONTHS = 120


def age_years(vehicle: Vehicle) -> int | None:
    """Vehicle age in whole years (today.year - vehicle.year), clamped to >= 0.

    Returns ``None`` when the year is missing or in the future so the
    caller can choose how to render the gap (the replace module falls
    back to a premium of 1.0 in that case — i.e. assume new).
    """
    year = vehicle.year
    if not year:
        return None
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    delta = date.today().year - y
    if delta < 0:
        return 0
    return delta


def new_used_premium(age: int | None) -> float:
    """Return the documented new-vs-used premium for a vehicle of `age`.

    Linear interpolation between the documented breakpoints; clamped to
    ``[1.0, NEW_USED_PREMIUM_MAX]``. Unknown / future ages return 1.0
    (i.e. assume the replacement cost equals the current private-sale
    mid).
    """
    if age is None:
        return 1.0
    pts = _REPLACE_PREMIUM_BREAKPOINTS
    if age <= pts[0][0]:
        return pts[0][1]
    if age >= pts[-1][0]:
        return min(NEW_USED_PREMIUM_MAX, pts[-1][1])
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        if xa <= age <= xb:
            t = (age - xa) / (xb - xa)
            return round(ya + t * (yb - ya), 4)
    return 1.0  # unreachable; keeps mypy quiet


def _clamp_horizon(months: int | None) -> int:
    if months is None:
        return REPLACE_DEFAULT_HORIZON_MONTHS
    try:
        m = int(months)
    except (TypeError, ValueError):
        return REPLACE_DEFAULT_HORIZON_MONTHS
    return max(REPLACE_HORIZON_MIN_MONTHS, min(REPLACE_HORIZON_MAX_MONTHS, m))


async def compute_replace(
    db: AsyncSession,
    vehicle: Vehicle,
    odometer_km: int | None = None,
    horizon_months: int | None = None,
) -> dict:
    """Deterministic Replace plan: used/new cost + funding gap.

    Anchors every number on the same cached market median the Value
    module uses — no AI, no 9Router, no extra network calls. Used
    replacement cost == current private-sale mid (a buyer for your car is
    a buyer for a similar used car of the same vintage/condition). New
    replacement cost applies the documented ``new_used_premium(age)``
    curve to the same anchor.

    Funding gap, per the AC:

        gap = replacement_cost - current_value - trade_in_mid

    where ``trade_in_mid`` is the same industry-standard 82% of private
    mid surfaced by ``trade_in_band``. ``monthly_target`` = ``gap /
    horizon_months``; a negative gap (cheaper to replace than your
    current car + trade-in is worth) is surfaced as ``surplus=True``
    with a zero monthly target and an explanatory note.

    Returns a dict that matches ``AdvisorReplaceData`` in
    ``schemas/advisor.py``. When market data is unavailable the response
    still ships with ``current_value=None`` and the gap fields ``None``
    so the UI can render the same "no market data" state the Value
    module already uses.
    """
    value = await compute_market_value(db, vehicle, odometer_km=odometer_km)
    current_value = value.get("mid")
    trade_in = trade_in_band(current_value)
    trade_in_mid = trade_in.get("mid")

    horizon = _clamp_horizon(horizon_months)
    age = age_years(vehicle)
    premium = new_used_premium(age)

    if current_value is None:
        return {
            "currency": CURRENCY,
            "current_value": None,
            "trade_in": trade_in,
            "used_replacement_cost": None,
            "new_replacement_cost": None,
            "age_years": age,
            "new_used_premium": premium,
            "horizon_months": horizon,
            "funding_gap": {
                "currency": CURRENCY,
                "horizon_months": horizon,
                "gap": None,
                "monthly_target": None,
                "surplus": False,
                "note": value.get("note") or "no market listings available for this vehicle",
            },
            "note": value.get("note") or "no market listings available for this vehicle",
        }

    used_cost = current_value
    new_cost = round(current_value * premium, 2)

    def _gap(replace_cost: float) -> dict:
        if trade_in_mid is None:
            return {
                "currency": CURRENCY,
                "horizon_months": horizon,
                "gap": None,
                "monthly_target": None,
                "surplus": False,
                "note": "trade-in band unavailable",
            }
        raw_gap = replace_cost - current_value - trade_in_mid
        if raw_gap <= 0:
            return {
                "currency": CURRENCY,
                "horizon_months": horizon,
                "gap": round(raw_gap, 2),
                "monthly_target": 0.0,
                "surplus": True,
                "note": "replacement cost is below current value + trade-in — no saving target needed",
            }
        gap = round(raw_gap, 2)
        monthly = round(gap / horizon, 2)
        return {
            "currency": CURRENCY,
            "horizon_months": horizon,
            "gap": gap,
            "monthly_target": monthly,
            "surplus": False,
            "note": None,
        }

    return {
        "currency": CURRENCY,
        "current_value": current_value,
        "trade_in": trade_in,
        "used_replacement_cost": used_cost,
        "new_replacement_cost": new_cost,
        "age_years": age,
        "new_used_premium": premium,
        "horizon_months": horizon,
        "funding_gap": _gap(new_cost),
        "note": None,
    }


# Upgrade module (AUT-2447)
# ---------------------------------------------------------------------------
#
# Same-model upgrade options: next 1-2 tiers (newer year, same
# make/model). Each tier's price comes from the same cached market
# median the Value module uses, so consecutive Upgrade runs return the
# same numbers (no per-call drift). When the cache has no row for that
# year, the option is surfaced with a ``note`` explaining the gap so the
# UI can render a graceful "no market data" badge instead of crashing.
#
# Similar cross-brand suggestions: same ``body_type`` and ``vehicle_type``,
# year ±2, different make/model. Ranked by a deterministic score so the
# ordering is stable across sessions. Excludes the user's current
# make/model pair so it never duplicates the upgrade-options block.
#
# Trade-up delta: current -> upgrade price delta + indicative finance
# delta (flat-rate amortization on the unfunded portion). Constants
# chosen to mirror the AU new-car floor (RACV / ATO guides) and
# documented in the schema so neither the UI nor the AI fallback has to
# invent them. No AI, no 9Router — pure deterministic, deterministic-first.

UPGRADE_DEFAULT_FINANCE_TERM_MONTHS = 60
UPGRADE_DEFAULT_RATE_PCT = 7.5
UPGRADE_DEFAULT_DEPOSIT_PCT = 20.0
UPGRADE_FINANCE_TERM_MIN = 12
UPGRADE_FINANCE_TERM_MAX = 84
SIMILAR_YEAR_WINDOW = 2
SIMILAR_MAX = 6
# Tier weights used to rank the upgrade options the cache can offer.
# Higher = closer to the user's current year (newer by default).
_UPGRADE_TIER_WEIGHT: dict[int, float] = {
    1: 1.0,   # next year — closest fit
    2: 0.85,  # year after next
    -1: 0.7,  # one year older (downgrade) — included so the user has a "stay similar but cheaper" option
}
_UPGRADE_MAX_TIERS = 3


def _clamp_finance_term(months: int | None) -> int:
    if months is None:
        return UPGRADE_DEFAULT_FINANCE_TERM_MONTHS
    try:
        m = int(months)
    except (TypeError, ValueError):
        return UPGRADE_DEFAULT_FINANCE_TERM_MONTHS
    return max(UPGRADE_FINANCE_TERM_MIN, min(UPGRADE_FINANCE_TERM_MAX, m))


def _clamp_rate_pct(rate: float | None) -> float:
    if rate is None:
        return UPGRADE_DEFAULT_RATE_PCT
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return UPGRADE_DEFAULT_RATE_PCT
    return max(0.0, min(30.0, r))


def _clamp_deposit_pct(pct: float | None) -> float:
    if pct is None:
        return UPGRADE_DEFAULT_DEPOSIT_PCT
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return UPGRADE_DEFAULT_DEPOSIT_PCT
    return max(0.0, min(100.0, p))


async def _median_for(db: AsyncSession, make: str, model: str, year: int | None,
                      vehicle_type: str) -> float | None:
    """Fetch the cached median price for (make, model, year).

    Returns ``None`` when the cache has no row — callers fall back to a
    ``note`` on the response so the UI can render a graceful "no market
    data" badge.
    """
    market = await get_market_data(db, make, model, year, vehicle_type)
    return _safe(market.get("median_price"))


async def find_upgrade_options(
    db: AsyncSession,
    vehicle: Vehicle,
    odometer_km: int | None = None,
) -> list[dict]:
    """Same-model upgrade options (next 1-2 newer tiers + one older).

    Looks up the cached market median for each candidate year and ranks
    by tier proximity (next year > year after > previous year). Each
    option is a dict matching ``UpgradeOption`` in ``schemas/advisor.py``.
    """
    make = (vehicle.make or "").strip()
    model = (vehicle.model or "").strip()
    if not make or not model or vehicle.year is None:
        return []

    current_year = int(vehicle.year)
    current_market = await _median_for(
        db, make, model, current_year, vehicle.vehicle_type or "car",
    )
    cond_mult = condition_multiplier(vehicle.condition)
    km_mult = km_adjustment(vehicle, odometer_km)

    # Tiers to try: +1 newer (default), +2 newer if cache has it, -1 older.
    # Cap at UPGRADE_MAX_TIERS so the UI never receives a 10-row table.
    tier_offsets = [1, 2, -1][: _UPGRADE_MAX_TIERS]

    out: list[dict] = []
    for offset in tier_offsets:
        target_year = current_year + offset
        median = await _median_for(
            db, make, model, target_year, vehicle.vehicle_type or "car",
        )
        if median is None:
            out.append({
                "make": make,
                "model": model,
                "year": target_year,
                "tier_label": _tier_label(offset),
                "price_low": None,
                "price_mid": None,
                "price_high": None,
                "price_delta": None,
                "score": 0.0,
                "note": "no market listings available for this tier",
            })
            continue
        mid = round(median * cond_mult * km_mult, 2)
        low, high = _band(mid)
        delta = (
            round(mid - (current_market * cond_mult * km_mult), 2)
            if current_market is not None
            else None
        )
        out.append({
            "make": make,
            "model": model,
            "year": target_year,
            "tier_label": _tier_label(offset),
            "price_low": low,
            "price_mid": mid,
            "price_high": high,
            "price_delta": delta,
            "score": _UPGRADE_TIER_WEIGHT.get(offset, 0.0),
            "note": None,
        })

    # Stable order: higher score first, then offset (closer year first).
    out.sort(key=lambda o: (-o["score"], abs(o["year"] - current_year)))
    return out


def _tier_label(offset: int) -> str:
    if offset == 1:
        return "newer (nxt)"
    if offset == 2:
        return "newer (+2)"
    if offset == -1:
        return "older (-1)"
    return f"{'+' if offset > 0 else ''}{offset}"


async def find_similar_vehicles(
    db: AsyncSession,
    vehicle: Vehicle,
    max_results: int = SIMILAR_MAX,
) -> list[dict]:
    """Cross-brand suggestions in the same segment.

    Looks for ``market_listing_cache`` rows in the vehicle's year ±2 window,
    excluding the user's own make/model pair (that's the upgrade_options
    block). Ranks by a deterministic score that blends year proximity
    and price-band proximity. ``body_type`` is surfaced on the row when
    the cache has it but is not used as a filter (the cache column is
    sparse; filtering on it would silently drop most suggestions).
    """
    current_year = vehicle.year
    if current_year is None:
        return []

    stmt = select(MarketListingCache).where(
        MarketListingCache.year >= current_year - SIMILAR_YEAR_WINDOW,
        MarketListingCache.year <= current_year + SIMILAR_YEAR_WINDOW,
    )
    rows = list((await db.scalars(stmt)).all())

    current_make = (vehicle.make or "").strip().lower()
    current_model = (vehicle.model or "").strip().lower()

    current_value = await _median_for(
        db, vehicle.make or "", vehicle.model or "", current_year,
        vehicle.vehicle_type or "car",
    )

    out: list[dict] = []
    seen: set[tuple[str, str, int]] = set()
    for row in rows:
        rm = (row.make or "").strip().lower()
        rmodel = (row.model or "").strip().lower()
        if not rm or not rmodel:
            continue
        # Skip the user's own make/model (that's the upgrade_options block).
        if rm == current_make and rmodel == current_model:
            continue
        key = (rm, rmodel, row.year or 0)
        if key in seen:
            continue
        seen.add(key)
        median = _safe(row.median_price)
        if median is None:
            continue
        score = _similarity_score(
            current_year=current_year, target_year=row.year,
            current_value=current_value, target_value=median,
        )
        out.append({
            "make": row.make,
            "model": row.model,
            "year": row.year,
            "body_type": getattr(row, "body_type", None),
            "price_mid": round(median, 2),
            "score": round(score, 4),
            "note": None,
        })

    out.sort(key=lambda o: -o["score"])
    return out[:max_results]


def _similarity_score(*, current_year: int, target_year: int | None,
                      current_value: float | None, target_value: float) -> float:
    """0..1 deterministic score blending age + price proximity.

    Age score: 1.0 if same year, decays 0.25 per year off.
    Price score: 1.0 if same band, decays 0.1 per 25% off.
    Returns the average; 0.5 floor so a single weak signal doesn't read
    as a great match.
    """
    if target_year is None:
        age_score = 0.5
    else:
        age_score = max(0.0, 1.0 - 0.25 * abs(int(target_year) - current_year))

    if current_value is None or current_value <= 0:
        price_score = 0.5
    else:
        diff = abs(target_value - current_value) / current_value
        price_score = max(0.0, 1.0 - 0.4 * diff)

    return max(0.0, min(1.0, (age_score + price_score) / 2))


def _amortize_monthly(principal: float, rate_pct: float, term_months: int) -> tuple[float, float]:
    """Flat-rate amortization: monthly payment + total interest.

    Returns ``(monthly, total_interest)``. Handles the zero-rate edge
    case (interest = 0) so a special promo or 0% finance row doesn't
    divide-by-zero on the UI.
    """
    if principal <= 0 or term_months <= 0:
        return 0.0, 0.0
    r = rate_pct / 100.0 / 12.0  # monthly rate
    if r <= 0:
        monthly = principal / term_months
        return round(monthly, 2), 0.0
    # Standard amortisation formula.
    monthly = principal * r / (1 - (1 + r) ** -term_months)
    total_paid = monthly * term_months
    total_interest = total_paid - principal
    return round(monthly, 2), round(total_interest, 2)


def build_trade_up(
    *,
    current_value: float | None,
    upgrade_value: float | None,
    trade_in_mid: float | None,
    finance_term_months: int,
    rate_pct: float,
    deposit_pct: float,
) -> dict:
    """Compute one row of the trade-up delta + indicative finance delta.

    Returns a dict matching ``TradeUpDelta`` in ``schemas/advisor.py``.
    Surplus flag fires when the upgrade is cheaper than the user's
    current private-sale value (rare in practice but possible for a
    downgrade tier or a stale cache).
    """
    if current_value is None or upgrade_value is None or trade_in_mid is None:
        return {
            "currency": CURRENCY,
            "finance_term_months": finance_term_months,
            "rate_pct": rate_pct,
            "deposit_pct": deposit_pct,
            "principal": None,
            "monthly_repayment": None,
            "total_interest": None,
            "surplus": False,
            "note": "missing price input — upgrade, current value, or trade-in band unavailable",
        }
    raw_gap = upgrade_value - current_value - trade_in_mid
    if raw_gap <= 0:
        return {
            "currency": CURRENCY,
            "finance_term_months": finance_term_months,
            "rate_pct": rate_pct,
            "deposit_pct": deposit_pct,
            "principal": 0.0,
            "monthly_repayment": 0.0,
            "total_interest": 0.0,
            "surplus": True,
            "note": "upgrade is below current value + trade-in — no finance needed",
        }
    principal = raw_gap * (1 - deposit_pct / 100.0)
    monthly, total_interest = _amortize_monthly(principal, rate_pct, finance_term_months)
    return {
        "currency": CURRENCY,
        "finance_term_months": finance_term_months,
        "rate_pct": rate_pct,
        "deposit_pct": deposit_pct,
        "principal": round(principal, 2),
        "monthly_repayment": monthly,
        "total_interest": total_interest,
        "surplus": False,
        "note": None,
    }


async def compute_upgrade(
    db: AsyncSession,
    vehicle: Vehicle,
    odometer_km: int | None = None,
    finance_term_months: int | None = None,
    rate_pct: float | None = None,
    deposit_pct: float | None = None,
) -> dict:
    """Deterministic Upgrade plan.

    Returns a dict that matches ``AdvisorUpgradeData`` in
    ``schemas/advisor.py``. Anchored on the same cached market median
    the Value module uses, so consecutive Upgrade runs return the same
    numbers (no per-call drift).
    """
    term = _clamp_finance_term(finance_term_months)
    rate = _clamp_rate_pct(rate_pct)
    deposit = _clamp_deposit_pct(deposit_pct)

    value = await compute_market_value(db, vehicle, odometer_km=odometer_km)
    current_value = value.get("mid")
    trade_in = trade_in_band(current_value)
    trade_in_mid = trade_in.get("mid")

    if current_value is None:
        return {
            "currency": CURRENCY,
            "current_value": None,
            "upgrade_options": [],
            "similar_vehicles": [],
            "trade_up": [],
            "finance_term_months": term,
            "rate_pct": rate,
            "deposit_pct": deposit,
            "note": value.get("note") or "no market listings available for this vehicle",
        }

    options = await find_upgrade_options(db, vehicle, odometer_km=odometer_km)
    similar = await find_similar_vehicles(db, vehicle)

    # Build one trade-up row per option with a usable price_mid so the
    # UI can show a per-tier table. Options whose price is missing are
    # surfaced with an explanatory note inside the delta row.
    trade_up: list[dict] = []
    for opt in options:
        if opt.get("price_mid") is None:
            trade_up.append(build_trade_up(
                current_value=current_value,
                upgrade_value=None,
                trade_in_mid=trade_in_mid,
                finance_term_months=term,
                rate_pct=rate,
                deposit_pct=deposit,
            ) | {"upgrade_year": opt["year"], "tier_label": opt["tier_label"]})
            continue
        trade_up.append(build_trade_up(
            current_value=current_value,
            upgrade_value=opt["price_mid"],
            trade_in_mid=trade_in_mid,
            finance_term_months=term,
            rate_pct=rate,
            deposit_pct=deposit,
        ) | {"upgrade_year": opt["year"], "tier_label": opt["tier_label"]})

    return {
        "currency": CURRENCY,
        "current_value": current_value,
        "upgrade_options": options,
        "similar_vehicles": similar,
        "trade_up": trade_up,
        "finance_term_months": term,
        "rate_pct": rate,
        "deposit_pct": deposit,
        "note": None,
    }

# --- Finance module (AUT-2448) --------------------------------------------
#
# Deterministic loan amortisation + lease + novated-coming-soon. Lives next
# to the other Ownership Advisor helpers so the module-level docs read as
# one file. The frontend posts
#   { down_payment, term_months, rate_pct, novated? }
# and gets back four mode blocks (novated gated by the request flag).

def _clamp_term(term_months: int, *, lease: bool) -> int:
    if lease:
        return max(LEASE_MIN_TERM_MONTHS, min(LEASE_MAX_TERM_MONTHS, int(term_months)))
    return max(FINANCE_MIN_TERM_MONTHS, min(FINANCE_MAX_TERM_MONTHS, int(term_months)))


def _loan_monthly_payment(principal: float, annual_rate_pct: float, term_months: int) -> float:
    """Standard amortising-loan monthly payment (P / i over n).

    Falls back to ``principal / term_months`` when the rate is zero so the
    zero-interest edge case stays sensible on the UI (e.g. manufacturer 0%
    finance promos).
    """
    if principal <= 0 or term_months <= 0:
        return 0.0
    monthly_rate = (annual_rate_pct / 100.0) / 12.0
    if monthly_rate <= 0:
        return round(principal / term_months, 2)
    factor = (1.0 + monthly_rate) ** term_months
    payment = principal * monthly_rate * factor / (factor - 1.0)
    return round(payment, 2)


def _amortization_schedule(
    principal: float, annual_rate_pct: float, term_months: int, monthly_payment: float,
) -> list[dict]:
    """Build a per-period amortisation schedule.

    Last period absorbs any floating-point rounding so the balance lands on
    exactly ``0``. Each row is shaped to match ``AmortizationRow``.
    """
    schedule: list[dict] = []
    if principal <= 0 or term_months <= 0:
        return schedule
    monthly_rate = (annual_rate_pct / 100.0) / 12.0
    balance = float(principal)
    pay = float(monthly_payment)
    for period in range(1, term_months + 1):
        interest = round(balance * monthly_rate, 2) if monthly_rate > 0 else 0.0
        if period == term_months:
            principal_paid = round(balance, 2)
            payment = round(principal_paid + interest, 2)
            balance = 0.0
        else:
            principal_paid = round(pay - interest, 2)
            if principal_paid > balance:
                principal_paid = round(balance, 2)
                payment = round(principal_paid + interest, 2)
            else:
                payment = pay
            balance = round(balance - principal_paid, 2)
            if balance < 0:
                balance = 0.0
        schedule.append({
            "period": period,
            "payment": payment,
            "interest": interest,
            "principal": principal_paid,
            "balance_end": balance,
        })
    return schedule


def _lease_residual_pct(term_months: int) -> float:
    """Residual value as a fraction of the original price at end of lease.

    Anchored on a 36-month base of 46%, scaling **upward** for shorter
    terms and **downward** for longer terms, capped so it never drops
    below the industry floor of 25% or exceed 75% (i.e. a one-month lease
    has a near-full residual, a 60-month lease has sunk most of the
    depreciation).
    """
    term = max(LEASE_MIN_TERM_MONTHS, min(LEASE_MAX_TERM_MONTHS, int(term_months)))
    delta = 36 - term  # positive when shorter than 36, negative when longer
    pct = _LEASE_RESIDUAL_36M + (_LEASE_RESIDUAL_PER_MONTH * delta)
    return max(0.25, min(0.75, round(pct, 4)))


def _lease_monthly(principal: float, residual_value: float, term_months: int, annual_rate_pct: float) -> tuple[float, float]:
    """Return (monthly_payment, money_factor).

    Standard lease payment = (depreciation + finance charge) / months,
    where depreciation = (principal - residual) / months and finance
    charge = (principal + residual) * money_factor, money_factor =
    (annual_rate_pct / 100) / 24.
    """
    if term_months <= 0:
        return 0.0, 0.0
    depreciation = (principal - residual_value) / term_months
    money_factor = (annual_rate_pct / 100.0) / LEASE_MONEY_FACTOR_DIVISOR
    finance_charge = (principal + residual_value) * money_factor
    return round(depreciation + finance_charge, 2), round(money_factor, 6)


def compute_finance_plan(
    *,
    vehicle_price: float,
    down_payment: float,
    term_months: int,
    rate_pct: float,
    novated: bool = False,
) -> dict:
    """Compute the four-mode finance plan (AUT-2448).

    Pure function — no DB, no AI, no 9Router. Returns a dict shaped to
    match ``AdvisorFinanceData``. ``vehicle_price`` is the negotiated drive-
    away price; ``down_payment`` is the cash the user puts in upfront; the
    financed principal is ``vehicle_price - down_payment`` (clamped at 0 so
    a deposit >= price produces a buy-outright scenario, not negative
    principal).

    The ``novated`` block is future-flagged: always returns
    ``status="coming_soon"`` until the EV / FBT-specific rules land in a
    follow-up ADR. The request flag gates whether the block is included in
    the response at all so the UI can hide it cleanly.
    """
    price = max(0.0, float(vehicle_price or 0.0))
    down = max(0.0, min(price, float(down_payment or 0.0)))
    principal = max(0.0, round(price - down, 2))
    finance_term = _clamp_term(term_months, lease=False)
    lease_term = _clamp_term(term_months, lease=True)
    rate = max(0.0, float(rate_pct or 0.0))

    # --- buy outright ---
    buy = {
        "mode": "buy",
        "status": "ok",
        "currency": CURRENCY,
        "purchase_price": round(price, 2),
        "effective_monthly": 0.0,
        "total_cost": round(price, 2),
        "total_interest": 0.0,
        "note": "Outright purchase — no monthly payments, no interest.",
    }

    # --- finance (loan) ---
    monthly = _loan_monthly_payment(principal, rate, finance_term)
    schedule = _amortization_schedule(principal, rate, finance_term, monthly)
    total_cost_finance = round(down + sum(row["payment"] for row in schedule), 2)
    total_interest = round(sum(row["interest"] for row in schedule), 2)
    finance_block = {
        "mode": "finance",
        "status": "ok",
        "currency": CURRENCY,
        "principal": principal,
        "term_months": finance_term,
        "annual_rate_pct": round(rate, 4),
        "monthly_payment": monthly,
        "effective_monthly": monthly,
        "total_cost": total_cost_finance,
        "total_interest": total_interest,
        "amortization": schedule,
        "note": None,
    }

    # --- lease (operating lease, residual + finance charge) ---
    residual_pct = _lease_residual_pct(lease_term)
    residual_value = round(price * residual_pct, 2)
    lease_monthly, money_factor = _lease_monthly(principal, residual_value, lease_term, rate)
    total_cost_lease = round(down + lease_monthly * lease_term, 2)
    lease_block = {
        "mode": "lease",
        "status": "ok",
        "currency": CURRENCY,
        "principal": principal,
        "term_months": lease_term,
        "residual_pct": round(residual_pct, 4),
        "residual_value": residual_value,
        "effective_monthly": lease_monthly,
        "total_cost": total_cost_lease,
        "money_factor": money_factor,
        "note": "Operating lease estimate. Excludes on-road costs, insurance and excess km charges.",
    }

    modes: list[dict] = [buy, finance_block, lease_block]
    if novated:
        modes.append({
            "mode": "novated",
            "status": "coming_soon",
            "currency": CURRENCY,
            "effective_monthly": None,
            "total_cost": None,
            "note": "Novated lease calculator is coming soon. The toggle is reserved in the UI.",
        })

    note = None
    if principal <= 0 and price > 0:
        note = "Down payment covers the full price — finance and lease blocks are zero-principal informational only."
    elif price <= 0:
        note = "No vehicle price available — finance block is informational only."

    return {
        "currency": CURRENCY,
        "vehicle_price": round(price, 2),
        "down_payment": round(down, 2),
        "modes": modes,
        "note": note,
    }


# --- AI Advisor baseline (AUT-2450) ----------------------------------------
# Mirror of ai/app/fallbacks/advisor.py so the backend can answer the
# /advisor/ai route when the AI gateway is unreachable. The rule tree is
# identical so the deterministic answer is consistent end-to-end.

_ADVISOR_UPGRADE_GAP_RATIO = 0.25
_ADVISOR_DELAY_GAP_RATIO = 0.75
_ADVISOR_UPGRADE_TCO_SAVING = 0.15
_ADVISOR_RATIONALE_MAX = 280
_ADVISOR_NEXT_ACTIONS_MAX = 3


def _advisor_f(value):
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _advisor_clip(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def _advisor_funding_gap(modules: dict) -> float | None:
    replace = modules.get("replace") or {}
    val = modules.get("value") or {}
    gap = _advisor_f(replace.get("funding_gap"))
    if gap is not None:
        return gap
    used = _advisor_f(replace.get("used_replacement_cost"))
    mid = _advisor_f(val.get("mid") or val.get("estimated_value"))
    if used is None or mid is None:
        return None
    return used - mid


def _advisor_estimated_value(modules: dict) -> float | None:
    val = modules.get("value") or {}
    return _advisor_f(val.get("mid") or val.get("estimated_value"))


def _advisor_monthly(modules: dict) -> float | None:
    fin = modules.get("finance") or {}
    for key in ("monthly", "effective_monthly", "payment"):
        v = _advisor_f(fin.get(key))
        if v is not None:
            return v
    return None


def _advisor_decision(modules: dict) -> str:
    gap = _advisor_funding_gap(modules)
    est = _advisor_estimated_value(modules)
    if gap is not None and est not in (None, 0):
        ratio = gap / est
        if ratio <= _ADVISOR_UPGRADE_GAP_RATIO:
            return "upgrade"
        if ratio > _ADVISOR_DELAY_GAP_RATIO:
            return "delay"
    monthly = _advisor_monthly(modules)
    if monthly is not None and est is not None and est > 0:
        if monthly * 12 < est * _ADVISOR_UPGRADE_TCO_SAVING:
            return "upgrade"
    dream = modules.get("dream") or {}
    if dream and isinstance(dream.get("affordability"), str):
        if dream["affordability"].strip().lower() in ("affordable", "yes", "within_budget", "ok"):
            return "strategy"
    return "keep"


def _advisor_rationale(decision: str, modules: dict, missing: list[str]) -> str:
    parts: list[str] = []
    est = _advisor_estimated_value(modules)
    gap = _advisor_funding_gap(modules)
    if est is not None:
        parts.append(f"current value ~${est:,.0f}")
    if gap is not None:
        parts.append(f"replacement gap ~${gap:,.0f}")
    head = {
        "keep": "Your current car is the smart money move.",
        "upgrade": "A clear trade-up is within reach.",
        "delay": "Wait — the numbers aren't in your favour yet.",
        "strategy": "A non-binary play fits this scenario.",
    }.get(decision, "Your current car is the smart money move.")
    text = head
    if parts:
        text = f"{head} " + ", ".join(parts) + "."
    if missing:
        text += f" (limited data: {', '.join(missing)}.)"
    return _advisor_clip(text, _ADVISOR_RATIONALE_MAX)


def _advisor_actions(decision: str) -> list[str]:
    table = {
        "keep": [
            "Stick with the current car; revisit in 6 months.",
            "Keep up scheduled services to protect residual value.",
        ],
        "upgrade": [
            "Shortlist 2-3 concrete upgrade candidates from the Upgrade tab.",
            "Get a pre-purchase inspection budget for each shortlist.",
        ],
        "delay": [
            "Re-run the advisor after your next service or in 3 months.",
            "Track market median for your model weekly on the Value tab.",
        ],
        "strategy": [
            "Compare a novated lease vs outright purchase on the Finance tab.",
            "Talk to a broker about a 2-3 year hold before committing.",
        ],
    }
    return table.get(decision, table["keep"])[:_ADVISOR_NEXT_ACTIONS_MAX]


async def compute_advisor_recommendation(
    modules: dict | None,
) -> dict:
    """Pure-deterministic AI-advisor baseline (AUT-2450).

    ``modules`` is the caller's dict of sub-module outputs (value /
    replace / upgrade / finance / dream). Returns the same
    ``AdvisorAIData`` shape the AI gateway returns, so the route can
    render either path through one parser. No 9Router call.
    """
    modules = modules or {}
    required = ("value", "replace", "upgrade", "finance", "dream")
    missing = [m for m in required if not modules.get(m)]
    decision = _advisor_decision(modules)
    strength = (len(required) - len(missing)) / len(required)
    confidence = round(max(0.0, min(1.0, 0.5 + 0.4 * strength)), 2)
    if decision == "delay" and missing:
        confidence = min(confidence, 0.55)
    return {
        "decision": decision,
        "confidence": confidence,
        "rationale": _advisor_rationale(decision, modules, missing),
        "next_actions": _advisor_actions(decision),
        "based_on": {m: bool(modules.get(m)) for m in required},
        "model": "rule-based-fallback",
    }


# ---------------------------------------------------------------------------
# Dream Car module (AUT-2449)
# ---------------------------------------------------------------------------
#
# Three deterministic blocks for an arbitrary target vehicle:
#
# 1. Target lookup — reuses ``get_market_data`` (same make/model/year key
#    shape as Value/Upgrade, so the cache row is shared — no duplicate
#    storage per ADR 0001 §2.5). Returns a low/mid/high band + sample
#    size; when the cache has no row, ``note`` explains the gap so the
#    UI can render a graceful "no market data" state.
#
# 2. Affordability — pure arithmetic on the request body's finance
#    profile (``annual_income``, ``monthly_expenses``, ``cash_on_hand``).
#    No DB read; finance inputs are ephemeral per ADR 0001 §2.4 (no
#    migration, no user-settings tab). Surplus flag fires when the user
#    can fund the deposit AND keep positive disposable income after the
#    indicative repayment.
#
# 3. Repayments — wraps the existing ``_loan_monthly_payment`` (the same
#    deterministic amortising-loan helper the Finance module publishes),
#    with the same default term (60), rate (7.5% p.a.) and deposit (20%)
#    — clamped via the existing helpers. Reusing rather than re-deriving
#    stops the AI Advisor (AUT-2450) from ever seeing two different
#    numbers for the same input.

# Debt-service-ratio ceiling: how much of monthly disposable income can
# be safely absorbed by the car loan. 30% is the conservative AU bank
# floor (most lenders cap serviceability at 30-35%). Industry standard,
# not invented.
DREAM_DSR_CEILING = 0.30


# Dream module's own finance clamps — kept inline so the module is
# self-contained (no dependency on the Upgrade module, which is in
# flight as PR #492). Same numeric bounds as the rest of the advisor
# surface; clamp failures fall back to the documented defaults.
DREAM_FINANCE_TERM_MIN = 12
DREAM_FINANCE_TERM_MAX = 84
DREAM_RATE_PCT_MIN = 0.0
DREAM_RATE_PCT_MAX = 30.0
DREAM_DEPOSIT_PCT_MIN = 0.0
DREAM_DEPOSIT_PCT_MAX = 100.0
DREAM_DEFAULT_FINANCE_TERM_MONTHS = 60
DREAM_DEFAULT_RATE_PCT = 7.5
DREAM_DEFAULT_DEPOSIT_PCT = 20.0


def _dream_clamp_term(months: int | None) -> int:
    if months is None:
        return DREAM_DEFAULT_FINANCE_TERM_MONTHS
    try:
        m = int(months)
    except (TypeError, ValueError):
        return DREAM_DEFAULT_FINANCE_TERM_MONTHS
    return max(DREAM_FINANCE_TERM_MIN, min(DREAM_FINANCE_TERM_MAX, m))


def _dream_clamp_rate(rate: float | None) -> float:
    if rate is None:
        return DREAM_DEFAULT_RATE_PCT
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return DREAM_DEFAULT_RATE_PCT
    return max(DREAM_RATE_PCT_MIN, min(DREAM_RATE_PCT_MAX, r))


def _dream_clamp_deposit(pct: float | None) -> float:
    if pct is None:
        return DREAM_DEFAULT_DEPOSIT_PCT
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return DREAM_DEFAULT_DEPOSIT_PCT
    return max(DREAM_DEPOSIT_PCT_MIN, min(DREAM_DEPOSIT_PCT_MAX, p))


async def compute_dream(
    db: AsyncSession,
    *,
    make: str,
    model: str,
    year: int,
    vehicle_type: str = "car",
    finance_term_months: int | None = None,
    rate_pct: float | None = None,
    deposit_pct: float | None = None,
    annual_income: float | None = None,
    monthly_expenses: float | None = None,
    cash_on_hand: float | None = None,
) -> dict:
    """Deterministic Dream Car plan.

    Returns a dict matching ``AdvisorDreamData`` in ``schemas/advisor.py``.
    All numbers come from the existing ``market_listing_cache`` (target
    lookup) or the request body's finance profile (affordability +
    repayments) — no AI, no 9Router.
    """
    term = _dream_clamp_term(finance_term_months)
    rate = _dream_clamp_rate(rate_pct)
    deposit = _dream_clamp_deposit(deposit_pct)

    # --- 1. Target lookup --------------------------------------------------
    market = await get_market_data(
        db, make or "", model or "", year, vehicle_type or "car",
    )
    target_mid = _safe(market.get("median_price"))
    target_block = {
        "make": (make or "").strip(),
        "model": (model or "").strip(),
        "year": year,
        "vehicle_type": vehicle_type or "car",
        "currency": CURRENCY,
        "low": _safe(market.get("low_price")),
        "mid": target_mid,
        "high": _safe(market.get("high_price")),
        "source": market.get("source", "fallback"),
        "as_of": market.get("as_of"),
        "stale": bool(market.get("stale")),
        "sample_size": int(market.get("sample_size") or 0),
        "note": market.get("note") if target_mid is None else None,
    }

    # --- 2. Affordability (pure arithmetic on request body) ----------------
    # Three inputs: annual_income, monthly_expenses, cash_on_hand. All
    # optional; any missing field makes the numeric block stay None and
    # ``note`` explains the gap. This matches the ADR 0001 §2.4 rule
    # that finance inputs are ephemeral — there's no DB row holding the
    # user's profile, so the screen always re-asks.
    has_profile = (
        annual_income is not None and monthly_expenses is not None
    )
    if not has_profile:
        affordability_block = {
            "currency": CURRENCY,
            "target_price_mid": target_mid,
            "deposit_required": (
                round(target_mid * deposit / 100.0, 2) if target_mid is not None else None
            ),
            "annual_income": annual_income,
            "monthly_disposable_income": None,
            "cash_on_hand": cash_on_hand,
            "cash_gap": (
                round(cash_on_hand - target_mid * deposit / 100.0, 2)
                if (cash_on_hand is not None and target_mid is not None)
                else None
            ),
            "surplus": False,
            "note": "annual income and monthly expenses required to compute affordability",
        }
    else:
        annual_income = float(annual_income)
        monthly_expenses = float(monthly_expenses)
        monthly_income = annual_income / 12.0
        monthly_disposable = max(0.0, monthly_income - monthly_expenses)
        deposit_required = (
            round(target_mid * deposit / 100.0, 2) if target_mid is not None else None
        )
        if cash_on_hand is None or deposit_required is None:
            cash_gap = None
        else:
            cash_gap = round(float(cash_on_hand) - deposit_required, 2)
        affordability_block = {
            "currency": CURRENCY,
            "target_price_mid": target_mid,
            "deposit_required": deposit_required,
            "annual_income": annual_income,
            "monthly_disposable_income": round(monthly_disposable, 2),
            "cash_on_hand": float(cash_on_hand) if cash_on_hand is not None else None,
            "cash_gap": cash_gap,
            "surplus": False,  # finalised below once repayments are known
            "note": None,
        }

    # --- 3. Repayments (reuse Finance's amortise helper) -------------------
    if target_mid is None or target_mid <= 0:
        repayments_block = {
            "currency": CURRENCY,
            "finance_term_months": term,
            "rate_pct": rate,
            "deposit_pct": deposit,
            "principal": None,
            "monthly_repayment": None,
            "total_interest": None,
            "note": "no market listings available for target — cannot estimate finance",
        }
    else:
        principal = round(target_mid * (1 - deposit / 100.0), 2)
        monthly = _loan_monthly_payment(principal, rate, term)
        total_interest = round(monthly * term - principal, 2) if term > 0 else 0.0
        repayments_block = {
            "currency": CURRENCY,
            "finance_term_months": term,
            "rate_pct": rate,
            "deposit_pct": deposit,
            "principal": principal,
            "monthly_repayment": monthly,
            "total_interest": total_interest,
            "note": None,
        }

    # --- Finalise affordability.surplus (cash + DSR headroom) ---------------
    # Surplus fires when the user can fund the deposit (cash_on_hand >=
    # deposit_required) AND the indicative monthly repayment fits under
    # the DSR ceiling against their disposable income. Both are pure
    # arithmetic on values already in the block — no new inputs.
    monthly_repayment = repayments_block.get("monthly_repayment")
    if has_profile and target_mid is not None and monthly_repayment:
        cash_ok = (
            affordability_block["cash_gap"] is None
            or affordability_block["cash_gap"] >= 0
        )
        monthly_disposable = float(affordability_block["monthly_disposable_income"] or 0.0)
        dsr_ok = monthly_disposable <= 0 or (
            monthly_repayment <= monthly_disposable * DREAM_DSR_CEILING
        )
        affordability_block["surplus"] = bool(cash_ok and dsr_ok)
        if not dsr_ok:
            affordability_block["note"] = (
                f"monthly repayment exceeds {int(DREAM_DSR_CEILING * 100)}% of "
                f"disposable income — consider a longer term or a cheaper car"
            )

    return {
        "currency": CURRENCY,
        "target": target_block,
        "affordability": affordability_block,
        "repayments": repayments_block,
        "note": target_block["note"],
    }
