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
import tempfile
import uuid

# AUT-514: app.db.session is a module singleton whose engine is created at import
# time. The first test module imported in a run pins that engine, so a fixed
# sqlite path here (e.g. ./test_verify.db) actually resolves to whatever engine a
# sibling module created first -> cross-file DB collisions. Isolate this module
# with its own temp DB, engine and SessionLocal, exactly like the other seed tests.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="autobrain-device-verify-")
os.close(_db_fd)
os.unlink(_db_path)  # aiosqlite opens it fresh; we only want a unique name
_db_url = f"sqlite+aiosqlite:///{_db_path}"

# Only fill config values that are not already set; DATABASE_URL is forced to our
# isolated sqlite file so this module never touches the shared app engine.
os.environ["DATABASE_URL"] = _db_url
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DONGLE_SERVER_API_KEY", "test-internal-key")
os.environ.setdefault("DONGLE_SERVER_URL", "http://dongle-server:8000")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.dongle_firmware import DongleInstalledFirmware  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.device_keys import generate_key, hash_key, key_prefix  # noqa: E402


# Settings is a process-wide singleton cached on first app import. A sibling test
# module may have imported it before our env vars above ran, so pin the dongle
# config directly on the cached instance instead of relying on os.environ.
from app.core.config import settings  # noqa: E402

settings.DONGLE_SERVER_API_KEY = os.environ["DONGLE_SERVER_API_KEY"]
settings.DONGLE_SERVER_URL = os.environ["DONGLE_SERVER_URL"]

INTERNAL_HEADERS = {"X-Internal-Api-Key": settings.DONGLE_SERVER_API_KEY}

engine = create_async_engine(_db_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def pytest_unconfigure(config):
    """Remove the per-run temp DB file so the runner stays clean."""
    try:
        if os.path.exists(_db_path):
            os.unlink(_db_path)
    except OSError:
        pass


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def _init_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True, scope="module")
def _override_get_db():
    """Route every endpoint through this module's own SessionLocal/engine so the
    HTTP client queries the same database that _setup_user_and_device wrote to
    (the app's get_db default references the shared app.db.session singleton)."""

    async def _local_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _local_db
    yield
    app.dependency_overrides.pop(get_db, None)


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
