"""DB-free unit tests for per-station cost annotations (AUT-2203).

Targets ``app.services.fuel_servo.annotate_price`` (pure helper) so we don't
have to spin up FastAPI / a DB / 9Router. Same env-stub pattern as
``test_fuel_prices.py``.

Coverage (from the issue):
  (1) avg_l_per_100km=8.5, avg fill=45L, price=$1.65/L (== 165 c/L) ->
      cost_per_km ~= 0.140 ($/km), avg_fill_cost == 74.25 ($)
  (2) no vehicle_id (no stats) -> both fields None on every station price
  (3) vehicle with no fuel logs (stats present but averages are None) ->
      both fields None on every station price
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"

from app.schemas.fuel import FuelStats  # noqa: E402
from app.services.fuel_servo import annotate_price, annotate_prices  # noqa: E402


def _stats(*, avg_l_per_100km: float | None, avg_litres_per_fill: float | None) -> FuelStats:
    """Tiny FuelStats carrying just the two fields the annotation helper uses."""
    return FuelStats(
        total_litres=0.0,
        total_cost=0.0,
        avg_l_per_100km=avg_l_per_100km,
        avg_cost_per_km=None,
        avg_litres_per_fill=avg_litres_per_fill,
        last_log=None,
        series=[],
    )


def test_annotate_price_full_stats_uses_issue_formula() -> None:
    # Issue scenario: avg 8.5 L/100km, avg fill 45 L, station price $1.65/L (165 c/L).
    # cost_per_km  = 8.5  * 165 / 100 = 14.025  -> rounded to 4dp = 0.1403 (displayed $0.14/km)
    # avg_fill_cost= 45   * 165 / 100 = 74.25   (exact)
    cost_per_km, avg_fill_cost = annotate_price(
        165.0,
        avg_l_per_100km=8.5,
        avg_litres_per_fill=45.0,
    )
    assert cost_per_km == 0.1403
    assert avg_fill_cost == 74.25


def test_annotate_price_no_vehicle_context_yields_none_fields() -> None:
    # /fuel/stations called without vehicle_id -> no stats -> every price stays un-annotated.
    cost_per_km, avg_fill_cost = annotate_price(
        189.9,
        avg_l_per_100km=None,
        avg_litres_per_fill=None,
    )
    assert cost_per_km is None
    assert avg_fill_cost is None


def test_annotate_price_vehicle_with_no_logs_yields_none_fields() -> None:
    # Vehicle exists but has zero fuel logs -> averages are None but stats object present.
    cost_per_km, avg_fill_cost = annotate_price(
        189.9,
        avg_l_per_100km=None,
        avg_litres_per_fill=None,
    )
    assert cost_per_km is None
    assert avg_fill_cost is None


def test_annotate_prices_without_stats_keeps_every_annotation_none() -> None:
    # The /fuel/stations caller passes vehicle_id=None -> annotate_prices receives None stats
    # and every price in the list must keep both fields None (no partial annotations).
    out = annotate_prices([165.0, 189.9, 220.5], None)
    assert out == [(None, None), (None, None), (None, None)]


def test_annotate_prices_with_empty_logs_stats_yields_none_per_price() -> None:
    # /fuel/stations called with vehicle_id for a vehicle that has no fuel logs yet.
    # stats object is present, but both averages are None -> every per-station annotation None.
    stats = _stats(avg_l_per_100km=None, avg_litres_per_fill=None)
    out = annotate_prices([165.0, 189.9, 220.5], stats)
    assert out == [(None, None), (None, None), (None, None)]


def test_annotate_prices_full_stats_annotates_every_price_independently() -> None:
    # Sanity: one stats object, three different station prices -> three different cost_per_km
    # / avg_fill_cost pairs in the same order. round() uses banker's rounding, so 85.455 -> 85.45.
    stats = _stats(avg_l_per_100km=8.5, avg_litres_per_fill=45.0)
    out = annotate_prices([165.0, 189.9, 220.5], stats)
    assert [c for c, _ in out] == [0.1403, 0.1614, 0.1874]
    assert [f for _, f in out] == [74.25, 85.45, 99.22]


def test_annotate_price_partial_stats_only_known_field_filled() -> None:
    # avg_l_per_100km known, avg_litres_per_fill missing -> only cost_per_km populated.
    cost_per_km, avg_fill_cost = annotate_price(
        165.0,
        avg_l_per_100km=8.5,
        avg_litres_per_fill=None,
    )
    assert cost_per_km == 0.1403
    assert avg_fill_cost is None