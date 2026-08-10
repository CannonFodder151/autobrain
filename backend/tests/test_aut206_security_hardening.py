"""AUT-206: constant-time admin key compare + CORS origin allow-list."""

import pytest
from starlette.requests import Request

from fastapi import HTTPException  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import require_admin_api_key, settings  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_KEY = "aut206-test-admin-key"


def _req(key: str | None) -> Request:
    headers = {}
    if key is not None:
        headers["X-Admin-API-Key"] = key
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("test", 123),
        }
    )


@pytest.mark.asyncio
async def test_admin_key_missing_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_API_KEY", ADMIN_KEY)
    with pytest.raises(HTTPException) as exc:
        await require_admin_api_key(_req(None))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_key_wrong_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_API_KEY", ADMIN_KEY)
    with pytest.raises(HTTPException) as exc:
        await require_admin_api_key(_req("definitely-not-the-key"))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_key_correct_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_API_KEY", ADMIN_KEY)
    assert await require_admin_api_key(_req(ADMIN_KEY)) is None


@pytest.mark.asyncio
async def test_cors_same_origin_only_by_default() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/health", headers={"Origin": "https://evil.example.com"}
        )
    assert "access-control-allow-origin" not in resp.headers
