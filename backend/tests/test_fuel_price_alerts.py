"""Unit tests for AUT-1859 servo-spy fuel price alerts (pure logic only).

Covers the deterministic price-change / direction / threshold decisioning and
the watch-list schema validation. No Postgres / Redis / network required, so
the guard logic is verifiable in CI without a DB provision.
"""

import pytest
from pydantic import ValidationError

from app.services.fuel_prices import compute_price_change
from app.schemas.fuel import FuelPriceWatchlistIn
from app.api.v1.fuel_prices import _price_delta_pct, router


def test_compute_price_change_up():
    pct, direction = compute_price_change(180.0, 170.0)
    assert direction == "up"
    assert pct == round((180.0 - 170.0) / 170 * 100, 2)


def test_compute_price_change_down():
    pct, direction = compute_price_change(160.0, 170.0)
    assert direction == "down"
    assert pct < 0


def test_compute_price_change_zero_is_no_direction():
    pct, direction = compute_price_change(170.0, 170.0)
    assert pct == 0.0
    assert direction is None


def test_compute_price_change_no_history():
    assert compute_price_change(170.0, None) == (None, None)
    assert compute_price_change(None, 170.0) == (None, None)


def test_compute_price_change_zero_divisor():
    assert compute_price_change(170.0, 0) == (None, None)


def test_price_delta_pct_helper_matches_compute():
    assert _price_delta_pct(180.0, 170.0) == compute_price_change(180.0, 170.0)[0]
    assert _price_delta_pct(170.0, None) is None
    assert _price_delta_pct(None, None) is None


def _route_paths() -> list[str]:
    return [getattr(r, "path", None) for r in router.routes]


def test_watchlist_routes_present():
    paths = _route_paths()
    assert "/fuel-prices/watchlist" in paths
    assert "/fuel-prices/watchlist/{watch_id}" in paths


def test_watchlist_schema_rejects_bad_direction():
    with pytest.raises(ValidationError):
        FuelPriceWatchlistIn(state="NSW", station_code="NSW001", fuel_type="E10", direction="sideways")


def test_watchlist_schema_threshold_must_be_positive():
    with pytest.raises(ValidationError):
        FuelPriceWatchlistIn(state="NSW", station_code="NSW001", fuel_type="E10", threshold_pct=0)


def test_watchlist_schema_defaults():
    w = FuelPriceWatchlistIn(state="NSW", station_code="NSW001", fuel_type="E10")
    assert w.direction == "both"
    assert w.threshold_pct == 5.0
