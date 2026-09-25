"""AUT-2203 — DB-free unit tests for ``app.services.fuel_servo.annotate_price``.

The math is the whole feature: deterministic, never AI, never ambiguous.
Mirrors the pattern in ``test_fuel_prices.py`` (no DB, no network).
"""

from app.services.fuel_servo import annotate_price


def test_cost_per_km_and_avg_fill_cost() -> None:
    # Vehicle: 8.5 L/100km, avg fill 45 L. Price $1.65/L.
    # cost_per_km = 8.5 * 165 / 10000 = 0.14025 → 0.1403
    # avg_fill_cost = 165 * 45 / 100 = 74.25
    cpkm, afc = annotate_price(
        165.0, avg_l_per_100km=8.5, avg_litres_per_fill=45.0
    )
    assert cpkm == 0.1403
    assert afc == 74.25


def test_no_vehicle_stats_returns_none() -> None:
    # No vehicle context → both fields absent (None).
    cpkm, afc = annotate_price(165.0, avg_l_per_100km=None, avg_litres_per_fill=None)
    assert cpkm is None
    assert afc is None


def test_no_fuel_logs_returns_none() -> None:
    # Vehicle exists but has no full-tank fills → avg_litres_per_fill is None.
    cpkm, afc = annotate_price(200.0, avg_l_per_100km=10.0, avg_litres_per_fill=None)
    assert cpkm == 0.2
    assert afc is None


def test_no_avg_l_per_100km_returns_none() -> None:
    # Vehicle exists but has no L/100km stat → cost_per_km is None.
    cpkm, afc = annotate_price(180.0, avg_l_per_100km=None, avg_litres_per_fill=40.0)
    assert cpkm is None
    assert afc == 72.0

def test_rounding_is_consistent() -> None:
    # cost_per_km rounds to 4dp, avg_fill_cost to 2dp.
    cpkm, afc = annotate_price(123.4, avg_l_per_100km=7.7, avg_litres_per_fill=33.3)
    assert cpkm == round(7.7 * 123.4 / 10000, 4)
    assert afc == round(123.4 * 33.3 / 100, 2)