"""VASS (Vehicle Approval & Safety System) schemas."""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Jurisdiction(str, Enum):
    VIC = "VIC"
    NSW = "NSW"
    QLD = "QLD"
    SA = "SA"
    WA = "WA"
    TAS = "TAS"
    ACT = "ACT"
    NT = "NT"


class ComplianceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    CONDITIONAL = "conditional"
    PENDING = "pending"
    NOT_APPLICABLE = "na"


class PrecheckStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class EngineerType(str, Enum):
    SIGNATORY = "signatory"
    INSPECTOR = "inspector"
    CONSULTANT = "consultant"


class ModificationSelection(BaseModel):
    """Single modification selection in pre-check."""
    name: str
    category: str
    brand: str | None = None
    notes: str | None = None


class PrecheckCreate(BaseModel):
    vehicle_id: str
    jurisdiction: Jurisdiction = Jurisdiction.VIC
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    body_type: str | None = None
    engine: str | None = None
    transmission: str | None = None
    modifications: list[ModificationSelection] = []


class PrecheckUpdate(BaseModel):
    jurisdiction: Jurisdiction | None = None
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    body_type: str | None = None
    engine: str | None = None
    transmission: str | None = None
    modifications: list[ModificationSelection] | None = None
    status: PrecheckStatus | None = None


class PrecheckOut(BaseModel):
    id: str
    vehicle_id: str
    user_id: str
    jurisdiction: Jurisdiction
    status: PrecheckStatus
    vin: str | None
    make: str | None
    model: str | None
    year: int | None
    body_type: str | None
    engine: str | None
    transmission: str | None
    modifications: list[ModificationSelection] = []
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComplianceResultOut(BaseModel):
    id: str
    precheck_id: str
    modification_name: str
    category: str
    status: ComplianceStatus
    adr_references: list[str] = []
    vsb_references: list[str] = []
    vsb6_references: list[str] = []
    notes: str | None
    conditional_details: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EngineerCreate(BaseModel):
    jurisdiction: Jurisdiction
    engineer_type: EngineerType = EngineerType.SIGNATORY
    name: str = Field(min_length=1, max_length=200)
    business_name: str | None = None
    abn: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    suburb: str | None = None
    postcode: str | None = None
    specialisations: list[str] = []
    license_number: str | None = None
    license_expiry: date | None = None


class EngineerUpdate(BaseModel):
    engineer_type: EngineerType | None = None
    name: str | None = None
    business_name: str | None = None
    abn: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    suburb: str | None = None
    postcode: str | None = None
    specialisations: list[str] | None = None
    license_number: str | None = None
    license_expiry: date | None = None
    is_active: bool | None = None


class EngineerOut(BaseModel):
    id: str
    jurisdiction: Jurisdiction
    engineer_type: EngineerType
    name: str
    business_name: str | None
    abn: str | None
    email: str | None
    phone: str | None
    address: str | None
    suburb: str | None
    postcode: str | None
    specialisations: list[str] = []
    license_number: str | None
    license_expiry: date | None
    is_active: bool
    rating: float | None
    review_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EngineerSearchParams(BaseModel):
    jurisdiction: Jurisdiction | None = None
    engineer_type: EngineerType | None = None
    specialisation: str | None = None
    suburb: str | None = None
    postcode: str | None = None
    min_rating: float | None = None
    is_active: bool = True
    page: int = 1
    page_size: int = 20


