"""Dedicated health endpoint tests for AUT-2118 — promoted from test_api.py.

Asserts:
  (1) /health returns 200
  (2) status == "ok"
  (3) service == "autobrain-backend"
  (4) version matches APP_VERSION (settings.APP_VERSION)
  (5) marks which env (demo/hosted/default) when run with DEMO_MODE=true
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_env():
    import importlib
    import app.core.config as _config
    import app.main as _main
    yield
    os.environ.pop("DEMO_MODE", None)
    os.environ.pop("SOCIAL_FEDERATION_HOSTED", None)
    importlib.reload(_config)
    importlib.reload(_main)


def _make_client(app_module):
    return AsyncClient(transport=ASGITransport(app=app_module), base_url="http://test")


@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    """(1) /health returns 200."""
    async with _make_client(app) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_status_is_ok() -> None:
    """(2) status == "ok"."""
    async with _make_client(app) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_health_service_is_autobrain_backend() -> None:
    """(3) service == "autobrain-backend"."""
    async with _make_client(app) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "autobrain-backend"


@pytest.mark.asyncio
async def test_health_version_matches_app_version() -> None:
    """(4) version matches APP_VERSION from settings."""
    async with _make_client(app) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["version"] == settings.APP_VERSION


@pytest.mark.asyncio
async def test_health_marks_demo_env_when_demo_mode_true() -> None:
    """(5) When DEMO_MODE=true, env == "demo"."""
    os.environ["DEMO_MODE"] = "true"
    import importlib
    import app.core.config as _config
    import app.main as _main
    importlib.reload(_config)
    importlib.reload(_main)
    from app.main import app as reload_app

    async with _make_client(reload_app) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["env"] == "demo"


@pytest.mark.asyncio
async def test_health_marks_hosted_env_when_federation_hosted() -> None:
    """When SOCIAL_FEDERATION_HOSTED=true and DEMO_MODE is false, env == "hosted"."""
    os.environ["SOCIAL_FEDERATION_HOSTED"] = "true"
    import importlib
    import app.core.config as _config
    import app.main as _main
    importlib.reload(_config)
    importlib.reload(_main)
    from app.main import app as reload_app

    async with _make_client(reload_app) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["env"] == "hosted"


@pytest.mark.asyncio
async def test_health_marks_default_env_when_neither_demo_nor_hosted() -> None:
    """When DEMO_MODE is false and SOCIAL_FEDERATION_HOSTED is false, env == "default"."""
    os.environ["SOCIAL_FEDERATION_HOSTED"] = "false"
    import importlib
    import app.core.config as _config
    import app.main as _main
    importlib.reload(_config)
    importlib.reload(_main)
    from app.main import app as reload_app

    async with _make_client(reload_app) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["env"] == "default"
