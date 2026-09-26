"""Replace module (AUT-2446): documented new-vs-used premium by vehicle age.

A 3yo used car is worth ~70% of its new equivalent; an 8yo is worth ~40%.
Interpolated linearly between the breakpoints below and clamped to
[1.0, NEW_USED_PREMIUM_MAX]. Numbers chosen to mirror the well-known
ATO/NRMA depreciation curve; documented here so neither the UI nor any
future AI fallback has to invent them.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle import Vehicle
from app.services.advisor._common import CURRENCY, _MIN_VALUE, _MAX_VALUE, _safe
from app.services.advisor.value import (
    compute_market_value,
    trade_in_band,
)


# Replace premium breakpoints (vehicle age -> premium factor).
# A 0yo (current model year) is worth 1.0× new; a 3yo ≈ 70% of new;
# a 6yo ≈ 55%; a 10yo ≈ 45%.
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

    Anchored on the same cached market median the Value module uses —
    no AI, no 9Router, no extra network calls. Used replacement cost ==
    current private-sale mid (a buyer for your car is a buyer for a
    similar used car of the same vintage/condition). New replacement
    cost applies the documented ``new_used_premium(age)`` curve to the
    same anchor.

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