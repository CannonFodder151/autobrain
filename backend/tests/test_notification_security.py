"""AUT-1603: Discord webhook URLs must allowlist discord.com only (SSRF guard)."""

import re

import pytest
from pydantic import ValidationError

from app.schemas.notification import (
    NotificationPreferenceIn,
    NotificationPreferenceOut,
)

VALID = (
    "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz_-",
    "https://discordapp.com/api/webhooks/42/abc_ABC123",
)
INVALID = (
    "http://169.254.169.254/latest/meta-data/",  # AWS IMDS / SSRF
    "http://localhost:9090/",
    "https://evil.com/api/webhooks/1/x",
    "https://discord.com/admin",
    "ftp://discord.com/api/webhooks/1/x",
    "javascript:alert(1)",
    "",
)


def test_response_schema_exists_and_is_orm_compatible() -> None:
    # The preferences API uses NotificationPreferenceOut as a response_model.
    assert NotificationPreferenceOut.__name__ == "NotificationPreferenceOut"
    assert NotificationPreferenceOut.model_config.get("from_attributes") is True


@pytest.mark.parametrize("url", VALID)
def test_valid_discord_urls_accepted(url: str) -> None:
    pref = NotificationPreferenceIn(discord_webhook_url=url)
    assert pref.discord_webhook_url == url


@pytest.mark.parametrize("url", INVALID)
def test_invalid_discord_urls_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        NotificationPreferenceIn(discord_webhook_url=url)


def test_regex_matches_service_guard_pattern() -> None:
    # Keep the schema validator and the notify._send_discord guard in sync.
    from app.services import notify as _notify

    schema_re: re.Pattern = re.compile(
        r"^https://discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$"
    )
    assert _notify._DISCORD_WEBHOOK_RE.pattern == schema_re.pattern


def test_notifications_api_imports_with_response_model() -> None:
    # AUT-1603 removed the response model, which broke this import. Ensure the
    # API router loads and exposes GET/PUT against NotificationPreferenceOut.
    from app.api.v1.notifications import router

    methods = [m for r in router.routes if hasattr(r, "methods") for m in r.methods]
    assert {"GET", "PUT"}.issubset(set(methods))
