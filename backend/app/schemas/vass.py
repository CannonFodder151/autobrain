"""VASS compliance schemas."""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class VASSState(str, Enum):
    """Australian state/territory for VASS compliance."""

    VIC = "VIC"
    NSW = "NSW"
    QLD = "QLD"
    WA = "WA"
    SA = "SA"
    TAS = "TAS"
    NT = "NT"
    ACT = "ACT"


class VehicleType(str, Enum):
    """Vehicle type for VASS."""

    CAR = "car"
    MOTORCYCLE = "motorcycle"
    LIGHT_COMMERCIAL = "light_commercial"
    HEAVY_VEHICLE = "heavy_vehicle"


class ModificationCategory(str, Enum):
    """Modification categories relevant to VASS."""

    ENGINE = "engine"
    EXHAUST = "exhaust"
    SUSPENSION = "suspension"
    BRAKES = "brakes"
    STEERING = "steering"
    WHEELS_TYRES = "wheels_tyres"
    BODY_CHASSIS = "body_chassis"
    LIGHTING = "lighting"
    EMISSIONS = "emissions"
    FUEL_SYSTEM = "fuel_system"
    TRANSMISSION = "transmission"
    SEATS_RESTRAINTS = "seats_restraints"
    NOISE = "noise"
    OTHER = "other"


class ComplianceStatus(str, Enum):
    """Compliance check result status."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    REQUIRES_INSPECTION = "requires_inspection"
    REQUIRES_CERTIFICATION = "requires_certification"
    UNKNOWN = "unknown"


class VehicleLookupRequest(BaseModel):
    """Request for vehicle make/model/year lookup."""

    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=1900, le=2100)
    state: VASSState = VASSState.VIC
    vehicle_type: VehicleType = VehicleType.CAR


class VehicleLookupResponse(BaseModel):
    """Response for vehicle make/model/year lookup."""

    make: str
    model: str
    year: int
    state: VASSState
    vehicle_type: VehicleType
    vin_pattern: Optional[str] = None
    adr_category: Optional[str] = None
    gross_vehicle_mass_kg: Optional[int] = None
    seating_capacity: Optional[int] = None
    engine_capacity_cc: Optional[int] = None
    fuel_type: Optional[str] = None
    found: bool = True


class VINValidationRequest(BaseModel):
    """Request for VIN validation."""

    vin: str = Field(min_length=17, max_length=17)
    state: VASSState = VASSState.VIC


class VINValidationResponse(BaseModel):
    """Response for VIN validation."""

    vin: str
    valid_format: bool
    valid_checksum: bool
    decoded: Optional[dict] = None
    state: VASSState
    matches_vehicle: Optional[bool] = None
    vehicle_id: Optional[str] = None


class ModificationChecklistItem(BaseModel):
    """Single item in a modification compliance checklist."""

    category: ModificationCategory
    modification_name: str
    description: str
    adr_references: list[str] = Field(default_factory=list)
    vsb6_references: list[str] = Field(default_factory=list)
    vsi_references: list[str] = Field(default_factory=list)
    requires_engineer_certification: bool = False
    requires_lab_testing: bool = False
    notes: Optional[str] = None


class ModificationChecklistRequest(BaseModel):
    """Request to generate a modification checklist."""

    vehicle_id: str
    modifications: list[dict] = Field(default_factory=list)
    state: VASSState = VASSState.VIC


class ModificationChecklistResponse(BaseModel):
    """Response with generated modification checklist."""

    vehicle_id: str
    state: VASSState
    checklist: list[ModificationChecklistItem]
    generated_at: datetime
    total_items: int
    items_requiring_certification: int
    items_requiring_lab_testing: int


class ComplianceResultItem(BaseModel):
    """Individual compliance check result."""

    category: ModificationCategory
    modification_name: str
    status: ComplianceStatus
    adr_references: list[str] = Field(default_factory=list)
    vsb6_references: list[str] = Field(default_factory=list)
    vsi_references: list[str] = Field(default_factory=list)
    details: str
    engineer_required: bool = False
    lab_testing_required: bool = False
    evidence_required: list[str] = Field(default_factory=list)


class ComplianceAggregationRequest(BaseModel):
    """Request to aggregate compliance results."""

    vehicle_id: str
    modification_ids: list[str] = Field(default_factory=list)
    state: VASSState = VASSState.VIC


class ComplianceAggregationResponse(BaseModel):
    """Aggregated compliance results."""

    vehicle_id: str
    state: VASSState
    overall_status: ComplianceStatus
    total_modifications: int
    compliant_count: int
    non_compliant_count: int
    requires_inspection_count: int
    requires_certification_count: int
    unknown_count: int
    results: list[ComplianceResultItem]
    generated_at: datetime
    summary: str
    next_steps: list[str] = Field(default_factory=list)


class VASSVehicleCreate(BaseModel):
    """Vehicle data for VASS compliance (extends base vehicle)."""

    vin: str = Field(min_length=17, max_length=17)
    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=1900, le=2100)
    vehicle_type: VehicleType = VehicleType.CAR
    state: VASSState = VASSState.VIC
    gross_vehicle_mass_kg: Optional[int] = None
    seating_capacity: Optional[int] = None
    engine_capacity_cc: Optional[int] = None
    fuel_type: Optional[str] = None
    adr_category: Optional[str] = None


class VASSVehicleOut(VASSVehicleCreate):
    """VASS vehicle output with ID and timestamps."""

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VASSModificationCreate(BaseModel):
    """Modification data for VASS compliance."""

    vehicle_id: str
    name: str = Field(min_length=1, max_length=255)
    category: ModificationCategory
    brand: Optional[str] = None
    description: Optional[str] = None
    install_date: Optional[date] = None
    odometer_km: Optional[int] = None
    cost: float = 0.0
    adr_references: list[str] = Field(default_factory=list)
    vsb6_references: list[str] = Field(default_factory=list)
    vsi_references: list[str] = Field(default_factory=list)
    requires_engineer_certification: bool = False
    requires_lab_testing: bool = False
    evidence_photos: list[str] = Field(default_factory=list)  # MinIO keys


class VASSModificationUpdate(BaseModel):
    """Modification update for VASS compliance."""

    name: Optional[str] = None
    category: Optional[ModificationCategory] = None
    brand: Optional[str] = None
    description: Optional[str] = None
    install_date: Optional[date] = None
    odometer_km: Optional[int] = None
    cost: Optional[float] = None
    adr_references: Optional[list[str]] = None
    vsb6_references: Optional[list[str]] = None
    vsi_references: Optional[list[str]] = None
    requires_engineer_certification: Optional[bool] = None
    requires_lab_testing: Optional[bool] = None
    evidence_photos: Optional[list[str]] = None


class VASSModificationOut(VASSModificationCreate):
    """VASS modification output with ID and timestamps."""

    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VASSComplianceResultCreate(BaseModel):
    """Compliance result creation."""

    vehicle_id: str
    modification_id: Optional[str] = None
    category: ModificationCategory
    modification_name: str
    status: ComplianceStatus
    adr_references: list[str] = Field(default_factory=list)
    vsb6_references: list[str] = Field(default_factory=list)
    vsi_references: list[str] = Field(default_factory=list)
    details: str
    engineer_required: bool = False
    lab_testing_required: bool = False
    evidence_required: list[str] = Field(default_factory=list)
    assessed_by: Optional[str] = None  # engineer ID or "ai"
    assessed_at: Optional[datetime] = None


class VASSComplianceResultOut(VASSComplianceResultCreate):
    """Compliance result output with ID."""

    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}