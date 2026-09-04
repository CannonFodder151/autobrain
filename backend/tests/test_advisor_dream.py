"""Tests for the Ownership Advisor Dream Car module (AUT-2449).

Mirrors ``test_advisor_upgrade.py``: pure-helper tests for the new code in
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

from datetime import date  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services.advisor import (  # noqa: E402
    DREAM_DSR_CEILING,
    _loan_monthly_payment,
    compute_dream,
)


# --- pure helpers ----------------------------------------------------------

@pytest.mark.asyncio
async def test_compute_dream_returns_three_blocks(monkeypatch) -> None:
    """Pure-helper smoke: every block present, deterministic numbers."""
    from app.services import advisor as advisor_mod

    async def _fake_market(db, make, model, year, vt):
        return {
            "median_price": 35_000.0,
            "low_price": 30_000.0,
            "high_price": 40_000.0,
            "sample_size": 12,
            "source": "provider",
            "as_of": "2026-09-04T00:00:00Z",
            "stale": False,
            "note": None,
        }

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    plan = await compute_dream(
        None,
        make="Toyota", model="GR Corolla", year=date.today().year,
        finance_term_months=60, rate_pct=7.5, deposit_pct=20.0,
        annual_income=120_000.0, monthly_expenses=4_500.0,
        cash_on_hand=15_000.0,
    )
    assert plan["currency"] == "AUD"
    assert plan["target"]["make"] == "Toyota"
    assert plan["target"]["mid"] == 35_000.0
    assert plan["target"]["source"] == "provider"
    # 35k * 0.2 = 7000 deposit, 35k * 0.8 = 28000 principal
    assert plan["affordability"]["deposit_required"] == 7_000.0
    # cash_on_hand 15000 - deposit_required 7000 = 8000 surplus
    assert plan["affordability"]["cash_gap"] == 8_000.0
    assert plan["repayments"]["principal"] == 28_000.0
    # 28k * (1 - 0.20) = 28k principal. 28k @ 7.5% / 60 → 561.06
    assert plan["repayments"]["monthly_repayment"] == pytest.approx(561.06, abs=0.10)
    assert plan["repayments"]["total_interest"] is not None
    # surplus = cash_ok AND dsr_ok. monthly_disposable = (120k/12 - 4500) = 5500.
    # DSR ceiling = 5500 * 0.3 = 1650 > 561.34 → dsr_ok.
    assert plan["affordability"]["surplus"] is True
    assert plan["affordability"]["note"] is None


@pytest.mark.asyncio
async def test_compute_dream_handles_no_market_data(monkeypatch) -> None:
    """Cache miss → null target, note explains the gap, no crash."""
    from app.services import advisor as advisor_mod

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": None, "low_price": None, "high_price": None,
                "sample_size": 0, "source": "fallback", "as_of": None,
                "stale": False, "note": "no market listings"}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    plan = await compute_dream(
        None, make="Toyota", model="GR Corolla", year=2024,
    )
    assert plan["target"]["mid"] is None
    assert plan["target"]["note"] == "no market listings"
    assert plan["repayments"]["principal"] is None
    assert plan["repayments"]["monthly_repayment"] is None
    assert "market listings" in plan["repayments"]["note"]
    # plan-level note should also propagate the gap
    assert plan["note"] == "no market listings"


@pytest.mark.asyncio
async def test_compute_dream_without_finance_profile(monkeypatch) -> None:
    """Missing annual_income/monthly_expenses → affordability note explains it."""
    from app.services import advisor as advisor_mod

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": 35_000.0, "low_price": 30_000.0,
                "high_price": 40_000.0, "sample_size": 5,
                "source": "fallback", "as_of": None, "stale": False}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    plan = await compute_dream(
        None, make="Toyota", model="GR Corolla", year=2024,
        annual_income=None, monthly_expenses=None, cash_on_hand=10_000.0,
    )
    assert plan["affordability"]["monthly_disposable_income"] is None
    assert plan["affordability"]["surplus"] is False
    assert "annual income" in plan["affordability"]["note"].lower()
    # Repayments still computed (no profile dependency).
    assert plan["repayments"]["principal"] == 28_000.0


@pytest.mark.asyncio
async def test_compute_dream_cash_shortfall_flags_no_surplus(monkeypatch) -> None:
    """cash_on_hand below deposit_required → cash_gap negative, no surplus."""
    from app.services import advisor as advisor_mod

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": 50_000.0, "low_price": 45_000.0,
                "high_price": 55_000.0, "sample_size": 3,
                "source": "fallback", "as_of": None, "stale": False}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    plan = await compute_dream(
        None, make="Porsche", model="911", year=2024,
        finance_term_months=60, rate_pct=7.5, deposit_pct=20.0,
        annual_income=200_000.0, monthly_expenses=6_000.0,
        cash_on_hand=2_000.0,
    )
    # 50k * 0.2 = 10000 deposit; cash 2k - 10k = -8000 shortfall
    assert plan["affordability"]["deposit_required"] == 10_000.0
    assert plan["affordability"]["cash_gap"] == -8_000.0
    assert plan["affordability"]["surplus"] is False
    assert plan["affordability"]["note"] is None  # cash shortfall alone isn't a note-worthy event, the gap field carries the signal


@pytest.mark.asyncio
async def test_compute_dream_dsr_ceiling_blocks_surplus(monkeypatch) -> None:
    """Indicative monthly > 30% disposable → surplus False with explanatory note."""
    from app.services import advisor as advisor_mod

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": 80_000.0, "low_price": 75_000.0,
                "high_price": 90_000.0, "sample_size": 5,
                "source": "fallback", "as_of": None, "stale": False}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    # 80k target, 20% deposit = 16k principal, 60mo @ 7.5% ≈ $320/mo.
    # monthly_disposable = (60k/12 - 4500) = 500. 30% ceiling = 150.
    # Monthly (320) > ceiling (150) → dsr violated → no surplus.
    plan = await compute_dream(
        None, make="BMW", model="M3", year=2024,
        finance_term_months=60, rate_pct=7.5, deposit_pct=20.0,
        annual_income=60_000.0, monthly_expenses=4_500.0,
        cash_on_hand=20_000.0,  # cash_ok (20000 > 16000)
    )
    assert plan["affordability"]["surplus"] is False
    assert plan["affordability"]["note"] is not None
    assert "30%" in plan["affordability"]["note"]


@pytest.mark.asyncio
async def test_compute_dream_clamp_finance_inputs(monkeypatch) -> None:
    """Out-of-range finance params get clamped to the documented bounds."""
    from app.services import advisor as advisor_mod

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": 30_000.0, "low_price": 25_000.0,
                "high_price": 35_000.0, "sample_size": 2,
                "source": "fallback", "as_of": None, "stale": False}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    plan = await compute_dream(
        None, make="Honda", model="Civic", year=2024,
        finance_term_months=999, rate_pct=99.0, deposit_pct=150.0,
    )
    assert plan["repayments"]["finance_term_months"] == 84
    assert plan["repayments"]["rate_pct"] == 30.0
    assert plan["repayments"]["deposit_pct"] == 100.0
    # principal = 30k * (1 - 1.0) = 0
    assert plan["repayments"]["principal"] == 0.0
    assert plan["repayments"]["monthly_repayment"] == 0.0


@pytest.mark.asyncio
async def test_compute_dream_uses_cached_market_no_duplication(monkeypatch) -> None:
    """compute_dream routes through get_market_data, never re-scrapes."""
    from app.services import advisor as advisor_mod

    calls = []

    async def _track(db, make, model, year, vt):
        calls.append((make, model, year, vt))
        return {"median_price": 20_000.0, "low_price": 18_000.0,
                "high_price": 22_000.0, "sample_size": 4,
                "source": "fallback", "as_of": None, "stale": False}

    monkeypatch.setattr(advisor_mod, "get_market_data", _track)

    await compute_dream(None, make="Mazda", model="3", year=2024)
    assert calls == [("Mazda", "3", 2024, "car")]
    # Vehicle type default
    await compute_dream(None, make="Yamaha", model="MT-07", year=2024,
                        vehicle_type="bike")
    assert calls[-1] == ("Yamaha", "MT-07", 2024, "bike")


# --- constants / DSR ------------------------------------------------------

def test_dsr_ceiling_is_30_percent() -> None:
    """Industry-standard bank serviceability ceiling for AU auto loans."""
    assert DREAM_DSR_CEILING == pytest.approx(0.30, abs=1e-6)


# --- envelope shape via direct Pydantic validation (no FastAPI boot) -------

def test_advisor_dream_envelope_shape() -> None:
    from datetime import datetime, timezone
    from app.schemas.advisor import (
        AdvisorDreamData,
        AdvisorResponse,
        DreamAffordability,
        DreamRepayments,
        DreamTarget,
    )

    data = AdvisorDreamData(
        currency="AUD",
        target=DreamTarget(
            make="Toyota", model="GR Corolla", year=2024, vehicle_type="car",
            low=30_000.0, mid=35_000.0, high=40_000.0, source="provider",
            as_of="2026-09-04T00:00:00Z", stale=False, sample_size=12,
            note=None,
        ),
        affordability=DreamAffordability(
            currency="AUD",
            target_price_mid=35_000.0,
            deposit_required=7_000.0,
            annual_income=120_000.0,
            monthly_disposable_income=5_500.0,
            cash_on_hand=15_000.0,
            cash_gap=8_000.0,
            surplus=True,
            note=None,
        ),
        repayments=DreamRepayments(
            currency="AUD", finance_term_months=60, rate_pct=7.5,
            deposit_pct=20.0, principal=28_000.0,
            monthly_repayment=561.06, total_interest=5_663.6,
            note=None,
        ),
        note=None,
    )
    resp = AdvisorResponse(
        module="dream",
        vehicle_id=None,
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback",
        data=data.model_dump(),
        factors={"target": {"make": "Toyota", "model": "GR Corolla",
                            "year": 2024, "vehicle_type": "car"},
                 "finance_term_months": 60, "rate_pct": 7.5,
                 "deposit_pct": 20.0, "dsr_ceiling": 0.30,
                 "profile_provided": True},
    )
    out = resp.model_dump()
    assert out["module"] == "dream"
    assert out["vehicle_id"] is None
    assert out["model"] == "rule-based-fallback"
    assert "generated_at" in out
    assert out["data"]["target"]["mid"] == 35_000.0
    assert out["data"]["affordability"]["surplus"] is True
    assert out["data"]["repayments"]["principal"] == 28_000.0
    assert out["data"]["repayments"]["monthly_repayment"] == pytest.approx(561.06, abs=0.05)
    assert out["factors"]["profile_provided"] is True


def test_advisor_dream_envelope_handles_missing_profile() -> None:
    from datetime import datetime, timezone
    from app.schemas.advisor import (
        AdvisorDreamData,
        AdvisorResponse,
        DreamAffordability,
        DreamRepayments,
        DreamTarget,
    )

    data = AdvisorDreamData(
        currency="AUD",
        target=DreamTarget(
            make="Toyota", model="GR Corolla", year=2024, vehicle_type="car",
            low=None, mid=None, high=None, source="fallback",
            as_of=None, stale=False, sample_size=0,
            note="no market listings",
        ),
        affordability=DreamAffordability(
            currency="AUD",
            target_price_mid=None,
            deposit_required=None,
            annual_income=None,
            monthly_disposable_income=None,
            cash_on_hand=None,
            cash_gap=None,
            surplus=False,
            note="annual income and monthly expenses required to compute affordability",
        ),
        repayments=DreamRepayments(
            currency="AUD", finance_term_months=60, rate_pct=7.5,
            deposit_pct=20.0, principal=None, monthly_repayment=None,
            total_interest=None,
            note="no market listings available for target — cannot estimate finance",
        ),
        note="no market listings",
    )
    resp = AdvisorResponse(
        module="dream", vehicle_id=None,
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback", data=data.model_dump(), factors={},
    )
    out = resp.model_dump()
    assert out["data"]["target"]["mid"] is None
    assert out["data"]["repayments"]["principal"] is None
    assert out["data"]["affordability"]["monthly_disposable_income"] is None
    assert "no market listings" in out["data"]["note"]


# --- the actual route via FastAPI TestClient -------------------------------

def _try_import_app():
    try:
        from app.main import app as _app  # type: ignore
        return _app
    except (SyntaxError, ImportError) as exc:
        pytest.skip(f"app boot blocked by unrelated pre-existing import error: {exc}")


@pytest.mark.asyncio
async def test_advisor_dream_route_envelope(monkeypatch) -> None:
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.api.v1 import advisor as advisor_mod

    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_compute_dream(db, **kwargs):
        return {
            "currency": "AUD",
            "target": {
                "make": "Toyota", "model": "GR Corolla", "year": 2024,
                "vehicle_type": "car", "low": 30_000.0, "mid": 35_000.0,
                "high": 40_000.0, "source": "provider",
                "as_of": "2026-09-04T00:00:00Z", "stale": False,
                "sample_size": 12, "note": None,
            },
            "affordability": {
                "currency": "AUD", "target_price_mid": 35_000.0,
                "deposit_required": 7_000.0, "annual_income": 120_000.0,
                "monthly_disposable_income": 5_500.0, "cash_on_hand": 15_000.0,
                "cash_gap": 8_000.0, "surplus": True, "note": None,
            },
            "repayments": {
                "currency": "AUD", "finance_term_months": 60,
                "rate_pct": 7.5, "deposit_pct": 20.0, "principal": 28_000.0,
                "monthly_repayment": 561.06, "total_interest": 5_663.6,
                "note": None,
            },
            "note": None,
        }

    monkeypatch.setattr(advisor_mod, "compute_dream", _fake_compute_dream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/advisor/dream",
            json={
                "make": "Toyota", "model": "GR Corolla", "year": 2024,
                "annual_income": 120000, "monthly_expenses": 4500,
                "cash_on_hand": 15000,
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == "dream"
    assert body["vehicle_id"] is None
    assert body["model"] == "rule-based-fallback"
    assert "generated_at" in body
    assert body["data"]["target"]["mid"] == 35_000.0
    assert body["data"]["affordability"]["cash_gap"] == 8_000.0
    assert body["data"]["repayments"]["principal"] == 28_000.0
    assert body["data"]["repayments"]["monthly_repayment"] == pytest.approx(561.06, abs=0.05)
    assert body["factors"]["profile_provided"] is True
    assert body["factors"]["dsr_ceiling"] == 0.30


@pytest.mark.asyncio
async def test_advisor_dream_route_blocks_free_account(monkeypatch) -> None:
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
        resp = await client.post(
            "/api/v1/advisor/dream",
            json={"make": "Toyota", "model": "GR Corolla", "year": 2024},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "paid" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_advisor_dream_route_validates_required_fields(monkeypatch) -> None:
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod

    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/advisor/dream",
            json={"make": "Toyota"},  # missing model + year
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 422


# --- share a SimpleNamespace stub with sibling tests ------------------------

from types import SimpleNamespace  # noqa: E402  # isort:skip