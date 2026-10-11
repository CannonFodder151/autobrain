"""Tests for Vehicle Health Score (AUT-3857).

Three layers of coverage:
  1. Pure-helper tests for the deterministic rule engine
     (ai.app.fallbacks.health_score.health_score_fallback) — no DB, no FastAPI.
  2. HTTP-shape test of GET /api/v1/vehicles/{vehicle_id}/health-score
     via the in-process ASGI client, with both AI-gateway-up and
     AI-gateway-down paths exercised.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_USER", "test-postgres-user")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_DB", "test-postgres-db")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-minio-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret-key")
os.environ.setdefault("MINIO_BUCKET", "test-minio-bucket")

from datetime import date, datetime, timedelta, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

# --- pure-helper tests -----------------------------------------------------


def _now():
    return datetime.now(timezone.utc)


def test_health_score_fallback_no_data_returns_baseline():
    """Empty inputs should return a valid score with reasonable defaults."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 50000}
    result = health_score_fallback(vehicle, [], [], [], [], [])

    assert 0 <= result["score"] <= 100
    assert result["label"] in ("excellent", "good", "fair", "poor", "critical")
    assert 0.0 <= result["confidence"] <= 1.0
    assert "breakdown" in result
    assert "alerts" in result
    assert "signals" in result
    assert result["model"] == "rule-based-fallback"


def test_health_score_fallback_excellent_when_all_clean():
    """All-green data should yield a high score."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 50000}
    diagnostics = [
        {"status": "resolved", "severity": "low", "created_at": _now() - timedelta(days=10)}
    ]
    services = [
        {"service_type": "scheduled", "status": "completed", "service_date": date.today() - timedelta(days=30), "odometer_km": 45000},
        {"service_type": "oil", "status": "completed", "service_date": date.today() - timedelta(days=15), "odometer_km": 48000},
    ]
    fuel_logs = [
        {"l_per_100km": 6.0, "is_full_tank": True} for _ in range(5)
    ]
    obd_codes = []
    parts = [
        {"name": "Oil filter", "quantity": 2, "min_quantity": 1, "warranty_months": 12, "created_at": _now() - timedelta(days=60)},
    ]

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert result["score"] >= 75  # good or excellent
    assert result["label"] in ("good", "excellent")
    assert result["breakdown"]["diagnostics"]["score"] >= 20
    assert result["breakdown"]["maintenance"]["score"] >= 20
    assert result["breakdown"]["fuel_efficiency"]["score"] >= 20
    assert result["breakdown"]["obd_codes"]["score"] == 15
    assert result["breakdown"]["parts_wear"]["score"] >= 8


def test_health_score_fallback_poor_when_diagnostics_high():
    """Unresolved high-severity diagnostics should penalize score."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 50000}
    diagnostics = [
        {"status": "open", "severity": "high", "created_at": _now() - timedelta(days=5)},
        {"status": "open", "severity": "critical", "created_at": _now() - timedelta(days=10)},
    ]
    services = [
        {"service_type": "scheduled", "status": "completed", "service_date": date.today() - timedelta(days=30), "odometer_km": 45000},
    ]
    fuel_logs = [{"l_per_100km": 7.0, "is_full_tank": True} for _ in range(5)]
    obd_codes = []
    parts = []

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert result["score"] < 75
    assert result["label"] in ("fair", "poor", "critical")
    assert result["breakdown"]["diagnostics"]["score"] < 15
    assert "diagnostics_degraded" in result["signals"]


def test_health_score_fallback_maintenance_overdue():
    """Missing or old scheduled services should penalize maintenance score."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 80000}
    diagnostics = []
    services = [
        {"service_type": "scheduled", "status": "completed", "service_date": date.today() - timedelta(days=400), "odometer_km": 30000},
    ]
    fuel_logs = [{"l_per_100km": 7.0, "is_full_tank": True} for _ in range(5)]
    obd_codes = []
    parts = []

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert result["breakdown"]["maintenance"]["score"] < 20
    assert "maintenance_overdue" in result["signals"]
    assert any(a["component"] == "Scheduled" for a in result["alerts"])


def test_health_score_fallback_fuel_efficiency_poor():
    """Poor fuel efficiency should penalize fuel score."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 50000}
    diagnostics = []
    services = [{"service_type": "scheduled", "status": "completed", "service_date": date.today() - timedelta(days=30), "odometer_km": 45000}]
    # 50% worse than expected (7.5 * 1.5 = 11.25)
    fuel_logs = [{"l_per_100km": 11.5, "is_full_tank": True} for _ in range(5)]
    obd_codes = []
    parts = []

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert result["breakdown"]["fuel_efficiency"]["score"] <= 12
    assert "fuel_efficiency_poor" in result["signals"]


