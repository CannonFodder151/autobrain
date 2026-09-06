"""Dongle (trip-logger) device for unattended WiFi upload (AUT-918).

A `device` is a piece of AutoBrain hardware (esp32-diy board, BLE dongle, …)
owned by one user. It authenticates to the upload surface with a
user-generated opaque `device_api_key` (see app.services.device_keys) rather
than a short-lived JWT, because it uploads unattended long after the phone
session that provisioned it ended.

`vehicle_id` is the dongle ↔ vehicle binding: the owning user picks the car
in-app, and every trip the dongle uploads lands in that vehicle's logbook.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Key lookup narrows by this short prefix index, then the full hash is
    # compared (see app.services.device_keys). The raw key is never stored.
    api_key_prefix: Mapped[str] = mapped_column(String(10), index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vehicle_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("vehicles.id"))
    # AUT-2706: last vehicle type classification from the dongle (0=unknown/1=ICE/2=EV/3=HEV/4=PHEV)
    vehicle_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )