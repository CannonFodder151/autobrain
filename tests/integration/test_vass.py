"""Integration tests for VASS API endpoints."""

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_vehicle_lookup_found():
    r = client.post("/api/v1/vass/lookup", json={"make": "Toyota", "model": "Hilux", "year": 2020})
    assert r.status_code == 200
    data = r.json()
    assert data["make"] == "Toyota"
    assert data["model"] == "Hilux"
    assert data["year"] == 2020
    assert data["base_vehicle_id"] == "BV001"
    assert data["vin_prefix"] == "MR0"
    assert data["compliance_status"] == "compliant"


def test_vehicle_lookup_not_found():
    r = client.post("/api/v1/vass/lookup", json={"make": "Unknown", "model": "Model", "year": 2025})
    assert r.status_code == 404
    assert r.json()["detail"] == "Vehicle not found"


def test_vin_decode_valid():
    r = client.get("/api/v1/vass/vin/MR0ABC12345678901/decode")
    assert r.status_code == 200
    data = r.json()
    assert data["vin"] == "MR0ABC12345678901"
    assert data["valid"] is True
    assert data["make"] == "Toyota"
    assert data["model"] == "Hilux"
    assert data["year"] == 2020


def test_vin_decode_invalid_length():
    r = client.get("/api/v1/vass/vin/SHORT/decode")
    assert r.status_code == 200
    data = r.json()
    assert data["vin"] == "SHORT"
    assert data["valid"] is False
    assert "VIN must be 17 characters" in data["errors"]


def test_vin_decode_unknown_prefix():
    r = client.get("/api/v1/vass/vin/ZZZABC12345678901/decode")
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    assert data["make"] is None


def test_compliance_checklist_basic():
    r = client.post("/api/v1/vass/checklist", json={"vehicle_id": "BV001"})
    assert r.status_code == 200
    data = r.json()
    assert data["vehicle_id"] == "BV001"
    assert data["total"] >= 3
    assert data["passed"] == 0
    assert data["failed"] == 0
    assert data["pending"] == data["total"]


def test_compliance_checklist_with_modifications():
    r = client.post("/api/v1/vass/checklist", json={"vehicle_id": "BV001", "modifications": ["exhaust", "engine"]})
    assert r.status_code == 200
    data = r.json()
    assert data["vehicle_id"] == "BV001"
    assert data["total"] >= 5  # base + exhaust + engine
    assert "Exhaust" in str(data["items"])
    assert "Engine" in str(data["items"])


def test_compliance_results_aggregation():
    results = [
        {"item_id": "ch001", "status": "pass", "notes": "OK"},
        {"item_id": "ch002", "status": "pass", "notes": "OK"},
        {"item_id": "ch003", "status": "fail", "notes": "Failed"},
    ]
    r = client.post("/api/v1/vass/results", json={"vehicle_id": "BV001", "results": results})
    assert r.status_code == 200
    data = r.json()
    assert data["vehicle_id"] == "BV001"
    assert data["total"] == 3
    assert data["passed"] == 2
    assert data["failed"] == 1
    assert data["score"] == 66.67
    assert data["overall_status"] == "non_compliant"


def test_compliance_results_all_pass():
    results = [
        {"item_id": "ch001", "status": "pass", "notes": "OK"},
        {"item_id": "ch002", "status": "pass", "notes": "OK"},
    ]
    r = client.post("/api/v1/vass/results", json={"vehicle_id": "BV001", "results": results})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert data["passed"] == 2
    assert data["failed"] == 0
    assert data["score"] == 100.0
    assert data["overall_status"] == "compliant"


def test_compliance_results_empty():
    r = client.post("/api/v1/vass/results", json={"vehicle_id": "BV001", "results": []})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["passed"] == 0
    assert data["failed"] == 0
    assert data["score"] == 0.0
    assert data["overall_status"] == "pending"