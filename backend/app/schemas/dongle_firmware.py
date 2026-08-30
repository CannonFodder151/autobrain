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
    """Posted by the dongle over BLE (device-authenticated).

    The dongle proves its identity via X-Device-API-Key, but the NVS values it
    reports are NOT trusted: every field is bounded by length AND a tight
    charset whitelist so a compromised/malicious board cannot inject stored XSS
    (rendered in the admin UI) or SQL-meta characters. This is defence-in-depth —
    the SQLAlchemy write path is parameterised regardless, so this exists to keep
    the stored strings safe to display. Firmware identifiers are alphanumeric
    with a small punctuation set; anything else is rejected here.
    """

    # Whitelist: alphanumerics, space, and the punctuation that legitimately
    # appears in model names / semver versions / serial numbers. Explicitly
    # excludes < > " ' ; ` \ and all control chars (XSS + SQLi surface).
    _safe_text = r"^[A-Za-z0-9 .,_/()-]+$"

    model: str = Field(min_length=1, max_length=64, pattern=_safe_text)
    firmware_version: str = Field(min_length=1, max_length=32, pattern=_safe_text)
    serial_number: str = Field(min_length=1, max_length=64, pattern=_safe_text)

    @field_validator("model", "firmware_version", "serial_number")
    @classmethod
    def _no_control(cls, v: str) -> str:
        # Belt-and-suspenders: the Field pattern above already excludes control
        # chars; this guard surfaces an explicit message and rejects NUL even if
        # a future caller loosens the pattern.
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
    # esptool / MinIO emit hex in either case; accept both.
    sha256: str = Field(pattern=r"(?i)^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0, le=16 * 1024 * 1024)
    blob_key: str = Field(min_length=1, max_length=256)
    release_notes: str | None = Field(default=None, max_length=4000)
