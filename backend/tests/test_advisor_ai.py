"""Tests for the AI Advisor module (AUT-2450).

Three layers of coverage, matching the pattern in
``test_advisor_value.py``:

  1. Pure-helper tests for the deterministic rule tree
     (``app.services.advisor.compute_advisor_recommendation`` and the
     AI-gateway fallback) — no DB, no FastAPI.
  2. Envelope-shape tests via direct Pydantic validation
     (``app.schemas.advisor.AdvisorAIData`` + ``AdvisorResponse``).
  3. HTTP-shape test of ``POST /api/v1/advisor/ai`` via the in-process
     ASGI client, with both the AI-gateway-up and AI-gateway-down paths
     exercised.

The test path is structured to avoid loading the pre-existing
``fuel_prices`` syntax bug (unrelated to this feature).
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


@pytest.mark.asyncio
async def test_compute_advisor_recommendation_keep_when_no_gap() -> None:
    """Mid-range funding gap (25-75%) and no dream -> default to keep."""
    from app.services.advisor import compute_advisor_recommendation

    modules = {
        "value": {"mid": 20_000.0, "low": 18_400.0, "high": 21_600.0},
        "replace": {"used_replacement_cost": 28_000.0, "funding_gap": 8_000.0},
        "upgrade": {},
        "finance": {"monthly": 350.0},
        "dream": {},
    }
    out = await compute_advisor_recommendation(modules)
    assert out["decision"] == "keep"
    assert 0.0 <= out["confidence"] <= 1.0
    assert isinstance(out["rationale"], str) and out["rationale"]
    assert 0 <= len(out["next_actions"]) <= 3
    assert out["based_on"]["value"] is True
    assert out["based_on"]["replace"] is True
    assert out["based_on"]["upgrade"] is False
    assert out["model"] == "rule-based-fallback"


@pytest.mark.asyncio
async def test_compute_advisor_recommendation_upgrade_when_gap_small() -> None:
    """Funding gap <= 25% of value => upgrade."""
    from app.services.advisor import compute_advisor_recommendation

    modules = {
        "value": {"mid": 20_000.0},
        "replace": {"used_replacement_cost": 24_000.0, "funding_gap": 4_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {},
    }
    out = await compute_advisor_recommendation(modules)
    assert out["decision"] == "upgrade"


@pytest.mark.asyncio
async def test_compute_advisor_recommendation_delay_when_gap_huge() -> None:
    """Funding gap > 75% of value => delay."""
    from app.services.advisor import compute_advisor_recommendation

    modules = {
        "value": {"mid": 20_000.0},
        "replace": {"used_replacement_cost": 50_000.0, "funding_gap": 30_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {},
    }
    out = await compute_advisor_recommendation(modules)
    assert out["decision"] == "delay"
    assert out["confidence"] <= 0.55  # low confidence on delay with weak signal


@pytest.mark.asyncio
async def test_compute_advisor_recommendation_strategy_when_dream_affordable() -> None:
    """An affordable dream where upgrade isn't a clear win => strategy."""
    from app.services.advisor import compute_advisor_recommendation

    modules = {
        "value": {"mid": 20_000.0},
        "replace": {"used_replacement_cost": 30_000.0, "funding_gap": 10_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {"affordability": "affordable"},
    }
    out = await compute_advisor_recommendation(modules)
    assert out["decision"] == "strategy"


@pytest.mark.asyncio
async def test_compute_advisor_recommendation_handles_empty_modules() -> None:
    """All-empty modules => keep with low confidence, no crash."""
    from app.services.advisor import compute_advisor_recommendation

    out = await compute_advisor_recommendation({})
    assert out["decision"] in ("keep", "delay")
    assert 0.0 <= out["confidence"] <= 1.0
    assert isinstance(out["rationale"], str)
    assert all(out["based_on"][m] is False for m in ("value", "replace", "upgrade", "finance", "dream"))


@pytest.mark.asyncio
async def test_compute_advisor_recommendation_rationale_capped_at_280_chars() -> None:
    """Rationale is always <= 280 chars so the UI never overflows."""
    from app.services.advisor import compute_advisor_recommendation

    modules = {
        "value": {"mid": 1_000_000.0},
        "replace": {"used_replacement_cost": 2_000_000.0, "funding_gap": 1_000_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {"affordability": "affordable"},
    }
    out = await compute_advisor_recommendation(modules)
    assert len(out["rationale"]) <= 280


@pytest.mark.asyncio
async def test_compute_advisor_recommendation_never_invents_numbers() -> None:
    """Rationale numbers must be derivable from the supplied modules.

    If a number appears in the rationale, the same value (rounded) must
    appear in one of the supplied module dicts. This is the hard
    contract per docs/ownership-advisor.md.
    """
    import re
    from app.services.advisor import compute_advisor_recommendation

    modules = {
        "value": {"mid": 17_500.0},
        "replace": {"funding_gap": 4_500.0},
        "upgrade": {},
        "finance": {},
        "dream": {},
    }
    out = await compute_advisor_recommendation(modules)
    mentioned = re.findall(r"\$([\d,]+)", out["rationale"])
    supplied_values = {"17500", "4500"}
    for m in mentioned:
        m_clean = m.replace(",", "")
        assert m_clean in supplied_values, f"rationale mentions ${m} but it wasn't supplied"


# --- AI gateway fallback (mirror) -------------------------------------------
# The AI gateway lives in a separate Python package (``ai/``). Its tests
# run from ``ai/tests/test_advisor.py``; this file exercises the
# backend-side mirror only.


# --- envelope shape via direct Pydantic validation -------------------------


def test_advisor_ai_data_schema_envelope_shape() -> None:
    from app.schemas.advisor import (
        AdvisorAIBasedOn,
        AdvisorAIData,
        AdvisorResponse,
    )

    data = AdvisorAIData(
        decision="upgrade",
        confidence=0.82,
        rationale="Gap is bridgeable.",
        next_actions=["shortlist 2-3 candidates", "budget for inspections"],
        based_on=AdvisorAIBasedOn(value=True, replace=True, upgrade=False, finance=False, dream=False),
    )
    factors = {"vehicle": {"id": "v1", "make": "Toyota", "model": "Corolla", "year": 2018}, "router_provenance": "9router/<combo>"}
    resp = AdvisorResponse(
        module="ai",
        vehicle_id="v1",
        generated_at=datetime.now(timezone.utc),
        model="9router/<combo>",
        data=data.model_dump(),
        factors=factors,
    )
    out = resp.model_dump()
    assert out["module"] == "ai"
    assert out["vehicle_id"] == "v1"
    assert out["model"] == "9router/<combo>"
    assert out["data"]["decision"] == "upgrade"
    assert out["data"]["confidence"] == 0.82
    assert out["data"]["based_on"]["value"] is True
    assert out["data"]["based_on"]["dream"] is False
    assert out["factors"]["router_provenance"] == "9router/<combo>"


def test_advisor_ai_request_schema_accepts_optional_fields() -> None:
    from app.schemas.advisor import AdvisorAIRequest

    req = AdvisorAIRequest()
    assert req.question is None
    assert req.value is None
    assert req.replace is None
    assert req.upgrade is None
    assert req.finance is None
    assert req.dream is None


def test_advisor_ai_request_rejects_oversized_question() -> None:
    from pydantic import ValidationError
    from app.schemas.advisor import AdvisorAIRequest

    with pytest.raises(ValidationError):
        AdvisorAIRequest(question="x" * 501)


# --- HTTP route via FastAPI TestClient -------------------------------------


def _try_import_app():
    try:
        from app.main import app as _app  # type: ignore
        return _app
    except SyntaxError as exc:
        pytest.skip(f"app boot blocked by unrelated pre-existing syntax error: {exc}")


@pytest.mark.asyncio
async def test_advisor_ai_route_falls_back_when_gateway_down(monkeypatch) -> None:
    """When the AI gateway returns None, the route renders the deterministic baseline."""
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.api.v1 import advisor as advisor_mod
    from app.services import ai_client

    fake_vehicle = SimpleNamespace(id="v1", make="Toyota", model="Corolla", year=2018)
    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_get_vehicle(db, vid, user):
        return fake_vehicle

    monkeypatch.setattr(advisor_mod, "get_accessible_vehicle", _fake_get_vehicle)
    # Simulate the AI gateway being down: return None.
    async def _fake_run(vehicle_id, modules):
        return None
    monkeypatch.setattr(advisor_mod, "run_advisor_ai", _fake_run)
    # Reset the in-process cache so a previous run can't leak.
    ai_client._ADVISOR_CACHE.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/advisor/ai",
            params={"vehicle_id": "v1"},
            json={
                "question": "should I keep it?",
                "value": {"mid": 20_000.0},
                "replace": {"funding_gap": 8_000.0},
                "upgrade": {},
                "finance": {"monthly": 350.0},
                "dream": {},
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == "ai"
    assert body["vehicle_id"] == "v1"
    assert body["model"] == "rule-based-fallback"
    assert body["data"]["decision"] == "keep"
    assert isinstance(body["data"]["rationale"], str) and body["data"]["rationale"]
    assert body["factors"]["fallback_reason"] == "ai_gateway_unreachable"
    assert body["factors"]["router_provenance"] is None


@pytest.mark.asyncio
async def test_advisor_ai_route_uses_ai_when_gateway_up(monkeypatch) -> None:
    """When the AI gateway returns a decision, the route uses it."""
    app = _try_import_app()
    if app is None:
        return
    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.api.v1 import advisor as advisor_mod
    from app.services import ai_client

    fake_vehicle = SimpleNamespace(id="v1", make="Toyota", model="Corolla", year=2018)
    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_get_vehicle(db, vid, user):
        return fake_vehicle

    monkeypatch.setattr(advisor_mod, "get_accessible_vehicle", _fake_get_vehicle)
    async def _fake_run(vehicle_id, modules):
        return {
            "decision": "upgrade",
            "confidence": 0.9,
            "rationale": "AI says upgrade now.",
            "next_actions": ["book a test drive", "compare finance offers"],
            "based_on": {"value": True, "replace": True, "upgrade": True, "finance": True, "dream": False},
            "model": "9router/<combo>",
        }
    monkeypatch.setattr(advisor_mod, "run_advisor_ai", _fake_run)
    ai_client._ADVISOR_CACHE.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/advisor/ai",
            params={"vehicle_id": "v1"},
            json={
                "value": {"mid": 20_000.0},
                "replace": {"funding_gap": 4_000.0},
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == "ai"
    assert body["model"] == "9router/<combo>"
    assert body["data"]["decision"] == "upgrade"
    assert body["data"]["confidence"] == 0.9
    assert body["factors"]["router_provenance"] == "9router/<combo>"
    assert "fallback_reason" not in body["factors"]


@pytest.mark.asyncio
async def test_advisor_ai_route_blocks_free_account(monkeypatch) -> None:
    """Free accounts get 403 on AI Advisor (same as every advisor module)."""
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
            "/api/v1/advisor/ai",
            params={"vehicle_id": "v1"},
            json={"value": {"mid": 1.0}},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "paid" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_advisor_cache_dedupes_repeat_calls(monkeypatch) -> None:
    """Identical module outputs hit the cache; the AI gateway is only called once."""
    from app.services import ai_client

    ai_client._ADVISOR_CACHE.clear()
    calls = {"n": 0}

    async def _fake_call(module, payload):
        calls["n"] += 1
        return {
            "decision": "keep",
            "confidence": 0.6,
            "rationale": "cached",
            "next_actions": [],
            "based_on": {"value": True, "replace": False, "upgrade": False, "finance": False, "dream": False},
            "model": "9router/<combo>",
        }

    monkeypatch.setattr(ai_client, "_call", _fake_call)
    modules = {"value": {"mid": 1.0}, "replace": None, "upgrade": None, "finance": None, "dream": None, "question": None}
    r1 = await ai_client.run_advisor_ai("v1", modules)
    r2 = await ai_client.run_advisor_ai("v1", modules)
    assert calls["n"] == 1
    assert r1 == r2
    # Different module outputs => cache miss.
    modules2 = {**modules, "value": {"mid": 2.0}}
    r3 = await ai_client.run_advisor_ai("v1", modules2)
    assert calls["n"] == 2
    assert r3 is not None
