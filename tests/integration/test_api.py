"""Integration tests for API endpoint."""

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health_check():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"

def test_known_vehicle_returns_200():
    r = client.get("/api/v1/vehicles/VIN1234567890/health-score")
    assert r.status_code == 200
    data = r.json()
    assert data["vehicle_id"] == "VIN1234567890"
    assert 0 <= data["overall_score"] <= 100
    assert data["overall_status"] in ["excellent", "good", "fair", "poor", "critical"]
    assert len(data["components"]) == 6
    assert data["mileage"] == 45000

def test_known_vehicle_score_accuracy():
    r = client.get("/api/v1/vehicles/VIN1234567890/health-score")
    data = r.json()
    assert data["overall_score"] == 85.4
    assert data["overall_status"] == "good"

def test_known_vehicle_0987654321():
    r = client.get("/api/v1/vehicles/VIN0987654321/health-score")
    assert r.status_code == 200
    data = r.json()
    assert data["overall_score"] == 57.5
    assert data["overall_status"] == "poor"

def test_unknown_vehicle_404():
    r = client.get("/api/v1/vehicles/NOTFOUND/health-score")
    assert r.status_code == 404
    assert r.json()["detail"] == "Vehicle not found"

def test_empty_vehicle_id_422():
    r = client.get("/api/v1/vehicles//health-score")
    assert r.status_code == 404  # path param captures empty

def test_long_vehicle_id_422():
    long_id = "X" * 51
    r = client.get(f"/api/v1/vehicles/{long_id}/health-score")
    # max_length=50 -> 422
    assert r.status_code == 422

def test_component_statuses_match_calculation():
    r = client.get("/api/v1/vehicles/VIN1234567890/health-score")
    data = r.json()
    for comp in data["components"]:
        if comp["score"] >= 90:
            assert comp["status"] == "excellent"
        elif comp["score"] >= 75:
            assert comp["status"] == "good"
        elif comp["score"] >= 60:
            assert comp["status"] == "fair"
        elif comp["score"] >= 40:
            assert comp["status"] == "poor"
        else:
            assert comp["status"] == "critical"

def test_overall_score_is_mean_of_components():
    r = client.get("/api/v1/vehicles/VIN1234567890/health-score")
    data = r.json()
    comp_scores = [c["score"] for c in data["components"]]
    expected = round(sum(comp_scores) / len(comp_scores), 1)
    assert data["overall_score"] == expected
