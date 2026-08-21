"""AUT-200: default creds refused in any env not explicitly 'development'.

Guards against the AUT-138 bypass where a prod stack omitting ENVIRONMENT
silently fell back to the 'development' default and accepted known creds.
"""

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


def _make(**env) -> Settings:
    for name, value in env.items():
        os.environ[name] = value
    return Settings(_env_file=None)


def _prod(**overrides) -> dict:
    base = dict(
        ENVIRONMENT="production",
        SECRET_KEY="a-real-64-char-secret-not-a-default",
        POSTGRES_PASSWORD="strong-db-pass",
        MINIO_SECRET_KEY="strong-minio-pass",
        POSTGRES_USER="u",
        MINIO_ACCESS_KEY="a",
    )
    base.update(overrides)
    return base


def test_missing_environment_fails_closed() -> None:
    with pytest.raises(ValidationError):
        _make(**{k: v for k, v in _prod().items() if k != "ENVIRONMENT"})


def test_environment_unset_default_creds_fail_closed() -> None:
    with pytest.raises(ValidationError):
        _make(SECRET_KEY="change-me", POSTGRES_PASSWORD="autobrain", MINIO_SECRET_KEY="autobrain")


def test_production_refuses_default_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _make(**_prod(SECRET_KEY="change-me"))


def test_production_refuses_default_db_password() -> None:
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        _make(**_prod(POSTGRES_PASSWORD="autobrain"))


def test_production_refuses_default_minio_secret() -> None:
    with pytest.raises(ValidationError, match="MINIO_SECRET_KEY"):
        _make(**_prod(MINIO_SECRET_KEY="autobrain"))


def test_production_accepts_real_creds() -> None:
    s = _make(**_prod())
    assert s.ENVIRONMENT == "production"


def test_development_accepts_db_defaults_but_regenerates_secret() -> None:
    """AUT-1181: dev may keep DB/MinIO defaults, but a known SECRET_KEY is
    replaced by an ephemeral random key (never used to sign tokens)."""
    s = _make(
        ENVIRONMENT="development",
        SECRET_KEY="change-me",
        POSTGRES_PASSWORD="autobrain",
        MINIO_SECRET_KEY="autobrain",
        POSTGRES_USER="u",
        MINIO_ACCESS_KEY="a",
    )
    assert s.SECRET_KEY != "change-me"
    assert len(s.SECRET_KEY) >= 64
