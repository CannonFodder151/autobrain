"""User notification preferences and delivery log."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class NotificationPreference(Base):
    """Per-user, per-vehicle notification settings."""

    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "vehicle_id", name="uq_notif_user_vehicle"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)

    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    discord_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Service-due triggers: alert when next service is within this many days
    # OR within this many km of the vehicle's current odometer.
    service_due_days: Mapped[int] = mapped_column(Integer, default=7)
    service_due_km: Mapped[int] = mapped_column(Integer, default=500)

    # Fuel-driven trigger: alert when the vehicle has travelled this many km
    # since the last logged fuel fill (encourages logging / shows gaps).
    fuel_gap_km: Mapped[int] = mapped_column(Integer, default=0)  # 0 = disabled

    discord_webhook_url: Mapped[str | None] = mapped_column(Text)
    fcm_token: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class NotificationDelivery(Base):
    """Tracks which notifications have been sent (dedupe per vehicle + kind)."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "kind", name="uq_notif_delivery_vehicle_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # service_due_days / service_due_km / fuel_gap
    channels: Mapped[str] = mapped_column(String(100), default="email")  # comma-separated
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
