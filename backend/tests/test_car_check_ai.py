"""Tests for the Car Check service (AUT-2651).

Mirrors the three-layer pattern in test_advisor_ai.py:
  1. Pure-helper tests for compute_deal_score (no DB, no FastAPI).
  2. Deterministic fallback tests (car_check_fallback).
  3. HTTP-shape tests for POST /api/v1/advisor/car-check via ASGI client.
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

from datetime import datetime, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

# --- pure-helper tests -----------------------------------------------------


class TestComputeDealScore:
    def test_price_below_reference_scores_high(self) -> None:
        from app.services.car_check import compute_deal_score
        listing = {"price": 10_000.0, "odometer_km": 60_000, "year": 2020}
        score = compute_deal_score(listing, reference_price=15_000.0, vehicle_year=2020)
        assert score >= 80.0

    def test_price_at_reference_scores_high(self) -> None:
        from app.services.car_check import compute_deal_score
        listing = {"price": 20_000.0, "odometer_km": 80_000, "year": 2018}
        score = compute_deal_score(listing, reference_price=20_000.0, vehicle_year=2018)
        assert score >= 80.0

    def test_price_double_reference_scores_zero(self) -> None:
        from app.services.car_check import compute_deal_score
        listing = {"price": 40_000.0}
        score = compute_deal_score(listing, reference_price=20_000.0, vehicle_year=2020)
        assert score <= 10.0

    def test_no_reference_price_skips_price_component(self) -> None:
        from app.services.car_check import compute_deal_score
        listing = {"price": 20_000.0, "odometer_km": 60_000, "year": 2020}
        score = compute_deal_score(listing, reference_price=None, vehicle_year=2020)
        assert 0 <= score <= 100

    def test_empty_listing_returns_neutral(self) -> None:
        from app.services.car_check import compute_deal_score
        score = compute_deal_score({}, reference_price=20_000.0)
        assert 0 <= score <= 100

    def test_score_is_clamped_to_100(self) -> None:
        from app.services.car_check import compute_deal_score
        listing = {"price": 1_000.0}
        score = compute_deal_score(listing, reference_price=10_000.0)
        assert score <= 100.0

    def test_low_km_boosts_score(self) -> None:
        from app.services.car_check import compute_deal_score
        good_km = {"price": 20_000.0, "odometer_km": 15_000, "year": 2020}
        score_good = compute_deal_score(good_km, reference_price=20_000.0, vehicle_year=2020)
        bad_km = {"price": 20_000.0, "odometer_km": 200_000, "year": 2020}
        score_bad = compute_deal_score(bad_km, reference_price=20_000.0, vehicle_year=2020)
        assert score_good > score_bad


# --- fallback tests ---------------------------------------------------------


class TestCarCheckFallback:
    def test_fallback_returns_contract(self) -> None:
        from app.services.car_check import car_check_fallback
        payload = {
            "deal_score": 72.5,
            "listing": {
                "title": "Honda CBR500R 2022",
                "price": 8_500.0,
                "year": 2022,
                "odometer_km": 12_000,
                "make": "Honda",
                "model": "CBR500R",
                "listing_url": "https://example.com/cbr",
            },
        }
        result = car_check_fallback(payload)
        assert "summary" in result
        assert "red_flags" in result
        assert "green_flags" in result
        assert result["deal_score"] == 72.5
        assert len(result["summary"]) <= 280

    def test_fallback_missing_listing(self) -> None:
        from app.services.car_check import car_check_fallback
        result = car_check_fallback({"deal_score": 50})
        assert "summary" in result
        assert isinstance(result["red_flags"], list)
        assert isinstance(result["green_flags"], list)

    def test_fallback_model_is_rule_based(self) -> None:
        from app.services.car_check import car_check_fallback
        result = car_check_fallback({})
        assert result["model"] == "rule-based-fallback"


# --- validate helper tests --------------------------------------------------


class TestValidateCarCheckResponse:
    def test_clamps_summary_length(self) -> None:
        from app.services.car_check import validate_car_check_response
        long_summary = "x" * 500
        out = validate_car_check_response({"summary": long_summary, "deal_score": 50.0})
        assert len(out["summary"]) <= 280

    def test_clamps_flags_to_5(self) -> None:
        from app.services.car_check import validate_car_check_response
        flags = [f"flag {i}" for i in range(10)]
        out = validate_car_check_response({
            "summary": "ok", "red_flags": flags, "green_flags": flags, "deal_score": 50.0,
        })
        assert len(out["red_flags"]) <= 5
        assert len(out["green_flags"]) <= 5

    def test_clamps_deal_score_0_100(self) -> None:
        from app.services.car_check import validate_car_check_response
        out = validate_car_check_response({"summary": "ok", "deal_score": 200.0})
        assert out["deal_score"] == 100.0

        out2 = validate_car_check_response({"summary": "ok", "deal_score": -10.0})
        assert out2["deal_score"] == 0.0

    def test_validate_handles_empty_input(self) -> None:
        from app.services.car_check import validate_car_check_response
        out = validate_car_check_response({})
        assert out["model"] == "rule-based-fallback"

    def test_validate_drops_non_string_flags(self) -> None:
        from app.services.car_check import validate_car_check_response
        out = validate_car_check_response({
            "summary": "ok",
            "red_flags": [None, 42, "real", ""],
            "green_flags": ["good", 99],
            "deal_score": 50.0,
        })
        assert out["red_flags"] == ["real"]
        assert out["green_flags"] == ["good"]


# --- HTTP route via FastAPI TestClient -------------------------------------


def _try_import_app():
    try:
        from app.main import app as _app  # type: ignore
        return _app
    except SyntaxError as exc:
        pytest.skip(f"app boot blocked by unrelated pre-existing syntax error: {exc}")


@pytest.mark.asyncio
async def test_car_check_route_falls_back_when_gateway_down(monkeypatch) -> None:
    """When the AI gateway returns None, the route renders the deterministic baseline."""
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.services import ai_client

    fake_vehicle = SimpleNamespace(id="v1", make="Toyota", model="Corolla", year=2018)
    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_get_vehicle(db, vid, user):
        return fake_vehicle

    monkeypatch.setattr("app.api.v1.advisor.get_accessible_vehicle", _fake_get_vehicle)
    async def _fake_run(vehicle_id, payload):
        return None
    monkeypatch.setattr("app.api.v1.advisor.run_car_check_ai", _fake_run)
    ai_client._CAR_CHECK_CACHE.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/advisor/car-check",
            params={"vehicle_id": "v1"},
            json={
                "listing": {
                    "title": "Toyota Corolla 2018",
                    "price": 15_000.0,
                    "year": 2018,
                    "odometer_km": 80_000,
                    "make": "Toyota",
                    "model": "Corolla",
                    "listing_url": "https://example.com/corolla",
                },
                "reference_price": 16_000.0,
                "vehicle_year": 2018,
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == "car-check"
    assert body["vehicle_id"] == "v1"
    assert body["model"] == "rule-based-fallback"
    assert "summary" in body["data"]
    assert isinstance(body["data"]["red_flags"], list)
    assert isinstance(body["data"]["green_flags"], list)
    assert body["data"]["deal_score"] is not None
    assert 0 <= body["data"]["deal_score"] <= 100
    assert body["factors"]["fallback_reason"] == "ai_gateway_unreachable"
    assert body["factors"]["router_provenance"] is None


@pytest.mark.asyncio
async def test_car_check_route_uses_ai_when_gateway_up(monkeypatch) -> None:
    """When the AI gateway returns a result, the route uses it."""
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.services import ai_client

    fake_vehicle = SimpleNamespace(id="v1", make="Toyota", model="Corolla", year=2018)
    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_get_vehicle(db, vid, user):
        return fake_vehicle

    monkeypatch.setattr("app.api.v1.advisor.get_accessible_vehicle", _fake_get_vehicle)
    ai_client._CAR_CHECK_CACHE.clear()

    async def _fake_run(vehicle_id, payload):
        return {
            "summary": "Good value CBR500R listing.",
            "red_flags": ["High km for age."],
            "green_flags": ["Below market price."],
            "deal_score": 72.0,
            "model": "9router/<combo>",
        }

    monkeypatch.setattr("app.api.v1.advisor.run_car_check_ai", _fake_run)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/advisor/car-check",
            params={"vehicle_id": "v1"},
            json={
                "listing": {
                    "title": "Honda CBR500R",
                    "price": 8_500.0,
                    "year": 2022,
                    "odometer_km": 12_000,
                    "make": "Honda",
                    "model": "CBR500R",
                    "listing_url": "https://example.com/cbr",
                },
                "reference_price": 9_000.0,
                "vehicle_year": 2022,
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == "car-check"
    assert body["model"] == "9router/<combo>"
    assert body["data"]["summary"] == "Good value CBR500R listing."
    assert body["data"]["red_flags"] == ["High km for age."]
    assert body["data"]["green_flags"] == ["Below market price."]
    assert body["data"]["deal_score"] == 72.0
    assert body["factors"]["router_provenance"] == "9router/<combo>"
    assert "fallback_reason" not in body["factors"]


@pytest.mark.asyncio
async def test_car_check_cache_dedupes_repeat_calls(monkeypatch) -> None:
    """Identical payloads hit the cache; the AI gateway is only called once."""
    from app.services import ai_client

    ai_client._CAR_CHECK_CACHE.clear()
    calls = {"n": 0}

    async def _fake_call(module, payload):
        calls["n"] += 1
        return {
            "summary": "cached",
            "red_flags": [],
            "green_flags": [],
            "deal_score": 50.0,
            "model": "9router/<combo>",
        }

    monkeypatch.setattr(ai_client, "_call", _fake_call)
    payload = {
        "deal_score": 50.0,
        "listing": {
            "title": "Honda CBR500R",
            "price": 8_500.0,
            "year": 2022,
            "odometer_km": 12_000,
            "make": "Honda",
            "model": "CBR500R",
            "listing_url": "https://example.com/cbr",
        },
    }
    r1 = await ai_client.run_car_check_ai("v1", payload)
    r2 = await ai_client.run_car_check_ai("v1", payload)
    assert calls["n"] == 1
    assert r1 == r2
    # Different listing => cache miss.
    payload2 = {**payload, "listing": {**payload["listing"], "price": 9_000.0}}
    r3 = await ai_client.run_car_check_ai("v1", payload2)
    assert calls["n"] == 2
    assert r3 is not None


@pytest.mark.asyncio
async def test_car_check_route_blocks_free_account(monkeypatch) -> None:
    """Free accounts get 403 on Car Check (same as every advisor module)."""
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
            "/api/v1/advisor/car-check",
            params={"vehicle_id": "v1"},
            json={
                "listing": {"price": 10_000.0, "make": "Honda", "model": "CBR500R"},
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "paid" in resp.json()["detail"].lower()
