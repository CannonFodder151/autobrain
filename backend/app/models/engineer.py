"""Engineer marketplace models (AUT-3661).

Engineers are certified mechanics/specialists available for vehicle services.
Search supports: geospatial (postcode/radius), specialty multi-select,
minimum rating, price range, availability window.

Engineer Dashboard models (AUT-3663):
- EngineerBookingRequest: incoming booking requests from users
- EngineerCertification: certifications with expiry dates and renewal tracking
- EngineerJob: completed jobs with earnings breakdown
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.vehicle import Vehicle


def _uuid() -> str:
    return str(uuid.uuid4())


class Engineer(Base):
    __tablename__ = "engineers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Identity
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Location (geospatial search)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Professional details
    specialties: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    certifications: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    years_experience: Mapped[int | None] = mapped_column(nullable=True)

    # Marketplace metrics
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    review_count: Mapped[int] = mapped_column(default=0, nullable=False)
    price_per_hour: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    price_per_job_min: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    price_per_job_max: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    # Availability: JSON array of {day: 0-6, start: "HH:MM", end: "HH:MM", timezone: "Australia/Sydney"}
    availability: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, verified, rejected

    # Embedding for semantic search on specialties/description
    embedding: Mapped[list[float] | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_engineers_active_rating", "is_active", "rating"),
        Index("ix_engineers_active_price", "is_active", "price_per_hour"),
        Index("ix_engineers_active_verified", "is_active", "is_verified"),
        Index("ix_engineers_postcode_active", "postcode", "is_active"),
    )


# Relationship back-populates are declared after all classes to avoid forward reference issues
# See bottom of file for Engineer.booking_requests, Engineer.certifications_detailed, Engineer.jobs


class EngineerReview(Base):
    __tablename__ = "engineer_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engineers.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    vehicle_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vehicles.id"), nullable=True, index=True
    )

    rating: Mapped[int] = mapped_column(nullable=False)  # 1-5
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Service context
    service_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engineer: Mapped["Engineer"] = relationship(back_populates="reviews")

    __table_args__ = (
        Index("ix_engineer_reviews_engineer_created", "engineer_id", "created_at"),
    )


# Back-reference for Engineer
Engineer.reviews: Mapped[list["EngineerReview"]] = relationship(
    back_populates="engineer", lazy="selectin", cascade="all, delete-orphan"
)


class EngineerBookingRequest(Base):
    """Incoming booking request from a user to an engineer."""

    __tablename__ = "engineer_booking_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engineers.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    vehicle_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vehicles.id"), nullable=False, index=True
    )

    # Request details
    service_type: Mapped[str] = mapped_column(String(60), nullable=False)  # scheduled/repair/diagnostic/tire/custom
    description: Mapped[str | None] = mapped_column(Text)
    preferred_date: Mapped[date | None] = mapped_column(Date)
    preferred_time: Mapped[time | None] = mapped_column(nullable=True)
    urgency: Mapped[str] = mapped_column(String(20), default="normal")  # low/normal/high/urgent

    # Pre-check report (from AI diagnostic or user input)
    pre_check_report: Mapped[dict | None] = mapped_column(JSONB)
    symptoms: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    odometer_km: Mapped[int | None] = mapped_column(Integer)

    # Status workflow
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # pending/accepted/rejected/completed/cancelled

    # Engineer response
    engineer_notes: Mapped[str | None] = mapped_column(Text)
    quoted_price: Mapped[float | None] = mapped_column(Float)
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    scheduled_time: Mapped[time | None] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    engineer: Mapped["Engineer"] = relationship(back_populates="booking_requests")
    user: Mapped["User"] = relationship()
    vehicle: Mapped["Vehicle"] = relationship()

    __table_args__ = (
        Index("ix_booking_requests_engineer_status", "engineer_id", "status"),
        Index("ix_booking_requests_user_status", "user_id", "status"),
        Index("ix_booking_requests_created", "created_at"),
    )


class EngineerCertification(Base):
    """Certification with expiry tracking for engineer dashboard."""

    __tablename__ = "engineer_certifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engineers.id"), nullable=False, index=True
    )

    # Certification details
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(200))
    certification_number: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(60))  # mechanical/electrical/diagnostic/hybrid/etc

    # Expiry tracking
    issued_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    is_recurring: Mapped[bool] = mapped_column(default=False)  # e.g., annual renewal
    renewal_period_months: Mapped[int | None] = mapped_column(Integer)  # 12 for annual

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )  # active/expired/expiring_soon/renewed

    # Reminder settings
    reminder_sent_90: Mapped[bool] = mapped_column(default=False)
    reminder_sent_30: Mapped[bool] = mapped_column(default=False)
    reminder_sent_7: Mapped[bool] = mapped_column(default=False)
    reminder_sent_expired: Mapped[bool] = mapped_column(default=False)

    # Document reference
    document_key: Mapped[str | None] = mapped_column(String(512))  # MinIO key for certificate PDF

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engineer: Mapped["Engineer"] = relationship(back_populates="certifications_detailed")

    __table_args__ = (
        Index("ix_certifications_engineer_expiry", "engineer_id", "expiry_date"),
        Index("ix_certifications_engineer_status", "engineer_id", "status"),
    )


class EngineerJob(Base):
    """Completed job with earnings breakdown for engineer dashboard."""

    __tablename__ = "engineer_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engineers.id"), nullable=False, index=True
    )
    booking_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("engineer_booking_requests.id"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    vehicle_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vehicles.id"), nullable=False, index=True
    )

    # Job details
    service_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(60))  # labour/parts/diagnostic/tire/etc
    description: Mapped[str | None] = mapped_column(Text)
    work_performed: Mapped[str | None] = mapped_column(Text)

    # Financial
    labour_hours: Mapped[float | None] = mapped_column(Float)
    labour_rate: Mapped[float | None] = mapped_column(Float)
    labour_total: Mapped[float] = mapped_column(Float, default=0.0)
    parts_total: Mapped[float] = mapped_column(Float, default=0.0)
    sublet_total: Mapped[float] = mapped_column(Float, default=0.0)  # subcontracted work
    discount: Mapped[float] = mapped_column(Float, default=0.0)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    total_earnings: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    currency: Mapped[str] = mapped_column(String(8), default="AUD")

    # Dates
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    invoiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Status
    payment_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # pending/invoiced/paid/partial/refunded

    # Parts used (JSON)
    parts_used: Mapped[list[dict] | None] = mapped_column(JSONB, default=list)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engineer: Mapped["Engineer"] = relationship(back_populates="jobs")
    booking_request: Mapped["EngineerBookingRequest"] = relationship()
    user: Mapped["User"] = relationship()
    vehicle: Mapped["Vehicle"] = relationship()

    __table_args__ = (
        Index("ix_jobs_engineer_completed", "engineer_id", "completed_at"),
        Index("ix_jobs_engineer_payment", "engineer_id", "payment_status"),
        Index("ix_jobs_engineer_service_type", "engineer_id", "service_type"),
    )


# Back-references for Engineer
Engineer.booking_requests: Mapped[list["EngineerBookingRequest"]] = relationship(
    back_populates="engineer", lazy="selectin", cascade="all, delete-orphan"
)
Engineer.certifications_detailed: Mapped[list["EngineerCertification"]] = relationship(
    back_populates="engineer", lazy="selectin", cascade="all, delete-orphan"
)
Engineer.jobs: Mapped[list["EngineerJob"]] = relationship(
    back_populates="engineer", lazy="selectin", cascade="all, delete-orphan"
)