"""Pure helpers for the Servo Spy fuel-price API (AUT-2203).

Lives under ``app/services`` (not ``app/api/v1``) so the math is unit-testable
without spinning up FastAPI / a DB / a 9Router call. Deterministic, no AI.

ponytail: if we ever need to vary by fuel type (e.g. LPG and U95 have different
energy densities) the per-litre and per-km constants move out of the helper into
``app.core.fuel_units`` and this module just composes them.
"""

from app.schemas.fuel import FuelStats


def annotate_price(
    price_cpl: float,
    *,
    avg_l_per_100km: float | None,
    avg_litres_per_fill: float | None,
) -> tuple[float | None, float | None]:
    """Per-station cost annotations for one fuel price against a vehicle's stats.

    Inputs:
      price_cpl           station price in cents per litre (the ``fuel_prices.price`` column)
      avg_l_per_100km     vehicle's mean L/100km across its full-tank fills, or None if unknown
      avg_litres_per_fill vehicle's mean litres per fill, or None if unknown

    Outputs:
      cost_per_km     $/km = avg_l_per_100km * price_cpl / 10000
                                (avg L/100km * cents/L * 1 L / 100 km = cents/km; /100 -> $/km)
      avg_fill_cost   $    = price_cpl * avg_litres_per_fill / 100
                                (cents/L * L / 100 = $)

    Each stat field is independently optional: a missing stat just leaves its
    annotation as ``None`` rather than failing the whole request. Units match the
    pre-existing per-fill ``FuelLog.cost_per_km`` (dollars per km) so the frontend
    can format both with the same ``$X.XX/km`` widget.
    """
    cost_per_km = (
        round(avg_l_per_100km * price_cpl / 10000, 4)
        if avg_l_per_100km is not None
        else None
    )
    avg_fill_cost = (
        round(price_cpl * avg_litres_per_fill / 100, 2)
        if avg_litres_per_fill is not None
        else None
    )
    return cost_per_km, avg_fill_cost


def annotate_prices(
    price_cpls: list[float],
    stats: FuelStats | None,
) -> list[tuple[float | None, float | None]]:
    """Convenience wrapper for many prices against one ``FuelStats``.

    Returns one ``(cost_per_km, avg_fill_cost)`` pair per input price. When
    ``stats`` is None (no vehicle context) every annotation is None.
    """
    if stats is None:
        return [(None, None) for _ in price_cpls]
    return [
        annotate_price(
            p,
            avg_l_per_100km=stats.avg_l_per_100km,
            avg_litres_per_fill=stats.avg_litres_per_fill,
        )
        for p in price_cpls
    ]