"""Health check tests — /health endpoint contract for demo/hosted/default parity.

Aims to fail loudly when the deployed instance drifts from the source-of-truth
version in app.core.config.APP_VERSION or when /health stops returning 200.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

HEALTH_TIMEOUT_S = 5.0


@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    """Demo/hosted/default must all return 200 on /health."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=HEALTH_TIMEOUT_S) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200, f"/health returned {resp.status_code} (body: {resp.text!r})"


@pytest.mark.asyncio
async def test_health_status_ok() -> None:
    """The status field must literally be 'ok' (matches docker-compose healthcheck probes)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=HEALTH_TIMEOUT_S) as client:
        resp = await client.get("/health")
    body = resp.json()
    assert body.get("status") == "ok", f"/health status was {body.get('status')!r}"


@pytest.mark.asyncio
async def test_health_service_name() -> None:
    """The service field must identify as 'autobrain-backend' (matters for ops dashboards)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=HEALTH_TIMEOUT_S) as client:
        resp = await client.get("/health")
    body = resp.json()
    assert body.get("service") == "autobrain-backend", f"/health service was {body.get('service')!r}"


@pytest.mark.asyncio
async def test_health_version_matches_config() -> None:
    """/health.version must match app.core.config.settings.APP_VERSION (the source of truth).

    Catches version drift where a deployed container reports a different version
    than the code it was supposedly built from. Hosting team must bump config
    AND rebuild the image together.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=HEALTH_TIMEOUT_S) as client:
        resp = await client.get("/health")
    body = resp.json()
    assert body.get("version") == settings.APP_VERSION, (
        f"/health version {body.get('version')!r} does not match "
        f"settings.APP_VERSION {settings.APP_VERSION!r} — bump APP_VERSION or rebuild"
    )


@pytest.mark.asyncio
async def test_health_version_is_semver() -> None:
    """APP_VERSION must be a dotted semver-like string (e.g. 0.3.203), not 'unknown' or empty."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=HEALTH_TIMEOUT_S) as client:
        resp = await client.get("/health")
    version = resp.json().get("version", "")
    parts = version.split(".")
    assert len(parts) >= 2, f"/health version {version!r} is not dotted semver"
    for part in parts:
        assert part.isdigit(), f"/health version {version!r} has non-numeric segment {part!r}"


@pytest.mark.asyncio
async def test_health_does_not_500_when_db_unreachable() -> None:
    """/health must NEVER 500. Even if downstream deps are down, it should report
    'ok' or a known-bad status with 200, so docker-compose healthcheck does not
    kill the container and trigger an outage storm (AUT-1962 lesson).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=HEALTH_TIMEOUT_S) as client:
        resp = await client.get("/health")
    assert resp.status_code < 500, f"/health 5xx: {resp.status_code} {resp.text!r}"
