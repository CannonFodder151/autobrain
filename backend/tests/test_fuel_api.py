"""Premium-gating tests for the Servo Spy fuel API (AUT-1817).

DB-free: we build a minimal FastAPI app with only the fuel_servo router and
override ``get_current_user`` (the auth boundary upstream of the
``require_fuel_access`` gate) so no Postgres is required. We assert:

  * free_account -> 403 with the founder-mandated message;
  * every route is locked behind `require_fuel_access` (mechanical gate proof);
  * a premium account reaches the DB-less /attribution route, 200, with the
    open-data attribution header.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MINIO_ACCESS_KEY"] = "a"
os.environ["MINIO_SECRET_KEY"] = "b"
os.environ["MINIO_BUCKET"] = "c"
os.environ["POSTGRES_USER"] = "u"
os.environ["POSTGRES_PASSWORD"] = "p"
os.environ["POSTGRES_DB"] = "d"
os.environ["ENVIRONMENT"] = "development"

import types  # noqa: E402
from typing import get_type_hints  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.api.v1.fuel_servo import require_fuel_access, router  # noqa: E402


def _user(free: bool) -> types.SimpleNamespace:
    return types.SimpleNamespace(id="u1", free_account=free, role="user", is_active=True)


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


def test_all_routes_locked_behind_premium_gate() -> None:
    """AUT-1813 founder ruling: every /api/fuel/* route must depend on
    require_fuel_access so free accounts cannot reach fuel data."""
    for route in router.routes:
        if not hasattr(route, "dependant"):
            continue
        deps = [d.call for d in route.dependant.dependencies]
        assert require_fuel_access in deps, f"{route.name or route.path} is not premium-gated"


def test_free_account_is_blocked_with_exact_message() -> None:
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _user(free=True)
    with TestClient(app) as client:
        r = client.get("/api/fuel/attribution")
    assert r.status_code == 403
    assert r.json()["detail"] == "Fuel prices are a premium feature. Upgrade to enable it."


def test_premium_account_reaches_attribution_with_header() -> None:
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _user(free=False)
    with TestClient(app) as client:
        r = client.get("/api/fuel/attribution")
    assert r.status_code == 200
    assert r.json()["sources"] == ["wa", "nsw", "qld"]
    assert "X-Fuel-Data-Attribution" in r.headers
    assert "WA FuelWatch" in r.headers["X-Fuel-Data-Attribution"]


def test_require_fuel_access_dependency_directly() -> None:
    import asyncio

    async def free_blocked():
        with pytest.raises(Exception) as e:  # HTTPException
            await require_fuel_access(_user(free=True))
        assert e.value.status_code == 403
        assert "premium feature" in e.value.detail

    async def premium_allowed():
        u = await require_fuel_access(_user(free=False))
        assert u.free_account is False

    asyncio.run(free_blocked())
    asyncio.run(premium_allowed())


# Re-export the type-hints import so linters don't flag it as unused in case
# future route-inspection logic grows here.
_ = get_type_hints
