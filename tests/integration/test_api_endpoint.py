"""Integration tests for the Vehicle Health Score API endpoint."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthScoreAPI:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}

    def test_known_vehicle_returns_200(self, client):
        resp = client.get("/api/v1/vehicles/VIN1234567890/health-score")
        assert resp.status_code == 200
        data = resp.json()
        assert data["vehicle_id"] == "VIN1234567890"
        assert 0 <= data["overall_score"] <= 100
        assert data["overall_status"] in ["excellent", "good", "fair", "poor", "critical"]
        assert isinstance(data["components"], list)
        assert len(data["components"]) > 0
        assert data["mileage"] == 45000

    def test_second_known_vehicle(self, client):
        resp = client.get("/api/v1/vehicles/VIN0987654321/health-score")
        assert resp.status_code == 200
        data = resp.json()
        assert data["vehicle_id"] == "VIN0987654321"
        assert data["mileage"] == 120000

    def test_unknown_vehicle_returns_404(self, client):
        resp = client.get("/api/v1/vehicles/UNKNOWN_VIN/health-score")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Vehicle not found"

    def test_component_structure(self, client):
        resp = client.get("/api/v1/vehicles/VIN1234567890/health-score")
        data = resp.json()
        comp = data["components"][0]
        assert "name" in comp
        assert "score" in comp
        assert "status" in comp
        assert 0 <= comp["score"] <= 100

    def test_last_updated_present(self, client):
        resp = client.get("/api/v1/vehicles/VIN1234567890/health-score")
        data = resp.json()
        assert "last_updated" in data
        assert data["last_updated"] is not None