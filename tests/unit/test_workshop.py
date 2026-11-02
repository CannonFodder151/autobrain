"""Tests for the Workshop CRUD + RBAC API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_create_workshop_requires_admin(client):
    r = client.post("/api/v1/workshops", json={"name": "Test Shop"}, headers={"X-Role": "tech"})
    assert r.status_code == 403


def test_workshop_crud_flow(client):
    r = client.post("/api/v1/workshops", json={"name": "Shop A"}, headers={"X-Role": "owner"})
    assert r.status_code == 200, r.text
    wid = r.json()["id"]

    r = client.get("/api/v1/workshops")
    assert r.status_code == 200
    assert any(w["id"] == wid for w in r.json())

    r = client.get(f"/api/v1/workshops/{wid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Shop A"

    r = client.patch(
        f"/api/v1/workshops/{wid}",
        json={"name": "Shop B"},
        headers={"X-Role": "admin"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Shop B"

    r = client.delete(f"/api/v1/workshops/{wid}", headers={"X-Role": "admin"})
    assert r.status_code == 200
    assert client.get(f"/api/v1/workshops/{wid}").status_code == 404


def test_user_management_rbac(client):
    r = client.post("/api/v1/workshops", json={"name": "Shop C"}, headers={"X-Role": "owner"})
    wid = r.json()["id"]

    r = client.post(
        f"/api/v1/workshops/{wid}/users",
        json={"username": "alice", "role": "tech"},
        headers={"X-Role": "manager"},
    )
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert r.json()["role"] == "tech"

    r = client.get(f"/api/v1/workshops/{wid}/users")
    assert r.status_code == 200
    assert any(u["id"] == uid for u in r.json())

    r = client.patch(
        f"/api/v1/workshops/{wid}/users/{uid}",
        json={"role": "manager"},
        headers={"X-Role": "manager"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "manager"

    r = client.patch(
        f"/api/v1/workshops/{wid}/users/{uid}",
        json={"role": "manager"},
        headers={"X-Role": "tech"},
    )
    assert r.status_code == 403

    r = client.delete(
        f"/api/v1/workshops/{wid}/users/{uid}",
        headers={"X-Role": "tech"},
    )
    assert r.status_code == 403

    r = client.delete(
        f"/api/v1/workshops/{wid}/users/{uid}",
        headers={"X-Role": "owner"},
    )
    assert r.status_code == 200