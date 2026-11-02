"""Integration tests for Track Car MVP acceptance criteria."""
from fastapi.testclient import TestClient
import pytest

from backend.app.main import app

client = TestClient(app)
import backend.app.api.v1.track as track_mod


@pytest.fixture(autouse=True)
def _reset_track_stores():
    track_mod._CARS.clear()
    track_mod._SESSIONS.clear()
    track_mod._LAPS.clear()
    track_mod._PREP.clear()
    track_mod._SERVICE.clear()
    yield


def _car():
    r = client.post("/api/track/cars", json={"baseVehicleId": "VIN1234567890", "trackOnly": True})
    assert r.status_code == 200
    return r.json()


def test_mark_track_only_isolation():
    car = _car()
    assert car["trackOnly"] is True
    assert car["baseVehicleId"] == "VIN1234567890"
    # road service history untouched: service list empty initially
    r = client.get(f"/api/track/cars/{car['id']}/service")
    assert r.status_code == 200
    assert r.json() == []


def test_prep_checklist_persists_and_completion():
    car = _car()
    s = client.post("/api/track/sessions", json={"carId": car["id"], "trackId": "t1", "date": "2026-11-01", "driverId": "d1_prep"})
    assert s.status_code == 200
    sid = s.json()["id"]
    items = [{"key": "fluids", "done": True}, {"key": "torque", "done": False}]
    r = client.post(f"/api/track/sessions/{sid}/prep", json={"items": items})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
    # patch completion
    r2 = client.patch(f"/api/track/sessions/{sid}/prep", json={"items": [{"key": "fluids", "done": True}, {"key": "torque", "done": True}], "completedAt": "2026-11-01T10:00:00Z"})
    assert r2.status_code == 200
    done = sum(1 for i in r2.json()["items"] if i["done"])
    assert done == 2


def test_lap_capture_and_summary():
    car = _car()
    s = client.post("/api/track/sessions", json={"carId": car["id"], "trackId": "t1", "date": "2026-11-01", "driverId": "d1_lap"})
    sid = s.json()["id"]
    r = client.post(f"/api/track/sessions/{sid}/laps", json={"number": 1, "timeMs": 90000, "sectors": [30000, 30000, 30000], "tyrePressures": [2.0, 2.1, 2.2, 2.3], "brakeTemps": [100.0, 110.0]})
    assert r.status_code == 200
    lap = r.json()
    assert lap["timeMs"] == 90000
    assert lap["sectors"] == [30000, 30000, 30000]
    assert lap["tyrePressures"] == [2.0, 2.1, 2.2, 2.3]
    assert lap["brakeTemps"] == [100.0, 110.0]
    r2 = client.post(f"/api/track/sessions/{sid}/laps", json={"number": 2, "timeMs": 88000, "sectors": [29000, 29500, 29500]})
    assert r2.status_code == 200
    stats = client.get("/api/track/drivers/d1_lap/stats").json()
    assert stats["bestLap"] == 88000
    assert stats["sessionsCount"] == 1


def test_tyre_pressures_and_brake_temps_stored():
    car = _car()
    s = client.post("/api/track/sessions", json={"carId": car["id"], "trackId": "t1", "date": "2026-11-01", "driverId": "d2"})
    sid = s.json()["id"]
    r = client.post(f"/api/track/sessions/{sid}/laps", json={"number": 1, "timeMs": 95000, "sectors": [], "tyrePressures": [1.8, 1.9, 2.0, 2.1], "brakeTemps": [95.0, 105.0, 100.0, 110.0]})
    assert r.status_code == 200
    data = r.json()
    assert data["tyrePressures"] == [1.8, 1.9, 2.0, 2.1]
    assert data["brakeTemps"] == [95.0, 105.0, 100.0, 110.0]


def test_service_intervals_track_hours():
    car = _car()
    r = client.post(f"/api/track/cars/{car['id']}/service", json={"kind": "oil", "trackHours": 5.0, "done": False})
    assert r.status_code == 200
    assert r.json()["trackHours"] == 5.0
    assert r.json()["mileageOrHours"] is None
    r2 = client.get(f"/api/track/cars/{car['id']}/service")
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_driver_stats_aggregate_across_sessions():
    car = _car()
    s1 = client.post("/api/track/sessions", json={"carId": car["id"], "trackId": "t1", "date": "2026-11-01", "driverId": "d3"})
    s2 = client.post("/api/track/sessions", json={"carId": car["id"], "trackId": "t1", "date": "2026-11-02", "driverId": "d3"})
    client.post(f"/api/track/sessions/{s1.json()['id']}/laps", json={"number": 1, "timeMs": 100000, "sectors": []})
    client.post(f"/api/track/sessions/{s2.json()['id']}/laps", json={"number": 1, "timeMs": 95000, "sectors": []})
    stats = client.get("/api/track/drivers/d3/stats").json()
    assert stats["bestLap"] == 95000
    assert stats["sessionsCount"] == 2
    assert stats["avgLap"] == 97500.0
    assert stats["consistency"] is not None