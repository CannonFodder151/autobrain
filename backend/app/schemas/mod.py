"""Modification schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class ModCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = "other"
    brand: str | None = None
    cost: float = 0.0
    install_date: date | None = None
    odometer_km: int | None = None
    notes: str | None = None


class ModUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    cost: float | None = None
    install_date: date | None = None
    odometer_km: int | None = None
    notes: str | None = None


class ModOut(BaseModel):
    id: str
    vehicle_id: str
    name: str
    category: str
    brand: str | None
    cost: float
    install_date: date | None
    odometer_km: int | None
    notes: str | None
    photo_keys: list[str] | None
    ai_impact: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModImpactRequest(BaseModel):
    name: str
    category: str
    vehicle: dict | None = None
    notes: str | None = None


class ModImpactResponse(BaseModel):
    summary: str
    performance_score: float | None
    value_impact: float | None
    reliability_impact: str | None
    model: str
