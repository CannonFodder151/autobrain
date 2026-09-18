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