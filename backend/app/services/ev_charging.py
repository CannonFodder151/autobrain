"""Pure helpers for the Electric Spy charging API (AUT-2435).

Same shape as ``fuel_servo``: deterministic, no AI, easily unit-tested without
spinning up FastAPI / a DB / 9Router.
"""

from __future__ import annotations


def cheapest_cost_per_kwh(
    costs: list[float | None],
) -> float | None:
    """Pick the lowest positive non-null cost from a list of $/kWh values.

    Returns None when the list is empty, every entry is None, or every entry
    is zero (free / missing). A zero price is treated as "no usable data" so
    we don't surface a misleading "cheapest = $0/kWh" badge to drivers.
    """
    cleaned = [c for c in costs if c is not None and c > 0]
    if not cleaned:
        return None
    return min(cleaned)
