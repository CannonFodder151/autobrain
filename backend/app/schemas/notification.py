"""Notification preference schemas."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_DISCORD_WEBHOOK_RE = re.compile(
    r"^https://discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$"
)

class NotificationPreferenceIn(BaseModel):
    push_enabled: bool | None = None
    email_enabled: bool | None = None
    discord_enabled: bool | None = None
    service_due_days: int | None = Field(default=None, ge=0, le=365)
    service_due_km: int | None = Field(default=None, ge=0, le=100000)
    fuel_gap_km: int | None = Field(default=None, ge=0, le=100000)
    discord_webhook_url: str | None = Field(default=None, max_length=500)
    fcm_token: str | None = Field(default=None, max_length=500)

    @field_validator("discord_webhook_url")
    @classmethod
    def _validate_discord_webhook(cls, v: str | None) -> str | None:
        if v is not None and not _DISCORD_WEBHOOK_RE.match(v):
            raise ValueError(
                "Must be a valid Discord webhook URL "
                "(https://discord.com/api/webhooks/{id}/{token})"
            )
        return v


class NotificationPreferenceOut(BaseModel):
    id: str
    vehicle_id: str
    push_enabled: bool
    email_enabled: bool
    discord_enabled: bool
    service_due_days: int
    service_due_km: int
    fuel_gap_km: int
    discord_webhook_url: str | None
    fcm_token: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

