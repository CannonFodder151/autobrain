"""Engineer dashboard schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.engineer import BookingStatus, CertificationType, JobType


# ---------------------------------------------------------------------------
# Certifications
# ---------------------------------------------------------------------------

class EngineerCertificationOut(BaseModel):
    id: str
    cert_type: CertificationType
    cert_number: str | None
    issuing_authority: str | None
    issued_date: date
    expiry_date: date
    status: str
    days_to_expiry: int | None
    document_key: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CertificationReminder(BaseModel):
    """A certification that needs renewal attention."""

    id: str
    cert_type: CertificationType
    cert_number: str | None
    issuing_authority: str | None
    issued_date: date
    expiry_date: date
    days_to_expiry: int | None
    status: str
    is_expired: bool
    is_expiring_soon: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Booking Requests
# ---------------------------------------------------------------------------

class PreCheckReportSummary(BaseModel):
    id: str
    symptoms: list[str] = []
    warning_lights: list[str] = []
    diagnostic_codes: list[str] = []
    ai_assessment: str | None
    ai_confidence: float | None
    ai_suggested_job_type: JobType | None
    ai_estimated_hours: float | None
    ai_estimated_cost: float | None
    photo_keys: list[str] = []

    model_config = {"from_attributes": True}


class EngineerMiniOut(BaseModel):
    id: str
    business_name: str
    abn: str | None
    suburb: str | None
    state: str | None
    specialties: list[str] = []
    hourly_rate: float | None
    verified_at: datetime | None
    active: bool

    model_config = {"from_attributes": True}


class VehicleMiniOut(BaseModel):
    id: str
    nickname: str
    make: str | None
    model: str | None
    year: int | None
    rego: str | None

    model_config = {"from_attributes": True}


class UserMiniOut(BaseModel):
    id: str
    email: str
    display_name: str

    model_config = {"from_attributes": True}


class BookingRequestSummary(BaseModel):
    id: str
    engineer_id: str
    vehicle: VehicleMiniOut
    customer: UserMiniOut
    job_type: JobType
    description: str
    preferred_date: date | None
    urgency: str
    has_pre_check: bool
    pre_check: PreCheckReportSummary | None
    status: BookingStatus
    engineer_notes: str | None
    quoted_price: float | None
    quoted_hours: float | None
    responded_at: datetime | None
    created_at: datetime
    age_hours: float | None

    model_config = {"from_attributes": True}


class BookingRequestDetail(BookingRequestSummary):
    pre_check_full: PreCheckReportSummary | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookingRequestAction(BaseModel):
    status: BookingStatus
    engineer_notes: str | None = None
    quoted_price: float | None = None
    quoted_hours: float | None = None
    currency: str | None = None


# ---------------------------------------------------------------------------
# Earnings
# ---------------------------------------------------------------------------

class EarningsByJobType(BaseModel):
    job_type: str
    job_count: int
    total_earnings: float
    total_charged: float
    total_parts: float
    total_labour: float
    currency: str = "AUD"


class EarningsPeriod(BaseModel):
    period: str  # e.g. "2026-09" or "2026-W38" or "2026-09-01..2026-09-21"
    total_earnings: float
    total_charged: float
    platform_fees: float
    job_count: int
    completed_at: datetime | None


class EarningsSummary(BaseModel):
    total_earnings: float
    total_charged: float
    total_platform_fees: float
    total_jobs: int
    currency: str
    by_job_type: list[EarningsByJobType] = []
    by_period: list[EarningsPeriod] = []


# ---------------------------------------------------------------------------
# Completed Jobs
# ---------------------------------------------------------------------------

class JobItemOut(BaseModel):
    name: str
    quantity: float
    unit_cost: float
    total_cost: float
    kind: str

    model_config = {"from_attributes": True}


class CompletedJobOut(BaseModel):
    id: str
    vehicle: VehicleMiniOut
    customer: UserMiniOut
    booking_request_id: str | None
    job_type: JobType
    title: str
    description: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    labour_hours: float
    labour_rate: float
    parts_cost: float
    parts_markup_pct: float
    sublet_cost: float
    total_charged: float
    total_earnings: float
    platform_fee_pct: float
    platform_fee_amount: float
    currency: str
    items: list[JobItemOut] = []
    engineer_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EngineerDashboardResponse(BaseModel):
    engineer: EngineerMiniOut
    total_bookings_incoming: int
    total_bookings_needs_response: int
    total_certifications: int
    expiring_certifications: list[CertificationReminder]
    upcoming_certifications: list[CertificationReminder]
    recent_bookings: list[BookingRequestSummary] = []
    recent_completed_jobs: list[CompletedJobOut] = []
    earnings_summary: EarningsSummary