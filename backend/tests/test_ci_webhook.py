"""Tests for the CI triage webhook receiver (AUT-1669)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.v1.ci import router as ci_router  # noqa: E402

CI_SECRET = "test-ci-webhook-secret"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("CI_TRIAGE_WEBHOOK_SECRET", CI_SECRET)
    monkeypatch.setenv("PAPERCLIP_API_URL", "https://paperclip.test")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-paperclip-key")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "test-company-id")
    monkeypatch.setenv("CI_TRIAGE_PARENT_ISSUE_ID", "parent-123")
    monkeypatch.setenv("CI_TRIAGE_GOAL_ID", "goal-456")
    monkeypatch.setenv("CI_TRIAGE_AGENT_ID", "acae6bf2")

    # rebuild settings so env overrides take effect
    import app.core.config as config_mod
    monkeypatch.setattr(config_mod, "settings", config_mod.Settings(_env_file=None))

    # ci.py bound `settings` at module import time; monkeypatch must also
    # repoint it here, otherwise ci.py keeps the original (unconfigured) object.
    import app.api.v1.ci as ci_mod
    monkeypatch.setattr(ci_mod, "settings", config_mod.settings)

    a = FastAPI()
    a.include_router(ci_router, prefix="/api/v1")
    return a


@pytest.fixture
def headers() -> dict:
    return {"Authorization": f"Bearer {CI_SECRET}"}


@pytest.mark.asyncio
async def test_unauthorized_missing_token(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/ci/webhook", json={"repo": "o/r", "ref": "main"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_bad_token(app: FastAPI, headers: dict) -> None:
    headers = dict(headers)
    headers["Authorization"] = "Bearer wrong"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/ci/webhook", json={"repo": "o/r", "ref": "main"}, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invalid_json(app: FastAPI, headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/ci/webhook", content="not json", headers=headers)
    assert resp.status_code == 400
    assert "Invalid JSON" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_missing_payload_fields(app: FastAPI, headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/ci/webhook", json={"event": "push"}, headers=headers)
    assert resp.status_code == 400
    assert "Missing" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_not_configured_503(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """When CI_TRIAGE_WEBHOOK_SECRET is unset → 503."""
    import app.core.config as config_mod
    import app.api.v1.ci as ci_mod
    monkeypatch.setattr(config_mod, "settings", config_mod.Settings(_env_file=None, CI_TRIAGE_WEBHOOK_SECRET=""))
    monkeypatch.setattr(ci_mod, "settings", config_mod.settings)

    a = FastAPI()
    a.include_router(ci_router, prefix="/api/v1")
    transport = ASGITransport(app=a)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/ci/webhook", json={"repo": "o/r", "ref": "main"})
    assert resp.status_code == 503


@pytest.mark.asyncio
@patch("app.api.v1.ci.httpx.AsyncClient")
async def test_webhook_creates_issue(mock_client_cls, app: FastAPI, headers: dict) -> None:
    mock_response = AsyncMock()
    mock_response.status_code = 201
    mock_response.text = "ok"
    mock_response.json = MagicMock(return_value={"id": "issue-abc"})
    mock_ac = AsyncMock()
    mock_ac.post = AsyncMock(return_value=mock_response)
    mock_ac.__aenter__ = AsyncMock(return_value=mock_ac)
    mock_ac.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = mock_ac

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/ci/webhook",
            json={"event": "push", "repo": "CannonFodder151/autobrain", "ref": "refs/heads/main"},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["issueId"] == "issue-abc"
    mock_ac.post.assert_awaited_once()
    call_kwargs = mock_ac.post.await_args
    assert "companies/test-company-id/issues" in call_kwargs[0][0]


@pytest.mark.asyncio
@patch("app.api.v1.ci.httpx.AsyncClient")
async def test_webhook_http_error_returns_502(mock_client_cls, app: FastAPI, headers: dict) -> None:
    """Network/transport errors from httpx -> 502."""
    import httpx as httpx_mod
    mock_ac = AsyncMock()
    mock_ac.post = AsyncMock(side_effect=httpx_mod.ConnectError("connection refused"))
    mock_ac.__aenter__ = AsyncMock(return_value=mock_ac)
    mock_ac.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = mock_ac

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/ci/webhook",
            json={"event": "push", "repo": "o/r", "ref": "main"},
            headers=headers,
        )
    assert resp.status_code == 502


@pytest.mark.asyncio
@patch("app.api.v1.ci.httpx.AsyncClient")
async def test_webhook_non_json_response_returns_502(mock_client_cls, app: FastAPI, headers: dict) -> None:
    """Non-JSON Paperclip response -> 502."""
    mock_response = AsyncMock()
    mock_response.status_code = 502
    mock_response.text = "<html>Bad Gateway</html>"
    mock_response.json = MagicMock(side_effect=ValueError("not JSON"))
    mock_ac = AsyncMock()
    mock_ac.post = AsyncMock(return_value=mock_response)
    mock_ac.__aenter__ = AsyncMock(return_value=mock_ac)
    mock_ac.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = mock_ac

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/ci/webhook",
            json={"event": "push", "repo": "o/r", "ref": "main"},
            headers=headers,
        )
    assert resp.status_code == 502
# 
