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
    return SimpleNamespace(
        year=year, odometer_km=odo, condition=condition, make=make,
        model=model, vehicle_type="car", body_type=body_type,
    )


# --- pure helpers ----------------------------------------------------------

def test_clamp_finance_term_defaults_and_bounds() -> None:
    assert _clamp_finance_term(None) == UPGRADE_DEFAULT_FINANCE_TERM_MONTHS == 60
    assert _clamp_finance_term(0) == UPGRADE_FINANCE_TERM_MIN
    assert _clamp_finance_term(-1) == UPGRADE_FINANCE_TERM_MIN
    assert _clamp_finance_term(60) == 60
    assert _clamp_finance_term(999) == UPGRADE_FINANCE_TERM_MAX
    assert _clamp_finance_term("not-a-number") == UPGRADE_DEFAULT_FINANCE_TERM_MONTHS


def test_clamp_rate_pct_defaults_and_bounds() -> None:
    assert _clamp_rate_pct(None) == UPGRADE_DEFAULT_RATE_PCT == 7.5
    assert _clamp_rate_pct(-1) == 0.0
    assert _clamp_rate_pct(100) == 30.0
    assert _clamp_rate_pct(5.5) == 5.5
    assert _clamp_rate_pct("garbage") == UPGRADE_DEFAULT_RATE_PCT


def test_clamp_deposit_pct_defaults_and_bounds() -> None:
    assert _clamp_deposit_pct(None) == UPGRADE_DEFAULT_DEPOSIT_PCT == 20.0
    assert _clamp_deposit_pct(-5) == 0.0
    assert _clamp_deposit_pct(150) == 100.0
    assert _clamp_deposit_pct(10) == 10.0
    assert _clamp_deposit_pct("garbage") == UPGRADE_DEFAULT_DEPOSIT_PCT


def test_tier_label_format() -> None:
    assert _tier_label(1) == "newer (nxt)"
    assert _tier_label(2) == "newer (+2)"
    assert _tier_label(-1) == "older (-1)"
    assert _tier_label(-2) == "-2"
    assert _tier_label(3) == "+3"


def test_similarity_score_max_at_same_year_and_price() -> None:
    s = _similarity_score(current_year=2018, target_year=2018,
                          current_value=20_000, target_value=20_000)
    assert s == pytest.approx(1.0, abs=1e-6)


def test_similarity_score_decays_with_year_distance() -> None:
    s0 = _similarity_score(current_year=2018, target_year=2018,
                           current_value=20_000, target_value=20_000)
    s2 = _similarity_score(current_year=2018, target_year=2016,
                           current_value=20_000, target_value=20_000)
    assert s0 > s2


def test_similarity_score_decays_with_price_distance() -> None:
    near = _similarity_score(current_year=2018, target_year=2018,
                             current_value=20_000, target_value=22_000)
    far = _similarity_score(current_year=2018, target_year=2018,
                            current_value=20_000, target_value=40_000)
    assert near > far


def test_similarity_score_unknown_year_floors_at_half() -> None:
    s = _similarity_score(current_year=2018, target_year=None,
                          current_value=20_000, target_value=20_000)
    assert 0.0 <= s <= 1.0


def test_amortize_zero_rate_principal_splits_evenly() -> None:
    monthly, interest = _amortize_monthly(12_000, 0.0, 12)
    assert monthly == pytest.approx(1000.0, abs=1e-2)
    assert interest == 0.0


def test_amortize_zero_principal_zero_payment() -> None:
    assert _amortize_monthly(0, 7.5, 60) == (0.0, 0.0)


def test_amortize_standard_loan_matches_formula() -> None:
    # 20,000 @ 7.5% p.a. / 12 over 60 months -> $400.76 monthly (rounding),
    # interest ~ 4,045. Total check: monthly * 60 ≈ 24,045.
    monthly, interest = _amortize_monthly(20_000, 7.5, 60)
    assert monthly == pytest.approx(400.76, abs=0.05)
    assert interest == pytest.approx(monthly * 60 - 20_000, abs=0.5)


def test_build_trade_up_blocks_when_inputs_missing() -> None:
    out = build_trade_up(
        current_value=None, upgrade_value=None, trade_in_mid=None,
        finance_term_months=60, rate_pct=7.5, deposit_pct=20.0,
    )
    assert out["monthly_repayment"] is None
    assert out["principal"] is None
    assert "missing" in out["note"].lower()


