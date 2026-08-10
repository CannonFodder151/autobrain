"""AUT-138: production must refuse default SECRET_KEY / DB / MinIO creds."""

import os
import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ENVIRONMENT", "SECRET_KEY", "POSTGRES_PASSWORD", "MINIO_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)


def _make(**env) -> Settings:
    for name, value in env.items():
        os.environ[name] = value
    return Settings(_env_file=None)


def test_production_refuses_default_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _make(ENVIRONMENT="production", SECRET_KEY="change-me")


def test_production_refuses_default_db_password() -> None:
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        _make(ENVIRONMENT="production", SECRET_KEY="real-secret", POSTGRES_PASSWORD="autobrain")


def test_production_refuses_default_minio_secret() -> None:
    with pytest.raises(ValidationError, match="MINIO_SECRET_KEY"):
        _make(ENVIRONMENT="production", SECRET_KEY="real-secret", MINIO_SECRET_KEY="autobrain")


def test_production_accepts_real_creds() -> None:
    s = _make(
        ENVIRONMENT="production",
        SECRET_KEY="a-64-char-random-secret-that-is-not-a-default",
        POSTGRES_PASSWORD="strong-db-pass",
        MINIO_SECRET_KEY="strong-minio-pass",
    )
    assert s.ENVIRONMENT == "production"


def test_development_accepts_defaults() -> None:
    s = _make(ENVIRONMENT="development", SECRET_KEY="change-me", POSTGRES_PASSWORD="autobrain")
    assert s.SECRET_KEY == "change-me"
