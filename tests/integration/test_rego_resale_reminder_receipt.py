"""Integration tests for new AUT-135 endpoints."""
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_rego_lookup_registered():
    r = client.get("/api/v1/rego/lookup", params={"rego": "ABC123", "state": "NSW"})
    assert r.status_code == 200
    d = r.json()
    assert d["vin"] == "MR0ABC1234567890"
    assert d["body"] == "Sedan"
    assert d["colour"] == "White"
    assert d["status"] == "registered"


def test_rego_lookup_expired():
    r = client.get("/api/v1/rego/lookup", params={"rego": "XYZ999", "state": "NSW"})
    assert r.status_code == 200
    assert r.json()["status"] == "expired"


def test_rego_lookup_empty():
    r = client.get("/api/v1/rego/lookup", params={"rego": "   ", "state": "NSW"})
    assert r.status_code == 200
    assert r.json()["status"] == "invalid"


def test_resale_estimate():
    r = client.get("/api/v1/resale/estimate", params={"make": "Toyota", "model": "Corolla", "year": 2019, "mileage": 40000})
    assert r.status_code == 200
    d = r.json()
    assert d["estimated_value"] >= d["trade_in"]
    assert 0 < d["depreciation_rate"] <= 0.1


def test_reminder_create_and_list():
    r = client.post("/api/v1/reminders", json={"vehicleId": "VIN1", "kind": "service", "dueDate": "2026-12-01", "message": "Service"})
    assert r.status_code == 200
    rid = r.json()["id"]
    lst = client.get("/api/v1/reminders", params={"vehicleId": "VIN1"})
    assert lst.status_code == 200
    assert any(x["id"] == rid for x in lst.json())


def test_receipt_scan_fallback():
    r = client.post("/api/v1/receipts/scan", files={"file": ("r.txt", b"hello", "text/plain")})
    assert r.status_code == 200
    assert r.json()["method"] == "deterministic_fallback"


def test_engineering_helper_obd_cost():
    r = client.post("/api/v1/vehicles/VIN1/engineering-helper", json={
        "vehicle_id": "VIN1", "engine_light_on": True, "fault_codes": ["P0301", "P0420"],
        "rego_valid": True, "service_interval_km": 10000, "ownership_status": "registered",
    })
    assert r.status_code == 200
    msg = r.json()["primary"]["message"]
    assert "P0301" in msg and "P0420" in msg
