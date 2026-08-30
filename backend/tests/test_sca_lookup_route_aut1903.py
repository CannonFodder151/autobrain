"""AUT-1903: the SCA parts lookup route must serve POST, not GET.

The client (frontend) posts a JSON body to ``/sca-lookup``; the route was
registered as GET, so every lookup returned 405. This proves POST is accepted
and the backend drives the lookup from the selected vehicle's plate + state
(call-supplied rego/state override the stored values).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_current_user, get_db  # noqa: E402
from app.api.v1.parts import router as parts_router  # noqa: E402


class _FakeVehicle:
    make = None
    model = None
    year = None
    rego = "ABC123"
    rego_state = "VIC"
    vehicle_type = "car"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    import app.core.config as config_mod

    monkeypatch.setattr(config_mod, "settings", config_mod.Settings(_env_file=None))

    fake_user = type("U", (), {"id": "u1"})()

    async def _get_db():
        s = AsyncMock()
        s.get = AsyncMock(return_value=_FakeVehicle())
        yield s

    def _get_current_user():
        return fake_user

    a = FastAPI()
    a.dependency_overrides[get_db] = _get_db
    a.dependency_overrides[get_current_user] = _get_current_user
    a.include_router(parts_router)
    return a


@pytest.mark.asyncio
async def test_sca_lookup_accepts_post_and_uses_vehicle_state(
    app: FastAPI,
) -> None:
    canned = {
        "parts": [
            {"name": "Oil Filter", "category": "Filters", "sku": "OF1",
             "supplier": "SCA", "unit_cost": 12.5},
        ],
        "vehicle": {"make": "Toyota", "model": "Corolla", "state": "VIC"},
        "source": "sca+9router",
        "model": "rule-based",
    }
    with patch(
        "app.api.v1.parts.get_accessible_vehicle", AsyncMock()
    ), patch(
        "app.services.parts_guide.lookup_sca_parts",
        new=AsyncMock(return_value=canned),
    ) as mock_lookup:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/vehicles/v1/parts/sca-lookup",
                json={"rego": "ABC123", "state": "VIC"},
            )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["parts"][0]["name"] == "Oil Filter"
    # The view drove the guide from the vehicle's stored plate + state.
    mock_lookup.assert_awaited_once()
    _, kwargs = mock_lookup.call_args
    assert kwargs["rego"] == "ABC123"
    assert kwargs["state"] == "VIC"


@pytest.mark.asyncio
async def test_sca_lookup_get_is_not_allowed(app: FastAPI) -> None:
    with patch("app.api.v1.parts.get_accessible_vehicle", AsyncMock()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/vehicles/v1/parts/sca-lookup")
    assert resp.status_code == 405
