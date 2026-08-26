"""Dongle firmware manifest + installed-firmware telemetry (AUT-1673).

Two lightweight tables supporting BLE-over-the-air updates:

- `dongle_firmware`  — one row per released firmware build per model. The blob
  lives in MinIO (key = `dongle_firmware/{id}.bin`); the row stores only the
  manifest (model, version, sha256, size_bytes, release_notes) plus the MinIO
  key so the app can fetch a short-lived signed URL.

- `dongle_installed_firmware` — one row per (device_id). The dongle reports
  its current model, firmware version and serial number on each BLE session;
  the row lets the app surface "Update available" without a fresh BLE read
  every page load, and lets ops see fleet-wide version distribution.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DongleFirmware(Base):
    __tablename__ = "dongle_firmware"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Hardware model, e.g. "OBD Logging Device V1". Stable string the firmware
    # also reports back so the app can pick the correct manifest.
    model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # Semver-ish string the firmware echoes verbatim, e.g. "1.4.2".
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 of the raw firmware blob (hex). The app/OTA loader verifies the
    # bytes it downloads from the signed URL against this before writing to
    # flash.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # MinIO object key (NOT a URL). The app gets a fresh presigned URL each
    # request via /dongle/firmware/latest, so the key never leaves the server.
    blob_key: Mapped[str] = mapped_column(String(256), nullable=False)
    release_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # A model never has two firmwares of the same version (re-publishing is
        # an update, not a duplicate).
        UniqueConstraint("model", "version", name="uq_dongle_firmware_model_version"),
    )


class DongleInstalledFirmware(Base):
    __tablename__ = "dongle_installed_firmware"

    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    firmware_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # Serial number is flashed to NVS at provisioning (see AUT-1673). It is the
    # hardware identity a user reads off the board — exposed to the owner only.
    serial_number: Mapped[str] = mapped_column(String(64), nullable=False)
    last_reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
