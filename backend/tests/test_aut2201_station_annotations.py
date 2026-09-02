"""Per-station cost annotations on /fuel/stations (AUT-2201).

Pure unit: tests ``_station_out`` directly with stubbed ``FuelStation``/
``FuelPrice`` and ``FuelStats`` objects. No DB, no FastAPI. Deterministic.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MINIO_ACCESS_KEY"] = "a"
os.environ["MINIO_SECRET_KEY"] = "b"
os.environ["MINIO_BUCKET"] = "c"
os.environ["POSTGRES_USER"] = "u"
os.environ["POSTGRES_PASSWORD"] = "p"
os.environ["POSTGRES_DB"] = "d"
os.environ["ENVIRONMENT"] = "development"

from datetime import datetime, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from app.api.v1.fuel_servo import _station_out  # noqa: E402
from app.schemas.fuel import FuelStats  # noqa: E402


def _station(station_id="s1", lat=-37.81, lon=144.96, brand="BP") -> SimpleNamespace:
    return SimpleNamespace(
        id=station_id, source="test", brand=brand, name="Test Servo",
        address=None, lat=lat, lon=lon,
    )


def _price(price=189.9, fuel_type="91") -> SimpleNamespace:
    return SimpleNamespace(
        fuel_type=fuel_type, price=price,
        effective_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_station_out_without_stats_does_not_annotate() -> None:
    out = _station_out(_station(), [_price(189.9)], 5.0)
    assert len(out.prices) == 1
    assert out.prices[0].cost_per_km is None
    assert out.prices[0].avg_fill_cost is None


def test_station_out_with_stats_annotates_cost_per_km_and_fill() -> None:
    # avg_l_per_100km=8.0, avg_litres_per_fill=45.0; price=190 c/L
    # cost_per_km = 8.0 * 190 / 100 = 15.2
    # avg_fill_cost = 190 * 45 / 100 = 85.5
    stats = FuelStats(
        total_litres=180.0, total_cost=342.0,
        avg_l_per_100km=8.0, avg_cost_per_km=0.19,
        avg_litres_per_fill=45.0,
        last_log=None, series=[],
    )
    out = _station_out(_station(), [_price(190.0)], 5.0, stats)
    p = out.prices[0]
    assert p.cost_per_km == 15.2
    assert p.avg_fill_cost == 85.5


def test_station_out_annotates_each_price_independently() -> None:
    stats = FuelStats(
        total_litres=0, total_cost=0,
        avg_l_per_100km=10.0, avg_cost_per_km=None,
        avg_litres_per_fill=50.0,
        last_log=None, series=[],
    )
    prices = [_price(180.0, "91"), _price(200.0, "95"), _price(220.0, "98")]
    out = _station_out(_station(), prices, 1.0, stats)
    assert [p.cost_per_km for p in out.prices] == [18.0, 20.0, 22.0]
    assert [p.avg_fill_cost for p in out.prices] == [90.0, 100.0, 110.0]


def test_station_out_partial_stats_only_cost_per_km() -> None:
    # avg_l_per_100km present, avg_litres_per_fill missing -> only cost_per_km
    stats = FuelStats(
        total_litres=0, total_cost=0,
        avg_l_per_100km=7.5, avg_cost_per_km=None,
        avg_litres_per_fill=None,
        last_log=None, series=[],
    )
    out = _station_out(_station(), [_price(200.0)], None, stats)
    p = out.prices[0]
    assert p.cost_per_km == 15.0
    assert p.avg_fill_cost is None