"""AUT-188: DB/MinIO credentials must be required (fail closed), never defaulted."""

import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings

REQUIRED = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.delenv("MINIO_BUCKET", raising=False)


def _make(**env) -> Settings:
    for name, value in env.items():
        os.environ[name] = value
    return Settings(_env_file=None)


def test_missing_creds_fail_closed() -> None:
    with pytest.raises(ValidationError):
        _make()


def test_partial_creds_fail_closed() -> None:
    with pytest.raises(ValidationError):
        _make(POSTGRES_USER="u", POSTGRES_PASSWORD="p")


def test_provided_creds_ok() -> None:
    s = _make(
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        MINIO_ACCESS_KEY="a",
        MINIO_SECRET_KEY="s",
    )
    assert s.POSTGRES_PASSWORD == "p"
    assert s.MINIO_SECRET_KEY == "s"