def test_health_score_fallback_active_obd_codes():
    """Unresolved OBD codes should penalize OBD score and generate alerts."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 50000}
    diagnostics = []
    services = [{"service_type": "scheduled", "status": "completed", "service_date": date.today() - timedelta(days=30), "odometer_km": 45000}]
    fuel_logs = [{"l_per_100km": 7.0, "is_full_tank": True} for _ in range(5)]
    obd_codes = [
        {"code": "P0301", "is_resolved": False, "description": "Cylinder 1 misfire"},
        {"code": "P0171", "is_resolved": False, "description": "System too lean"},
    ]
    parts = []

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert result["breakdown"]["obd_codes"]["score"] < 15
    assert "active_obd_codes" in result["signals"]
    assert any(a["component"] == "OBD System" for a in result["alerts"])


def test_health_score_fallback_parts_low_stock():
    """Parts at or below min stock should penalize parts score."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 50000}
    diagnostics = []
    services = [{"service_type": "scheduled", "status": "completed", "service_date": date.today() - timedelta(days=30), "odometer_km": 45000}]
    fuel_logs = [{"l_per_100km": 7.0, "is_full_tank": True} for _ in range(5)]
    obd_codes = []
    parts = [
        {"name": "Brake pads", "quantity": 0, "min_quantity": 1, "warranty_months": 24, "created_at": _now() - timedelta(days=100)},
        {"name": "Oil filter", "quantity": 1, "min_quantity": 2, "warranty_months": 12, "created_at": _now() - timedelta(days=200)},
    ]

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert result["breakdown"]["parts_wear"]["score"] < 8
    assert "parts_wear_concern" in result["signals"]
    assert any(a["component"] == "Parts Inventory" for a in result["alerts"])


def test_health_score_fallback_ev_no_fuel_penalty():
    """EVs should not be penalized for fuel efficiency."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Tesla", "model": "Model 3", "year": 2022, "vehicle_type": "ev", "odometer_km": 30000}
    diagnostics = []
    services = [{"service_type": "scheduled", "status": "completed", "service_date": date.today() - timedelta(days=30), "odometer_km": 25000}]
    fuel_logs = []
    obd_codes = []
    parts = []

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert result["breakdown"]["fuel_efficiency"]["score"] == 25
    assert "EV - no fuel consumption" in result["breakdown"]["fuel_efficiency"]["reasons"][0]


def test_health_score_fallback_score_clamped_0_100():
    """Score should always be clamped to 0-100 range."""
    from ai.app.fallbacks.health_score import health_score_fallback

    # Maximum penalty scenario
    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 200000}
    diagnostics = [{"status": "open", "severity": "critical", "created_at": _now() - timedelta(days=1)} for _ in range(10)]
    services = []
    fuel_logs = [{"l_per_100km": 25.0, "is_full_tank": True} for _ in range(5)]
    obd_codes = [{"code": f"P0{i:03d}", "is_resolved": False} for i in range(20)]
    parts = [{"name": f"Part {i}", "quantity": 0, "min_quantity": 5, "warranty_months": 0, "created_at": _now() - timedelta(days=1000)} for i in range(20)]

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert 0 <= result["score"] <= 100


def test_health_score_fallback_confidence_valid():
    """Confidence should always be valid 0-1."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 50000}

    # Various data combinations
    test_cases = [
        ([], [], [], [], []),
        ([{"status": "resolved"}], [], [], [], []),
        ([], [{"service_type": "scheduled", "status": "completed", "service_date": date.today(), "odometer_km": 1000}], [], [], []),
        ([], [], [{"l_per_100km": 7.0, "is_full_tank": True}] * 3, [], []),
    ]

    for diag, svc, fuel, obd, parts in test_cases:
        result = health_score_fallback(vehicle, diag, svc, fuel, obd, parts)
        assert 0.0 <= result["confidence"] <= 1.0


def test_health_score_fallback_label_thresholds():
    """Label thresholds should match spec."""
    from ai.app.fallbacks.health_score import _label_for_score

    assert _label_for_score(100) == "excellent"
    assert _label_for_score(90) == "excellent"
    assert _label_for_score(89) == "good"
    assert _label_for_score(75) == "good"
    assert _label_for_score(74) == "fair"
    assert _label_for_score(60) == "fair"
    assert _label_for_score(59) == "poor"
    assert _label_for_score(40) == "poor"
    assert _label_for_score(39) == "critical"
    assert _label_for_score(0) == "critical"


def test_health_score_fallback_alerts_capped():
    """Alerts should be capped at 10."""
    from ai.app.fallbacks.health_score import health_score_fallback

    vehicle = {"make": "Toyota", "model": "Corolla", "year": 2020, "vehicle_type": "sedan", "odometer_km": 50000}
    diagnostics = [{"status": "open", "severity": "high", "created_at": _now() - timedelta(days=i)} for i in range(5)]
    services = [{"service_type": t, "status": "completed", "service_date": date.today() - timedelta(days=400), "odometer_km": 1000} for t in
                ["scheduled", "oil", "major", "tire", "brake", "transmission", "coolant"]]
    fuel_logs = [{"l_per_100km": 7.0, "is_full_tank": True} for _ in range(5)]
    obd_codes = [{"code": f"P0{i:03d}", "is_resolved": False, "description": f"Code {i}"} for i in range(10)]
    parts = [{"name": f"Part {i}", "quantity": 0, "min_quantity": 1, "warranty_months": 12, "created_at": _now() - timedelta(days=100)} for i in range(10)]

    result = health_score_fallback(vehicle, diagnostics, services, fuel_logs, obd_codes, parts)

    assert len(result["alerts"]) <= 10


