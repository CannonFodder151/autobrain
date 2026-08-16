"""AUT-918: dongle device keys + idempotent WiFi trip upload.

Covers: device create returns a key and stores only a hash; the upload
surface authenticates via X-Device-API-Key; trips land bound to the device's
vehicle as `diy_dongle`; retries dedupe on (device_id, device_trip_id);
club-reg vehicles are still rejected; unbound devices 409.

Requires the compose Postgres (same as the rest of the suite). Run locally with:
    DATABASE_URL=sqlite+aiosqlite:////tmp/autobrain-test.db pytest backend/tests/test_device_api.py
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
from app.models.device import Device  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.device_keys import hash_key


@pytest.fixture(scope="module", autouse=True)
def _init_schema() -> None:
    asyncio.run(init_db())


async def _setup(user_email: str, *, club_reg: bool = False) -> dict:
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
        vehicle = Vehicle(user_id=user.id, nickname="Dongle Whip", club_reg=club_reg)
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        token = create_access_token(user.id)
        user_id = user.id
        vehicle_id = vehicle.id
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return {"client": client, "token": token, "user_id": user_id, "vehicle_id": vehicle_id}


def _trip(device_trip_id: str, gps: list | None = None) -> dict:
    payload = {
        "device_trip_id": device_trip_id,
        "started_at": "2026-08-01T09:00:00Z",
        "ended_at": "2026-08-01T09:30:00Z",
    }
    if gps:
        payload["gps_samples"] = gps
    return payload


@pytest.mark.asyncio
async def test_create_device_returns_key_and_hashes_it() -> None:
    world = await _setup("dev-create")
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]

    resp = await client.post(
        "/api/v1/devices",
        json={"name": "Garage dongle", "vehicle_id": world["vehicle_id"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["api_key"].startswith("abdev_"), body["api_key"]
    assert len(body["api_key"]) > 32, body["api_key"]

    device_id = body["id"]
    async with SessionLocal() as db:
        stored = await db.get(Device, device_id)
        assert stored is not None
        assert stored.api_key_hash != body["api_key"]
        assert len(stored.api_key_hash) == 64
        assert stored.api_key_prefix == body["api_key"][:10]
        assert stored.vehicle_id == world["vehicle_id"]

    listed = await client.get("/api/v1/devices", headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(d["id"] == device_id for d in listed.json()), listed.text
    # Plaintext key never leaks back through the list.
    assert all("api_key" not in d for d in listed.json()), listed.text

    await client.aclose()


@pytest.mark.asyncio
async def test_dongle_upload_is_idempotent() -> None:
    world = await _setup("dev-idem")
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]

    created = await client.post(
        "/api/v1/devices",
        json={"name": "Dongle", "vehicle_id": world["vehicle_id"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    device_id = created.json()["id"]
    dev_headers = {"X-Device-API-Key": created.json()["api_key"]}
    url = f"/api/v1/devices/{device_id}/trips"

    gps = [{"t": 1767200000, "lat": -33.8687241, "lon": 151.2109053}]
    first = await client.post(
        url,
        json={"trips": [_trip("trip-1767200000", gps)]},
        headers=dev_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["accepted"] == 1, first.text
    assert first.json()["duplicates"] == 0, first.text

    # WiFi retry: same device_trip_id must not double-log.
    retry = await client.post(
        url, json={"trips": [_trip("trip-1767200000", gps)]}, headers=dev_headers
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["accepted"] == 0, retry.text
    assert retry.json()["duplicates"] == 1, retry.text

    listed = await client.get(
        f"/api/v1/vehicles/{world['vehicle_id']}/logbook", headers=headers
    )
    entries = [e for e in listed.json() if e["source"] == "diy_dongle"]
    assert len(entries) == 1, listed.text
    assert entries[0]["status"] == "completed"
    assert "gps_samples" not in entries[0]  # list view omits samples

    detail = await client.get(
        f"/api/v1/vehicles/{world['vehicle_id']}/logbook/{entries[0]['id']}",
        headers=headers,
    )
    assert detail.json()["gps_samples"] == gps, detail.text

    await client.aclose()


@pytest.mark.asyncio
async def test_dongle_upload_rejects_bad_key_and_wrong_device() -> None:
    world = await _setup("dev-auth")
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]

    created = await client.post(
        "/api/v1/devices",
        json={"name": "Dongle", "vehicle_id": world["vehicle_id"]},
        headers=headers,
    )
    device_id = created.json()["id"]

    bad = await client.post(
        f"/api/v1/devices/{device_id}/trips",
        json={"trips": [_trip("trip-1")]},
        headers={"X-Device-API-Key": "abdev_wrongwrongwrong"},
    )
    assert bad.status_code == 401, bad.text

    other = await client.post(
        "/api/v1/devices",
        json={"name": "Other", "vehicle_id": world["vehicle_id"]},
        headers=headers,
    )
    other_id = other.json()["id"]
    # Key for the OTHER device used against this URL path => 404.
    wrong = await client.post(
        f"/api/v1/devices/{device_id}/trips",
        json={"trips": [_trip("trip-1")]},
        headers={"X-Device-API-Key": other.json()["api_key"]},
    )
    assert wrong.status_code == 404, wrong.text

    await client.aclose()


@pytest.mark.asyncio
async def test_dongle_upload_survives_prefix_collision() -> None:
    """Security F1: prefix-colliding keys must still resolve to the right device.

    Forced collision (same api_key_prefix on two devices) used to let
    `db.scalar()` silently pick an arbitrary row, giving the second device a
    persistent 401. The lookup now checks every candidate with the full digest.
    """
    world = await _setup("dev-collide")
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]

    first = await client.post(
        "/api/v1/devices",
        json={"name": "Dongle A", "vehicle_id": world["vehicle_id"]},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    first_key = first.json()["api_key"]
    first_id = first.json()["id"]

    # Forge a genuine prefix collision: a second key that shares the first
    # key's 10-char prefix but has a different body, and store it on another
    # device row. Real-world collisions are equally rare (65,536 prefixes) but
    # must still resolve to the owning device instead of a random row.
    second_key = first_key[:10] + ("9" * (len(first_key) - 10))
    second = await client.post(
        "/api/v1/devices",
        json={"name": "Dongle B", "vehicle_id": world["vehicle_id"]},
        headers=headers,
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]

    async with SessionLocal() as db:
        dev = await db.get(Device, second_id)
        dev.api_key_prefix = first_key[:10]
        dev.api_key_hash = hash_key(second_key)
        await db.commit()

    # The second device's real key must now upload even though the prefix
    # collides with the first device.
    resp = await client.post(
        f"/api/v1/devices/{second_id}/trips",
        json={"trips": [_trip("trip-collide")]},
        headers={"X-Device-API-Key": second_key},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted"] == 1, resp.text

    # And the first device's key must still resolve to the first device
    # (not be confused by the collision).
    first_resp = await client.post(
        f"/api/v1/devices/{first_id}/trips",
        json={"trips": [_trip("trip-collide-first")]},
        headers={"X-Device-API-Key": first_key},
    )
    assert first_resp.status_code == 200, first_resp.text

    await client.aclose()


@pytest.mark.asyncio
async def test_dongle_upload_needs_bound_vehicle() -> None:
    world = await _setup("dev-unbound")
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]

    created = await client.post("/api/v1/devices", json={"name": "Loose"}, headers=headers)
    assert created.status_code == 201, created.text
    resp = await client.post(
        f"/api/v1/devices/{created.json()['id']}/trips",
        json={"trips": [_trip("trip-1")]},
        headers={"X-Device-API-Key": created.json()["api_key"]},
    )
    assert resp.status_code == 409, resp.text

    await client.aclose()


@pytest.mark.asyncio
async def test_dongle_upload_rejected_on_club_reg_vehicle() -> None:
    world = await _setup("dev-club", club_reg=True)
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]

    created = await client.post(
        "/api/v1/devices",
        json={"name": "Dongle", "vehicle_id": world["vehicle_id"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    resp = await client.post(
        f"/api/v1/devices/{created.json()['id']}/trips",
        json={"trips": [_trip("trip-1")]},
        headers={"X-Device-API-Key": created.json()["api_key"]},
    )
    assert resp.status_code == 403, resp.text

    await client.aclose()


@pytest.mark.asyncio
async def test_dongle_upload_gps_samples_are_cleaned_deterministically() -> None:
    world = await _setup("dev-gps")
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]

    created = await client.post(
        "/api/v1/devices",
        json={"name": "Dongle", "vehicle_id": world["vehicle_id"]},
        headers=headers,
    )
    device_id = created.json()["id"]
    dev_headers = {"X-Device-API-Key": created.json()["api_key"]}

    # 0,0 (no fix) rows must be dropped, valid ones kept, by the shared cleaner.
    gps = [
        {"t": 1767200000, "lat": 0, "lon": 0},
        {"t": 1767200001, "lat": -33.8687241, "lon": 151.2109053},
        {"t": 1767200002, "lat": 91.0, "lon": 151.0},
    ]
    resp = await client.post(
        url := f"/api/v1/devices/{device_id}/trips",
        json={"trips": [_trip("trip-gps1", gps)]},
        headers=dev_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted"] == 1

    listed = await client.get(f"/api/v1/vehicles/{world['vehicle_id']}/logbook", headers=headers)
    dongle_entries = [e for e in listed.json() if e["source"] == "diy_dongle"]
    detail = await client.get(
        f"/api/v1/vehicles/{world['vehicle_id']}/logbook/{dongle_entries[0]['id']}",
        headers=headers,
    )
    samples = detail.json()["gps_samples"]
    assert len(samples) == 1, samples
    assert samples[0]["lat"] == -33.8687241

    await client.aclose()