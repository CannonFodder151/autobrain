"""Tests for the 7-Eleven fuel-price service (deterministic, no AI, no network).

We stub the network fetch and exercise pure parse/geo logic against a small
fixture that mirrors the projectzerothree.info schema (regions with rank
suffixes + per-store lat/lng).
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SEVEN_ELEVEN_API_URL"] = "https://example.test/api.php?format=json"

import base64  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from unittest import mock  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.core.config import settings  # noqa: E402
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

SAMPLE_NSW_PAYLOAD = {
    "lastUpdated": "2026-08-29T01:00:00Z",
    "stations": [
        {"code": "NSW001", "name": "Shell Sydney", "brand": "Shell", "address": "1 Main St",
         "location": {"latitude": -33.86, "longitude": 151.2}},
        {"code": "NSW002", "name": "BP Alexandria", "brand": "BP", "address": "2 Oyster St",
         "location": {"latitude": -33.93, "longitude": 151.2}},
    ],
    "prices": [
        {"stationcode": "NSW001", "fueltype": "E10", "price": 168.9, "lastupdated": "2026-08-29T01:00:00Z"},
        {"stationcode": "NSW001", "fueltype": "P98", "price": 189.5, "lastupdated": "2026-08-29T01:00:00Z"},
        {"stationcode": "NSW002", "fueltype": "E10", "price": 170.2, "lastupdated": "2026-08-29T01:00:00Z"},
        {"stationcode": "NOPE", "fueltype": "E10", "price": 1.0, "lastupdated": "2026-08-29T01:00:00Z"},
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


def test_normalise_nsw_joins_prices_to_stations_and_skips_unknown():
    rows = fp_svc._normalise_nsw(SAMPLE_NSW_PAYLOAD)
    codes = {(r["station_code"], r["fuel_type"]) for r in rows}
    assert codes == {("NSW001", "E10"), ("NSW001", "P98"), ("NSW002", "E10")}
    e10 = next(r for r in rows if r["station_code"] == "NSW001" and r["fuel_type"] == "E10")
    assert e10["price"] == 168.9
    assert e10["station_name"] == "Shell Sydney"
    assert e10["brand"] == "Shell"
    assert e10["latitude"] == -33.86
    assert e10["currency"] == "AUD"


def test_normalise_nsw_empty_payload():
    assert fp_svc._normalise_nsw({}) == []


def test_basic_auth_header_builds_from_key_secret(monkeypatch):
    monkeypatch.setattr(settings, "FUEL_NSW_API_KEY", "BqKey")
    monkeypatch.setattr(settings, "FUEL_NSW_API_SECRET", "SecRet")
    hdr = fp_svc._basic_auth_header()
    scheme, cred = hdr.split(" ", 1)
    assert scheme == "Basic"
    decoded = base64.b64decode(cred).decode()
    assert decoded == "BqKey:SecRet"


def test_enabled_only_when_configured_and_on(monkeypatch):
    monkeypatch.setattr(settings, "FUEL_NSW_ENABLED", True)
    monkeypatch.setattr(settings, "FUEL_NSW_API_KEY", "k")
    monkeypatch.setattr(settings, "FUEL_NSW_API_SECRET", "s")
    assert fp_svc.enabled() is True
    monkeypatch.setattr(settings, "FUEL_NSW_ENABLED", False)
    assert fp_svc.enabled() is False


def test_poll_due_gate_enforces_once_per_day():
    now = datetime.now(timezone.utc)
    # no prior poll -> due
    assert fp_svc.poll_due(None, hours=24) is True
    # within 24h -> not due
    assert fp_svc.poll_due(now - timedelta(hours=23), hours=24) is False
    # exactly 24h+ -> due
    assert fp_svc.poll_due(now - timedelta(hours=24, minutes=1), hours=24) is True