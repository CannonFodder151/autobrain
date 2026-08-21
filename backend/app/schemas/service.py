"""Service schemas."""

import json
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

# AUT-1275: "Oil Change" service type is merged into "Scheduled Service" across
# the entire stack. Legacy values are normalised on ingress so stored records
# stay consistent. The _LEGACY_OIL_TYPES set covers every variant that may
# exist in the DB (seed data uses "oil", old clients used "oil_change").
_LEGACY_OIL_TYPES = frozenset({"oil", "oil_change"})


class ServiceItemIn(BaseModel):
    part_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    quantity: int = 1
    unit_cost: float = 0.0
    kind: str = "item"  # part/labour/item
    part_no: str | None = None
    labour_hours: float | None = None
    labour_rate: float | None = None


class ServiceItemOut(BaseModel):
    id: str
    name: str
    quantity: int
    unit_cost: float
    kind: str
    part_no: str | None
    part_id: str | None
    labour_hours: float | None
    labour_rate: float | None

    model_config = {"from_attributes": True}


class ServiceCreate(BaseModel):
    service_date: date
    odometer_km: int
    service_type: str = "scheduled"
    description: str | None = None
    workshop: str | None = None
    cost: float = 0.0
    currency: str = "AUD"
    notes: str | None = None
    status: str = Field(default="completed", pattern="^(scheduled|completed)$")
    steps: list[str] = []
    items: list[ServiceItemIn] = []

    @field_validator("service_type")
    @classmethod
    def _merge_oil_change(cls, v: str) -> str:
        return "scheduled" if v in _LEGACY_OIL_TYPES else v


class ServiceUpdate(BaseModel):
    service_date: date | None = None
    odometer_km: int | None = None
    service_type: str | None = None
    description: str | None = None
    workshop: str | None = None
    cost: float | None = None
    currency: str | None = None
    notes: str | None = None
    status: str | None = Field(default=None, pattern="^(scheduled|completed)$")
    completed_date: date | None = None
    steps: list[str] | None = None
    items: list[ServiceItemIn] | None = None

    @field_validator("service_type")
    @classmethod
    def _merge_oil_change(cls, v: str | None) -> str | None:
        return "scheduled" if v in _LEGACY_OIL_TYPES else v


class ServiceOut(BaseModel):
    id: str
    vehicle_id: str
    service_date: date
    odometer_km: int
    service_type: str
    description: str | None
    workshop: str | None
    cost: float
    currency: str
    notes: str | None
    ai_prediction: str | None
    next_due_km: int | None
    next_due_date: date | None
    status: str
    completed_date: date | None
    steps: list[str] = []
    items: list[ServiceItemOut] = []
    created_at: datetime

    @field_validator("steps", mode="before")
    @classmethod
    def _parse_steps(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []

    model_config = {"from_attributes": True}


class ServicePredictionRequest(BaseModel):
    make: str
    model: str
    year: int
    odometer_km: int
    last_service_km: int | None = None
    last_service_days_ago: int | None = None
    service_type: str = "scheduled"

    @field_validator("service_type")
    @classmethod
    def _merge_oil_change(cls, v: str) -> str:
        return "scheduled" if v in _LEGACY_OIL_TYPES else v


class ServicePredictionResponse(BaseModel):
    service_type: str
    interval_km: int
    interval_months: int
    due_in_km: int
    due_in_days: int
    next_due_km: int
    next_due_date: date
    confidence: float
    reason: str
