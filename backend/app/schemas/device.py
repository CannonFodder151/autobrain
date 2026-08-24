"""Dongle device + unattended trip-upload schemas (AUT-918)."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from app.services.trip_gps import clean_samples


class DeviceCreate(BaseModel):
    name: str = Field(default="", max_length=80)
    vehicle_id: str | None = None


class DeviceOut(BaseModel):
    id: str
    name: str
    vehicle_id: str | None
    api_key_prefix: str
    last_seen_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceCreated(DeviceOut):
    """Create response: includes the plaintext key — the only time it exists
    server-side. The dongle/app must keep it; it cannot be recovered later."""

    api_key: str


class DeviceTripIn(BaseModel):
    """One completed trip from the dongle. `device_trip_id` is the dongle's
    stable id (derived from the RTC start time, e.g. `trip-<epoch>`) — the
    server keys `(device_id, device_trip_id)` so a WiFi retry is idempotent
    and never double-logs a trip."""

    device_trip_id: str = Field(min_length=1, max_length=64)
    started_at: datetime
    ended_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    start_odometer_km: int | None = None
    end_odometer_km: int | None = None
    distance_km: float | None = None
    purpose: str = Field(default="private", pattern="^(work|private)$")
    gps_samples: list[dict] | None = None

    @field_validator("gps_samples")
    @classmethod
    def _clean(cls, v: list[dict] | None) -> list[dict] | None:
        return clean_samples(v)


class DeviceTripsIn(BaseModel):
    trips: list[DeviceTripIn] = Field(min_length=1, max_length=64)


class DeviceTripsResult(BaseModel):
    accepted: int
    duplicates: int
    vehicle_id: str


class DeviceCodeIn(BaseModel):
    """One DTC read off the car by the dongle (mode 03)."""

    code: str = Field(min_length=1, max_length=16)
    description: str | None = None


class DeviceCodesIn(BaseModel):
    """Snapshot of the dongle's current DTC list (AUT-1573).

    The whole list replaces the previous `source=obd` rows for the bound
    vehicle; manual entries are never touched. An empty list clears the
    adapter-sourced codes (the dongle read none / they were cleared on-car).
    """

    codes: list[DeviceCodeIn] = Field(max_length=64)