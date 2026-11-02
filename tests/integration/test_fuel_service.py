"""Integration tests for the Fuel & Service Record Tracking API."""
from fastapi.testclient import TestClient
import pytest

from backend.app.main import app

client = TestClient(app)
import backend.app.api.v1.fuel_service as fs


@pytest.fixture(autouse=True)
def _reset():
    fs._FUEL.clear()
    fs._SERVICE.clear()
    yield


def test_fillup_entry_and_list():
    r = client.post("/api/v1/fuel-service/fuel", json={
        "vehicleId": "VIN1", "date": "2026-10-01", "litres": 40,
        "pricePerLitre": 1.9, "odometer": 1000, "station": "BP Perth", "fuelType": "ULP",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["station"] == "BP Perth"
    assert body["fuelType"] == "ULP"
    assert body["totalCost"] == 76.0

    r2 = client.get("/api/v1/fuel-service/fuel", params={"vehicleId": "VIN1"})
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_service_record_and_list():
    r = client.post("/api/v1/fuel-service/service", json={
        "vehicleId": "VIN1", "date": "2026-10-15", "mileage": 12000,
        "cost": 250.0, "items": ["oil", "filter"],
    })
    assert r.status_code == 200
    assert r.json()["items"] == ["oil", "filter"]

    r2 = client.get("/api/v1/fuel-service/service", params={"vehicleId": "VIN1"})
    assert len(r2.json()) == 1


def test_l_per_100km_calculation():
    client.post("/api/v1/fuel-service/fuel", json={
        "vehicleId": "VIN2", "date": "2026-10-01", "litres": 40,
        "pricePerLitre": 1.9, "odometer": 1000, "station": "S", "fuelType": "ULP",
    })
    client.post("/api/v1/fuel-service/fuel", json={
        "vehicleId": "VIN2", "date": "2026-10-20", "litres": 50,
        "pricePerLitre": 1.95, "odometer": 1300, "station": "S", "fuelType": "ULP",
    })
    r = client.get("/api/v1/fuel-service/economy", params={"vehicleId": "VIN2"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["readings"]) == 1
    assert abs(data["readings"][0]["lPer100km"] - (50 / 300 * 100)) < 1e-6


def test_spending_trend():
    client.post("/api/v1/fuel-service/fuel", json={
        "vehicleId": "VIN3", "date": "2026-10-01", "litres": 40,
        "pricePerLitre": 1.9, "odometer": 1000,
    })
    client.post("/api/v1/fuel-service/service", json={
        "vehicleId": "VIN3", "date": "2026-10-10", "mileage": 10500,
        "cost": 200.0, "items": ["oil"],
    })
    r = client.get("/api/v1/fuel-service/spending", params={"vehicleId": "VIN3"})
    assert r.status_code == 200
    months = {m["month"]: m["total"] for m in r.json()["monthly"]}
    assert abs(months["2026-10"] - (76.0 + 200.0)) < 1e-6


def test_tax_export_claimable():
    client.post("/api/v1/fuel-service/fuel", json={
        "vehicleId": "VIN4", "date": "2026-10-01", "litres": 40,
        "pricePerLitre": 1.9, "odometer": 1000,
    })
    client.post("/api/v1/fuel-service/service", json={
        "vehicleId": "VIN4", "date": "2026-10-10", "mileage": 10500,
        "cost": 200.0, "items": ["oil"],
    })
    r = client.get("/api/v1/fuel-service/tax-export", params={"vehicleId": "VIN4", "businessUsePct": 50})
    assert r.status_code == 200
    text = r.text
    assert "fuel,2026-10-01,76.0,50.0,38.0" in text
    assert "service,2026-10-10,200.0,50.0,100.0" in text