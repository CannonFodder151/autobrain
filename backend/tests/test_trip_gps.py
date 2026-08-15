"""AUT-395: trip GPS — board CSV parser + API storage/return roundtrip.

Covers:
- `parse_board_csv` accepts the board schema `epoch,...,lat,lon` (raw degrees
  x10^7), converts to degrees, drops `0,0` (no-fix) rows, and is deterministic.
- invalid samples are dropped by the schema validator on create/update.
- the detail endpoint returns `gps_samples` while the list stays light.

Runs against a throwaway SQLite DB (no compose Postgres needed):
    DATABASE_URL=sqlite+aiosqlite:////tmp/autobrain-tripgps.db \
        pytest backend/tests/test_trip_gps.py
"""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/autobrain-tripgps.db"
os.environ["SECRET_KEY"] = "test-secret"

import asyncio  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.schemas.logbook import LogEntryCreate  # noqa: E402
from app.services.trip_gps import MAX_GPS_SAMPLES, clean_samples, parse_board_csv  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema() -> None:
    asyncio.run(init_db())


# --- board CSV parser (pure, deterministic) --------------------------------

BOARD_CSV = """\
# autobrain-obd2-diy NEO-8M GPS dump (degrees x10^7, 0,0 = no fix)
1723400000,14.2,3010,3.9,376385000,1451936000
1723400001,14.2,3012,3.9,0,0
1723400002,14.1,3011,3.9,376386500,1451937000
garbage,line,that,is,not,numeric
1723400003,14.1,3009,3.9,376388000,1451940000
"""


def test_parse_board_csv_accepts_board_schema() -> None:
    samples = parse_board_csv(BOARD_CSV)
    assert [s["t"] for s in samples] == [1723400000, 1723400002, 1723400003]
    # x10^7 -> degrees, and the 0,0 "no fix" row is skipped.
    assert samples[0]["lat"] == pytest.approx(37.6385, abs=1e-7)
    assert samples[0]["lon"] == pytest.approx(145.1936, abs=1e-7)
    assert samples[1] == {"t": 1723400002, "lat": 37.63865, "lon": 145.1937}


def test_parse_board_csv_empty_and_junk() -> None:
    assert parse_board_csv("") == []
    assert parse_board_csv("# only comments\n") == []
    # "epoch,lat,lon" is skipped as a header; "1,2,3" is a minimal valid
    # `epoch,lat,lon` row (board schema with zero intermediate columns).
    assert parse_board_csv("epoch,lat,lon\n1,2,3\n") == [{"t": 1, "lat": 2e-07, "lon": 3e-07}]
    assert parse_board_csv("1723400000,0,0\n") == []


def test_clean_samples_drops_invalid_and_dedupes() -> None:
    samples = [
        {"t": 1, "lat": 0.0, "lon": 0.0},  # no fix
        {"t": 2, "lat": -37.6, "lon": 145.1},
        {"t": 3, "lat": -37.6, "lon": 145.1},  # consecutive duplicate
        {"t": 4, "lat": -91.0, "lon": 145.1},  # out of range
        {"t": 5, "lat": -37.6, "lon": 145.2},
    ]
    cleaned = clean_samples(samples)
    assert cleaned is not None
    assert [(s.t, s.lat, s.lon) for s in cleaned] == [
        (2, -37.6, 145.1),
        (5, -37.6, 145.2),
    ]
    assert clean_samples(None) is None


def test_clean_samples_caps_length_at_max() -> None:
    samples = [{"t": i, "lat": -37.6, "lon": 145.1 + (i % 10) * 1e-6} for i in range(MAX_GPS_SAMPLES + 100)]
    cleaned = clean_samples(samples)
    assert cleaned is not None
    assert len(cleaned) == MAX_GPS_SAMPLES
    # keeps the earliest fixes, not the tail
    assert cleaned[0].t == 0
    assert cleaned[-1].t == MAX_GPS_SAMPLES - 1


def test_schema_validator_rejects_bad_samples() -> None:
    entry = LogEntryCreate(
        started_at="2026-08-12T10:00:00Z",
        gps_samples=[
            {"t": 1, "lat": 0, "lon": 0},
            {"t": 2, "lat": -37.6, "lon": 145.1},
        ],
    )
    assert [s.lat for s in entry.gps_samples] == [-37.6]


# --- API roundtrip -----------------------------------------------------------

async def _setup() -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        user = User(
            email=f"gps-{suffix}@example.com",
            display_name="Owner",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        vehicle = Vehicle(user_id=user.id, nickname="Whip", rego="GPS001")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        token = create_access_token(user.id)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return {"client": client, "token": token, "vehicle_id": vehicle.id}


@pytest.mark.asyncio
async def test_gps_samples_store_and_detail_return() -> None:
    world = await _setup()
    headers = {"Authorization": f"Bearer {world['token']}"}
    base = f"/api/v1/vehicles/{world['vehicle_id']}/logbook"
    client: AsyncClient = world["client"]
    samples = [
        {"t": 1723400000, "lat": -37.6385, "lon": 145.1936},
        {"t": 1723400001, "lat": -37.6387, "lon": 145.1940},
    ]

    created = await client.post(
        base,
        json={"started_at": "2026-08-12T10:00:00Z", "gps_samples": samples},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    entry_id = created.json()["id"]
    # list stays light: no gps_samples field
    listed = await client.get(base, headers=headers)
    assert listed.status_code == 200
    assert "gps_samples" not in listed.json()[0]

    detail = await client.get(f"{base}/{entry_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["gps_samples"] == samples

    # patch appends/replaces samples (response is the light list shape)
    updated = await client.patch(
        f"{base}/{entry_id}",
        json={"status": "completed", "gps_samples": samples + [{"t": 1723400002, "lat": -37.639, "lon": 145.195}]},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert "gps_samples" not in updated.json()

    after = await client.get(f"{base}/{entry_id}", headers=headers)
    assert len(after.json()["gps_samples"]) == 3
    assert after.json()["status"] == "completed"

    await client.aclose()
