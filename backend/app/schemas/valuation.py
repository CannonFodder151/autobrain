"""Valuation schemas."""

from datetime import datetime

from pydantic import BaseModel


class ValuationRequest(BaseModel):
    odometer_km: int | None = None
    condition: str | None = None
    extra_context: dict | None = None


class ValuationResponse(BaseModel):
    estimated_value: float
    low: float
    high: float
    currency: str
    factors: dict
    recommendations: list[str]
    trend: list[dict]
    model: str


class ValuationOut(BaseModel):
    id: str
    vehicle_id: str
    estimated_value: float
    low: float
    high: float
    currency: str
    factors: str | None
    recommendations: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
