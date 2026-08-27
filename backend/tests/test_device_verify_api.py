"""AUT-1673: paid-account gate enforcement for the dongle-server backchannel.

Covers:
- POST /devices/verify (dongle-server backchannel) resolves the device from its
  API key hash, matches the hardware serial, and reports the paid status.
- Missing/wrong X-Internal-Api-Key is rejected (401) so only the dongle-server
  can reach the paid-gate check.
- Wrong serial -> serial_matched=False; free account -> paid=False.
- GET /dongle/firmware/latest requires a paid account (403 for free).
- POST /dongle/firmware/report upserts the serial whitelist on the dongle-server
  when the owner is paid.

Requires the compose Postgres. Run locally with:
    DATABASE_URL=sqlite+aiosqlite:////tmp/autobrain-test.db \
    DONGLE_SERVER_API_KEY=test-internal-key pytest backend/tests/test_device_verify_api.py
"""

import os
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DONGLE_SERVER_API_KEY", "test-internal-key")
os.environ.setdefault("DONGLE_SERVER_URL", "http://dongle-server:8000")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.dongle_firmware import DongleInstalledFirmware  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.device_keys import generate_key, hash_key, key_prefix  # noqa: E402


INTERNAL_HEADERS = {"X-Internal-Api-Key": os.environ["DONGLE_SERVER_API_KEY"]}


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _init_schema() -> None:
    await init_db()


async def _setup_user_and_device(*, free: bool = False) -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        user = User(
            email=f"dev-{suffix}@example.com",
            display_name="Owner",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
            free_account=free,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        vehicle = Vehicle(user_id=user.id, nickname="Dongle Whip")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        key = generate_key()
        device = Device(
            user_id=user.id,
            name="Test Dongle",
            vehicle_id=vehicle.id,
            api_key_prefix=key_prefix(key),
            api_key_hash=hash_key(key),
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)
        installed = DongleInstalledFirmware(
            device_id=device.id,
            model="OBD Logging Device V1",
            firmware_version="1.4.2",
            serial_number="AB123456789",
        )
        db.add(installed)
        await db.commit()
        token = create_access_token(user.id)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return {
        "client": client,
        "token": token,
        "user": user,
        "device": device,
        "api_key": key,
        "installed": installed,
    }


@pytest.mark.asyncio
async def test_verify_valid_paid_device() -> None:
    world = await _setup_user_and_device(free=False)
    client: AsyncClient = world["client"]
    resp = await client.post(
        "/api/v1/devices/verify",
        json={"serial": "AB123456789", "api_key": world["api_key"]},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["serial_matched"] is True
    assert body["paid"] is True
    assert body["model"] == "OBD Logging Device V1"
    assert body["device_id"] == world["device"].id
    assert body["user_id"] == world["user"].id
    await client.aclose()


@pytest.mark.asyncio
async def test_verify_wrong_serial() -> None:
    world = await _setup_user_and_device(free=False)
    client: AsyncClient = world["client"]
    resp = await client.post(
        "/api/v1/devices/verify",
        json={"serial": "WRONG_SERIAL", "api_key": world["api_key"]},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["serial_matched"] is False
    # paid is still reported accurately even when serial doesn't match
    assert body["paid"] is True
    await client.aclose()


@pytest.mark.asyncio
async def test_verify_free_account_not_paid() -> None:
    world = await _setup_user_and_device(free=True)
    client: AsyncClient = world["client"]
    resp = await client.post(
        "/api/v1/devices/verify",
        json={"serial": "AB123456789", "api_key": world["api_key"]},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["serial_matched"] is True
    assert body["paid"] is False
    await client.aclose()


@pytest.mark.asyncio
async def test_verify_rejects_missing_internal_key() -> None:
    world = await _setup_user_and_device(free=False)
    client: AsyncClient = world["client"]
    resp = await client.post(
        "/api/v1/devices/verify",
        json={"serial": "AB123456789", "api_key": world["api_key"]},
    )
    assert resp.status_code == 401
    await client.aclose()


@pytest.mark.asyncio
async def test_verify_rejects_wrong_internal_key() -> None:
    world = await _setup_user_and_device(free=False)
    client: AsyncClient = world["client"]
    resp = await client.post(
        "/api/v1/devices/verify",
        json={"serial": "AB123456789", "api_key": world["api_key"]},
        headers={"X-Internal-Api-Key": "wrong-key"},
    )
    assert resp.status_code == 401
    await client.aclose()


@pytest.mark.asyncio
async def test_verify_unknown_device_key_fails_closed() -> None:
    world = await _setup_user_and_device(free=False)
    client: AsyncClient = world["client"]
    # A valid-format but unknown key must NOT match any device.
    fake_key = "abdev_" + "0" * 64
    resp = await client.post(
        "/api/v1/devices/verify",
        json={"serial": "AB123456789", "api_key": fake_key},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["serial_matched"] is False
    assert body["paid"] is False
    assert body["device_id"] is None
    assert body["user_id"] is None
    await client.aclose()


@pytest.mark.asyncio
async def test_latest_firmware_rejects_free_account() -> None:
    world = await _setup_user_and_device(free=True)
    client: AsyncClient = world["client"]
    resp = await client.get(
        "/api/v1/dongle/firmware/latest?model=OBD+Logging+Device+V1",
        headers={"Authorization": f"Bearer {world['token']}"},
    )
    assert resp.status_code == 403, resp.text
    await client.aclose()


@pytest.mark.asyncio
async def test_latest_firmware_allows_paid_account() -> None:
    world = await _setup_user_and_device(free=False)
    client: AsyncClient = world["client"]
    resp = await client.get(
        "/api/v1/dongle/firmware/latest?model=OBD+Logging+Device+V1",
        headers={"Authorization": f"Bearer {world['token']}"},
    )
    # Paid user: 200 (null body = no release published yet, which is fine)
    assert resp.status_code == 200, resp.text
    await client.aclose()


@pytest.mark.asyncio
async def test_report_upserts_whitelist_for_paid_account() -> None:
    world = await _setup_user_and_device(free=False)
    client: AsyncClient = world["client"]
    dev_headers = {"X-Device-API-Key": world["api_key"]}
    with patch("app.api.v1.dongle_firmware.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=AsyncMock(status_code=200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client
        resp = await client.post(
            "/api/v1/dongle/firmware/report",
            json={
                "model": "OBD Logging Device V1",
                "firmware_version": "1.4.2",
                "serial_number": "AB123456789",
            },
            headers=dev_headers,
        )
    assert resp.status_code == 200, resp.text
    assert mock_client.post.called
    call_args = mock_client.post.call_args
    assert "AB123456789" in call_args.kwargs["data"]["serial"]
    assert call_args.kwargs["data"]["paid"] == "true"
    assert world["device"].id == call_args.kwargs["data"]["device_id"]
    await client.aclose()


@pytest.mark.asyncio
async def test_report_skips_whitelist_for_free_account() -> None:
    world = await _setup_user_and_device(free=True)
    client: AsyncClient = world["client"]
    dev_headers = {"X-Device-API-Key": world["api_key"]}
    with patch("app.api.v1.dongle_firmware.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client
        resp = await client.post(
            "/api/v1/dongle/firmware/report",
            json={
                "model": "OBD Logging Device V1",
                "firmware_version": "1.4.2",
                "serial_number": "AB123456789",
            },
            headers=dev_headers,
        )
    assert resp.status_code == 200, resp.text
    assert not mock_client.post.called
    await client.aclose()
