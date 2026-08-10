"""Regression tests for AUT-203 S1: WebSocket channel takeover.

The /ws/{user_id} endpoint must reject anonymous / mismatched connections
(fail closed) and only serve a user their own channel. Fail against the old
code (no auth at all: anonymous connections accepted).
"""

import os

os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost/test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402
from app.ws.manager import manager  # noqa: E402


class _FakeUser:
    def __init__(self, user_id: str, is_active: bool = True) -> None:
        self.id = user_id
        self.is_active = is_active


class _StubDB:
    """DB-free stand-in for the async session used by authenticate_ws."""

    def __init__(self, users: dict[str, _FakeUser]) -> None:
        self._users = users

    async def get(self, model, user_id: str):  # noqa: A002 (model ignored)
        return self._users.get(user_id)


@pytest.fixture()
def client():
    db = _StubDB({"alice": _FakeUser("alice"), "carol": _FakeUser("carol", is_active=False)})

    async def _override_db():
        yield db

    # No context manager: TestClient only runs the app lifespan on __enter__,
    # and lifespan would try to init the (absent) dev database.
    c = TestClient(app)
    app.dependency_overrides[get_db] = _override_db
    yield c
    app.dependency_overrides.pop(get_db, None)
    manager._connections.clear()
    c.close()


def test_ws_rejects_anonymous(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/alice"):
            pass
    assert exc_info.value.code == 4401


def test_ws_rejects_bad_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/alice?token=not-a-real-token"):
            pass
    assert exc_info.value.code == 4401


def test_ws_rejects_inactive_user(client: TestClient) -> None:
    token = create_access_token("carol")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/carol?token={token}"):
            pass
    assert exc_info.value.code == 4401


def test_ws_rejects_identity_mismatch(client: TestClient) -> None:
    token = create_access_token("alice")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/bob?token={token}"):
            pass
    assert exc_info.value.code == 4401
    # The attacker's connection must not have been registered on bob's channel.
    assert not manager._connections.get("bob")


def test_ws_accepts_own_authed_channel(client: TestClient) -> None:
    token = create_access_token("alice")
    with client.websocket_connect(f"/ws/alice?token={token}") as ws:
        assert ws.receive_json()["event"] == "connected"
    assert "alice" in manager._connections
