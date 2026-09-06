"""AUT-2216: ADMIN_INITIAL_PASSWORD_FILE must populate ADMIN_INITIAL_PASSWORD
when the file exists. Compose sets ADMIN_INITIAL_PASSWORD_FILE on the hosted
stack; the config must resolve it just like AI_ROUTER_API_KEY_FILE."""
import os
import tempfile

import pytest

from app.core.config import Settings


def _make(**env) -> Settings:
    os.environ.update(env)
    return Settings(_env_file=None)


def test_admin_password_loaded_from_file(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("ADMIN_INITIAL_PASSWORD", "ADMIN_INITIAL_PASSWORD_FILE"):
        monkeypatch.delenv(k, raising=False)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pwd") as f:
        f.write("s3cureP@ss\n")
        path = f.name
    try:
        s = _make(ADMIN_INITIAL_PASSWORD_FILE=path)
        assert s.ADMIN_INITIAL_PASSWORD == "s3cureP@ss"
    finally:
        os.unlink(path)


def test_admin_password_env_wins_over_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD_FILE", raising=False)
    os.environ["ADMIN_INITIAL_PASSWORD"] = "env-password"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pwd") as f:
        f.write("file-password\n")
        path = f.name
    try:
        s = _make(ADMIN_INITIAL_PASSWORD_FILE=path)
        assert s.ADMIN_INITIAL_PASSWORD == "env-password"
    finally:
        os.unlink(path)
        os.environ.pop("ADMIN_INITIAL_PASSWORD", None)


def test_admin_password_missing_file_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("ADMIN_INITIAL_PASSWORD", "ADMIN_INITIAL_PASSWORD_FILE"):
        monkeypatch.delenv(k, raising=False)
    s = _make(ADMIN_INITIAL_PASSWORD_FILE="/nonexistent/path/to/password")
    assert s.ADMIN_INITIAL_PASSWORD == ""
