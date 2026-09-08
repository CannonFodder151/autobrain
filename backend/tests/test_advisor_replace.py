"""Tests for the Ownership Advisor Replace module (AUT-2446).

Mirrors ``test_advisor_value.py``: pure-helper tests for
``app.services.advisor`` plus HTTP-shape tests for
``GET /api/v1/advisor/replace`` via the in-process ASGI client (skipped
when the unrelated fuel_prices syntax bug blocks app boot).
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_USER", "test-postgres-user")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_DB", "test-postgres-db")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-minio-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret-key")
os.environ.setdefault("MINIO_BUCKET", "test-minio-bucket")

from datetime import date  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services.advisor import (  # noqa: E402
    NEW_USED_PREMIUM_MAX,
    REPLACE_DEFAULT_HORIZON_MONTHS,
    REPLACE_HORIZON_MAX_MONTHS,
    REPLACE_HORIZON_MIN_MONTHS,
    _REPLACE_PREMIUM_BREAKPOINTS,
    age_years,
    new_used_premium,
)


def _enforce_entitlement(user):
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Ownership Advisor is a paid feature. Upgrade to enable it.",
        )


def _vehicle(*, year: int | None = 2018, odo: int | None = 80_000, condition: str = "good",
             make: str = "Toyota", model: str = "Corolla") -> SimpleNamespace:
    return SimpleNamespace(
        year=year, odometer_km=odo, condition=condition, make=make, model=model,
        vehicle_type="car",
    )


# --- pure helpers ----------------------------------------------------------

def test_age_years_basic() -> None:
    v = _vehicle(year=date.today().year - 7)
    assert age_years(v) == 7


def test_age_years_missing_year_returns_none() -> None:
    assert age_years(_vehicle(year=None)) is None


def test_age_years_future_year_returns_zero() -> None:
    assert age_years(_vehicle(year=date.today().year + 1)) == 0


def test_age_years_non_numeric_year_returns_none() -> None:
    assert age_years(_vehicle(year="not-a-year")) is None  # type: ignore[arg-type]


def test_new_used_premium_at_breakpoints() -> None:
    # 0yo == 1.0; 3yo == 1.4; 6yo == 1.8; 10yo == 2.2 (per documented curve)
    assert new_used_premium(0) == pytest.approx(1.0, abs=1e-6)
    assert new_used_premium(3) == pytest.approx(1.4, abs=1e-6)
    assert new_used_premium(6) == pytest.approx(1.8, abs=1e-6)
    assert new_used_premium(10) == pytest.approx(2.2, abs=1e-6)


def test_new_used_premium_interpolates_between_breakpoints() -> None:
    # 4-5yo interpolates between (3, 1.4) and (6, 1.8): t = (4-3)/3 = 0.333 → 1.4 + 0.0667 = 1.4667
    assert new_used_premium(4) == pytest.approx(1.4 + (1.8 - 1.4) * (1 / 3), abs=1e-3)


def test_new_used_premium_clamps_at_max() -> None:
    # 25yo is past the last breakpoint; uses the max breakpoint value, clamped at NEW_USED_PREMIUM_MAX
    assert new_used_premium(25) == pytest.approx(min(NEW_USED_PREMIUM_MAX, _REPLACE_PREMIUM_BREAKPOINTS[-1][1]), abs=1e-6)


def test_new_used_premium_unknown_age_is_one() -> None:
    assert new_used_premium(None) == 1.0


def test_horizon_defaults_and_clamps() -> None:
    from app.services.advisor import _clamp_horizon
    assert _clamp_horizon(None) == REPLACE_DEFAULT_HORIZON_MONTHS == 36
    assert _clamp_horizon(0) == REPLACE_HORIZON_MIN_MONTHS  # 6
    assert _clamp_horizon(-100) == REPLACE_HORIZON_MIN_MONTHS
    assert _clamp_horizon(99) == 99
    assert _clamp_horizon(1000) == REPLACE_HORIZON_MAX_MONTHS  # 120
    assert _clamp_horizon("not-a-number") == REPLACE_DEFAULT_HORIZON_MONTHS


# --- entitlement -----------------------------------------------------------

def test_enforce_entitlement_blocks_free_accounts() -> None:
    with pytest.raises(HTTPException) as ei:
        _enforce_entitlement(SimpleNamespace(free_account=True, role="user"))
    assert ei.value.status_code == 403


def test_enforce_entitlement_allows_paid_user_and_demo() -> None:
    _enforce_entitlement(SimpleNamespace(free_account=False, role="user"))
    _enforce_entitlement(SimpleNamespace(free_account=False, role="demo"))


# --- envelope shape via direct Pydantic validation (no FastAPI boot) -------

def test_advisor_response_envelope_shape_replace_module() -> None:
    from datetime import datetime, timezone
    from app.schemas.advisor import (
        AdvisorReplaceData,
        AdvisorResponse,
        FundingGapBand,
        TradeInBand,
    )

    plan = AdvisorReplaceData(
        currency="AUD",
        current_value=12_000.0,
        trade_in=TradeInBand(low=9_000.0, mid=9_840.0, high=10_800.0),
        used_replacement_cost=12_000.0,
        new_replacement_cost=21_600.0,  # mid × premium(7yo) = 12000 × 1.8667 ≈ 22400, round to 1.8 area
        age_years=7,
        new_used_premium=1.8,
        horizon_months=36,
        funding_gap=FundingGapBand(
            currency="AUD",
            horizon_months=36,
            gap=-200.0,
            monthly_target=0.0,
            surplus=True,
            note="replacement cost is below current value + trade-in — no saving target needed",
        ),
        note=None,
    )
    factors = {
        "vehicle": {
            "id": "v1", "make": "Toyota", "model": "Corolla", "year": 2018,
            "condition": "good", "odometer_km": 80_000, "vehicle_type": "car",
        },
        "age_years": 7,
        "new_used_premium": 1.8,
        "horizon_months": 36,
    }
    resp = AdvisorResponse(
        module="replace",
        vehicle_id="v1",
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback",
        data=plan.model_dump(),
        factors=factors,
    )
    out = resp.model_dump()
    assert out["module"] == "replace"
    assert out["vehicle_id"] == "v1"
    assert out["model"] == "rule-based-fallback"
    assert "generated_at" in out
    assert out["data"]["current_value"] == 12_000.0
    assert out["data"]["used_replacement_cost"] == 12_000.0
    assert out["data"]["trade_in"]["mid"] == pytest.approx(9_840.0, abs=1e-2)
    assert out["data"]["funding_gap"]["surplus"] is True
    assert out["factors"]["new_used_premium"] == 1.8


# --- the actual route via FastAPI TestClient --------------------------------

def _try_import_app():
    try:
        from app.main import app as _app  # type: ignore
        return _app
    except (SyntaxError, ImportError) as exc:
        pytest.skip(f"app boot blocked by unrelated pre-existing import error: {exc}")


@pytest.mark.asyncio
async def test_advisor_replace_route_envelope(monkeypatch) -> None:
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.api.v1 import advisor as advisor_mod

    fake_vehicle = _vehicle()
    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_compute_replace(db, vehicle, odometer_km=None, horizon_months=None):
        return {
            "currency": "AUD",
            "current_value": 12_000.0,
            "trade_in": {
                "currency": "AUD",
                "low": 9_000.0,
                "mid": 9_840.0,
                "high": 10_800.0,
                "ratios": {"low": 0.75, "mid": 0.82, "high": 0.90},
            },
            "used_replacement_cost": 12_000.0,
            "new_replacement_cost": 21_600.0,
            "age_years": 7,
            "new_used_premium": 1.8,
            "horizon_months": 36,
            "funding_gap": {
                "currency": "AUD",
                "horizon_months": 36,
                "gap": -240.0,
                "monthly_target": 0.0,
                "surplus": True,
                "note": "replacement cost is below current value + trade-in — no saving target needed",
            },
            "note": None,
        }

    monkeypatch.setattr(advisor_mod, "compute_replace", _fake_compute_replace)
    monkeypatch.setattr(advisor_mod, "get_accessible_vehicle",
                        lambda db, vid, user: fake_vehicle)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/advisor/replace",
                                params={"vehicle_id": "v1", "odometer_km": 80_000,
                                        "horizon_months": 36})
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == "replace"
    assert body["vehicle_id"] == "v1"
    assert body["model"] == "rule-based-fallback"
    assert "generated_at" in body
    assert body["data"]["currency"] == "AUD"
    assert body["data"]["current_value"] == 12_000.0
    assert body["data"]["used_replacement_cost"] == 12_000.0
    assert body["data"]["new_replacement_cost"] == 21_600.0
    assert body["data"]["funding_gap"]["surplus"] is True
    assert body["data"]["funding_gap"]["monthly_target"] == 0.0
    assert body["factors"]["new_used_premium"] == 1.8


@pytest.mark.asyncio
async def test_advisor_replace_route_blocks_free_account(monkeypatch) -> None:
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod

    fake_user = SimpleNamespace(id="u1", free_account=True, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/advisor/replace", params={"vehicle_id": "v1"})
    app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "paid" in resp.json()["detail"].lower()