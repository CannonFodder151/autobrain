"""SQLAlchemy models: firmware manifests + serial-number whitelist."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .util import utcnow

def _uuid() -> str:
    return str(uuid.uuid4())

class FirmwareManifest(Base):
    __tablename__ = "firmware_manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    blob_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    release_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow, nullable=False,
    )

    __table_args__ = (
        # A model never has two manifests of the same version (re-publish =
        # bump the version string).
        UniqueConstraint("model", "version", name="uq_manifests_model_version"),
    )

class SerialWhitelist(Base):
    """A device serial is whitelisted only when its owning account is paid.

    Populated by the AutoBrain backend (on paid /report) so the dongle-server
    can enforce the paid-account gate without owning subscription state.
    """

    __tablename__ = "serial_whitelist"

    serial_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow, nullable=False
    )