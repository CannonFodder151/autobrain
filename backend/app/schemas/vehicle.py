"""Vehicle schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class RegoLookupRequest(BaseModel):
    rego: str = Field(min_length=1, max_length=20)
    jurisdiction: str = Field(default="AU", max_length=4)
    state: str = Field(default="VIC", max_length=4)  # NSW/VIC/QLD/WA/SA/TAS/NT/ACT
    vehicle_type: str = "car"  # car/motorcycle — some states need the type
    vehicle_id: str | None = None  # owner's plan gates rego for shared vehicles


class RegoLookupResponse(BaseModel):
    rego: str
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    engine: str | None = None
    transmission: str | None = None
    body_type: str | None = None
    colour: str | None = None
    expiry_date: str | None = None
    description: str | None = None
    state: str | None = None
    source: str = "unknown"
    matched: str | None = None


class VehicleCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=120)
    rego: str | None = None
    rego_state: str | None = None
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    colour: str | None = None
    body_type: str | None = None
    year: int | None = None
    engine: str | None = None
    transmission: str | None = None
    odometer_km: int | None = 0
    condition: str = "good"
    vehicle_type: str = "car"
    is_primary: bool = False
    club_reg: bool = False
    auto_suggest_service: bool = False


class VehicleUpdate(BaseModel):
    nickname: str | None = None
    rego: str | None = None
    rego_state: str | None = None
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    colour: str | None = None
    body_type: str | None = None
    year: int | None = None
    engine: str | None = None
    transmission: str | None = None
    odometer_km: int | None = None
    condition: str | None = None
    vehicle_type: str | None = None
    is_primary: bool | None = None
    club_reg: bool | None = None
    auto_suggest_service: bool | None = None


class VehicleOut(BaseModel):
    id: str
    nickname: str
    rego: str | None
    rego_state: str | None = None
    vin: str | None
    make: str | None
    model: str | None
    colour: str | None
    body_type: str | None
    year: int | None
    engine: str | None
    transmission: str | None
    odometer_km: int | None
    condition: str
    vehicle_type: str = "car"
    is_primary: bool
    club_reg: bool = False
    auto_suggest_service: bool = False
    is_shared: bool = False
    shared_by: str | None = None  # owner display name when viewed via a share
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


class ShareCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ShareOut(BaseModel):
    id: str
    vehicle_id: str
    invitee_user_id: str
    invitee_email: str
    invitee_display_name: str
    status: str  # pending/accepted
    created_at: datetime


class ShareInviteOut(BaseModel):
    """A share as seen by the invitee (pending or accepted)."""

    id: str
    status: str  # pending/accepted
    vehicle_id: str
    vehicle_nickname: str
    owner_name: str
    created_at: datetime
