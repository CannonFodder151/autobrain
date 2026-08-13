"""AUT-360: bulk clear of saved OBD fault codes.

DELETE /vehicles/{id}/obd/codes wipes every saved code for the vehicle while
the per-code DELETE /codes/{id} keeps working. Requires the compose Postgres
(same as the rest of the suite).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402

async def _setup(*, obd_enabled: bool = True) -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        user = User(
            email=f"obd-clear-{suffix}@example.com",
            display_name="Owner",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
            obd_enabled=obd_enabled,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        vehicle = Vehicle(user_id=user.id, nickname="Whip")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        token = create_access_token(user.id)
        vehicle_id = vehicle.id
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return {"client": client, "token": token, "vehicle_id": vehicle_id}

@pytest.mark.asyncio
async def test_bulk_clear_removes_all_codes() -> None:
    await init_db()
    world = await _setup()
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    base = f"/api/v1/vehicles/{world['vehicle_id']}/obd"

    for code in ("P0301", "P0302", "P0171"):
        r = await client.post(f"{base}/codes", json={"code": code}, headers=headers)
        assert r.status_code == 201, r.text

    listed = await client.get(f"{base}/codes", headers=headers)
    assert len(listed.json()) == 3

    cleared = await client.delete(f"{base}/codes", headers=headers)
    assert cleared.status_code == 204, cleared.text

    listed = await client.get(f"{base}/codes", headers=headers)
    assert listed.json() == []

    await client.aclose()

@pytest.mark.asyncio
async def test_per_code_delete_still_works() -> None:
    await init_db()
    world = await _setup()
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    base = f"/api/v1/vehicles/{world['vehicle_id']}/obd"

    created = await client.post(f"{base}/codes", json={"code": "P0301"}, headers=headers)
    assert created.status_code == 201, created.text
    code_id = created.json()["id"]

    r = await client.delete(f"{base}/codes/{code_id}", headers=headers)
    assert r.status_code == 204, r.text

    listed = await client.get(f"{base}/codes", headers=headers)
    assert listed.json() == []

    await client.aclose()

@pytest.mark.asyncio
async def test_bulk_clear_requires_obd_access() -> None:
    await init_db()
    world = await _setup(obd_enabled=False)
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    base = f"/api/v1/vehicles/{world['vehicle_id']}/obd"

    r = await client.delete(f"{base}/codes", headers=headers)
    assert r.status_code == 403, r.text

    await client.aclose()
