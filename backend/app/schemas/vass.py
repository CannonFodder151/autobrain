"""VASS (Vehicle Assessment Safety System) schemas."""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

from app.models.vass import (
    VehicleClass,
    StandardType,
    ModificationCategory,
    ComplianceStatus,
)


class VASRuleBase(BaseModel):
    mod_category: ModificationCategory
    mod_name: str = Field(..., max_length=120)
    mod_description: Optional[str] = None
    vehicle_class: VehicleClass
    standard_type: StandardType
    standard_ref: str = Field(..., max_length=40)
    standard_section: Optional[str] = None
    standard_title: Optional[str] = None
    default_status: ComplianceStatus = ComplianceStatus.CONDITIONAL
    conditions: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


class VASRuleCreate(VASRuleBase):
    pass


class VASRuleUpdate(BaseModel):
    mod_category: Optional[ModificationCategory] = None
    mod_name: Optional[str] = Field(None, max_length=120)
    mod_description: Optional[str] = None
    vehicle_class: Optional[VehicleClass] = None
    standard_type: Optional[StandardType] = None
    standard_ref: Optional[str] = Field(None, max_length=40)
    standard_section: Optional[str] = None
    standard_title: Optional[str] = None
    default_status: Optional[ComplianceStatus] = None
    conditions: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class VASRuleOut(VASRuleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VASCheckRequest(BaseModel):
    """Request to check a modification against VASS rules."""
    mod_category: str = Field(..., description="Modification category (e.g., 'engine', 'suspension', 'lighting')")
    mod_name: str = Field(..., max_length=120, description="Name of the modification")
    vehicle_class: str = Field(..., description="Vehicle class (e.g., 'PASS_CAR', 'LIGHT_TRUCK', 'HEAVY_TRUCK')")
    mod_description: Optional[str] = None


class VASCheckResponse(BaseModel):
    """VASS compliance check result."""
    status: ComplianceStatus
    matched_rules: List[dict] = []
    applied_standards: List[str] = []
    conditions_met: Optional[str] = None
    notes: Optional[str] = None
    checked_at: datetime


class VASCheckOut(VASCheckResponse):
    id: str
    vehicle_id: Optional[str] = None
    modification_id: Optional[str] = None

    class Config:
        from_attributes = True


class VASSeedRule(BaseModel):
    """Schema for seeding VASS rules from known data."""
    mod_category: ModificationCategory
    mod_name: str
    mod_description: Optional[str] = None
    vehicle_class: VehicleClass
    standard_type: StandardType
    standard_ref: str
    standard_section: Optional[str] = None
    standard_title: Optional[str] = None
    default_status: ComplianceStatus
    conditions: Optional[str] = None
    notes: Optional[str] = None