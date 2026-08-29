"""Tests for the 7-Eleven fuel-price service (deterministic, no AI, no network).

We stub the network fetch and exercise pure parse/geo logic against a small
fixture that mirrors the projectzerothree.info schema (regions with rank
suffixes + per-store lat/lng).
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SEVEN_ELEVEN_API_URL"] = "https://example.test/api.php?format=json"

import httpx  # noqa: E402
import pytest  # noqa: E402
from unittest import mock  # noqa: E402

from app.services import fuel_prices as fp_svc  # noqa: E402

FIXTURE = {
    "updated": 1700000000,
    "regions": [
        {
            "region": "All",
            "prices": [
                # Melbourne CBD
                {"type": "U91", "price": 189.9, "name": "11-Seven Swanston", "state": "VIC",
                 "postcode": "3000", "suburb": "Melbourne", "lat": -37.8136, "lng": 144.9631},
                # Sydney CBD
                {"type": "U91", "price": 195.5, "name": "11-Seven Pitt", "state": "NSW",
                 "postcode": "2000", "suburb": "Sydney", "lat": -33.8688, "lng": 151.2093},
                # Geelong
                {"type": "U91", "price": 185.7, "name": "11-Seven Geelong", "state": "VIC",
                 "postcode": "3220", "suburb": "Geelong", "lat": -38.1506, "lng": 144.3637},
                {"type": "E10", "price": 165.3, "name": "11-Seven Swanston", "state": "VIC",
                 "postcode": "3000", "suburb": "Melbourne", "lat": -37.8136, "lng": 144.9631},
            ],
        },
        {"region": "VIC", "prices": [
            {"type": "U91", "price": 185.7, "name": "11-Seven Geelong", "state": "VIC",
             "postcode": "3220", "suburb": "Geelong", "lat": -38.1506, "lng": 144.3637},
        ]},
        {"region": "VIC-2", "prices": [
            {"type": "U91", "price": 188.0, "name": "11-Seven Box Hill", "state": "VIC",
             "postcode": "3128", "suburb": "Box Hill", "lat": -37.8169, "lng": 145.1240},
        ]},
        {"region": "VIC-3", "prices": [
            {"type": "U91", "price": 189.9, "name": "11-Seven Swanston", "state": "VIC",
             "postcode": "3000", "suburb": "Melbourne", "lat": -37.8136, "lng": 144.9631},
        ]},
        {"region": "NSW", "prices": [
            {"type": "U91", "price": 195.5, "name": "11-Seven Pitt", "state": "NSW",
             "postcode": "2000", "suburb": "Sydney", "lat": -33.8688, "lng": 151.2093},
        ]},
    ],
}


@pytest.fixture
def stub_fetch():
    with mock.patch.object(fp_svc, "fetch_7eleven_prices", return_value=FIXTURE) as m:
        yield m


def test_haversine_known_distance() -> None:
    # Sydney (-33.8688,151.2093) to Melbourne (-37.8136,144.9631): ~715 km.
    d = fp_svc._haversine_km(-33.8688, 151.2093, -37.8136, 144.9631)
    assert 690 < d < 740


@pytest.mark.asyncio
async def test_cheapest_by_region_returns_ranked_quotes(stub_fetch) -> None:
    out = await fp_svc.cheapest_7eleven("VIC", "U91")
    assert [q["rank"] for q in out] == [1, 2, 3]
    assert [q["price_cpl"] for q in out] == [185.7, 188.0, 189.9]
    assert out[0]["station"] == "11-Seven Geelong"


@pytest.mark.asyncio
async def test_cheapest_region_all_falls_back_to_empty_when_missing(stub_fetch) -> None:
    out = await fp_svc.cheapest_7eleven("WA", "U91")  # WA block absent in fixture
    assert out == []


@pytest.mark.asyncio
async def test_cheapest_unknown_fuel_type_rejected(stub_fetch) -> None:
    with pytest.raises(ValueError):
        await fp_svc.cheapest_7eleven("VIC", "B5")


@pytest.mark.asyncio
async def test_nearest_orders_by_distance(stub_fetch) -> None:
    # Search from Sydney; Sydney store must come before Melbourne/Geelong.
    out = await fp_svc.nearest_7eleven(-33.8688, 151.2093, "U91", max_results=3)
    assert len(out) == 3
    assert out[0]["suburb"] == "Sydney"
    assert out[0]["distance_km"] < out[1]["distance_km"]
    assert out[1]["distance_km"] < out[2]["distance_km"]
    assert out[0]["station"] == "11-Seven Pitt"


@pytest.mark.asyncio
async def test_nearest_filters_by_fuel_type(stub_fetch) -> None:
    out = await fp_svc.nearest_7eleven(-37.8136, 144.9631, "E10", max_results=5)
    assert len(out) == 1
    assert out[0]["suburb"] == "Melbourne"


@pytest.mark.asyncio
async def test_nearest_respects_max_km(stub_fetch) -> None:
    # Melbourne->Geelong ~75km, ->Sydney ~715km; capping at 50km keeps only Melbourne.
    out = await fp_svc.nearest_7eleven(-37.8136, 144.9631, "U91", max_results=10, max_km=50)
    assert len(out) == 1
    assert out[0]["suburb"] == "Melbourne"


@pytest.mark.asyncio
async def test_quote_shape() -> None:
    q = fp_svc._quote({"type": "U91", "price": "190.1", "name": "X", "state": "VIC",
                       "postcode": "3000", "suburb": "Mel", "lat": "-37.8", "lng": "144.9"})
    assert q["fuel_type"] == "U91"
    assert q["price_cpl"] == 190.1
    assert q["rank"] is None
    assert q["distance_km"] is None


@pytest.mark.asyncio
async def test_fetch_serves_cache_on_upstream_failure() -> None:
    # Prime the cache, then break the network; should serve the cache rather than
    # raise so callers can fall back to manual entry instead of a 500.
    fp_svc._cache["data"] = FIXTURE
    fp_svc._cache["fetched_at"] = fp_svc._now_ts()

    class _BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("network down")

    import app.services.fuel_prices as mod
    with mock.patch.object(mod.httpx, "AsyncClient", _BoomClient):
        out = await fp_svc.fetch_7eleven_prices(force=True)
        assert out is FIXTURE


@pytest.mark.asyncio
async def test_fetch_raises_when_cache_empty_and_upstream_fails() -> None:
    fp_svc._cache["data"] = None
    fp_svc._cache["fetched_at"] = 0.0

    class _BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("network down")

    with mock.patch.object(fp_svc.httpx, "AsyncClient", _BoomClient):
        with pytest.raises(RuntimeError):
            await fp_svc.fetch_7eleven_prices(force=True)


@pytest.mark.asyncio
async def test_station_prices_groups_all_fuel_types(stub_fetch) -> None:
    # "11-Seven Swanston" carries both U91 and E10 in the fixture; search from
    # its own coords so it is the nearest match.
    out = await fp_svc.station_prices(-37.8136, 144.9631, "11-Seven Swanston")
    assert out is not None
    types = {p["fuel_type"] for p in out["prices"]}
    assert types == {"U91", "E10"}
    by_type = {p["fuel_type"]: p["price_cpl"] for p in out["prices"]}
    assert by_type["U91"] == 189.9
    assert by_type["E10"] == 165.3
    assert out["suburb"] == "Melbourne"


@pytest.mark.asyncio
async def test_station_prices_none_when_too_far(stub_fetch) -> None:
    # Searching from Sydney for a Melbourne store with a 1km cap finds nothing.
    out = await fp_svc.station_prices(-33.8688, 151.2093, "11-Seven Swanston", max_km=1.0)
    assert out is None


@pytest.mark.asyncio
async def test_station_prices_none_on_unknown_name(stub_fetch) -> None:
    out = await fp_svc.station_prices(-37.8136, 144.9631, "Nowhere Store")
    assert out is None
