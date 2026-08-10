"""Tests for AI gateway auth and payload size caps (AUT-140)."""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")
os.environ["AI_GATEWAY_API_KEY"] = "test-shared-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import MAX_BODY_BYTES, app  # noqa: E402

client = TestClient(app)


def test_health_open() -> None:
    assert client.get("/health").status_code == 200


def test_infer_requires_key() -> None:
    resp = client.post("/v1/diagnostics", json={"payload": {"symptoms": "squealing brakes"}})
    assert resp.status_code == 401


def test_infer_wrong_key_rejected() -> None:
    resp = client.post(
        "/v1/diagnostics",
        json={"payload": {"symptoms": "squealing brakes"}},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_infer_with_key_ok() -> None:
    resp = client.post(
        "/v1/diagnostics",
        json={"payload": {"symptoms": "squealing brakes"}},
        headers={"Authorization": "Bearer test-shared-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["model"].startswith("rule-based")


def test_oversized_payload_rejected() -> None:
    resp = client.post(
        "/v1/diagnostics",
        json={"payload": {"x": "a" * MAX_BODY_BYTES}},
        headers={"Authorization": "Bearer test-shared-key"},
    )
    assert resp.status_code == 413
