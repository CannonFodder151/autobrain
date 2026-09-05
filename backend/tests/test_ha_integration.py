"""Home Assistant integration tests (AUT-2541).

Requires the compose Postgres (same as the rest of the suite). Run locally with:
    DATABASE_URL=postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain pytest backend/tests/test_ha_integration.py

Covers:
  - token lifecycle (create / list / revoke)
  - raw key never exposed past creation (list never returns it)
  - HA-polled endpoints reject unknown / missing tokens (401)
  - HA-polled endpoints enforce vehicle ownership
  - analytics summary + service-reminders payload shape
  - single-vehicle-scoped token
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402
from datetime import date, timedelta  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.ha import HaIntegration  # noqa: E402
from app.models.service import ServiceRecord  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.ha_keys import PREFIX  # noqa: E402


async def _create_user(db, email: str, name: str) -> User:
    user = User(
        email=email,
        display_name=name,
        hashed_password=hash_password("hunter22"),
        max_vehicles=3,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _world() -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        owner = await _create_user(db, f"haown-{suffix}@example.com", "HA Owner")
        stranger = await _create_user(db, f"hastr-{suffix}@example.com", "Stranger")
        vehicle = Vehicle(user_id=owner.id, nickname="HA Car", rego="HAT123", odometer_km=10000)
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        completed = ServiceRecord(
            vehicle_id=vehicle.id,
            service_date=date.today() - timedelta(days=30),
            odometer_km=9500,
            service_type="scheduled",
            cost=120.0,
            status="completed",
            next_due_km=12000,
            next_due_date=date.today() + timedelta(days=60),
        )
        db.add(completed)
        await db.commit()
        await db.refresh(completed)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return {
        "client": client,
        "owner_token": create_access_token(owner.id),
        "stranger_token": create_access_token(stranger.id),
        "vehicle_id": vehicle.id,
        "vehicle_nickname": vehicle.nickname,
        "rego": vehicle.rego,
    }


@pytest.mark.asyncio
async def test_token_create_list_revoke() -> None:
    w = await _world()
    c, auth = w["client"], {"Authorization": f"Bearer {w['owner_token']}"}
    try:
        created = await c.post("/api/v1/ha/tokens", json={}, headers=auth)
        assert created.status_code == 201, created.text
        body = created.json()
        assert "api_key" in body
        assert body["api_key"].startswith(PREFIX)
        assert body["vehicle_id"] is None

        listed = await c.get("/api/v1/ha/tokens", headers=auth)
        assert listed.status_code == 200
        tokens = listed.json()
        assert len(tokens) == 1
        # raw key never leaks after creation
        assert "api_key" not in tokens[0]
        assert tokens[0]["token_prefix"] == body["token_prefix"]

        rev = await c.delete(f"/api/v1/ha/tokens/{body['id']}", headers=auth)
        assert rev.status_code == 204
        listed2 = await c.get("/api/v1/ha/tokens", headers=auth)
        assert listed2.status_code == 200
        assert listed2.json() == []
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_ha_polled_vehicles() -> None:
    w = await _world()
    c, auth = w["client"], {"Authorization": f"Bearer {w['owner_token']}"}
    try:
        raw = (await c.post("/api/v1/ha/tokens", json={}, headers=auth)).json()["api_key"]
        resp = await c.get("/api/v1/ha/vehicles", headers={"X-HA-API-Key": raw})
        assert resp.status_code == 200, resp.text
        vehicles = resp.json()
        assert len(vehicles) == 1
        assert vehicles[0]["nickname"] == w["vehicle_nickname"]
        assert vehicles[0]["rego"] == w["rego"]
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_ha_polled_service_intervals() -> None:
    w = await _world()
    c, auth = w["client"], {"Authorization": f"Bearer {w['owner_token']}"}
    try:
        raw = (await c.post("/api/v1/ha/tokens", json={}, headers=auth)).json()["api_key"]
        resp = await c.get(
            f"/api/v1/ha/vehicles/{w['vehicle_id']}/service-intervals",
            headers={"X-HA-API-Key": raw},
        )
        assert resp.status_code == 200, resp.text
        intervals = resp.json()
        assert len(intervals) == 1
        assert intervals[0]["next_due_km"] == 12000
        assert intervals[0]["vehicle_nickname"] == w["vehicle_nickname"]
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_ha_polled_analytics() -> None:
    w = await _world()
    c, auth = w["client"], {"Authorization": f"Bearer {w['owner_token']}"}
    try:
        raw = (await c.post("/api/v1/ha/tokens", json={}, headers=auth)).json()["api_key"]
        resp = await c.get(
            f"/api/v1/ha/vehicles/{w['vehicle_id']}/analytics",
            headers={"X-HA-API-Key": raw},
        )
        assert resp.status_code == 200, resp.text
        a = resp.json()
        assert a["vehicle_nickname"] == w["vehicle_nickname"]
        assert a["service_total"] == 120.0
        assert isinstance(a["total_km_tracked"], (int, float))
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_ha_polled_service_reminders() -> None:
    w = await _world()
    c, auth = w["client"], {"Authorization": f"Bearer {w['owner_token']}"}
    try:
        raw = (await c.post("/api/v1/ha/tokens", json={}, headers=auth)).json()["api_key"]
        resp = await c.get(
            "/api/v1/ha/service-reminders",
            headers={"X-HA-API-Key": raw},
        )
        assert resp.status_code == 200, resp.text
        reminders = resp.json()
        assert len(reminders) == 1
        assert reminders[0]["vehicle_nickname"] == w["vehicle_nickname"]
        assert reminders[0]["next_due_km"] == 12000
        assert "days_until_due" in reminders[0]
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_ha_rejects_unknown_or_missing_token() -> None:
    w = await _world()
    c = w["client"]
    try:
        resp = await c.get("/api/v1/ha/vehicles", headers={"X-HA-API-Key": "abha_bad"})
        assert resp.status_code == 401
        resp = await c.get("/api/v1/ha/vehicles")
        assert resp.status_code == 401
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_ha_stranger_cannot_use_token() -> None:
    w = await _world()
    c, auth = w["client"], {"Authorization": f"Bearer {w['stranger_token']}"}
    try:
        raw = (await c.post("/api/v1/ha/tokens", json={}, headers=auth)).json()["api_key"]
        resp = await c.get("/api/v1/ha/vehicles", headers={"X-HA-API-Key": raw})
        assert resp.status_code == 200
        # token is stranger's own (empty list of vehicles), can't see owner's data
        assert resp.json() == []
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_token_vehicle_scope() -> None:
    w = await _world()
    c, auth = w["client"], {"Authorization": f"Bearer {w['owner_token']}"}
    try:
        created = (await c.post(
            "/api/v1/ha/tokens", json={"vehicle_id": w["vehicle_id"]}, headers=auth
        )).json()
        assert created["vehicle_id"] == w["vehicle_id"]
        listed = await c.get("/api/v1/ha/tokens", headers=auth)
        assert listed.json()[0]["vehicle_id"] == w["vehicle_id"]
    finally:
        await c.aclose()
