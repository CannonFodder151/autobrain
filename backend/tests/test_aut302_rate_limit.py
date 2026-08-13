"""AUT-302: per-user AI rate limiting (cost abuse / worker DoS).

Regression: an authenticated user issuing N+1 AI calls must get 429 on call
N+1. The Redis counter is stubbed out so the suite runs without Redis.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.models.user import User
from app.services import rate_limit
from app.core.config import settings

USER = User(id="aut302-user", email="paid@example.com", display_name="Paid", hashed_password="x")


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/ai")
    async def ai_route(_: None = Depends(rate_limit.require_ai_rate_limit)) -> dict:
        return {"ok": True}

    return app


def _client(monkeypatch: pytest.MonkeyPatch, *, per_window: int, daily: int, window: int = 60) -> TestClient:
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_WINDOW", per_window)
    monkeypatch.setattr(settings, "AI_RATE_WINDOW_SECONDS", window)
    monkeypatch.setattr(settings, "AI_DAILY_LIMIT", daily)

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
def burst_client(monkeypatch: pytest.MonkeyPatch):
    yield from _client(monkeypatch, per_window=2, daily=100)


@pytest.fixture
def daily_client(monkeypatch: pytest.MonkeyPatch):
    yield from _client(monkeypatch, per_window=100, daily=2)


def test_burst_limit_429_on_n_plus_one(burst_client: TestClient) -> None:
    assert burst_client.post("/ai").status_code == 200
    assert burst_client.post("/ai").status_code == 200
    assert burst_client.post("/ai").status_code == 429


def test_daily_cap_429_after_limit(daily_client: TestClient) -> None:
    assert daily_client.post("/ai").status_code == 200
    assert daily_client.post("/ai").status_code == 200
    assert daily_client.post("/ai").status_code == 429


def test_rate_limiter_unavailable_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_bump(key: str, ttl: int) -> int:
        raise RuntimeError("redis down")

    monkeypatch.setattr(rate_limit, "_bump", broken_bump)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: USER
    try:
        resp = TestClient(app).post("/ai")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.clear()
