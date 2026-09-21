"""Tire schemas."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_serializer


class TireSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    size: str = Field(min_length=1, max_length=30)
    compound: str = Field(min_length=1, max_length=30)
    position: Optional[str] = None
    purchase_date: Optional[date] = None
    purchase_cost: Optional[float] = None
    new_tread_mm: Optional[float] = 8.0
    notes: Optional[str] = None


class TireSetUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    size: Optional[str] = None
    compound: Optional[str] = None
    position: Optional[str] = None
    purchase_date: Optional[date] = None
    purchase_cost: Optional[float] = None
    new_tread_mm: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class TireSetOut(BaseModel):
    id: str
    vehicle_id: str
    name: str
    brand: str
    model: str
    size: str
    compound: str
    position: Optional[str]
    purchase_date: Optional[date]
    purchase_cost: Optional[float]
    new_tread_mm: float
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Computed fields
    heat_cycles: int
    total_sessions: int
    remaining_tread_mm: Optional[float]
    predicted_remaining_km: Optional[float]
    end_of_life_pct: Optional[float]
    is_end_of_life: bool

    @field_serializer("purchase_date")
    def _serialise_purchase(self, v):
        if isinstance(v, date):
            return v.isoformat()
        return v

    model_config = {"from_attributes": True}


class TireSessionCreate(BaseModel):
    session_date: date
    track_name: Optional[str] = None
    session_type: str = "street"
    distance_km: Optional[float] = None
    duration_minutes: Optional[int] = None
    weather: Optional[str] = None
    notes: Optional[str] = None


class TireSessionUpdate(BaseModel):
    session_date: Optional[date] = None
    track_name: Optional[str] = None
    session_type: Optional[str] = None
    distance_km: Optional[float] = None
    duration_minutes: Optional[int] = None
    weather: Optional[str] = None
    notes: Optional[str] = None


class TireSessionOut(BaseModel):
    id: str
    tire_set_id: str
    session_date: date
    track_name: Optional[str]
    session_type: str
    distance_km: Optional[float]
    duration_minutes: Optional[int]
    weather: Optional[str]
    notes: Optional[str]
    created_at: datetime

    @field_serializer("session_date")
    def _serialise_date(self, v):
        if isinstance(v, date):
            return v.isoformat()
        return v

    model_config = {"from_attributes": True}


class TireTreadReadingCreate(BaseModel):
    reading_date: date
    depth_mm: float = Field(gt=0)
    notes: Optional[str] = None


class TireTreadReadingUpdate(BaseModel):
    reading_date: Optional[date] = None
    depth_mm: Optional[float] = Field(default=None, gt=0)
    notes: Optional[str] = None


class TireTreadReadingOut(BaseModel):
    id: str
    tire_set_id: str
    reading_date: date
    depth_mm: float
    notes: Optional[str]
    created_at: datetime

    @field_serializer("reading_date")
    def _serialise_reading_date(self, v):
        if isinstance(v, date):
            return v.isoformat()
        return v

    model_config = {"from_attributes": True}


# Compound constants for frontend dropdowns
COMPOUND_CHOICES = [
    {"value": "street", "label": "Street / Daily"},
    {"value": "all_season", "label": "All Season"},
    {"value": "performance", "label": "Performance Street"},
    {"value": "track", "label": "Track Day / Semi-Slick"},
    {"value": "racing", "label": "Racing Slick"},
    {"value": "rally", "label": "Rally / Gravel"},
    {"value": "wet", "label": "Wet / Rain"},
    {"value": "drag", "label": "Drag Radial"},
]

SESSION_TYPE_CHOICES = [
    {"value": "street", "label": "Street / Daily"},
    {"value": "track", "label": "Track Day"},
    {"value": "autocross", "label": "Autocross / Time Attack"},
    {"value": "race", "label": "Race"},
]

TIRE_STATUS_CHOICES = [
    {"value": "active", "label": "Active (Mounted)"},
    {"value": "retired", "label": "Retired (Worn Out)"},
    {"value": "damaged", "label": "Damaged / Replaced"},
    {"value": "spare", "label": "Spare / Stored"},
]
