"""AUT-361: manual VIN update over OBD.

POST /vehicles/{id}/obd/vin saves the VIN on explicit user action and may
replace an existing VIN (the app only sends it from the manual "Update VIN"
button or manual entry). Requires the compose Postgres (same as the rest of
the suite).
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

VIN_A = "1HGCM82633A004352"
VIN_B = "JH2PC50A0MK000000"


async def _setup(*, obd_enabled: bool = True) -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        user = User(
            email=f"obd-vin-{suffix}@example.com",
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
async def test_set_vin_saves_and_overwrites() -> None:
    await init_db()
    world = await _setup()
    headers = {"Authorization": f"Bearer {world['token']}"}
    url = f"/api/v1/vehicles/{world['vehicle_id']}/obd/vin"

    async with world["client"] as client:
        first = await client.post(url, json={"vin": VIN_A}, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["vin"] == VIN_A

        # Manual "Update VIN" replaces an existing VIN rather than 409ing.
        second = await client.post(url, json={"vin": VIN_B}, headers=headers)
        assert second.status_code == 200, second.text
        assert second.json()["vin"] == VIN_B


@pytest.mark.asyncio
async def test_set_vin_requires_obd_enabled() -> None:
    await init_db()
    world = await _setup(obd_enabled=False)
    headers = {"Authorization": f"Bearer {world['token']}"}
    url = f"/api/v1/vehicles/{world['vehicle_id']}/obd/vin"

    async with world["client"] as client:
        resp = await client.post(url, json={"vin": VIN_A}, headers=headers)
        assert resp.status_code == 403