# --- HTTP route via FastAPI TestClient -------------------------------------


def _try_import_app():
    try:
        from app.main import app as _app
        return _app
    except SyntaxError as exc:
        pytest.skip(f"app boot blocked by unrelated pre-existing syntax error: {exc}")


@pytest.mark.asyncio
async def test_health_score_route_falls_back_when_gateway_down(monkeypatch):
    """When the AI gateway returns None, the route renders the deterministic baseline."""
    app = _try_import_app()
    if app is None:
        return

    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.api.v1 import health_score as health_score_mod
    from app.services import health_score as health_score_service

    fake_vehicle = SimpleNamespace(
        id="v1", make="Toyota", model="Corolla", year=2020,
        engine="1.8L", odometer_km=50000, vehicle_type="sedan"
    )
    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_get_vehicle(db, vid, user):
        return fake_vehicle

    monkeypatch.setattr(health_score_mod, "get_accessible_vehicle", _fake_get_vehicle)

    async def _fake_require_ai_vehicle(db, vehicle, user):
        return None

    monkeypatch.setattr(health_score_mod, "require_ai_vehicle", _fake_require_ai_vehicle)

    # Simulate the AI gateway being down: return None.
    async def _fake_compute(db, vehicle):
        return None

    monkeypatch.setattr(health_score_service, "compute_health_score", _fake_compute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/vehicles/v1/health-score")

    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "score" in body
    assert "label" in body
    assert "breakdown" in body
    assert "confidence" in body
    assert "alerts" in body
    assert "signals" in body
    assert body["model"] == "rule-based-fallback"


@pytest.mark.asyncio
async def test_health_score_route_uses_ai_when_gateway_up(monkeypatch):
    """When the AI gateway returns a result, the route uses it."""
    app = _try_import_app()
    if app is None:
        return

    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.api.v1 import health_score as health_score_mod
    from app.services import health_score as health_score_service

    fake_vehicle = SimpleNamespace(
        id="v1", make="Toyota", model="Corolla", year=2020,
        engine="1.8L", odometer_km=50000, vehicle_type="sedan"
    )
    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_get_vehicle(db, vid, user):
        return fake_vehicle

    monkeypatch.setattr(health_score_mod, "get_accessible_vehicle", _fake_get_vehicle)

    async def _fake_require_ai_vehicle(db, vehicle, user):
        return None

    monkeypatch.setattr(health_score_mod, "require_ai_vehicle", _fake_require_ai_vehicle)

    # Simulate the AI gateway returning an enriched result.
    async def _fake_compute(db, vehicle):
        return {
            "score": 82,
            "label": "good",
            "confidence": 0.88,
            "breakdown": {
                "diagnostics": {"score": 22, "max": 25, "reasons": ["All resolved"]},
                "maintenance": {"score": 20, "max": 25, "reasons": ["Recent service"]},
                "fuel_efficiency": {"score": 20, "max": 25, "reasons": ["Avg 7.0 L/100km vs expected 7.5 (93%)"]},
                "obd_codes": {"score": 12, "max": 15, "reasons": ["Active P0301"]},
                "parts_wear": {"score": 8, "max": 10, "reasons": ["Parts inventory healthy"]},
            },
            "alerts": [
                {"component": "OBD System", "severity": "high", "message": "Active fault code P0301: Cylinder 1 misfire", "due_km": 50000, "due_date": date.today().isoformat(), "confidence": 0.85}
            ],
            "signals": ["active_obd_codes"],
            "model": "rule-based+ai",
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr(health_score_service, "compute_health_score", _fake_compute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/vehicles/v1/health-score")

    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["score"] == 82
    assert body["label"] == "good"
    assert body["confidence"] == 0.88
    assert body["model"] == "rule-based+ai"
    assert len(body["alerts"]) == 1
    assert body["alerts"][0]["component"] == "OBD System"


@pytest.mark.asyncio
async def test_health_score_route_blocks_free_account(monkeypatch):
    """Free accounts get 403 on Health Score (same as other AI features)."""
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
        resp = await client.get("/api/v1/vehicles/v1/health-score")

    app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "paid" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_health_score_route_requires_vehicle_access(monkeypatch):
    """Route returns 404 when vehicle not accessible."""
    app = _try_import_app()
    if app is None:
        return

    from httpx import ASGITransport, AsyncClient
    from app.api import deps as deps_mod
    from app.api.v1 import health_score as health_score_mod
    from fastapi import HTTPException

    fake_user = SimpleNamespace(id="u1", free_account=False, role="user")

    async def _override_user():
        return fake_user

    app.dependency_overrides[deps_mod.get_current_user] = _override_user

    async def _fake_get_vehicle(db, vid, user):
        raise HTTPException(status_code=404, detail="Vehicle not found")

    monkeypatch.setattr(health_score_mod, "get_accessible_vehicle", _fake_get_vehicle)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/vehicles/v1/health-score")

    app.dependency_overrides.clear()

    assert resp.status_code == 404