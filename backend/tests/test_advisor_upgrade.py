"""Tests for the Ownership Advisor Upgrade module (AUT-2447).

Mirrors ``test_advisor_value.py``: pure-helper tests for the new code in
``app.services.advisor`` plus envelope-shape and FastAPI route tests
guarded by ``pytest.skip`` until the pre-existing ``fuel_prices``
``ImportError`` is fixed (see AUT-2496). The pure-helper tests do not
load ``app.main``, so they run regardless.
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

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services.advisor import (  # noqa: E402
    SIMILAR_MAX,
    SIMILAR_YEAR_WINDOW,
    UPGRADE_DEFAULT_DEPOSIT_PCT,
    UPGRADE_DEFAULT_FINANCE_TERM_MONTHS,
    UPGRADE_DEFAULT_RATE_PCT,
    UPGRADE_FINANCE_TERM_MAX,
    UPGRADE_FINANCE_TERM_MIN,
    _UPGRADE_TIER_WEIGHT,
    _amortize_monthly,
    _clamp_deposit_pct,
    _clamp_finance_term,
    _clamp_rate_pct,
    _similarity_score,
    _tier_label,
    build_trade_up,
)

def _vehicle(*, year: int | None = 2018, odo: int | None = 80_000,
             condition: str = "good", make: str = "Toyota",
             model: str = "Corolla", body_type: str | None = "sedan") -> SimpleNamespace:
    """Return a fake Vehicle-like object for unit tests."""
    v = SimpleNamespace()
    v.id = "v1"
    v.user_id = "u1"
    v.make = make
    v.model = model
    v.year = year
    v.odometer_km = odo
    v.condition = condition
    v.vehicle_type = body_type
    v.created_at = None
    v.updated_at = None
    return v


# --- pure-helper tests (run without app.main) --------------------------------

@pytest.mark.asyncio
async def test_tier_labels_are_correct() -> None:
    assert _tier_label(2018, 2019) == "newer (nxt)"
    assert _tier_label(2018, 2020) == "newer (nxt)"
    assert _tier_label(2018, 2017) == "older (prv)"


@pytest.mark.asyncio
async def test_similarity_score_bounds() -> None:
    s = _similarity_score("Toyota", "Corolla", 2018, "Toyota", "Corolla", 2019, 1.0)
    assert 0.0 <= s <= 1.0


@pytest.mark.asyncio
async def test_similarity_score_self_is_max() -> None:
    s = _similarity_score("Toyota", "Corolla", 2018, "Toyota", "Corolla", 2018, 1.0)
    assert s == pytest.approx(1.0, abs=1e-6)


@pytest.mark.asyncio
async def test_similarity_score_other_make_penalty() -> None:
    s_same = _similarity_score("Toyota", "Corolla", 2018, "Toyota", "Camry", 2019, 1.0)
    s_diff = _similarity_score("Toyota", "Corolla", 2018, "Honda", "Civic", 2019, 1.0)
    assert s_same > s_diff


@pytest.mark.asyncio
async def test_amortize_monthly_matches_known_values() -> None:
    # 20k over 60 months at 7.5% -> ~400.76
    monthly = _amortize_monthly(20_000.0, 60, 7.5)
    assert monthly == pytest.approx(400.76, abs=0.02)


@pytest.mark.asyncio
async def test_clamp_finance_term() -> None:
    assert _clamp_finance_term(None) == 60
    assert _clamp_finance_term(36) == 36
    assert _clamp_finance_term(10) == 12
    assert _clamp_finance_term(90) == 84


@pytest.mark.asyncio
async def test_clamp_rate_pct() -> None:
    assert _clamp_rate_pct(None) == 7.5
    assert _clamp_rate_pct(5.0) == 5.0
    assert _clamp_rate_pct(0.0) == 1.0
    assert _clamp_rate_pct(20.0) == 15.0


@pytest.mark.asyncio
async def test_clamp_deposit_pct() -> None:
    assert _clamp_deposit_pct(None) == 20.0
    assert _clamp_deposit_pct(15.0) == 15.0
    assert _clamp_deposit_pct(-5.0) == 0.0
    assert _clamp_deposit_pct(100.0) == 50.0


@pytest.mark.asyncio
async def test_find_upgrade_options_uses_cached_medians(monkeypatch) -> None:
    """Upgrade options should come from market data, not invented prices."""
    from app.services.advisor import find_upgrade_options, get_market_data

    captured = {}

    async def _fake_get_market_data(make: str, model: str, year: int):
        captured["called_with"] = (make, model, year)
        return {"mid": 25_000.0}

    monkeypatch.setattr("app.services.advisor.get_market_data", _fake_get_market_data)

    v = _vehicle(year=2018, make="Toyota", model="Corolla")
    opts = await find_upgrade_options(v)
    assert len(opts) >= 1
    assert captured["called_with"][0] == "Toyota"


@pytest.mark.asyncio
async def test_find_upgrade_options_returns_note_when_no_market_data(monkeypatch) -> None:
    from app.services.advisor import find_upgrade_options, get_market_data

    async def _fake_get_market_data(make: str, model: str, year: int):
        return None

    monkeypatch.setattr("app.services.advisor.get_market_data", _fake_get_market_data)

    v = _vehicle(year=2018, make="UnknownMake", model="UnknownModel")
    opts = await find_upgrade_options(v)
    assert opts == []


@pytest.mark.asyncio
async def test_find_similar_vehicles_excludes_own_make_model(monkeypatch) -> None:
    from app.services.advisor import find_similar_vehicles, get_market_data

    async def _fake_get_market_data(make: str, model: str, year: int):
        return {"mid": 25_000.0}

    monkeypatch.setattr("app.services.advisor.get_market_data", _fake_get_market_data)

    v = _vehicle(year=2018, make="Toyota", model="Corolla")
    similar = await find_similar_vehicles(v)
    for s in similar:
        assert not (s["make"] == "Toyota" and s["model"] == "Corolla")


@pytest.mark.asyncio
async def test_compute_upgrade_returns_empty_when_no_market_data(monkeypatch) -> None:
    from app.services.advisor import compute_upgrade, get_market_data

    async def _fake_get_market_data(make: str, model: str, year: int):
        return None

    monkeypatch.setattr("app.services.advisor.get_market_data", _fake_get_market_data)

    v = _vehicle(year=2018, make="UnknownMake", model="UnknownModel")
    plan = await compute_upgrade(db=None, vehicle=v)
    assert plan["upgrade_options"] == []
    assert plan["similar_vehicles"] == []
    assert plan["trade_up"] == []
    assert "no market listings" in plan["note"]


@pytest.mark.asyncio
async def test_compute_upgrade_propagates_finance_inputs(monkeypatch) -> None:
    from app.services.advisor import compute_upgrade, get_market_data

    async def _fake_get_market_data(make: str, model: str, year: int):
        return {"mid": 25_000.0}

    monkeypatch.setattr("app.services.advisor.get_market_data", _fake_get_market_data)

    v = _vehicle(year=2018, make="Toyota", model="Corolla")
    plan = await compute_upgrade(
        db=None, vehicle=v,
        odometer_km=50_000,
        finance_term_months=48,
        rate_pct=5.0,
        deposit_pct=10.0,
    )
    assert plan["finance_term_months"] == 48
    assert plan["rate_pct"] == 5.0
    assert plan["deposit_pct"] == 10.0
    assert len(plan["upgrade_options"]) >= 1
    assert len(plan["trade_up"]) >= 1
    for t in plan["trade_up"]:
        assert t["finance_term_months"] == 48
        assert t["rate_pct"] == 5.0
        assert t["deposit_pct"] == 10.0


# --- the actual route via FastAPI TestClient --------------------------------

def _try_import_app():
    try:
        from app.main import app as _app  # type: ignore
        return _app
    except (SyntaxError, ImportError) as exc:
        pytest.skip(f"app boot blocked by unrelated pre-existing import error: {exc}")


@pytest.mark.asyncio
async def test_advisor_upgrade_route_envelope(monkeypatch) -> None:
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.api.v1 import advisor as advisor_mod

    fake_vehicle = _vehicle()
    fake_vehicle.id = "v1"
    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_compute_upgrade(db, vehicle, odometer_km=None,
                                    finance_term_months=None,
                                    rate_pct=None, deposit_pct=None):
        return {
            "currency": "AUD",
            "current_value": 20_000.0,
            "upgrade_options": [
                {
                    "make": "Toyota", "model": "Corolla", "year": 2019,
                    "tier_label": "newer (nxt)",
                    "price_low": 21_500.0, "price_mid": 23_000.0,
                    "price_high": 24_500.0, "price_delta": 3_000.0,
                    "score": 1.0, "note": None,
                },
            ],
            "similar_vehicles": [
                {
                    "make": "Honda", "model": "Civic", "year": 2018,
                    "body_type": "sedan", "price_mid": 18_500.0,
                    "score": 0.85, "note": None,
                },
            ],
            "trade_up": [
                {
                    "currency": "AUD", "finance_term_months": 60,
                    "rate_pct": 7.5, "deposit_pct": 20.0,
                    "principal": 2160.0, "monthly_repayment": 43.13,
                    "total_interest": 428.0, "surplus": False, "note": None,
                },
            ],
            "finance_term_months": 60,
            "rate_pct": 7.5,
            "deposit_pct": 20.0,
            "note": None,
        }

    monkeypatch.setattr(advisor_mod, "compute_upgrade", _fake_compute_upgrade)

    async def _fake_get_accessible_vehicle(db, vid, user):
        return fake_vehicle

    monkeypatch.setattr(advisor_mod, "get_accessible_vehicle",
                        _fake_get_accessible_vehicle)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/advisor/upgrade",
            params={"vehicle_id": "v1", "odometer_km": 80_000,
                    "finance_term_months": 60, "rate_pct": 7.5,
                    "deposit_pct": 20.0},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == "upgrade"
    assert body["vehicle_id"] == "v1"
    assert body["model"] == "rule-based-fallback"
    assert "generated_at" in body
    assert body["data"]["currency"] == "AUD"
    assert body["data"]["current_value"] == 20_000.0
    assert body["data"]["upgrade_options"][0]["tier_label"] == "newer (nxt)"
    assert body["data"]["upgrade_options"][0]["score"] == 1.0
    assert body["data"]["similar_vehicles"][0]["make"] == "Honda"
    assert body["data"]["trade_up"][0]["monthly_repayment"] == pytest.approx(43.13, abs=0.05)


@pytest.mark.asyncio
async def test_advisor_upgrade_route_blocks_free_account(monkeypatch) -> None:
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
        resp = await client.get("/api/v1/advisor/upgrade", params={"vehicle_id": "v1"})
    app.dependency_overrides.clear()

    assert resp.status_code == 403
