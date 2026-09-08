"""User notification preferences and delivery log."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class NotificationPreference(Base):
    """Per-user notification settings.

    One row per (user, vehicle). ``vehicle_id`` is nullable so a single
    user-global row (used by vehicle-independent alerts such as servo-spy fuel
    price moves, AUT-1859) can exist. ``uq_notif_user_vehicle`` covers
    per-vehicle rows; the partial ``uq_notif_user_global`` index enforces at
    most one user-global row.
    """

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "vehicle_id", name="uq_notif_user_vehicle"),
        Index(
            "uq_notif_user_global",
            "user_id",
            unique=True,
            postgresql_where=text("vehicle_id IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vehicles.id"), index=True, nullable=True
    )

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

    # Rego expiry trigger: alert when registration expires within N days.
    # Premium-only setting evaluated by the daily sweep (AUT-2416).
    rego_expiry_days: Mapped[int] = mapped_column(Integer, default=0)  # 0 = disabled

    discord_webhook_url: Mapped[str | None] = mapped_column(Text)
    fcm_token: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class NotificationDelivery(Base):
    """Tracks which notifications have been sent (dedupe per scope + kind).

    Vehicle alerts dedupe on (vehicle_id, kind); user-global alerts (e.g.
    servo-spy fuel moves, AUT-1859) dedupe on (user_id, kind) via the partial
    ``uq_notif_delivery_user_kind`` index (only rows with vehicle_id IS NULL).
    """

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "kind", name="uq_notif_delivery_vehicle_kind"),
        Index(
            "uq_notif_delivery_user_kind",
            "user_id",
            "kind",
            unique=True,
            postgresql_where=text("vehicle_id IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vehicles.id"), index=True, nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30))  # service_due_days / service_due_km / fuel_gap / fuel_price:*
    channels: Mapped[str] = mapped_column(String(100), default="email")  # comma-separated
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
