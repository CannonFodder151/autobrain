"""Service deletion tests: DELETE restores parts stock and removes timeline event.

Requires the compose Postgres (same as the rest of the suite).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.part import Part, PartMovement  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle, VehicleEvent  # noqa: E402


@pytest.mark.asyncio
async def test_delete_service_restores_stock_and_event() -> None:
    suffix = uuid.uuid4().hex[:8]
    email = f"owner-{suffix}@example.com"

    async with SessionLocal() as db:
        owner = User(
            email=email,
            display_name="Owner",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
        )
        db.add(owner)
        await db.commit()
        await db.refresh(owner)

        vehicle = Vehicle(user_id=owner.id, nickname="R34 Skyline")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)

        part = Part(vehicle_id=vehicle.id, name="Oil filter", quantity=5)
        db.add(part)
        await db.commit()
        await db.refresh(part)

        token = create_access_token(owner.id)
        vehicle_id = vehicle.id
        part_id = part.id

    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/services",
            json={
                "service_date": "2026-01-10",
                "odometer_km": 12000,
                "service_type": "scheduled",
                "cost": 80.0,
                "status": "completed",
                "items": [{"part_id": part_id, "name": "Oil filter", "quantity": 2}],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        service_id = created.json()["id"]

    async with SessionLocal() as db:
        part_now = await db.get(Part, part_id)
        assert part_now.quantity == 3
        assert (await db.scalar(
            select(PartMovement).where(PartMovement.service_id == service_id)
        )) is not None
        event = await db.scalar(
            select(VehicleEvent).where(VehicleEvent.source_id == service_id)
        )
        assert event is not None

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        deleted = await client.delete(
            f"/api/v1/vehicles/{vehicle_id}/services/{service_id}", headers=headers
        )
        assert deleted.status_code == 204, deleted.text

        gone = await client.get(
            f"/api/v1/vehicles/{vehicle_id}/services/{service_id}", headers=headers
        )
        assert gone.status_code == 404

        listed = await client.get(
            f"/api/v1/vehicles/{vehicle_id}/services", headers=headers
        )
        assert listed.json() == []

    async with SessionLocal() as db:
        part_now = await db.get(Part, part_id)
        assert part_now.quantity == 5
        assert (await db.scalar(
            select(PartMovement).where(PartMovement.service_id == service_id)
        )) is None
        event = await db.scalar(
            select(VehicleEvent).where(VehicleEvent.source_id == service_id)
        )
        assert event is None


@pytest.mark.asyncio
async def test_delete_service_not_found() -> None:
    suffix = uuid.uuid4().hex[:8]
    email = f"owner-{suffix}@example.com"

    async with SessionLocal() as db:
        owner = User(
            email=email,
            display_name="Owner",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
        )
        db.add(owner)
        await db.commit()
        await db.refresh(owner)
        vehicle = Vehicle(user_id=owner.id, nickname="R34 Skyline")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        token = create_access_token(owner.id)
        vehicle_id = vehicle.id

    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(
            f"/api/v1/vehicles/{vehicle_id}/services/{uuid.uuid4()}", headers=headers
        )
        assert resp.status_code == 404
