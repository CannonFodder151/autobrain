"""AUT-1181: secret env guards — SECRET_KEY required, ADMIN_API_KEY min length,
STRIPE_WEBHOOK_SECRET required when Stripe is configured."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

REQUIRED = (
    "ENVIRONMENT",
    "SECRET_KEY",
    "ADMIN_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "POSTGRES_PASSWORD",
    "MINIO_SECRET_KEY",
    "POSTGRES_USER",
    "MINIO_ACCESS_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)


def _make(monkeypatch: pytest.MonkeyPatch, **env) -> Settings:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


@pytest.fixture
def make(monkeypatch: pytest.MonkeyPatch):
    return lambda **env: _make(monkeypatch, **env)


def _prod(**overrides) -> dict:
    base = dict(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 64,
        POSTGRES_PASSWORD="strong-db-pass",
        MINIO_SECRET_KEY="strong-minio-pass",
        POSTGRES_USER="u",
        MINIO_ACCESS_KEY="a",
    )
    base.update(overrides)
    return base


# ── AB-01: SECRET_KEY ───────────────────────────────────────────


def test_missing_secret_key_fails_closed_outside_dev(make) -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(**{k: v for k, v in _prod().items() if k != "SECRET_KEY"})


@pytest.mark.parametrize("placeholder", ["change-me", "change-me-to-a-long-random-string"])
def test_placeholder_secret_key_refused_outside_dev(placeholder: str, make) -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(**_prod(SECRET_KEY=placeholder))


def test_development_generates_ephemeral_secret_when_unset(make) -> None:
    dev = {k: v for k, v in _prod().items() if k != "SECRET_KEY"} | {"ENVIRONMENT": "development"}
    s = make(**dev)
    assert len(s.SECRET_KEY) >= 64
    assert make(**dev).SECRET_KEY != s.SECRET_KEY  # random per boot, never guessable


# ── AB-02: ADMIN_API_KEY min length ─────────────────────────────


def test_admin_api_key_too_short_rejected(make) -> None:
    with pytest.raises(ValidationError, match="ADMIN_API_KEY"):
        make(**_prod(ADMIN_API_KEY="short"))


def test_admin_api_key_min_length_accepted(make) -> None:
    assert make(**_prod(ADMIN_API_KEY="a" * 32)).ADMIN_API_KEY == "a" * 32


def test_admin_api_key_empty_still_disables_endpoints(make) -> None:
    assert make(**_prod()).ADMIN_API_KEY == ""


# ── AB-08: STRIPE_WEBHOOK_SECRET startup guard ──────────────────


def test_stripe_key_without_webhook_secret_rejected(make) -> None:
    with pytest.raises(ValidationError, match="STRIPE_WEBHOOK_SECRET"):
        make(**_prod(STRIPE_SECRET_KEY="sk_test_x"))


def test_stripe_pair_ok_and_stripe_off_ok(make, monkeypatch: pytest.MonkeyPatch) -> None:
    paired = make(**_prod(STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET="whsec_x"))
    assert paired.STRIPE_WEBHOOK_SECRET == "whsec_x"
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    assert make(**_prod()).STRIPE_WEBHOOK_SECRET == ""
