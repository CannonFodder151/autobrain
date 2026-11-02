"""Integration tests for the VASS engineering helper endpoint."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _payload(**kw):
    base = {
        "vehicle_id": "VIN1234567890",
        "engine_light_on": False,
        "fault_codes": [],
        "rego_valid": True,
        "service_interval_km": 10000,
        "ownership_status": "registered",
    }
    base.update(kw)
    return base


def test_clean_vehicle_all_info():
    r = client.post("/api/v1/vehicles/VIN1234567890/engineering-helper", json=_payload())
    assert r.status_code == 200
    data = r.json()
    assert data["vehicle_id"] == "VIN1234567890"
    assert data["used_fallback"] is True
    states = {g["state"] for g in data["guidances"]}
    assert states == {
        "engine_light", "rego", "service_interval", "ownership", "fuel", "ev_powertrain",
    }
    assert data["primary"]["severity"] == "info"


def test_engine_light_critical():
    r = client.post(
        "/api/v1/vehicles/VIN1234567890/engineering-helper",
        json=_payload(engine_light_on=True, fault_codes=["P0301"]),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["primary"]["state"] == "engine_light"
    assert data["primary"]["severity"] == "critical"


def test_rego_invalid_critical():
    r = client.post(
        "/api/v1/vehicles/VIN1234567890/engineering-helper",
        json=_payload(rego_valid=False, rego_expiry="2026-01-01"),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["primary"]["state"] == "rego"
    assert data["primary"]["severity"] == "critical"


def test_service_overdue():
    r = client.post(
        "/api/v1/vehicles/VIN1234567890/engineering-helper",
        json=_payload(current_mileage=20000, last_service_mileage=10000, service_interval_km=5000),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["primary"]["state"] == "service_interval"
    assert data["primary"]["severity"] == "warning"


def test_path_body_mismatch_422():
    r = client.post(
        "/api/v1/vehicles/OTHER/engineering-helper",
        json=_payload(vehicle_id="VIN1234567890"),
    )
    assert r.status_code == 422


def test_deterministic_always_produces_answer():
    # No AI model wired — fallback must always produce an answer.
    r = client.post(
        "/api/v1/vehicles/VIN1234567890/engineering-helper",
        json=_payload(),
    )
    assert r.status_code == 200
    assert r.json()["primary"]["message"]