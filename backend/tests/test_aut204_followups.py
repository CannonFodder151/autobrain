"""Tests for AUT-204 follow-up fixes.

Covers the pure-logic pieces of the AUT-171 re-review findings so they run
without a live Postgres: search hardening (entity-type validation + ILIKE
escaping), shared FY helpers, and the batched odometer backfill rule.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.api.v1.search import search as search_endpoint  # noqa: E402
from app.services.dates import current_fy, fy_bounds  # noqa: E402
from app.services.odometer import sync_odometer_from_fuel  # noqa: E402
from app.services.search import _escape_like, validate_entity_types  # noqa: E402


def test_escape_like_escapes_wildcards() -> None:
    assert _escape_like("50%_off\\x") == "50\\%\\_off\\\\x"
    assert _escape_like("plain") == "plain"
    assert _escape_like("%") == "\\%"


def test_validate_entity_types() -> None:
    validate_entity_types(["diagnostic", "service", "modification", "receipt"])
    validate_entity_types([])
    with pytest.raises(ValueError) as exc:
        validate_entity_types(["diagnostic", "bogus"])
    assert "bogus" in str(exc.value)


@pytest.mark.asyncio
async def test_search_endpoint_rejects_unknown_types() -> None:
    with pytest.raises(HTTPException) as exc:
        await search_endpoint(
            q="oil",
            entity_types="service,bogus",
            limit=10,
            db=None,  # type: ignore[arg-type]  # validation runs before db use
            user=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 400


def test_fy_helpers() -> None:
    assert fy_bounds(2026) == (
        datetime(2025, 7, 1, tzinfo=timezone.utc),
        datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
    )
    assert isinstance(current_fy(), int)


class _Result:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Scripted AsyncSession: returns fuel/trip rows based on the statement."""

    def __init__(self, fuel_rows, trip_rows) -> None:
        self.fuel_rows = fuel_rows
        self.trip_rows = trip_rows

    async def execute(self, stmt):
        text = str(stmt)
        if "logbook_entries" in text:
            return _Result(self.trip_rows)
        return _Result(self.fuel_rows)


class _V:
    def __init__(self, vid, odo) -> None:
        self.id = vid
        self.odometer_km = odo


@pytest.mark.asyncio
async def test_sync_odometer_from_fuel_batches_and_obeys_rule() -> None:
    # v1: no fuel, no trip -> stays None. v2: fuel max 88000 (two entries),
    # no trip -> 88000. v3: fuel 50000 + completed trip 61000 -> trip governs.
    db = _FakeDB(
        fuel_rows=[("v2", 88000), ("v3", 50000)],
        trip_rows=[("v3", 61000)],
    )
    vehicles = [_V("v1", None), _V("v2", None), _V("v3", None), _V("v4", 120000)]
    await sync_odometer_from_fuel(db, vehicles)  # type: ignore[arg-type]

    assert vehicles[0].odometer_km is None  # no data
    assert vehicles[1].odometer_km == 88000  # max fuel odometer
    assert vehicles[2].odometer_km == 61000  # completed trip governs
    assert vehicles[3].odometer_km == 120000  # existing value untouched
