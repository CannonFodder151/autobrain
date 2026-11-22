"""AUT-412 — Electric Spy vehicle-stats projection onto charging prices.

Pure-function tests (no DB). The math is the whole feature: deterministic,
never AI, never ambiguous.
"""

from types import SimpleNamespace
from datetime import datetime, timezone

from app.services.charging_servo import annotate_price
from app.models.charging_station import ChargingPrice

def _price(cents_per_kwh: float) -> ChargingPrice:
    return ChargingPrice(
        id="p1",
        station_id="s1",
        connector_type="CCS2",
        price_per_kwh=cents_per_kwh,
        effective_at=datetime.now(timezone.utc),
    )

def test_project_no_stats_returns_none() -> None:
    cpkm = annotate_price(45.0, avg_wh_per_km=None)
    assert cpkm is None

def test_project_cost_per_km() -> None:
    # 45 c/kWh, vehicle 200 Wh/km → $0.09/km
    cpkm = annotate_price(45.0, avg_wh_per_km=200.0)
    assert cpkm == 0.09

def test_project_cost_per_km_higher_efficiency() -> None:
    # 45 c/kWh, vehicle 150 Wh/km → $0.0675/km
    cpkm = annotate_price(45.0, avg_wh_per_km=150.0)
    assert cpkm == 0.0675

def test_project_handles_zero_values() -> None:
    cpkm = annotate_price(45.0, avg_wh_per_km=0.0)
    assert cpkm is None