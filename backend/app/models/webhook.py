"""Webhooks for event-driven integrations (AUT-423).

A `webhook` is an HTTPS URL a developer registers to receive events
(service due, fuel entry, rego expiry, diagnostics, etc.). Each delivery
is POSTed with an HMAC-SHA256 signature (`X-Autobrain-Signature`) so the
receiver can verify authenticity.

Deliveries are tracked in `webhook_deliveries` for retry/backoff and
visibility. Failed deliveries are retried with exponential backoff up to
`max_retries` times before the webhook is paused.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


def _uuid() -> str:
    return str(uuid.uuid4())


class WebhookEventType(str, enum.Enum):
    """Canonical event types exposed by the public API."""

    SERVICE_DUE = "service.due"
    SERVICE_COMPLETED = "service.completed"
    FUEL_ENTRY = "fuel.entry"
    FUEL_RECEIPT = "fuel.receipt"
    REGO_EXPIRY = "rego.expiry"
    DIAGNOSTIC = "diagnostic.created"
    DIAGNOSTIC_RESOLVED = "diagnostic.resolved"
    VEHICLE_CREATED = "vehicle.created"
    VEHICLE_UPDATED = "vehicle.updated"
    VEHICLE_DELETED = "vehicle.deleted"
    ODOMETER_UPDATED = "odometer.updated"
    LOGBOOK_TRIP = "logbook.trip"
    NOTIFICATION = "notification.received"


class WebhookStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class Webhook(Base):
    """A registered webhook endpoint owned by a user."""

    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    # JSON array of event types this webhook subscribes to
    events: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # Secret used to sign payloads (HMAC-SHA256). Stored in plaintext because
    # it must be reproducible for signing; the raw secret is never returned
    # in API responses — only its prefix.
    secret: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_prefix: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(16), default=WebhookStatus.ACTIVE.value)
    # Max delivery attempts before pausing
    max_retries: Mapped[int] = mapped_column(Integer, default=5)
    # Current consecutive failure count (reset on success)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WebhookDelivery(Base):
    """One delivery attempt for a webhook event."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    webhook_id: Mapped[str] = mapped_column(String(36), ForeignKey("webhooks.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    # JSON payload that was (or will be) POSTed
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    # HTTP status returned, or None if the request never completed
    http_status: Mapped[int | None] = mapped_column(Integer)
    # Error message if delivery failed
    error: Mapped[str | None] = mapped_column(Text)
    # Number of attempts so far
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Next retry timestamp (null if no retry scheduled)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))