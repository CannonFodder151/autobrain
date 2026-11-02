"""Integration tests for the fuel watchlist/alert API."""

from fastapi.testclient import TestClient

from backend.app.main import app
from app.api.v1 import fuel_watchlist

client = TestClient(app)


def _reset():
    fuel_watchlist._WATCHES.clear()
    fuel_watchlist._NOTIFICATIONS.clear()


def test_create_and_list_watch():
    _reset()
    r = client.post("/api/v1/fuel-watchlist", json={
        "station_id": "wa-1",
        "state": "WA",
        "fuel_type": "ULP",
        "threshold_pct": 5.0,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["station_id"] == "wa-1"
    assert data["station_name"] == "BP Perth CBD"
    assert data["active"] is True

    listing = client.get("/api/v1/fuel-watchlist").json()
    assert len(listing) == 1
    assert listing[0]["id"] == data["id"]


def test_patch_and_delete_watch():
    _reset()
    r = client.post("/api/v1/fuel-watchlist", json={
        "station_id": "wa-1",
        "state": "WA",
        "fuel_type": "ULP",
        "threshold_pct": 5.0,
    })
    wid = r.json()["id"]

    patched = client.patch(
        f"/api/v1/fuel-watchlist/{wid}",
        json={"threshold_pct": 8.0, "active": False},
    )
    assert patched.status_code == 200
    assert patched.json()["threshold_pct"] == 8.0
    assert patched.json()["active"] is False

    assert client.delete(f"/api/v1/fuel-watchlist/{wid}").status_code == 200
    assert client.get("/api/v1/fuel-watchlist").json() == []


def test_check_alerts_triggers_on_threshold():
    _reset()
    r = client.post("/api/v1/fuel-watchlist", json={
        "station_id": "wa-1",
        "state": "WA",
        "fuel_type": "ULP",
        "threshold_pct": 5.0,
    })
    wid = r.json()["id"]

    # First check records baseline price (189.9) with no alert.
    client.post("/api/v1/fuel-watchlist/check-alerts")
    assert client.get("/api/v1/fuel-watchlist/notifications").json() == []

    # Force a price move past threshold.
    fuel_watchlist._WATCHES[wid]["last_price"] = 170.0
    triggered = client.post("/api/v1/fuel-watchlist/check-alerts").json()
    assert len(triggered) == 1
    alert = triggered[0]
    assert alert["watch_id"] == wid
    assert alert["direction"] == "up"
    assert abs(alert["change_pct"]) >= 5.0
    assert alert["previous_price"] == 170.0
    assert alert["current_price"] == 189.9

    notifications = client.get("/api/v1/fuel-watchlist/notifications").json()
    assert len(notifications) == 1
    assert notifications[0]["watch_id"] == wid


def test_check_alerts_qld_station():
    _reset()
    client.post("/api/v1/fuel-watchlist", json={
        "station_id": "qld-1",
        "state": "QLD",
        "fuel_type": "ULP",
        "threshold_pct": 5.0,
    })
    client.post("/api/v1/fuel-watchlist/check-alerts")
    assert client.get("/api/v1/fuel-watchlist/notifications").json() == []


def test_check_alerts_qld_station_triggers_on_threshold():
    _reset()
    r = client.post("/api/v1/fuel-watchlist", json={
        "station_id": "qld-1",
        "state": "QLD",
        "fuel_type": "ULP",
        "threshold_pct": 5.0,
    })
    wid = r.json()["id"]

    client.post("/api/v1/fuel-watchlist/check-alerts")
    assert client.get("/api/v1/fuel-watchlist/notifications").json() == []

    fuel_watchlist._WATCHES[wid]["last_price"] = 180.0
    triggered = client.post("/api/v1/fuel-watchlist/check-alerts").json()
    assert len(triggered) == 1
    alert = triggered[0]
    assert alert["watch_id"] == wid
    assert alert["direction"] == "up"
    assert abs(alert["change_pct"]) >= 5.0
    assert alert["previous_price"] == 180.0
    assert alert["current_price"] == 192.3

    notifications = client.get("/api/v1/fuel-watchlist/notifications").json()
    assert len(notifications) == 1
    assert notifications[0]["watch_id"] == wid


def test_404_on_missing_watch():
    _reset()
    assert client.patch("/api/v1/fuel-watchlist/nope", json={"active": True}).status_code == 404
    assert client.delete("/api/v1/fuel-watchlist/nope").status_code == 404