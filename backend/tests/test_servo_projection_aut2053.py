"""AUT-2053 — Servo Spy vehicle-stats projection onto station prices.

Pure-function tests (no DB). The math is the whole feature: deterministic,
never AI, never ambiguous.
"""

from types import SimpleNamespace
from datetime import datetime, timezone

from app.api.v1.fuel_servo import _project_price
from app.models.fuel_station import FuelPrice


def _price(cents: float) -> FuelPrice:
    return FuelPrice(
        id="p1",
        station_id="s1",
        fuel_type="91",
        price=cents,
        effective_at=datetime.now(timezone.utc),
    )


def _stats(avg_l_per_100km=8.0, avg_fill_litres=40.0):
    return SimpleNamespace(
        avg_l_per_100km=avg_l_per_100km,
        avg_fill_litres=avg_fill_litres,
    )


def test_project_no_stats_returns_none() -> None:
    cpkm, afc = _project_price(_price(180.0), None)
    assert cpkm is None and afc is None


def test_project_cost_per_km_and_avg_fill_cost() -> None:
    # $1.80/L, vehicle 8 L/100km → $0.144/km; avg fill 40L → $72.00.
    cpkm, afc = _project_price(_price(180.0), _stats())
    assert cpkm == 0.144
    assert afc == 72.0


def test_project_handles_missing_fill_avg() -> None:
    # Vehicle with no full-tank fills → no avg_fill_cost, but cost/km still works.
    cpkm, afc = _project_price(_price(200.0), _stats(avg_l_per_100km=10.0, avg_fill_litres=None))
    assert cpkm == 0.2
    assert afc is None


def test_project_handles_zero_values() -> None:
    cpkm, afc = _project_price(_price(180.0), _stats(avg_l_per_100km=0.0, avg_fill_litres=0.0))
    assert cpkm is None and afc is None