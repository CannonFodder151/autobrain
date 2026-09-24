"""Schemas for engineer dashboard (AUT-3663)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# --- Booking Request Schemas ---

class BookingRequestSummary(BaseModel):
    """Incoming booking request summary for dashboard list."""

    id: str
    user_name: str | None = None
    vehicle_make: str | None = None
    vehicle_model: str | None = None
    vehicle_rego: str | None = None
    service_type: str
    description: str | None = None
    preferred_date: date | None = None
    urgency: str = "normal"
    status: str = "pending"
    created_at: str | None = None

    # Pre-check info
    symptoms: list[str] = Field(default_factory=list)
    odometer_km: int | None = None


class BookingRequestDetail(BaseModel):
    """Full booking request detail view."""

    id: str
    user_name: str | None = None
    user_email: str | None = None
    user_phone: str | None = None
    vehicle_id: str | None = None
    vehicle_make: str | None = None
    vehicle_model: str | None = None
    vehicle_rego: str | None = None
    vehicle_year: int | None = None

    service_type: str
    description: str | None = None
    preferred_date: date | None = None
    preferred_time: str | None = None
    urgency: str = "normal"

    # Pre-check report
    pre_check_report: dict | None = None
    symptoms: list[str] = Field(default_factory=list)
    odometer_km: int | None = None

    # Status
    status: str = "pending"
    engineer_notes: str | None = None
    quoted_price: float | None = None
    scheduled_date: date | None = None
    scheduled_time: str | None = None

    created_at: str | None = None
    updated_at: str | None = None
    responded_at: str | None = None
    completed_at: str | None = None


class BookingRequestUpdate(BaseModel):
    """Engineer response to a booking request."""

    status: str | None = Field(
        default=None,
        description="New status: accepted/rejected/completed/cancelled",
    )
    engineer_notes: str | None = None
    quoted_price: float | None = Field(default=None, ge=0)
    scheduled_date: date | None = None
    scheduled_time: str | None = None


# --- Owner-facing Booking Request Schemas (AUT-3662) ---

VALID_SERVICE_TYPES = ["repair", "diagnostic", "tire", "scheduled", "custom"]
VALID_URGENCY_LEVELS = ["low", "normal", "high", "urgent"]


class BookingRequestCreate(BaseModel):
    """Owner submits a booking request to a specific engineer.

    The vehicle context is provided by the URL path (/vehicles/{vehicle_id}).
    The engineer is provided by the URL path (/engineers/{engineer_id}).
    """

    service_type: str = Field(
        "repair",
        pattern="^(repair|diagnostic|tire|scheduled|custom)$",
        description="Type of service needed.",
    )
    description: str | None = Field(default=None, max_length=2000)
    preferred_date: date | None = None
    preferred_time: str | None = Field(
        default=None,
        description="Preferred time in HH:MM format (24-hour).",
    )
    urgency: str = Field("normal", pattern="^(low|normal|high|urgent)$")
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    odometer_km: int | None = Field(default=None, ge=0, le=1000000)
    mods: list[str] = Field(default_factory=list, max_length=50)
    auto_generate_precheck: bool = Field(
        default=True,
        description="Generate a pre-check report from vehicle + mods data.",
    )


class BookingRequestOwnerSummary(BaseModel):
    """Owner view of a booking request in list/summary form."""

    id: str
    engineer_id: str
    engineer_name: str | None = None
    engineer_rating: float | None = None
    engineer_phone: str | None = None
    vehicle_id: str
    vehicle_make: str | None = None
    vehicle_model: str | None = None
    vehicle_rego: str | None = None

    service_type: str
    description: str | None = None
    preferred_date: date | None = None
    preferred_time: str | None = None
    urgency: str = "normal"
    status: str = "pending"
    created_at: str | None = None
    responded_at: str | None = None
    engineer_notes: str | None = None
    quoted_price: float | None = None
    scheduled_date: date | None = None
    scheduled_time: str | None = None


class BookingRequestOwnerDetail(BaseModel):
    """Owner view of a booking request with full detail and engineer response."""

    id: str
    engineer_id: str
    engineer_name: str | None = None
    engineer_rating: float | None = None
    engineer_phone: str | None = None
    engineer_email: str | None = None
    engineer_specialties: list[str] = Field(default_factory=list)
    engineer_years_experience: int | None = None

    vehicle_id: str
    vehicle_make: str | None = None
    vehicle_model: str | None = None
    vehicle_rego: str | None = None
    vehicle_year: int | None = None
    vehicle_nickname: str | None = None

    service_type: str
    description: str | None = None
    preferred_date: date | None = None
    preferred_time: str | None = None
    urgency: str = "normal"

    # Pre-check report (generated at submission time)
    pre_check_report: dict | None = None
    symptoms: list[str] = Field(default_factory=list)
    mods: list[str] = Field(default_factory=list)
    odometer_km: int | None = None

    # Status + engineer response
    status: str = "pending"
    engineer_notes: str | None = None
    quoted_price: float | None = None
    scheduled_date: date | None = None
    scheduled_time: str | None = None

    created_at: str | None = None
    updated_at: str | None = None
    responded_at: str | None = None
    completed_at: str | None = None


# --- Certification Schemas ---

class CertificationSummary(BaseModel):
    """Certification summary for dashboard."""

    id: str
    name: str
    issuer: str | None = None
    certification_number: str | None = None
    category: str | None = None
    issued_date: date | None = None
    expiry_date: date | None = None
    status: str = "active"
    days_until_expiry: int | None = None
    is_recurring: bool = False


class CertificationCreate(BaseModel):
    """Create a new certification."""

    name: str = Field(..., max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    certification_number: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=60)
    issued_date: date | None = None
    expiry_date: date | None = None
    is_recurring: bool = False
    renewal_period_months: int | None = Field(default=None, ge=1, le=60)


class CertificationUpdate(BaseModel):
    """Update a certification."""

    name: str | None = Field(default=None, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    certification_number: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=60)
    issued_date: date | None = None
    expiry_date: date | None = None
    status: str | None = None
    is_recurring: bool | None = None
    renewal_period_months: int | None = None


# --- Job / Earnings Schemas ---

class JobSummary(BaseModel):
    """Completed job summary for dashboard list."""

    id: str
    user_name: str | None = None
    vehicle_make: str | None = None
    vehicle_model: str | None = None
    vehicle_rego: str | None = None
    service_type: str
    category: str | None = None
    description: str | None = None
    labour_total: float = 0.0
    parts_total: float = 0.0
    sublet_total: float = 0.0
    total_earnings: float = 0.0
    currency: str = "AUD"
    payment_status: str = "pending"
    completed_at: str | None = None
    paid_at: str | None = None


class EarningsSummary(BaseModel):
    """Earnings summary for a period."""

    total_earnings: float = 0.0
    total_jobs: int = 0
    average_job_value: float = 0.0
    labour_earnings: float = 0.0
    parts_earnings: float = 0.0
    sublet_earnings: float = 0.0
    paid_count: int = 0
    pending_count: int = 0
    invoiced_count: int = 0


class EarningsByJobType(BaseModel):
    """Earnings breakdown by service/job type."""

    service_type: str
    job_count: int = 0
    total_earnings: float = 0.0
    average_earnings: float = 0.0
    labour_total: float = 0.0
    parts_total: float = 0.0


class EarningsByPeriod(BaseModel):
    """Earnings tracking by period (day/week/month/quarter/year)."""

    period: str  # e.g. "2026-09", "2026-W38", "2026-09-21"
    total_earnings: float = 0.0
    job_count: int = 0


# --- Dashboard Aggregation ---

class EngineerDashboard(BaseModel):
    """Complete engineer dashboard summary."""

    engineer_id: str
    display_name: str

    # Incoming requests
    pending_requests: int = 0
    recent_requests: list[BookingRequestSummary] = Field(default_factory=list)

    # Certifications
    active_certifications: int = 0
    expiring_certifications: int = Field(
        default=0,
        description="Certifications expiring within 30 days",
    )
    expired_certifications: int = 0
    certifications: list[CertificationSummary] = Field(default_factory=list)
    renewal_reminders: list[CertificationSummary] = Field(
        default_factory=list,
        description="Certifications needing renewal attention",
    )

    # Jobs & earnings
    completed_jobs: int = 0
    total_earnings: float = 0.0
    recent_jobs: list[JobSummary] = Field(default_factory=list)
    earnings_summary: EarningsSummary = Field(default_factory=EarningsSummary)
    earnings_by_type: list[EarningsByJobType] = Field(default_factory=list)
    earnings_by_period: list[EarningsByPeriod] = Field(default_factory=list)

    # Quick stats
    this_month_earnings: float = 0.0
    last_month_earnings: float = 0.0
    year_to_date_earnings: float = 0.0


# --- CSV Export ---

class DashboardExport(BaseModel):
    """Export data for CSV download."""

    export_type: str  # earnings|certifications|jobs|requests
    period_start: date | None = None
    period_end: date | None = None
