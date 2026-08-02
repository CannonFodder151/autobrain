"""Fuel schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class FuelLogCreate(BaseModel):
    fill_date: date
    odometer_km: int
    litres: float = Field(gt=0)
    price_per_litre: float = Field(gt=0)
    total_cost: float | None = None
    is_full_tank: bool = True
    notes: str | None = None


class FuelLogOut(BaseModel):
    id: str
    vehicle_id: str
    fill_date: date
    odometer_km: int
    litres: float
    price_per_litre: float
    total_cost: float
    is_full_tank: bool
    notes: str | None
    distance_km: float | None
    l_per_100km: float | None
    cost_per_km: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FuelStats(BaseModel):
    total_litres: float
    total_cost: float
    avg_l_per_100km: float | None
    avg_cost_per_km: float | None
    last_log: FuelLogOut | None
    series: list[dict]
