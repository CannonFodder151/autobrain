"""Shared Fuel schemas used by both backend and AI."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

FuelType = Literal["petrol", "diesel", "lpg", "e85", "electric", "hybrid"]
Currency = str  # ISO 4217, default "AUD"


class FuelLogBase(BaseModel):
    """Base fuel log entry (minimal shared fields)."""
    vehicle_id: str
    fill_date: date
    odometer_km: int
    litres: float
    total_cost: float
    price_per_litre: Optional[float] = None
    is_full_tank: bool = True
    fuel_type: FuelType = "petrol"
    station_name: Optional[str] = None
    receipt_id: Optional[str] = None


class FuelLogOut(FuelLogBase):
    """Fuel log output (includes computed fields)."""
    id: str
    distance_km: Optional[int] = None
    l_per_100km: Optional[float] = None
    cost_per_km: Optional[float] = None


class FuelStats(BaseModel):
    """Aggregated fuel statistics for a vehicle."""
    total_litres: float = 0.0
    total_cost: float = 0.0
    avg_l_per_100km: Optional[float] = None
    avg_cost_per_km: Optional[float] = None
    fill_count: int = 0
    first_fill: Optional[date] = None
    last_fill: Optional[date] = None
    currency: Currency = "AUD"
    series: list[dict] = Field(default_factory=list)


class FuelReceiptOCR(BaseModel):
    """OCR-extracted fuel receipt fields."""
    vendor: Optional[str] = None
    date: Optional[date] = None
    amount: Optional[float] = None
    litres: Optional[float] = None
    price_per_litre: Optional[float] = None
    fuel_type: Optional[FuelType] = None
    odometer_km: Optional[int] = None
    confidence: float = 0.0
    model: str = "rule-based-fallback"