"""Integration tests for demo request flow."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

def test_happy_path():
    r = client.post("/api/v1/demo/request", json={"email": "a@example.com", "name": "Alice", "company": "Acme"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "delivered"
    assert data["login_url"] == "https://demo.autobrainservice.app"

def test_spam_honeypot():
    r = client.post("/api/v1/demo/request", json={"email": "a@example.com", "honeypot": "x"})
    assert r.status_code == 422

def test_rate_limit_ip():
    for i in range(5):
        r = client.post("/api/v1/demo/request", json={"email": f"u{i}@example.com"})
        assert r.status_code == 200
    r = client.post("/api/v1/demo/request", json={"email": "extra@example.com"})
    assert r.status_code == 429

def test_rate_limit_email():
    for i in range(3):
        r = client.post("/api/v1/demo/request", json={"email": "same@example.com"})
        assert r.status_code == 200, r.text
    r = client.post("/api/v1/demo/request", json={"email": "same@example.com"})
    assert r.status_code == 429

def test_invalid_email_rejected():
    r = client.post("/api/v1/demo/request", json={"email": "not-an-email"})
    assert r.status_code == 422