class EngineerSearchResponse(BaseModel):
    engineers: list[EngineerOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class EngineerRequestCreate(BaseModel):
    engineer_id: str
    vehicle_id: str | None = None
    precheck_id: str | None = None
    message: str | None = None


class EngineerRequestOut(BaseModel):
    id: str
    engineer_id: str
    user_id: str
    vehicle_id: str | None
    precheck_id: str | None
    message: str | None
    status: str
    quoted_amount: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImportPathwayRequest(BaseModel):
    vin: str = Field(min_length=17, max_length=17)
    jurisdiction: Jurisdiction = Jurisdiction.VIC


class ImportPathwayOut(BaseModel):
    id: str
    vin: str
    jurisdiction: Jurisdiction
    vehicle_make: str | None
    vehicle_model: str | None
    vehicle_year: int | None
    pathway_type: str
    eligibility: str
    requirements: dict | None = None
    adr_requirements: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentChecklistItem(BaseModel):
    name: str
    description: str | None = None
    required: bool = True
    provided: bool = False
    notes: str | None = None


class ImportPathwayDetailOut(ImportPathwayOut):
    document_checklist: list[DocumentChecklistItem] = []


class CompliancePackOut(BaseModel):
    id: str
    precheck_id: str
    filename: str
    file_size: int
    overall_score: float | None
    total_mods: int
    passed_mods: int
    failed_mods: int
    conditional_mods: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CompliancePackGenerateRequest(BaseModel):
    precheck_id: str
    include_images: bool = False


class VassSettingsOut(BaseModel):
    default_jurisdiction: Jurisdiction = Jurisdiction.VIC
    available_jurisdictions: list[Jurisdiction] = [
        Jurisdiction.VIC, Jurisdiction.NSW, Jurisdiction.QLD,
        Jurisdiction.SA, Jurisdiction.WA, Jurisdiction.TAS,
        Jurisdiction.ACT, Jurisdiction.NT
    ]


class VassSettingsUpdate(BaseModel):
    default_jurisdiction: Jurisdiction | None = None


# ── Vehicle make/model/year lookup ────────────────────────────────


class VehicleLookupRequest(BaseModel):
    """Request for vehicle make/model/year lookup."""
    make: str = Field(min_length=1, max_length=80)
    model: str | None = Field(None, max_length=120)
    year: int | None = Field(None, ge=1900, le=2030)


class VehicleLookupItem(BaseModel):
    """Single vehicle record from lookup."""
    make: str
    model: str
    year_from: int
    year_to: int
    category: str
    rhd: bool


class VehicleLookupResponse(BaseModel):
    """Response containing matching vehicles."""
    vehicles: list[VehicleLookupItem]
    total: int
    make: str
    model: str | None = None
    year: int | None = None


# ── VIN validation ────────────────────────────────────────────────


class VinValidationRequest(BaseModel):
    """VIN to validate."""
    vin: str = Field(min_length=17, max_length=17)


class VinValidationResponse(BaseModel):
    """VIN validation result."""
    vin: str
    is_valid: bool
    errors: list[str] = []
    check_digit_valid: bool | None = None
    manufacturer: str | None = None
    country: str | None = None
    year: int | None = None
    is_right_hand_drive: bool | None = None


# ── Modification checklist ────────────────────────────────────────


class ModificationItem(BaseModel):
    """Input modification for checklist generation."""
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=60)
    brand: str | None = None
    notes: str | None = None


class ModificationChecklistRequest(BaseModel):
    """Request for modification checklist generation."""
    modifications: list[ModificationItem] = Field(min_length=1)
    vehicle_category: str = "passenger"
    jurisdiction: Jurisdiction = Jurisdiction.VIC


class ChecklistItemOut(BaseModel):
    """Single checklist item."""
    id: str
    category: str
    name: str
    description: str
    required: bool
    adr_references: list[str] = []
    vsb_references: list[str] = []
    est_cost_aud: int | None = None
    notes: str | None = None


class ModificationChecklistResponse(BaseModel):
    """Generated checklist for modifications."""
    modifications: list[ModificationItem]
    vehicle_category: str
    jurisdiction: str
    checklist: list[ChecklistItemOut]
    total_items: int
    required_items: int
    est_total_cost_aud: int


# ── Compliance results aggregation ────────────────────────────────


class ComplianceResultDetail(BaseModel):
    """Single compliance result detail."""
    name: str
    category: str
    status: str
    adr_references: list[str] = []
    vsb_references: list[str] = []
    notes: str | None = None
    conditional_details: str | None = None
    created_at: str | None = None


class ComplianceAggregationRequest(BaseModel):
    """Request for compliance results aggregation."""
    precheck_id: str


class ComplianceAggregationResponse(BaseModel):
    """Aggregated compliance results."""
    overall_score: float = Field(ge=0.0, le=100.0)
    total_mods: int
    passed: int
    failed: int
    conditional: int
    pending: int
    requires_engineer_review: bool
    summary: str
    results: list[ComplianceResultDetail] = []


# ── Modification model ───────────────────────────────────────────


class ModificationCreate(BaseModel):
    """Create a modification record."""
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=60)
    brand: str | None = None
    part_number: str | None = None
    description: str | None = None
    vehicle_id: str | None = None
    precheck_id: str | None = None


class ModificationOut(BaseModel):
    """Modification record output."""
    id: str
    name: str
    category: str
    brand: str | None = None
    part_number: str | None = None
    description: str | None = None
    vehicle_id: str | None = None
    precheck_id: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}