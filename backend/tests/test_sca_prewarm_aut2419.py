"""AUT-2419: nightly SCA parts cache prewarm task."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.workers import tasks


@pytest.mark.asyncio
async def test_refresh_sca_parts_cache_logs_summary(monkeypatch):
    sigs = [
        {"make": "Toyota", "model": "Corolla", "year": 2018, "vehicle_count": 3},
        {"make": "Ford", "model": "Ranger", "year": 2020, "vehicle_count": 1},
    ]
    lookup = AsyncMock(return_value={"parts": [], "vehicle": {}, "source": "sca+9router", "model": "rule-based"})

    async def _run(coro):
        return await coro

    def _make_sessionlocal():
        class _CM:
            async def __aenter__(self):
                return None
            async def __aexit__(self, *exc):
                return False
        class _SL:
            def __call__(self):
                return _CM()
        return _SL()

    monkeypatch.setattr(tasks, "_run", _run)
    monkeypatch.setattr(tasks, "SessionLocal", _make_sessionlocal())
    monkeypatch.setattr("app.services.parts_guide.list_vehicle_signatures",
                        AsyncMock(return_value=sigs))
    monkeypatch.setattr("app.services.parts_guide.lookup_sca_parts", lookup)

    result = await tasks.refresh_sca_parts_cache.run()

    assert result["vehicles"] == 2
    assert result["ok"] == 2
    assert result["failed"] == 0
    assert lookup.await_count == 2


@pytest.mark.asyncio
async def test_refresh_sca_parts_cache_empty_fleet(monkeypatch):
    async def _run(coro):
        return await coro

    def _make_sessionlocal():
        class _CM:
            async def __aenter__(self):
                return None
            async def __aexit__(self, *exc):
                return False
        class _SL:
            def __call__(self):
                return _CM()
        return _SL()

    monkeypatch.setattr(tasks, "_run", _run)
    monkeypatch.setattr(tasks, "SessionLocal", _make_sessionlocal())
    monkeypatch.setattr("app.services.parts_guide.list_vehicle_signatures",
                        AsyncMock(return_value=[]))

    result = await tasks.refresh_sca_parts_cache.run()

    assert result == {"vehicles": 0, "ok": 0, "failed": 0, "duration_s": 0.0}


def test_beat_schedule_has_midnight_prewarm():
    from app.workers.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("refresh-sca-parts-cache")
    assert entry is not None
    assert entry["task"] == "app.workers.tasks.refresh_sca_parts_cache"
