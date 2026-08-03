"""Vehicle schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class RegoLookupRequest(BaseModel):
    rego: str = Field(min_length=1, max_length=20)
    jurisdiction: str = Field(default="AU", max_length=4)
    state: str = Field(default="VIC", max_length=4)  # NSW/VIC/QLD/WA/SA/TAS/NT/ACT


class RegoLookupResponse(BaseModel):
    rego: str
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    engine: str | None = None
    transmission: str | None = None
    state: str | None = None
    source: str = "unknown"
    matched: str | None = None


class VehicleCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=120)
    rego: str | None = None
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    engine: str | None = None
    transmission: str | None = None
    odometer_km: int | None = 0
    condition: str = "good"
    is_primary: bool = False


class VehicleUpdate(BaseModel):
    nickname: str | None = None
    rego: str | None = None
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    engine: str | None = None
    transmission: str | None = None
    odometer_km: int | None = None
    condition: str | None = None
    is_primary: bool | None = None


class VehicleOut(BaseModel):
    id: str
    nickname: str
    rego: str | None
    vin: str | None
    make: str | None
    model: str | None
    year: int | None
    engine: str | None
    transmission: str | None
    odometer_km: int | None
    condition: str
    is_primary: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TimelineEventOut(BaseModel):
    id: str
    event_type: str
    title: str
    occurred_on: date
    odometer_km: int | None
    amount: float | None
    source_id: str | None

    model_config = {"from_attributes": True}
