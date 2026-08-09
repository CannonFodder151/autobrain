"""AUT-21: shared-vehicle access, list tagging, and owner-based feature gating.

Requires the compose Postgres (same as the rest of the suite). Run locally with:
    DATABASE_URL=sqlite+aiosqlite:////tmp/autobrain-test.db pytest backend/tests/test_share_access.py
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://autobrain:autobrain@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402


async def _create_user(db, email: str, display_name: str, free: bool = False) -> User:
    user = User(
        email=email,
        display_name=display_name,
        hashed_password=hash_password("hunter22"),
        max_vehicles=3,
        free_account=free,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _world() -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        owner = await _create_user(db, f"own-{suffix}@example.com", "Owner Name")
        invitee = await _create_user(db, f"inv-{suffix}@example.com", "Invitee Name", free=True)
        stranger = await _create_user(db, f"str-{suffix}@example.com", "Stranger")
        vehicle = Vehicle(user_id=owner.id, nickname="Shared Whip", rego="TOY123")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        owner_token = create_access_token(owner.id)
        invitee_token = create_access_token(invitee.id)
        stranger_token = create_access_token(stranger.id)
        vehicle_id = vehicle.id
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/shares",
        json={"email": f"inv-{suffix}@example.com"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 201, resp.text
    return {
        "client": client,
        "owner_token": owner_token,
        "invitee_token": invitee_token,
        "stranger_token": stranger_token,
        "vehicle_id": vehicle_id,
        "share_id": resp.json()["id"],
        "invitee_email": f"inv-{suffix}@example.com",
    }


async def _accept(world: dict) -> None:
    resp = await world["client"].post(
        f"/api/v1/vehicle-shares/{world['share_id']}/accept",
        headers={"Authorization": f"Bearer {world['invitee_token']}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_pending_share_is_invite_only() -> None:
    world = await _world()
    c, vid = world["client"], world["vehicle_id"]
    ih = {"Authorization": f"Bearer {world['invitee_token']}"}

    # Pending share shows up as an invite...
    invites = (await c.get("/api/v1/vehicle-shares", headers=ih)).json()
    assert [i["id"] for i in invites] == [world["share_id"]]
    assert invites[0]["status"] == "pending"
    assert invites[0]["vehicle_nickname"] == "Shared Whip"
    assert invites[0]["owner_name"] == "Owner Name"

    # ...but grants no garage or data access until accepted.
    garage = (await c.get("/api/v1/vehicles", headers=ih)).json()
    assert all(r["id"] != vid for r in garage)
    assert (await c.get(f"/api/v1/vehicles/{vid}", headers=ih)).status_code == 404
    await c.aclose()


@pytest.mark.asyncio
async def test_shared_vehicle_appears_in_invitee_list_tagged() -> None:
    world = await _world()
    await _accept(world)
    resp = await world["client"].get(
        "/api/v1/vehicles",
        headers={"Authorization": f"Bearer {world['invitee_token']}"},
    )
    assert resp.status_code == 200
    rows = resp.json()
    shared = [r for r in rows if r["id"] == world["vehicle_id"]]
    assert len(shared) == 1, rows
    assert shared[0]["is_shared"] is True
    assert shared[0]["shared_by"] == "Owner Name"

    own = [r for r in rows if not r["is_shared"]]
    assert all(r["shared_by"] is None for r in own)
    await world["client"].aclose()


@pytest.mark.asyncio
async def test_invitee_can_read_but_not_manage_shared_vehicle() -> None:
    world = await _world()
    await _accept(world)
    c, vid = world["client"], world["vehicle_id"]
    ih = {"Authorization": f"Bearer {world['invitee_token']}"}
    sh = {"Authorization": f"Bearer {world['stranger_token']}"}

    assert (await c.get(f"/api/v1/vehicles/{vid}", headers=ih)).status_code == 200
    assert (await c.get(f"/api/v1/vehicles/{vid}/timeline", headers=ih)).status_code == 200

    # Owner-only: mutate the vehicle or manage shares.
    assert (await c.patch(f"/api/v1/vehicles/{vid}", json={"nickname": "Hijack"}, headers=ih)).status_code == 404
    assert (await c.delete(f"/api/v1/vehicles/{vid}", headers=ih)).status_code == 404
    assert (await c.get(f"/api/v1/vehicles/{vid}/shares", headers=ih)).status_code == 404
    assert (await c.post(
        f"/api/v1/vehicles/{vid}/shares", json={"email": "x@example.com"}, headers=ih
    )).status_code == 404

    # A stranger with no share still gets nothing.
    assert (await c.get(f"/api/v1/vehicles/{vid}", headers=sh)).status_code == 404
    await c.aclose()


@pytest.mark.asyncio
async def test_free_invitee_inherits_owners_rego_entitlement() -> None:
    world = await _world()
    await _accept(world)
    c, vid = world["client"], world["vehicle_id"]
    body = {"rego": "TOY123", "state": "VIC", "vehicle_type": "car"}

    # Free invitee + paid owner -> gate passes (lookup returns heuristic 200).
    resp = await c.post(
        "/api/v1/vehicles/rego-lookup",
        json={**body, "vehicle_id": vid},
        headers={"Authorization": f"Bearer {world['invitee_token']}"},
    )
    assert resp.status_code == 200, resp.text

    # Same free invitee without a vehicle context is still gated.
    resp = await c.post(
        "/api/v1/vehicles/rego-lookup",
        json=body,
        headers={"Authorization": f"Bearer {world['invitee_token']}"},
    )
    assert resp.status_code == 403, resp.text
    await c.aclose()


@pytest.mark.asyncio
async def test_free_owner_blocks_invitee_ai_and_rego() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        free_owner = await _create_user(db, f"fo-{suffix}@example.com", "Free Owner", free=True)
        invitee = await _create_user(db, f"iv-{suffix}@example.com", "Invitee Name")
        vehicle = Vehicle(user_id=free_owner.id, nickname="Free Whip", rego="TOY456")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        invitee_token = create_access_token(invitee.id)
        vehicle_id = vehicle.id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/shares",
            json={"email": f"iv-{suffix}@example.com"},
            headers={"Authorization": f"Bearer {create_access_token(free_owner.id)}"},
        )
        assert resp.status_code == 201, resp.text
        share_id = resp.json()["id"]
        ih = {"Authorization": f"Bearer {invitee_token}"}
        acc = await client.post(f"/api/v1/vehicle-shares/{share_id}/accept", headers=ih)
        assert acc.status_code == 200, acc.text

        resp = await client.post(
            "/api/v1/vehicles/rego-lookup",
            json={"rego": "TOY456", "state": "VIC", "vehicle_type": "car", "vehicle_id": vehicle_id},
            headers=ih,
        )
        assert resp.status_code == 403, resp.text

        resp = await client.post(
            f"/api/v1/vehicles/{vehicle_id}/diagnostics",
            json={"symptoms": "engine knocking on cold start"},
            headers=ih,
        )
        assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_invite_accept_deny_and_remove_flow() -> None:
    world = await _world()
    c, vid = world["client"], world["vehicle_id"]
    ih = {"Authorization": f"Bearer {world['invitee_token']}"}
    oh = {"Authorization": f"Bearer {world['owner_token']}"}
    sh = {"Authorization": f"Bearer {world['stranger_token']}"}
    share_id = world["share_id"]

    # Stranger cannot act on the invite.
    assert (await c.post(
        f"/api/v1/vehicle-shares/{share_id}/accept", headers=sh
    )).status_code == 404
    assert (await c.post(
        f"/api/v1/vehicle-shares/{share_id}/deny", headers=sh
    )).status_code == 404
    assert (await c.delete(
        f"/api/v1/vehicle-shares/{share_id}", headers=sh
    )).status_code == 404

    # Deny removes the share entirely.
    assert (await c.post(
        f"/api/v1/vehicle-shares/{share_id}/deny", headers=ih
    )).status_code == 204
    assert (await c.get("/api/v1/vehicle-shares", headers=ih)).json() == []
    assert (await c.get(f"/api/v1/vehicles/{vid}/shares", headers=oh)).json() == []

    # Re-share, then accept.
    share2 = (await c.post(
        f"/api/v1/vehicles/{vid}/shares",
        json={"email": world["invitee_email"]},
        headers=oh,
    )).json()
    assert share2["status"] == "pending"
    acc = await c.post(
        f"/api/v1/vehicle-shares/{share2['id']}/accept", headers=ih
    )
    assert acc.status_code == 200
    assert acc.json()["status"] == "accepted"
    assert (await c.post(
        f"/api/v1/vehicle-shares/{share2['id']}/accept", headers=ih
    )).status_code == 409

    # Owner sees accepted status.
    assert (await c.get(f"/api/v1/vehicles/{vid}/shares", headers=oh)).json()[0]["status"] == "accepted"

    # Invitee can remove the shared car from their garage.
    assert (await c.delete(
        f"/api/v1/vehicle-shares/{share2['id']}", headers=ih
    )).status_code == 204
    assert (await c.get("/api/v1/vehicles", headers=ih)).json() == []

    # Owner can also revoke access.
    share3 = (await c.post(
        f"/api/v1/vehicles/{vid}/shares",
        json={"email": world["invitee_email"]},
        headers=oh,
    )).json()
    assert (await c.delete(
        f"/api/v1/vehicle-shares/{share3['id']}", headers=oh
    )).status_code == 204
    await c.aclose()
