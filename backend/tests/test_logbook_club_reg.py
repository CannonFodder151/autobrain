"""AUT-177 / PR-1: digital logbook is disabled for club-registered vehicles.

Victoria requires the physical VicRoads club log book for club-permit vehicles,
so club_reg vehicles must not be able to create/read/export digital logbook
entries. DELETE stays available so stale entries can be cleaned up.

Requires the compose Postgres (same as the rest of the suite). Run locally with:
    DATABASE_URL=sqlite+aiosqlite:////tmp/autobrain-test.db pytest backend/tests/test_logbook_club_reg.py
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import asyncio  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema() -> None:
    asyncio.run(init_db())


async def _setup(user_email: str, *, club_reg: bool) -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        user = User(
            email=f"{user_email}-{suffix}@example.com",
            display_name="Owner",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        vehicle = Vehicle(user_id=user.id, nickname="Whip", rego="CLB001", club_reg=club_reg)
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        token = create_access_token(user.id)
        vehicle_id = vehicle.id
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return {"client": client, "token": token, "vehicle_id": vehicle_id}


@pytest.mark.asyncio
async def test_club_reg_logbook_is_disabled() -> None:
    world = await _setup("club", club_reg=True)
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    base = f"/api/v1/vehicles/{world['vehicle_id']}/logbook"

    create = await client.post(base, json={"started_at": "2026-08-01T10:00:00Z"}, headers=headers)
    assert create.status_code == 403, create.text

    listed = await client.get(base, headers=headers)
    assert listed.status_code == 403, listed.text

    stats = await client.get(f"{base}/stats", headers=headers)
    assert stats.status_code == 403, stats.text

    export = await client.get(f"{base}/export", headers=headers)
    assert export.status_code == 403, export.text

    await client.aclose()


@pytest.mark.asyncio
async def test_non_club_reg_logbook_unaffected() -> None:
    world = await _setup("normal", club_reg=False)
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    base = f"/api/v1/vehicles/{world['vehicle_id']}/logbook"

    resp = await client.post(
        base, json={"started_at": "2026-08-01T10:00:00Z", "purpose": "work"}, headers=headers
    )
    assert resp.status_code == 201, resp.text

    await client.aclose()


@pytest.mark.asyncio
async def test_toggling_club_reg_on_disables_logbook() -> None:
    world = await _setup("toggle", club_reg=False)
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    base = f"/api/v1/vehicles/{world['vehicle_id']}/logbook"

    resp = await client.post(base, json={"started_at": "2026-08-01T10:00:00Z"}, headers=headers)
    assert resp.status_code == 201, resp.text

    updated = await client.patch(
        f"/api/v1/vehicles/{world['vehicle_id']}",
        json={"club_reg": True},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text

    blocked = await client.post(base, json={"started_at": "2026-08-02T10:00:00Z"}, headers=headers)
    assert blocked.status_code == 403, blocked.text

    await client.aclose()


@pytest.mark.asyncio
async def test_obd_auto_source_flag_round_trips() -> None:
    world = await _setup("autosrc", club_reg=False)
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    base = f"/api/v1/vehicles/{world['vehicle_id']}/logbook"

    created = await client.post(
        base,
        json={
            "started_at": "2026-08-01T09:00:00Z",
            "source": "obd_auto",
            "reason": "Auto-logged (OBD)",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "obd_auto", created.text

    done = await client.patch(
        f"{base}/{created.json()['id']}",
        json={"ended_at": "2026-08-01T09:30:00Z", "status": "completed"},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed", done.text
    assert done.json()["source"] == "obd_auto", done.text

    listed = await client.get(base, headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(e["source"] == "obd_auto" for e in listed.json()), listed.text

    await client.aclose()

@pytest.mark.asyncio
async def test_car_auto_source_with_gps_distance_round_trips() -> None:
    """AUT-367 phone path: car_auto source + GPS odometer diff distance."""
    world = await _setup("carauto", club_reg=False)
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    base = f"/api/v1/vehicles/{world['vehicle_id']}/logbook"

    created = await client.post(
        base,
        json={
            "started_at": "2026-08-01T09:00:00Z",
            "source": "car_auto",
            "reason": "Auto-logged (Car Kit)",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "car_auto", created.text

    done = await client.patch(
        f"{base}/{created.json()['id']}",
        json={
            "ended_at": "2026-08-01T10:00:00Z",
            "status": "completed",
            "distance_km": 42.5,
        },
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed", done.text
    assert done.json()["source"] == "car_auto", done.text
    # Caller-provided GPS distance is authoritative (not recomputed from odo).
    assert done.json()["distance_km"] == 42.5, done.text

    await client.aclose()

