"""AUT-134: /search results are scoped to the requesting user (IDOR fix).

Requires the compose Postgres (same as the rest of the suite). Run locally with:
    DATABASE_URL=sqlite+aiosqlite:////tmp/autobrain-test.db pytest backend/tests/test_search_scope.py
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://autobrain:autobrain@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")

import uuid  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.diagnostic import Diagnostic  # noqa: E402
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


async def _seed_diagnostic(db, vehicle_id: str, symptoms: str, summary: str) -> None:
    db.add(
        Diagnostic(
            vehicle_id=vehicle_id,
            symptoms=symptoms,
            ai_response=json.dumps({"summary": summary}),
            summary=summary,
            severity="medium",
        )
    )
    await db.commit()


async def _world() -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        owner = await _create_user(db, f"own-{suffix}@example.com", "Owner")
        invitee = await _create_user(db, f"inv-{suffix}@example.com", "Invitee")
        stranger = await _create_user(db, f"str-{suffix}@example.com", "Stranger")
        owned = Vehicle(user_id=owner.id, nickname="Owner Whip")
        shared = Vehicle(user_id=owner.id, nickname="Shared Whip")
        db.add_all([owned, shared])
        await db.commit()
        await db.refresh(owned)
        await db.refresh(shared)
        await _seed_diagnostic(
            db, owned.id, "blinking check engine light misfire cylinder two", "Misfire detected"
        )
        await _seed_diagnostic(
            db, shared.id, "clunking noise over speed bumps rear axle", "Rear suspension noise"
        )
        owner_token = create_access_token(owner.id)
        invitee_token = create_access_token(invitee.id)
        stranger_token = create_access_token(stranger.id)
        invitee_email = f"inv-{suffix}@example.com"
        owned_id, shared_id = owned.id, shared.id
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    share = (
        await client.post(
            f"/api/v1/vehicles/{shared_id}/shares",
            json={"email": invitee_email},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
    ).json()
    acc = await client.post(
        f"/api/v1/vehicle-shares/{share['id']}/accept",
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    assert acc.status_code == 200, acc.text
    return {
        "client": client,
        "owner_token": owner_token,
        "invitee_token": invitee_token,
        "stranger_token": stranger_token,
        "owned_id": owned_id,
        "shared_id": shared_id,
    }


def _h(headers: dict) -> dict:
    return {"Authorization": f"Bearer {headers}"}


@pytest.mark.asyncio
async def test_stranger_and_invitee_do_not_see_owners_private_data() -> None:
    w = await _world()
    c = w["client"]
    q = "misfire"

    stranger = await c.get("/api/v1/search", params={"q": q}, headers=_h(w["stranger_token"]))
    assert stranger.status_code == 200
    assert stranger.json() == [], stranger.text

    invitee = await c.get("/api/v1/search", params={"q": q}, headers=_h(w["invitee_token"]))
    assert invitee.status_code == 200
    assert invitee.json() == [], invitee.text

    owner = await c.get("/api/v1/search", params={"q": q}, headers=_h(w["owner_token"]))
    assert owner.status_code == 200
    assert [r["vehicle_id"] for r in owner.json()] == [w["owned_id"]], owner.text
    await c.aclose()


@pytest.mark.asyncio
async def test_invitee_can_search_shared_vehicle() -> None:
    w = await _world()
    c = w["client"]

    resp = await c.get(
        "/api/v1/search",
        params={"q": "clunking"},
        headers=_h(w["invitee_token"]),
    )
    assert resp.status_code == 200
    assert [r["vehicle_id"] for r in resp.json()] == [w["shared_id"]]
    await c.aclose()


@pytest.mark.asyncio
async def test_vehicle_id_param_requires_access_and_rejects_unknown_types() -> None:
    w = await _world()
    c = w["client"]

    # Stranger querying the owner's vehicle by id -> 404.
    resp = await c.get(
        "/api/v1/search",
        params={"q": "misfire", "vehicle_id": w["owned_id"]},
        headers=_h(w["stranger_token"]),
    )
    assert resp.status_code == 404, resp.text

    # Invitee can scope to the shared vehicle.
    resp = await c.get(
        "/api/v1/search",
        params={"q": "clunking", "vehicle_id": w["shared_id"]},
        headers=_h(w["invitee_token"]),
    )
    assert resp.status_code == 200
    assert [r["vehicle_id"] for r in resp.json()] == [w["shared_id"]]

    # Unknown entity type -> 400, not 500.
    resp = await c.get(
        "/api/v1/search",
        params={"q": "x", "entity_types": "bogus"},
        headers=_h(w["owner_token"]),
    )
    assert resp.status_code == 400, resp.text
    await c.aclose()
