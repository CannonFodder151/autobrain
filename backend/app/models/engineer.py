"""Engineer dashboard models: profiles, certifications, bookings, jobs."""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


if TYPE_CHECKING:
    from app.models.user import User
    from app.models.vehicle import Vehicle


class CertificationType(str, enum.Enum):
    """Professional certification types for engineers."""

    BLUE_SLIP = "blue_slip"  # NSW Light Vehicle Inspection
    RWC = "rwc"  # Roadworthy Certificate (VIC/QLD/SA/WA)
    HEAVY_VEHICLE = "heavy_vehicle"
    AIR_CONDITIONING = "air_conditioning"
    LPG_INSTALLATION = "lpg_installation"
    AUTOMOTIVE_ELECTRICAL = "automotive_electrical"
    BRAKE_SPECIALIST = "brake_specialist"
    EMISSIONS_TESTING = "emissions_testing"
    OTHER = "other"


class BookingStatus(str, enum.Enum):
    """Status of a booking request."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class JobType(str, enum.Enum):
    """Job categories for earnings breakdown."""

    SCHEDULED_SERVICE = "scheduled_service"
    REPAIR = "repair"
    DIAGNOSTICS = "diagnostics"
    BRAKES = "brakes"
    SUSPENSION = "suspension"
    ENGINE = "engine"
    TRANSMISSION = "transmission"
    ELECTRICAL = "electrical"
    TYRES = "tyres"
    INSPECTION = "inspection"
    MODIFICATION = "modification"
    OTHER = "other"


class EngineerProfile(Base):
    """Professional engineer/mechanic profile linked to a User."""

    __tablename__ = "engineer_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True)
    business_name: Mapped[str] = mapped_column(String(255))
    abn: Mapped[str | None] = mapped_column(String(20), index=True)  # Australian Business Number
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    suburb: Mapped[str | None] = mapped_column(String(100), index=True)
    state: Mapped[str | None] = mapped_column(String(8), index=True)
    postcode: Mapped[str | None] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    specialties: Mapped[list[str] | None] = mapped_column(Text)  # JSON array of JobType values
    hourly_rate: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="engineer_profile")
    certifications: Mapped[list["EngineerCertification"]] = relationship(
        back_populates="engineer", cascade="all, delete-orphan", lazy="selectin"
    )
    booking_requests: Mapped[list["BookingRequest"]] = relationship(
        back_populates="engineer", lazy="selectin"
    )
    jobs: Mapped[list["EngineerJob"]] = relationship(
        back_populates="engineer", lazy="selectin"
    )


class EngineerCertification(Base):
    """Professional certification with expiry tracking."""

    __tablename__ = "engineer_certifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(String(36), ForeignKey("engineer_profiles.id"), index=True)
    cert_type: Mapped[str] = mapped_column(Enum(CertificationType), index=True)
    cert_number: Mapped[str | None] = mapped_column(String(100))
    issuing_authority: Mapped[str | None] = mapped_column(String(255))
    issued_date: Mapped[date] = mapped_column(Date, index=True)
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active/expired/suspended
    document_key: Mapped[str | None] = mapped_column(String(512))  # MinIO key for cert document
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engineer: Mapped["EngineerProfile"] = relationship(back_populates="certifications")

    __table_args__ = (
        Index("ix_engineer_certifications_engineer_expiry", "engineer_id", "expiry_date"),
        Index("ix_engineer_certifications_type_expiry", "cert_type", "expiry_date"),
    )


class BookingRequest(Base):
    """Incoming booking request from a vehicle owner."""

    __tablename__ = "booking_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(String(36), ForeignKey("engineer_profiles.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    customer_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)

    # Request details
    job_type: Mapped[str] = mapped_column(Enum(JobType), index=True)
    description: Mapped[str] = mapped_column(Text)
    preferred_date: Mapped[date | None] = mapped_column(Date, index=True)
    preferred_time: Mapped[str | None] = mapped_column(String(10))  # "morning"/"afternoon"/"any"
    urgency: Mapped[str] = mapped_column(String(20), default="normal")  # low/normal/high/emergency

    # Pre-check report (from customer or AI)
    has_pre_check: Mapped[bool] = mapped_column(default=False)
    pre_check_summary: Mapped[str | None] = mapped_column(Text)
    pre_check_report_key: Mapped[str | None] = mapped_column(String(512))  # MinIO key for full report

    # Status and response
    status: Mapped[str] = mapped_column(Enum(BookingStatus), default=BookingStatus.PENDING, index=True)
    engineer_notes: Mapped[str | None] = mapped_column(Text)
    quoted_price: Mapped[float | None] = mapped_column(Float)
    quoted_hours: Mapped[float | None] = mapped_column(Float)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engineer: Mapped["EngineerProfile"] = relationship(back_populates="booking_requests")
    vehicle: Mapped["Vehicle"] = relationship()
    customer: Mapped["User"] = relationship()
    pre_check_report: Mapped["PreCheckReport | None"] = relationship(
        back_populates="booking_request", cascade="all, delete-orphan", lazy="selectin"
    )
    job: Mapped["EngineerJob | None"] = relationship(
        back_populates="booking_request", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_booking_requests_engineer_status", "engineer_id", "status"),
        Index("ix_booking_requests_customer_status", "customer_user_id", "status"),
    )


class PreCheckReport(Base):
    """Detailed pre-check report for a booking request."""

    __tablename__ = "pre_check_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    booking_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("booking_requests.id"), unique=True, index=True
    )

    # Structured pre-check data
    symptoms: Mapped[str | None] = mapped_column(Text)  # JSON array of symptoms
    warning_lights: Mapped[str | None] = mapped_column(Text)  # JSON array
    diagnostic_codes: Mapped[str | None] = mapped_column(Text)  # JSON array of OBD codes
    recent_services: Mapped[str | None] = mapped_column(Text)  # JSON array of recent service IDs
    modifications: Mapped[str | None] = mapped_column(Text)  # JSON array of modification IDs

    # AI-generated assessment
    ai_assessment: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_suggested_job_type: Mapped[str | None] = mapped_column(Enum(JobType))
    ai_estimated_hours: Mapped[float | None] = mapped_column(Float)
    ai_estimated_cost: Mapped[float | None] = mapped_column(Float)

    # Attachments
    photo_keys: Mapped[list[str] | None] = mapped_column(Text)  # JSON array of MinIO keys
    document_keys: Mapped[list[str] | None] = mapped_column(Text)  # JSON array of MinIO keys

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    booking_request: Mapped["BookingRequest"] = relationship(back_populates="pre_check_report")


class EngineerJob(Base):
    """Completed or in-progress job for earnings tracking."""

    __tablename__ = "engineer_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(String(36), ForeignKey("engineer_profiles.id"), index=True)
    booking_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("booking_requests.id"), unique=True, index=True
    )
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    customer_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)

    # Job details
    job_type: Mapped[str] = mapped_column(Enum(JobType), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)  # in_progress/completed/cancelled

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Earnings
    labour_hours: Mapped[float] = mapped_column(Float, default=0.0)
    labour_rate: Mapped[float] = mapped_column(Float, default=0.0)
    parts_cost: Mapped[float] = mapped_column(Float, default=0.0)
    parts_markup_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sublet_cost: Mapped[float] = mapped_column(Float, default=0.0)  # outsourced work
    total_charged: Mapped[float] = mapped_column(Float, default=0.0)
    total_earnings: Mapped[float] = mapped_column(Float, default=0.0)  # after platform fees
    platform_fee_pct: Mapped[float] = mapped_column(Float, default=10.0)  # AutoBrain platform fee
    platform_fee_amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="AUD")

    # Items (parts/labour breakdown)
    items: Mapped[str | None] = mapped_column(Text)  # JSON array of job items

    # Notes
    engineer_notes: Mapped[str | None] = mapped_column(Text)
    customer_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engineer: Mapped["EngineerProfile"] = relationship(back_populates="jobs")
    booking_request: Mapped["BookingRequest | None"] = relationship(back_populates="job")
    vehicle: Mapped["Vehicle"] = relationship()
    customer: Mapped["User"] = relationship()

    __table_args__ = (
        Index("ix_engineer_jobs_engineer_completed", "engineer_id", "completed_at"),
        Index("ix_engineer_jobs_customer_completed", "customer_user_id", "completed_at"),
        Index("ix_engineer_jobs_type_completed", "job_type", "completed_at"),
    )