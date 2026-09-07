"""Home Assistant integration schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class HaTokenCreate(BaseModel):
    vehicle_id: str | None = Field(default=None, description="Limit token to one vehicle; omit for all")


class HaTokenOut(BaseModel):
    id: str
    label: str
    token_prefix: str
    vehicle_id: str | None
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class HaTokenCreated(HaTokenOut):
    """Token response on creation — the raw key is shown exactly once."""

    api_key: str


class HaVehicleOut(BaseModel):
    id: str
    nickname: str
    rego: str | None
    make: str | None
    model: str | None
    year: int | None
    odometer_km: int | None
    fuel_type: str | None
    powertrain: str


class HaServiceIntervalOut(BaseModel):
    id: str
    vehicle_nickname: str
    service_type: str
    next_due_km: int | None
    next_due_date: str | None
    status: str


class HaServiceReminderOut(BaseModel):
    vehicle_id: str
    vehicle_nickname: str
    service_type: str
    next_due_km: int | None
    next_due_date: str | None
    due_in_km: int | None
    days_until_due: int | None


class HaAnalyticsOut(BaseModel):
    vehicle_id: str
    vehicle_nickname: str
    fuel_total: float
    service_total: float
    total_cost_of_ownership: float
    cost_per_km: float | None
    total_km_tracked: float
    count_services: int
