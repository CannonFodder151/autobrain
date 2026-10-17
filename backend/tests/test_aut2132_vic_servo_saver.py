"""AUT-2132 — VIC Servo Saver polling consumer tests.

Tests the three skip cases from AUT-2132:
  a) FUEL_VIC_ENABLED=true + key present -> polls and parses
  b) FUEL_VIC_ENABLED=true + key absent  -> skipped silently
  c) FUEL_VIC_ENABLED=false              -> skipped silently
"""

import os
from unittest import mock

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"


VIC_SAMPLE_RESP = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "stationid": "VIC001",
                "brand": "Ampol",
                "name": "Ampol Melbourne",
                "address": "1 Collins St",
                "fueltype": "E10",
                "price_cpl": 17890,
                "lastupdated": "2026-08-29T01:00:00Z",
            },
            "geometry": {"type": "Point", "coordinates": [144.9631, -37.8136]},
        },
    ],
}


def _run_coro(coro):
    """Run a coroutine to completion in a fresh event loop (DB-free tests)."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_vic_parse_maps_station_and_price():
    """_parse_vic maps the Servo Saver GeoJSON into canonical station + price rows."""
    from app.services.fuel_feeds import _parse_vic

    stations, prices = _parse_vic(VIC_SAMPLE_RESP)
    assert len(stations) == 1
    s = stations[0]
    assert s["source"] == "vic"
    assert s["source_id"] == "VIC001"
    assert s["brand"] == "Ampol"
    assert s["lat"] == -37.8136
    assert len(prices) == 1
    fuel_type, price, ts = prices["VIC001"][0]
    assert fuel_type == "E10"
    assert price == 178.9  # cents → dollars
    assert ts is not None


def test_ingest_vic_fuel_saver_skips_when_disabled(monkeypatch):
    """c) FUEL_VIC_ENABLED=false -> skipped silently (no network, no DB)."""
    from app.core.config import settings
    from app.services.fuel_feeds import ingest_vic_fuel_saver

    monkeypatch.setattr(settings, "FUEL_VIC_ENABLED", False)
    monkeypatch.setattr(settings, "FUEL_VIC_API_KEY", "key")
    result = _run_coro(ingest_vic_fuel_saver(_FakeDB()))
    assert result["skipped"] == "disabled"
    assert result["stations"] == 0


def test_ingest_vic_fuel_saver_skips_when_key_absent(monkeypatch):
    """b) FUEL_VIC_ENABLED=true + key absent -> skipped silently (no network, no DB)."""
    from app.core.config import settings
    from app.services.fuel_feeds import ingest_vic_fuel_saver

    monkeypatch.setattr(settings, "FUEL_VIC_ENABLED", True)
    monkeypatch.setattr(settings, "FUEL_VIC_API_KEY", "")
    result = _run_coro(ingest_vic_fuel_saver(_FakeDB()))
    assert result["skipped"] == "no_api_key"
    assert result["stations"] == 0


def test_ingest_vic_fuel_saver_polls_and_parses_when_enabled(monkeypatch):
    """a) FUEL_VIC_ENABLED=true + key present -> polls and parses."""
    from app.core.config import settings
    from app.services.fuel_feeds import ingest_vic_fuel_saver

    monkeypatch.setattr(settings, "FUEL_VIC_ENABLED", True)
    monkeypatch.setattr(settings, "FUEL_VIC_API_KEY", "partner-key")
    # Mock _fetch_json to return sample data (no real network call).
    async def _fake_fetch(url, *, headers=None, params=None, client=None):
        assert headers["Authorization"] == "Bearer partner-key"
        return VIC_SAMPLE_RESP

    with mock.patch("app.services.fuel_feeds._fetch_json", side_effect=_fake_fetch), \
         mock.patch("app.services.fuel_feeds._ingest", _async_return(
             {"source": "vic", "stations": 1, "prices": 1}
         )) as ingest_mock:
        result = _run_coro(ingest_vic_fuel_saver(_FakeDB()))
        assert result["stations"] == 1
        assert result["prices"] == 1
        assert "skipped" not in result
        assert ingest_mock.called


def test_poll_vic_skips_when_disabled(monkeypatch):
    """poll_vic_fuel_prices silently skips when FUEL_VIC_ENABLED=False."""
    from app.workers import tasks
    from app.core.config import settings

    monkeypatch.setattr(settings, "FUEL_VIC_ENABLED", False)
    monkeypatch.setattr(settings, "FUEL_VIC_API_KEY", "key")

    # SessionLocal should not be opened when VIC is disabled.
    with mock.patch.object(tasks, "SessionLocal") as sl_mock:
        tasks.poll_vic_fuel_prices()
        assert not sl_mock.called


def test_poll_vic_skips_when_key_absent(monkeypatch):
    """poll_vic_fuel_prices silently skips when FUEL_VIC_API_KEY=' '."""
    from app.workers import tasks
    from app.core.config import settings

    monkeypatch.setattr(settings, "FUEL_VIC_ENABLED", True)
    monkeypatch.setattr(settings, "FUEL_VIC_API_KEY", "")

    with mock.patch.object(tasks, "SessionLocal") as sl_mock, \
         mock.patch.object(tasks, "fuel_svc") as fs_mock:
        fs_mock.should_poll = _async_return(False)
        fs_mock.mark_polled = _async_return(None)
        with mock.patch("app.services.fuel_feeds.ingest_vic_fuel_saver") as ing:
            tasks.poll_vic_fuel_prices()
            assert not sl_mock.called
            assert not ing.called


def _async_return(value):
    async def _f(*a, **kw):
        return value
    return _f


class _FakeDB:
    """Minimal stand-in so the import path resolves; skip paths never reach it."""
    pass
