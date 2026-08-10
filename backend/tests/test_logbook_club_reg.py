"""AUT-177 / PR-1: digital logbook is disabled for club-registered vehicles.

Victoria requires the physical VicRoads club log book for club-permit vehicles,
so club_reg vehicles must not be able to create/read/export digital logbook
entries. DELETE stays available so stale entries can be cleaned up.

Requires the compose Postgres (same as the rest of the suite). Run locally with:
    DATABASE_URL=sqlite+aiosqlite:////tmp/autobrain-test.db pytest backend/tests/test_logbook_club_reg.py
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://autobrain:autobrain@postgres:5432/autobrain")
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
