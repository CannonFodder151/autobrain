"""Electricity log schemas (AUT-2436)."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class ElectricityLogCreate(BaseModel):
    charge_date: date
    odometer_km: int
    kwh: float = Field(gt=0)
    price_per_kwh: float = Field(gt=0)
    total_cost: float | None = None
    is_full_charge: bool = True
    notes: str | None = None
    receipt_id: str | None = None


class ElectricityLogUpdate(BaseModel):
    charge_date: date | None = None
    odometer_km: int | None = None
    kwh: float | None = Field(default=None, gt=0)
    price_per_kwh: float | None = Field(default=None, gt=0)
    total_cost: float | None = None
    is_full_charge: bool | None = None
    notes: str | None = None
    receipt_id: str | None = None


class ElectricityLogOut(BaseModel):
    id: str
    vehicle_id: str
    charge_date: date
    odometer_km: int
    kwh: float
    price_per_kwh: float
    total_cost: float
    is_full_charge: bool
    notes: str | None
    distance_km: float | None
    km_per_kwh: float | None
    cost_per_km: float | None
    receipt_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ElectricityStats(BaseModel):
    total_kwh: float
    total_cost: float
    avg_km_per_kwh: float | None
    avg_cost_per_km: float | None
    avg_kwh_per_charge: float | None
    last_log: ElectricityLogOut | None
    series: list[dict]