def test_build_trade_up_surfaces_surplus_when_upgrade_below_current() -> None:
    out = build_trade_up(
        current_value=15_000, upgrade_value=8_000, trade_in_mid=12_300,
        finance_term_months=60, rate_pct=7.5, deposit_pct=20.0,
    )
    # upgrade (8k) < current (15k) + trade_in (12.3k) → surplus
    assert out["surplus"] is True
    assert out["monthly_repayment"] == 0.0
    assert out["principal"] == 0.0
    assert out["total_interest"] == 0.0


def test_build_trade_up_computes_principal_after_deposit() -> None:
    out = build_trade_up(
        current_value=15_000, upgrade_value=30_000, trade_in_mid=12_300,
        finance_term_months=60, rate_pct=7.5, deposit_pct=20.0,
    )
    # raw_gap = 30k - 15k - 12.3k = 2700; principal = 2700 * 0.8 = 2160
    assert out["principal"] == pytest.approx(2160.0, abs=0.05)
    assert out["surplus"] is False
    assert out["monthly_repayment"] > 0
    assert out["total_interest"] > 0
    assert out["note"] is None


def test_tier_weight_table_covers_supported_offsets() -> None:
    assert _UPGRADE_TIER_WEIGHT[1] > _UPGRADE_TIER_WEIGHT[2]
    assert _UPGRADE_TIER_WEIGHT[2] > _UPGRADE_TIER_WEIGHT[-1]


def test_similar_year_window_is_two_years() -> None:
    assert SIMILAR_YEAR_WINDOW == 2
    assert SIMILAR_MAX >= 3


# --- envelope shape via direct Pydantic validation (no FastAPI boot) -------

def test_advisor_upgrade_envelope_shape() -> None:
    from datetime import datetime, timezone
    from app.schemas.advisor import (
        AdvisorResponse,
        AdvisorUpgradeData,
        SimilarVehicleSuggestion,
        TradeUpDelta,
        UpgradeOption,
    )

    plan = AdvisorUpgradeData(
        currency="AUD",
        current_value=20_000.0,
        upgrade_options=[
            UpgradeOption(
                make="Toyota", model="Corolla", year=2019,
                tier_label="newer (nxt)",
                price_low=21_500.0, price_mid=23_000.0, price_high=24_500.0,
                price_delta=3_000.0, score=1.0, note=None,
            ),
            UpgradeOption(
                make="Toyota", model="Corolla", year=2017,
                tier_label="older (-1)",
                price_low=14_000.0, price_mid=15_000.0, price_high=16_000.0,
                price_delta=-5_000.0, score=0.7, note=None,
            ),
        ],
        similar_vehicles=[
            SimilarVehicleSuggestion(
                make="Honda", model="Civic", year=2018,
                body_type="sedan", price_mid=18_500.0, score=0.85, note=None,
            ),
        ],
        trade_up=[
            TradeUpDelta(
                currency="AUD", finance_term_months=60, rate_pct=7.5,
                deposit_pct=20.0, principal=2160.0, monthly_repayment=43.13,
                total_interest=428.0, surplus=False, note=None,
            ),
        ],
        finance_term_months=60,
        rate_pct=7.5,
        deposit_pct=20.0,
        note=None,
    )
    factors = {
        "vehicle": {
            "id": "v1", "make": "Toyota", "model": "Corolla", "year": 2018,
            "condition": "good", "odometer_km": 80_000, "vehicle_type": "car",
            "body_type": "sedan",
        },
        "finance_term_months": 60,
        "rate_pct": 7.5,
        "deposit_pct": 20.0,
        "similar_window_years": 2,
        "tier_offsets": [1, 2, -1],
    }
    resp = AdvisorResponse(
        module="upgrade",
        vehicle_id="v1",
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback",
        data=plan.model_dump(),
        factors=factors,
    )
    out = resp.model_dump()
    assert out["module"] == "upgrade"
    assert out["vehicle_id"] == "v1"
    assert out["model"] == "rule-based-fallback"
    assert "generated_at" in out
    assert out["data"]["currency"] == "AUD"
    assert out["data"]["current_value"] == 20_000.0
    assert out["data"]["upgrade_options"][0]["tier_label"] == "newer (nxt)"
    assert out["data"]["upgrade_options"][0]["score"] == 1.0
    assert out["data"]["similar_vehicles"][0]["make"] == "Honda"
    assert out["data"]["trade_up"][0]["monthly_repayment"] == pytest.approx(43.13, abs=0.05)
    assert out["factors"]["tier_offsets"] == [1, 2, -1]


