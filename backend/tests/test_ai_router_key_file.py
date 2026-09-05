"""AUT-2108: AI_ROUTER_API_KEY_FILE must populate AI_ROUTER_API_KEY when the
file exists. Compose sets AI_ROUTER_API_KEY_FILE; the config must read it."""
import os
import tempfile

import pytest

from app.core.config import Settings


def _make(**env) -> Settings:
    os.environ.update(env)
    return Settings(_env_file=None)


def test_router_api_key_loaded_from_file(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("AI_ROUTER_API_KEY", "AI_ROUTER_API_KEY_FILE"):
        monkeypatch.delenv(k, raising=False)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".key") as f:
        f.write("file-loaded-key\n")
        path = f.name
    try:
        s = _make(AI_ROUTER_API_KEY_FILE=path)
        assert s.AI_ROUTER_API_KEY == "file-loaded-key"
    finally:
        os.unlink(path)


def test_router_api_key_env_wins_over_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_ROUTER_API_KEY_FILE", raising=False)
    os.environ["AI_ROUTER_API_KEY"] = "env-key"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".key") as f:
        f.write("file-key\n")
        path = f.name
    try:
        s = _make(AI_ROUTER_API_KEY_FILE=path)
        assert s.AI_ROUTER_API_KEY == "env-key"
    finally:
        os.unlink(path)
        os.environ.pop("AI_ROUTER_API_KEY", None)


def test_router_api_key_missing_file_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("AI_ROUTER_API_KEY", "AI_ROUTER_API_KEY_FILE"):
        monkeypatch.delenv(k, raising=False)
    s = _make(AI_ROUTER_API_KEY_FILE="/nonexistent/path/to/key")
    assert s.AI_ROUTER_API_KEY == ""
