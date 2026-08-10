"""Scheduled service timeline tests: a service edited to future/scheduled drops
off the timeline until it is completed again (AUT-18).

Requires the compose Postgres (same as the rest of the suite).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402


async def _setup(suffix: str) -> tuple[str, str]:
    async with SessionLocal() as db:
        owner = User(
            email=f"owner-{suffix}@example.com",
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
        return create_access_token(owner.id), vehicle.id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_edit_to_scheduled_drops_service_from_timeline_until_completed() -> None:
    token, vehicle_id = await _setup(uuid.uuid4().hex[:8])
    transport = ASGITransport(app=app)
    headers = _headers(token)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/services",
            json={
                "service_date": "2026-01-10",
                "odometer_km": 12000,
                "service_type": "scheduled",
                "cost": 80.0,
                "status": "completed",
                "items": [],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        service_id = created.json()["id"]

        timeline = await client.get(
            f"/api/v1/vehicles/{vehicle_id}/timeline", headers=headers
        )
        assert timeline.status_code == 200, timeline.text
        assert [e["source_id"] for e in timeline.json()] == [service_id]

        edited = await client.patch(
            f"/api/v1/vehicles/{vehicle_id}/services/{service_id}",
            json={"status": "scheduled", "service_date": "2026-12-01"},
            headers=headers,
        )
        assert edited.status_code == 200, edited.text

        timeline = await client.get(
            f"/api/v1/vehicles/{vehicle_id}/timeline", headers=headers
        )
        assert timeline.status_code == 200, timeline.text
        assert timeline.json() == []

        recompleted = await client.patch(
            f"/api/v1/vehicles/{vehicle_id}/services/{service_id}",
            json={"status": "completed", "service_date": "2026-01-10"},
            headers=headers,
        )
        assert recompleted.status_code == 200, recompleted.text

        timeline = await client.get(
            f"/api/v1/vehicles/{vehicle_id}/timeline", headers=headers
        )
        assert timeline.status_code == 200, timeline.text
        assert [e["source_id"] for e in timeline.json()] == [service_id]
