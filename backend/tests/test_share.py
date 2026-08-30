"""Vehicle sharing tests: invite by email + list shares.

Requires the compose Postgres (same as the rest of the suite).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-0123456789-0123456789")

import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.share import VehicleShare  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402


async def _create_user(db, email: str, display_name: str) -> User:
    user = User(
        email=email,
        display_name=display_name,
        hashed_password=hash_password("hunter22"),
        max_vehicles=3,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_share_vehicle_end_to_end() -> None:
    suffix = uuid.uuid4().hex[:8]
    owner_email = f"owner-{suffix}@example.com"
    invitee_email = f"invitee-{suffix}@example.com"

    async with SessionLocal() as db:
        owner = await _create_user(db, owner_email, "Owner")
        invitee = await _create_user(db, invitee_email, "Invitee Person")
        vehicle = Vehicle(user_id=owner.id, nickname="R34 Skyline")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)

        owner_token = create_access_token(owner.id)
        invitee_token = create_access_token(invitee.id)
        vehicle_id = vehicle.id
        invitee_id = invitee.id

    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {owner_token}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            json={"email": invitee_email},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "pending"
        assert body["invitee_email"] == invitee_email
        assert body["invitee_display_name"] == "Invitee Person"
        assert body["invitee_user_id"] == invitee_id

        listed = await client.get(f"/api/v1/vehicles/{vehicle_id}/shares", headers=headers)
        assert listed.status_code == 200
        assert [s["id"] for s in listed.json()] == [body["id"]]

        dup = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            json={"email": invitee_email},
            headers=headers,
        )
        assert dup.status_code == 409

        unknown = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            json={"email": f"nobody-{suffix}@example.com"},
            headers=headers,
        )
        assert unknown.status_code == 404

        self_share = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            json={"email": owner_email},
            headers=headers,
        )
        assert self_share.status_code == 400

        other_user = await client.get(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            headers={"Authorization": f"Bearer {invitee_token}"},
        )
        assert other_user.status_code == 404


@pytest.mark.asyncio
async def test_delete_vehicle_with_shares() -> None:
    suffix = uuid.uuid4().hex[:8]
    owner_email = f"owner-del-{suffix}@example.com"
    invitee_email = f"invitee-del-{suffix}@example.com"

    async with SessionLocal() as db:
        owner = await _create_user(db, owner_email, "Owner")
        await _create_user(db, invitee_email, "Invitee")
        vehicle = Vehicle(user_id=owner.id, nickname="Shared to delete")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        owner_token = create_access_token(owner.id)
        vehicle_id = vehicle.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {owner_token}"}
        resp = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            json={"email": invitee_email},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        resp = await client.delete(f"/api/v1/vehicles/{vehicle_id}", headers=headers)
        assert resp.status_code == 204, resp.text

    async with SessionLocal() as db:
        remaining = (
            await db.execute(
                select(VehicleShare).where(VehicleShare.vehicle_id == vehicle_id)
            )
        ).scalars().all()
        assert remaining == []


@pytest.mark.asyncio
async def test_delete_user_with_shares() -> None:
    suffix = uuid.uuid4().hex[:8]
    owner_email = f"owner-del-user-{suffix}@example.com"
    invitee_email = f"invitee-del-user-{suffix}@example.com"

    async with SessionLocal() as db:
        owner = await _create_user(db, owner_email, "Owner")
        invitee = await _create_user(db, invitee_email, "Invitee")
        vehicle = Vehicle(user_id=owner.id, nickname="Shared car")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        owner_token = create_access_token(owner.id)
        vehicle_id = vehicle.id
        invitee_id = invitee.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            json={"email": invitee_email},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 201, resp.text

        resp = await client.delete(
            f"/api/v1/admin-api/users/{invitee_id}",
            headers={"X-Admin-API-Key": "test-admin-key-0123456789-0123456789"},
        )
        assert resp.status_code == 204, resp.text

    async with SessionLocal() as db:
        remaining = (
            await db.execute(
                select(VehicleShare).where(VehicleShare.invitee_user_id == invitee_id)
            )
        ).scalars().all()
        assert remaining == []


@pytest.mark.asyncio
async def test_delete_owner_user_with_shares() -> None:
    suffix = uuid.uuid4().hex[:8]
    owner_email = f"owner-del-user-{suffix}@example.com"
    invitee_email = f"invitee-del-user-{suffix}@example.com"

    async with SessionLocal() as db:
        owner = await _create_user(db, owner_email, "Owner")
        await _create_user(db, invitee_email, "Invitee")
        vehicle = Vehicle(user_id=owner.id, nickname="Shared car")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        owner_token = create_access_token(owner.id)
        vehicle_id = vehicle.id
        owner_id = owner.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            json={"email": invitee_email},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 201, resp.text

        resp = await client.delete(
            f"/api/v1/admin-api/users/{owner_id}",
            headers={"X-Admin-API-Key": "test-admin-key-0123456789-0123456789"},
        )
        assert resp.status_code == 204, resp.text

    async with SessionLocal() as db:
        remaining = (
            await db.execute(
                select(VehicleShare).where(VehicleShare.vehicle_id == vehicle_id)
            )
        ).scalars().all()
        assert remaining == []
