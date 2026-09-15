"""AUT-3080: CORS wildcard + credentials validator."""

import json
import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings

REQUIRED = (
    "ENVIRONMENT",
    "SECRET_KEY",
    "POSTGRES_PASSWORD",
    "MINIO_SECRET_KEY",
    "POSTGRES_USER",
    "MINIO_ACCESS_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)


def _make(**env) -> Settings:
    for name, value in env.items():
        os.environ[name] = value
    return Settings(_env_file=None)


def _base(**overrides) -> dict:
    base = dict(
        ENVIRONMENT="development",
        SECRET_KEY="change-me",
        POSTGRES_PASSWORD="autobrain",
        MINIO_SECRET_KEY="autobrain",
        POSTGRES_USER="u",
        MINIO_ACCESS_KEY="a",
    )
    base.update(overrides)
    return base


def test_wildcard_origin_rejected() -> None:
    """CORS_ALLOWED_ORIGINS=['*'] must fail at startup."""
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        _make(**_base(CORS_ALLOWED_ORIGINS=json.dumps(["*"])))


def test_explicit_origin_accepted() -> None:
    s = _make(**_base(CORS_ALLOWED_ORIGINS=json.dumps(["https://autobrainservice.app"])))
    assert "https://autobrainservice.app" in s.CORS_ALLOWED_ORIGINS


def test_empty_origins_accepted() -> None:
    s = _make(**_base())
    assert s.CORS_ALLOWED_ORIGINS == []


def test_multiple_explicit_accepted() -> None:
    origins = ["https://autobrainservice.app", "https://demo.autobrainservice.app"]
    s = _make(**_base(CORS_ALLOWED_ORIGINS=json.dumps(origins)))
    assert s.CORS_ALLOWED_ORIGINS == origins
