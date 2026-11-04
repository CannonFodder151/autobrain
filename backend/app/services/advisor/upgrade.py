"""Upgrade module (AUT-2447): deterministic upgrade planning.

Same-model upgrade options (next 1-2 tiers newer + one older) and
cross-brand suggestions. Each option's price comes from the cached
market median the Value module uses, so consecutive runs return the
same numbers (no per-call drift). No AI, no 9Router.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.market_listing import MarketListingCache
from app.models.vehicle import Vehicle
from app.services.advisor._common import CURRENCY, _safe
from app.services.advisor.value import (
    condition_multiplier,
    km_adjustment,
    _band,
    COMPARABLES_MAX,
    COMPARABLES_YEAR_WINDOW,
)
from app.services.advisor.replace import (
    age_years,
    _clamp_horizon,
)
from app.services.market_data import get_market_data

logger = get_logger(__name__)

# Tier weights used to rank upgrade options.
_UPGRADE_TIER_WEIGHT: dict[int, float] = {
    1: 1.0,   # next year — closest fit
    2: 0.85,  # year after next
    -1: 0.7,  # one year older (downgrade)
}
_UPGRADE_MAX_TIERS = 3

SIMILAR_MAX = 6
SIMILAR_YEAR_WINDOW = 2

# Finance constants (same values the old single-file used).
UPGRADE_DEFAULT_FINANCE_TERM_MONTHS = 60
UPGRADE_DEFAULT_RATE_PCT = 7.5
UPGRADE_DEFAULT_DEPOSIT_PCT = 20.0
UPGRADE_FINANCE_TERM_MIN = 12
UPGRADE_FINANCE_TERM_MAX = 84


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


def _tier_label(offset: int) -> str:
    if offset == 1:
        return "newer (nxt)"
    if offset == 2:
        return "newer (+2)"
    if offset == -1:
        return "older (-1)"
    return f"{'+' if offset > 0 else ''}{offset}"


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


async def find_similar_vehicles(
    db: AsyncSession,
    vehicle: Vehicle,
    max_results: int = SIMILAR_MAX,
) -> list[dict]:
    """Cross-brand suggestions in the same segment.

    Looks for ``market_listing_cache`` rows in the vehicle's year +/-2 window,
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

    from app.services.advisor.value import compute_market_value
    from app.services.advisor.value import trade_in_band

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