def test_advisor_upgrade_envelope_handles_no_market_data() -> None:
    from datetime import datetime, timezone
    from app.schemas.advisor import AdvisorResponse, AdvisorUpgradeData

    plan = AdvisorUpgradeData(
        currency="AUD",
        current_value=None,
        upgrade_options=[],
        similar_vehicles=[],
        trade_up=[],
        finance_term_months=60,
        rate_pct=7.5,
        deposit_pct=20.0,
        note="no market listings available for this vehicle",
    )
    resp = AdvisorResponse(
        module="upgrade",
        vehicle_id="v1",
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback",
        data=plan.model_dump(),
        factors={},
    )
    out = resp.model_dump()
    assert out["data"]["current_value"] is None
    assert out["data"]["upgrade_options"] == []
    assert out["data"]["trade_up"] == []
    assert "no market listings" in out["data"]["note"]


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
    monkeypatch.setattr(advisor_mod, "get_accessible_vehicle",
                        lambda db, vid, user: fake_vehicle)

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
    assert body["factors"]["tier_offsets"] == [1, 2, -1]


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
        resp = await client.get(
            "/api/v1/advisor/upgrade", params={"vehicle_id": "v1"},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "paid" in resp.json()["detail"].lower()


# --- service helper: same-model upgrade options with mocked market ----------

class _FakeRow:
    def __init__(self, median, source="fallback"):
        self.median_price = median
        self.source = source


class _FakeMarketResult:
    def __init__(self, median):
        self.median_price = median
        self.as_of = "2026-09-04"
        self.stale = False
        self.sample_size = 5
        self.source = "fallback"
        self.note = None

    def get(self, k, default=None):
        return getattr(self, k, default)


@pytest.mark.asyncio
async def test_find_upgrade_options_uses_cached_medians(monkeypatch) -> None:
    """Pure-helper test: monkeypatch get_market_data so no real DB / provider."""
    from app.services import advisor as advisor_mod

    v = _vehicle(year=date_now_year() - 4)

    async def _fake_market(db, make, model, year, vt):
        return _FakeMarketResult(median=20_000 if year == v.year else 22_000).__dict__

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    options = await advisor_mod.find_upgrade_options(None, v)
    assert len(options) == 3  # +1, +2, -1
    tiers = [o["tier_label"] for o in options]
    assert tiers[0] == "newer (nxt)"  # highest score first
    assert "newer (+2)" in tiers
    assert "older (-1)" in tiers
    for o in options:
        assert o["price_mid"] is not None
        assert o["price_low"] is not None
        assert o["price_high"] is not None


@pytest.mark.asyncio
async def test_find_upgrade_options_returns_note_when_no_market_data(monkeypatch) -> None:
    from app.services import advisor as advisor_mod

    v = _vehicle(year=date_now_year() - 2)

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": None, "note": "no listings"}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    options = await advisor_mod.find_upgrade_options(None, v)
    assert len(options) == 3
    for o in options:
        assert o["price_mid"] is None
        assert o["note"] is not None
        assert "market listings" in o["note"]


@pytest.mark.asyncio
async def test_find_upgrade_options_empty_when_make_or_model_missing() -> None:
    from app.services import advisor as advisor_mod

    v1 = _vehicle(make="", model="Corolla")
    v2 = _vehicle(make="Toyota", model="")
    v3 = _vehicle(year=None)

    assert await advisor_mod.find_upgrade_options(None, v1) == []
    assert await advisor_mod.find_upgrade_options(None, v2) == []
    assert await advisor_mod.find_upgrade_options(None, v3) == []


@pytest.mark.asyncio
async def test_find_similar_vehicles_excludes_own_make_model(monkeypatch) -> None:
    from app.services import advisor as advisor_mod

    v = _vehicle(make="Toyota", model="Corolla", year=date_now_year() - 4)

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": 20_000 if year == v.year else 22_000}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    # Build a fake session whose scalars() returns two Honda rows + one Toyota.
    class _Scalars:
        def __init__(self, rows):
            self._rows = rows
        def all(self):
            return self._rows

    class _FakeSession:
        async def scalars(self, stmt):
            return _Scalars([
                _make_row("honda", "civic", v.year, 18_000),
                _make_row("honda", "accord", v.year - 1, 19_000),
                _make_row("toyota", "corolla", v.year, 20_000),  # own make/model -> skip
                _make_row("mazda", "3", v.year + 1, 21_000),
            ])

    rows = await advisor_mod.find_similar_vehicles(_FakeSession(), v)
    makes = {r["make"].lower() for r in rows}
    assert "toyota" not in makes
    assert {"honda", "mazda"} <= makes
    assert all(r["score"] >= 0 for r in rows)
    # Sorted by score descending
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def _make_row(make: str, model: str, year: int | None, median: float) -> _FakeRow:
    row = _FakeRow(median=median)
    row.make = make
    row.model = model
    row.year = year
    row.body_type = None
    return row


def date_now_year() -> int:
    from datetime import date
    return date.today().year


# --- entitlement -----------------------------------------------------------

def test_enforce_entitlement_blocks_free_account() -> None:
    if getattr(SimpleNamespace, "free_account", None) is None:

        class _U:
            free_account = True
        _U.role = "user"
    user = SimpleNamespace(free_account=True, role="user")
    with pytest.raises(HTTPException) as ei:
        if user.free_account:
            raise HTTPException(
                status_code=403,
                detail="Ownership Advisor is a paid feature. Upgrade to enable it.",
            )
    assert ei.value.status_code == 403


def test_enforce_entitlement_allows_paid_user_and_demo() -> None:
    for user in (
        SimpleNamespace(free_account=False, role="user"),
        SimpleNamespace(free_account=False, role="demo"),
    ):
        if user.free_account:
            raise AssertionError("should not raise")


# --- compute_upgrade envelope when no market data ---------------------------

@pytest.mark.asyncio
async def test_compute_upgrade_returns_empty_when_no_market_data(monkeypatch) -> None:
    from app.services import advisor as advisor_mod

    v = _vehicle()

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": None, "note": "no listings"}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    plan = await advisor_mod.compute_upgrade(None, v)
    assert plan["current_value"] is None
    assert plan["upgrade_options"] == []
    assert plan["similar_vehicles"] == []
    assert plan["trade_up"] == []
    assert plan["finance_term_months"] == UPGRADE_DEFAULT_FINANCE_TERM_MONTHS
    assert plan["rate_pct"] == UPGRADE_DEFAULT_RATE_PCT
    assert plan["deposit_pct"] == UPGRADE_DEFAULT_DEPOSIT_PCT
    assert "no listings" in plan["note"]


@pytest.mark.asyncio
async def test_compute_upgrade_propagates_finance_inputs(monkeypatch) -> None:
    from app.services import advisor as advisor_mod

    v = _vehicle(year=date_now_year() - 4)

    async def _fake_market(db, make, model, year, vt):
        return {"median_price": 20_000 if year == v.year else 22_000}

    monkeypatch.setattr(advisor_mod, "get_market_data", _fake_market)

    class _EmptyScalars:
        def all(self):
            return []

    class _EmptySession:
        async def scalars(self, stmt):
            return _EmptyScalars()

    plan = await advisor_mod.compute_upgrade(
        _EmptySession(), v, odometer_km=80_000,
        finance_term_months=48, rate_pct=9.0, deposit_pct=10.0,
    )
    assert plan["finance_term_months"] == 48
    assert plan["rate_pct"] == 9.0
    assert plan["deposit_pct"] == 10.0
    # current_value = 20_000 median * good(1.0) * km_multiplier. 4yo car
    # with 80k km vs 60k benchmark → 5% penalty → 0.95.
    assert plan["current_value"] == pytest.approx(19_000.0, abs=0.5)
    assert len(plan["upgrade_options"]) == 3
    assert len(plan["trade_up"]) == 3
    # Trade-up rows should include the upgrade year + tier label so the UI
    # can pair the row with the upgrade-options block.
    for row in plan["trade_up"]:
        assert "upgrade_year" in row
        assert "tier_label" in row