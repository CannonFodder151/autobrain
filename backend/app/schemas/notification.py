"""Notification preference schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class NotificationPreferenceIn(BaseModel):
    push_enabled: bool | None = None
    email_enabled: bool | None = None
    discord_enabled: bool | None = None
    service_due_days: int | None = Field(default=None, ge=0, le=365)
    service_due_km: int | None = Field(default=None, ge=0, le=100000)
    fuel_gap_km: int | None = Field(default=None, ge=0, le=100000)
    discord_webhook_url: str | None = Field(default=None, max_length=500)
    fcm_token: str | None = Field(default=None, max_length=500)


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
