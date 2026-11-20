"""Tests for AUT-412 + AUT-466 electric charging station price watchlist.

Pure-logic tests (no DB / network). Mirrors test_fuel_price_alerts.py.
"""

import pytest
from pydantic import ValidationError

from app.schemas.electric_price import (
    ChargingStationPriceOut,
    ChargingStationPriceWatchlistIn,
    ChargingStationPriceWatchlistOut,
)
from app.api.v1.electric_prices import router


def test_watchlist_schema_defaults():
    w = ChargingStationPriceWatchlistIn(station_id="ABC", connector_type="CCS2")
    assert w.direction == "both"
    assert w.threshold_pct == 5.0


def test_watchlist_schema_rejects_bad_direction():
    with pytest.raises(ValidationError):
        ChargingStationPriceWatchlistIn(
            station_id="ABC", connector_type="CCS2", direction="sideways"
        )


def test_watchlist_schema_rejects_bad_direction_uppercase():
    with pytest.raises(ValidationError):
        ChargingStationPriceWatchlistIn(
            station_id="ABC", connector_type="CCS2", direction="UP"
        )


def test_watchlist_schema_threshold_must_be_positive():
    with pytest.raises(ValidationError):
        ChargingStationPriceWatchlistIn(
            station_id="ABC", connector_type="CCS2", threshold_pct=0
        )


def test_watchlist_schema_threshold_negative_rejected():
    with pytest.raises(ValidationError):
        ChargingStationPriceWatchlistIn(
            station_id="ABC", connector_type="CCS2", threshold_pct=-1
        )


def test_watchlist_schema_accepts_all_directions():
    for d in ("up", "down", "both"):
        w = ChargingStationPriceWatchlistIn(
            station_id="ABC", connector_type="CCS2", direction=d
        )
        assert w.direction == d


def _route_paths() -> list[str]:
    return [getattr(r, "path", None) for r in router.routes]


def test_watchlist_routes_present():
    paths = _route_paths()
    assert "/electric-prices/stations" in paths
    assert "/electric-prices/watchlist" in paths
    assert "/electric-prices/watchlist/{watch_id}" in paths


def test_price_out_from_attributes():
    """ChargingStationPriceOut accepts ORM-style attribute access."""
    class _Row:
        station_id = "ST1"
        station_name = "Test Station"
        brand = "ChargeCo"
        address = "1 Main St"
        latitude = -33.86
        longitude = 151.2
        connector_type = "CCS2"
        price_per_kwh = 0.55
        currency = "AUD"
        updated_at = None

    out = ChargingStationPriceOut.model_validate(_Row())
    assert out.station_id == "ST1"
    assert out.station_name == "Test Station"
    assert out.brand == "ChargeCo"
    assert out.price_per_kwh == 0.55
    assert out.currency == "AUD"


def test_watchlist_out_from_attributes():
    """ChargingStationPriceWatchlistOut accepts ORM-style attribute access."""
    class _Row:
        id = "abc-123"
        user_id = "user-1"
        station_id = "ST1"
        station_name = "Test Station"
        brand = "ChargeCo"
        connector_type = "CCS2"
        direction = "both"
        threshold_pct = 5.0
        created_at = None

    out = ChargingStationPriceWatchlistOut.model_validate(_Row())
    assert out.id == "abc-123"
    assert out.station_id == "ST1"
    assert out.connector_type == "CCS2"
    assert out.direction == "both"
    assert out.threshold_pct == 5.0