"""Shared Vehicle schemas used by both backend and AI."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ConditionLabel = Literal["excellent", "good", "fair", "poor"]
VehicleType = Literal["car", "motorcycle", "truck", "van", "suv"]


class VehicleBase(BaseModel):
    """Base vehicle identification (minimal shared fields)."""
    make: str
    model: str
    year: Optional[int] = None
    vehicle_type: VehicleType = "car"
    odometer_km: Optional[int] = None
    condition: Optional[ConditionLabel] = None


class VehicleOut(VehicleBase):
    """Vehicle output schema shared across services."""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class VehicleCreate(BaseModel):
    """Vehicle creation input."""
    make: str
    model: str
    year: Optional[int] = None
    vehicle_type: VehicleType = "car"
    odometer_km: Optional[int] = None
    condition: Optional[ConditionLabel] = None
    rego: Optional[str] = None
    vin: Optional[str] = None


class TradeInBand(BaseModel):
    """Trade-in value band (75/82/90% of private sale)."""
    currency: str = "AUD"
    low: Optional[float] = None
    mid: Optional[float] = None
    high: Optional[float] = None
    ratios: dict[str, float] = Field(
        default_factory=lambda: {"low": 0.75, "mid": 0.82, "high": 0.90}
    )


class ValuationOut(BaseModel):
    """Valuation result shared between backend and AI."""
    currency: str = "AUD"
    low: Optional[float] = None
    mid: Optional[float] = None
    high: Optional[float] = None
    source: str = "fallback"
    as_of: Optional[str] = None
    stale: bool = False
    sample_size: int = 0
    condition_multiplier: float = 1.0
    km_multiplier: float = 1.0
    trade_in: Optional[TradeInBand] = None
    comparables: list[dict] = Field(default_factory=list)
    model: str = "rule-based-fallback"