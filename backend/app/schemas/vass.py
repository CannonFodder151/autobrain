from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class VehicleLookupIn(BaseModel):
    make: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=50)
    year: int = Field(..., ge=1900, le=2100)


class VehicleLookupOut(BaseModel):
    make: str
    model: str
    year: int
    base_vehicle_id: str
    vin_prefix: Optional[str] = None
    compliance_status: str = "unknown"


class VinDecodeOut(BaseModel):
    vin: str
    valid: bool
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    body_style: Optional[str] = None
    engine: Optional[str] = None
    country: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


class ChecklistItem(BaseModel):
    id: str
    category: str
    description: str
    required: bool = True
    status: str = "pending"  # pending, pass, fail, na
    notes: Optional[str] = None


class ChecklistIn(BaseModel):
    vehicle_id: str
    modifications: List[str] = Field(default_factory=list)


class ChecklistOut(BaseModel):
    vehicle_id: str
    items: List[ChecklistItem]
    total: int
    passed: int
    failed: int
    pending: int


class ComplianceResultIn(BaseModel):
    vehicle_id: str
    checklist_id: Optional[str] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)


class ComplianceResultOut(BaseModel):
    vehicle_id: str
    overall_status: str
    score: float
    passed: int
    failed: int
    total: int
    details: List[Dict[str, Any]] = Field(default_factory=list)
