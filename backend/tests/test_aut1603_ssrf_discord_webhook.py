"""Tests for AUT-1603: SSRF prevention via Discord webhook URL validation."""

import pytest
from pydantic import ValidationError

from app.schemas.notification import NotificationPreferenceIn


class TestDiscordWebhookURLValidation:
    """Validate that NotificationPreferenceIn rejects non-Discord webhook URLs."""

    def test_accepts_valid_discord_webhook(self):
        pref = NotificationPreferenceIn(
            discord_webhook_url="https://discord.com/api/webhooks/1234567890/abcdefghijklmnop"
        )
        assert pref.discord_webhook_url == "https://discord.com/api/webhooks/1234567890/abcdefghijklmnop"

    def test_accepts_valid_discordapp_webhook(self):
        pref = NotificationPreferenceIn(
            discord_webhook_url="https://discordapp.com/api/webhooks/1234567890/abcdefghijklmnop"
        )
        assert "discordapp.com" in pref.discord_webhook_url

    def test_none_passes_through(self):
        pref = NotificationPreferenceIn(discord_webhook_url=None)
        assert pref.discord_webhook_url is None

    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="Must be a valid Discord webhook URL"):
            NotificationPreferenceIn(discord_webhook_url="")

    def test_rejects_cloud_metadata_url(self):
        with pytest.raises(ValidationError, match="Must be a valid Discord webhook URL"):
            NotificationPreferenceIn(
                discord_webhook_url="http://169.254.169.254/latest/meta-data/"
            )

    def test_rejects_localhost_url(self):
        with pytest.raises(ValidationError, match="Must be a valid Discord webhook URL"):
            NotificationPreferenceIn(discord_webhook_url="http://localhost:8000/admin-api/backup")

    def test_rejects_internal_service_url(self):
        with pytest.raises(ValidationError, match="Must be a valid Discord webhook URL"):
            NotificationPreferenceIn(discord_webhook_url="http://postgres:5432")

    def test_rejects_http_scheme(self):
        with pytest.raises(ValidationError, match="Must be a valid Discord webhook URL"):
            NotificationPreferenceIn(
                discord_webhook_url="http://discord.com/api/webhooks/1234567890/abcdefghijklmnop"
            )

    def test_rejects_arbitrary_path(self):
        with pytest.raises(ValidationError, match="Must be a valid Discord webhook URL"):
            NotificationPreferenceIn(
                discord_webhook_url="https://discord.com/api/webhooks/not-a-number/sometoken"
            )

    def test_rejects_double_discord_prefix(self):
        with pytest.raises(ValidationError, match="Must be a valid Discord webhook URL"):
            NotificationPreferenceIn(
                discord_webhook_url="https://discorddiscord.com/api/webhooks/12345/abc"
            )

    def test_other_fields_still_work(self):
        pref = NotificationPreferenceIn(
            discord_enabled=True,
            service_due_days=30,
            discord_webhook_url=None,
        )
        assert pref.discord_enabled is True
        assert pref.service_due_days == 30
