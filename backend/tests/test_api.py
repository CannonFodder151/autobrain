"""Smoke tests for core backend behaviour (auth + vehicles)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://autobrain:autobrain@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import asyncio  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402

from app.core.security import create_access_token, hash_password, verify_password  # noqa: E402
from app.main import app  # noqa: E402


def test_password_hashing() -> None:
    h = hash_password("hunter22")
    assert h != "hunter22"
    assert verify_password("hunter22", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip() -> None:
    token = create_access_token("user-1")
    assert token


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_unauthorized_rejected() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/vehicles")
    assert resp.status_code == 401
