"""Integration tests for the Fuel Price API endpoints."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_fuel_price_wa_live():
    r = client.get("/api/v1/fuel-price/WA")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "WA"
    assert data["available"] is True
    assert data["message"] is None
    assert len(data["stations"]) >= 2
    for s in data["stations"]:
        assert "id" in s
        assert "name" in s
        assert "price_cpl" in s
        assert "freshness_minutes" in s
        assert s["freshness_minutes"] is not None
    assert data["feed_status"] is not None
    assert data["feed_status"]["state"] == "WA"
    assert data["feed_status"]["status"] == "ok"


def test_fuel_price_qld_live():
    r = client.get("/api/v1/fuel-price/QLD")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "QLD"
    assert data["available"] is True
    assert len(data["stations"]) >= 2
    assert data["feed_status"]["state"] == "QLD"
    assert data["feed_status"]["status"] == "ok"


def test_fuel_price_nsw_pending():
    r = client.get("/api/v1/fuel-price/NSW")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "NSW"
    assert data["available"] is False
    assert "pending" in data["message"].lower()


def test_fuel_price_act_pending():
    r = client.get("/api/v1/fuel-price/ACT")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is False
    assert "pending" in data["message"].lower()


def test_fuel_price_vic_pending():
    r = client.get("/api/v1/fuel-price/VIC")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is False
    assert "pending" in data["message"].lower()


def test_fuel_price_unknown_state():
    r = client.get("/api/v1/fuel-price/XX")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is False
    assert "unknown" in data["message"].lower()


def test_fuel_price_default():
    r = client.get("/api/v1/fuel-price")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "WA"
    assert data["available"] is True


def test_feed_health_all_states():
    r = client.get("/api/v1/fuel-price/feeds/health")
    assert r.status_code == 200
    data = r.json()
    assert "feeds" in data
    feeds = data["feeds"]
    assert len(feeds) == 5
    states = {f["state"] for f in feeds}
    assert states == {"WA", "QLD", "NSW", "ACT", "VIC"}
    for f in feeds:
        assert "state" in f
        assert "feed" in f
        assert "status" in f
        assert f["status"] in ["ok", "down", "pending"]


def test_case_insensitive_state():
    r = client.get("/api/v1/fuel-price/wa")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "WA"
    assert data["available"] is True