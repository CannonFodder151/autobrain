"""AUT-304: no user enumeration on signup + burst rate limit on auth endpoints.

Regression:
- POST /auth/signup with an already-registered email returns the same 201 +
  generic body as a fresh signup (no account existence leak).
- > AUTH_BURST_LIMIT rapid requests from one IP → 429.
Redis + SMTP are stubbed/unset so the suite runs without infrastructure.
"""

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers all tables)
from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.services import auth as auth_svc

_engine = create_async_engine(
    "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
)
_SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _db_override():
    async with _SessionLocal() as session:
        yield session


class _FakeRedis:
    """Minimal in-memory Redis subset for the burst limiter (mirrors AUT-303 stub)."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, float]] = {}

    async def zadd(self, key: str, mapping: dict) -> None:
        self._data.setdefault(key, {}).update(mapping)

    async def zremrangebyscore(self, key: str, min_: float, max_: float) -> None:
        for member, score in list(self._data.get(key, {}).items()):
            if min_ <= score <= max_:
                del self._data[key][member]

    async def zcard(self, key: str) -> int:
        return len(self._data.get(key, {}))

    async def expire(self, key: str, ttl: int) -> None:
        pass

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)

    async def aclose(self) -> None:
        pass


class _FakePipeline:
    def __init__(self, fake: _FakeRedis) -> None:
        self._fake = fake
        self._ops: list[tuple] = []

    def zadd(self, key: str, mapping: dict) -> "_FakePipeline":
        self._ops.append(("zadd", key, mapping))
        return self

    def expire(self, key: str, ttl: int) -> "_FakePipeline":
        self._ops.append(("expire", key, ttl))
        return self

    async def execute(self) -> list:
        for kind, *args in self._ops:
            if kind == "zadd":
                await self._fake.zadd(args[0], args[1])
            elif kind == "expire":
                await self._fake.expire(args[0], args[1])
        return []


@pytest.fixture
def _stub_burst(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(auth_svc, "_redis", lambda: fake)
    return fake


async def _use_db():
    """Wire the app's DB dependency to the in-memory sqlite tables (fresh each call)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = _db_override


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_burst_limit_blocks_after_budget(monkeypatch, _stub_burst) -> None:
    monkeypatch.setattr("app.services.auth.settings.AUTH_BURST_LIMIT", 3)
    monkeypatch.setattr("app.services.auth.settings.AUTH_BURST_WINDOW_SECONDS", 60)
    for _ in range(3):
        await auth_svc.check_burst_limit("1.2.3.4")
    with pytest.raises(HTTPException) as exc:
        await auth_svc.check_burst_limit("1.2.3.4")
    assert exc.value.status_code == 429
    # Another IP is unaffected.
    await auth_svc.check_burst_limit("5.6.7.8")


@pytest.mark.asyncio
async def test_signup_existing_email_returns_identical_response(monkeypatch) -> None:
    await _use_db()
    monkeypatch.setattr(settings, "SELF_SIGNUP_ENABLED", True)
    async with _client() as client:
        body = {"email": "enum@example.com", "display_name": "Enum"}
        first = await client.post("/api/v1/auth/signup", json=body)
        second = await client.post(
            "/api/v1/auth/signup", json={**body, "display_name": "Other"}
        )
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["email"] == "enum@example.com"


@pytest.mark.asyncio
async def test_signup_rapid_burst_gets_429(monkeypatch, _stub_burst) -> None:
    await _use_db()
    monkeypatch.setattr(settings, "SELF_SIGNUP_ENABLED", True)
    monkeypatch.setattr("app.services.auth.settings.AUTH_BURST_LIMIT", 5)
    monkeypatch.setattr("app.services.auth.settings.AUTH_BURST_WINDOW_SECONDS", 60)
    async with _client() as client:
        codes = []
        for i in range(6):
            resp = await client.post(
                "/api/v1/auth/signup",
                json={"email": f"burst-{i}@example.com", "display_name": f"Burst {i}"},
            )
            codes.append(resp.status_code)
    assert codes[:5] == [201] * 5
    assert codes[5] == 429


@pytest.mark.asyncio
async def test_password_reset_rapid_burst_gets_429(monkeypatch, _stub_burst) -> None:
    await _use_db()
    monkeypatch.setattr("app.services.auth.settings.AUTH_BURST_LIMIT", 3)
    monkeypatch.setattr("app.services.auth.settings.AUTH_BURST_WINDOW_SECONDS", 60)
    async with _client() as client:
        codes = []
        for i in range(4):
            resp = await client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": f"reset-{i}@example.com"},
            )
            codes.append(resp.status_code)
    assert codes[:3] == [200] * 3
    assert codes[3] == 429
