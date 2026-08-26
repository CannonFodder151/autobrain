"""Dongle firmware manifest + installed-firmware telemetry schemas (AUT-1673)."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DongleFirmwareOut(BaseModel):
    """Manifest returned to the app for one model. The signed URL is short-lived."""

    model: str
    version: str
    sha256: str
    size_bytes: int
    release_notes: str | None
    created_at: datetime
    blob_url: str

    model_config = {"from_attributes": True}


class DongleInstalledFirmwareReport(BaseModel):
    """Posted by the dongle over BLE (device-authenticated)."""

    model: str = Field(min_length=1, max_length=64)
    firmware_version: str = Field(min_length=1, max_length=32)
    serial_number: str = Field(min_length=1, max_length=64)

    @field_validator("model", "firmware_version", "serial_number")
    @classmethod
    def _no_control(cls, v: str) -> str:
        # Firmware writes these from NVS; the API trusts them only after this
        # length+charset guard. Newlines/tabs would let a rogue device poison
        # future log lines or admin views.
        for ch in ("\n", "\r", "\t", "\x00"):
            if ch in v:
                raise ValueError("must not contain control characters")
        return v


class DongleInstalledFirmwareOut(BaseModel):
    """Returned to the app so it can render "Update available" without re-asking BLE."""

    model: str
    firmware_version: str
    serial_number: str
    last_reported_at: datetime

    model_config = {"from_attributes": True}


class DongleFirmwareCreate(BaseModel):
    """Admin upload payload. The blob itself is PUT to MinIO separately — this
    row records the manifest that points at it."""

    model: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=32)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0, le=16 * 1024 * 1024)
    blob_key: str = Field(min_length=1, max_length=256)
    release_notes: str | None = Field(default=None, max_length=4000)
