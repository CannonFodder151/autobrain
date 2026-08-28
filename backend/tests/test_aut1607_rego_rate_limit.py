"""AUT-1607: per-user rego-lookup rate limiting (plate enumeration / abuse).

Regression: an authenticated user issuing N+1 rego lookups must get 429 on
call N+1, and the 429 message must reflect the configured limit. Redis is
stubbed so the suite runs without a live Redis.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.models.user import User
from app.services import rate_limit
from app.core.config import settings

USER = User(id="aut1607-user", email="paid@example.com", display_name="Paid", hashed_password="x")


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/rego")
    async def rego_route(_: None = Depends(rate_limit.require_rego_rate_limit)) -> dict:
        return {"ok": True}

    return app


def _client(monkeypatch: pytest.MonkeyPatch, *, per_hour: int, window: int = 3600) -> TestClient:
    monkeypatch.setattr(settings, "REGO_RATE_LIMIT_PER_HOUR", per_hour)
    monkeypatch.setattr(settings, "REGO_RATE_WINDOW_SECONDS", window)

    counts: dict[str, int] = {}

    async def fake_bump(key: str, ttl: int) -> int:
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(rate_limit, "_bump", fake_bump)

    app = _app()
    app.dependency_overrides[get_current_user] = lambda: USER
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def rego_client(monkeypatch: pytest.MonkeyPatch):
    yield from _client(monkeypatch, per_hour=2)


def test_rego_limit_429_on_n_plus_one(rego_client: TestClient) -> None:
    assert rego_client.post("/rego").status_code == 200
    assert rego_client.post("/rego").status_code == 200
    resp = rego_client.post("/rego")
    assert resp.status_code == 429
    assert str(settings.REGO_RATE_LIMIT_PER_HOUR) in resp.json()["detail"]


def test_rego_limit_message_reflects_configured_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "REGO_RATE_LIMIT_PER_HOUR", 7)
    monkeypatch.setattr(settings, "REGO_RATE_WINDOW_SECONDS", 3600)

    counts: dict[str, int] = {}

    async def fake_bump(key: str, ttl: int) -> int:
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(rate_limit, "_bump", fake_bump)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: USER
    try:
        client = TestClient(app)
        for _ in range(7):
            assert client.post("/rego").status_code == 200
        resp = client.post("/rego")
        assert resp.status_code == 429
        assert "7/hour" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_rego_limit_per_user_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Different users must have independent counters (AUT-1607 design note)."""
    monkeypatch.setattr(settings, "REGO_RATE_LIMIT_PER_HOUR", 1)
    monkeypatch.setattr(settings, "REGO_RATE_WINDOW_SECONDS", 3600)

    counts: dict[str, int] = {}

    async def fake_bump(key: str, ttl: int) -> int:
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(rate_limit, "_bump", fake_bump)
    other = User(id="other-user", email="other@example.com", display_name="Other", hashed_password="x")
    users = [USER, other]
    seq = {"n": 0}

    def _user() -> User:
        u = users[seq["n"] % len(users)]
        seq["n"] += 1
        return u

    app = _app()
    app.dependency_overrides[get_current_user] = _user
    try:
        client = TestClient(app)
        # Each user may use their one allowed lookup; neither trips the other's cap.
        assert client.post("/rego").status_code == 200
        assert client.post("/rego").status_code == 200
        resp = client.post("/rego")
        assert resp.status_code == 429
        assert "1/hour" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_rego_limiter_unavailable_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_bump(key: str, ttl: int) -> int:
        raise RuntimeError("redis down")

    monkeypatch.setattr(rate_limit, "_bump", broken_bump)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: USER
    try:
        resp = TestClient(app).post("/rego")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()
