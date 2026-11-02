"""Integration tests for Ownership Advisor endpoint."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _payload(**kw):
    base = {
        "vehicle_id": "VIN1234567890",
        "make": "Toyota",
        "model": "Corolla",
        "year": 2018,
        "mileage": 60000,
        "current_value": 18000.0,
        "replacement_cost": 25000.0,
        "upgrade_budget": 10000.0,
        "interest_rate": 0.06,
        "loan_term_months": 60,
        "dream_price": 45000.0,
        "dream_monthly_budget": 600.0,
    }
    base.update(kw)
    return base


def test_all_six_modes_returned():
    r = client.post("/api/v1/vehicles/VIN1234567890/ownership-advisor", json=_payload())
    assert r.status_code == 200
    data = r.json()
    assert data["vehicle_id"] == "VIN1234567890"
    assert data["used_fallback"] is True
    modes = [x["mode"] for x in data["results"]]
    assert modes == ["value", "replace", "upgrade", "finance", "dream", "ai_advisor"]


def test_deterministic_always_produces_answer():
    r = client.post("/api/v1/vehicles/VIN1234567890/ownership-advisor", json=_payload())
    assert r.status_code == 200
    for x in r.json()["results"]:
        assert x["detail"]
        assert isinstance(x["value"], (int, float))
        assert "breakdown" in x


def test_path_body_mismatch_422():
    r = client.post(
        "/api/v1/vehicles/OTHER/ownership-advisor",
        json=_payload(vehicle_id="VIN1234567890"),
    )
    assert r.status_code == 422
