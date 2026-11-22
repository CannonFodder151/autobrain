"""PHEV dual-source tracking schemas."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class PhevDistanceMetrics(BaseModel):
    total_km: float
    ev_km: float
    ice_km: float
    ev_ratio: float = Field(ge=0, le=1)


class PhevEnergyMetrics(BaseModel):
    fuel_litres: float
    fuel_cost: float
    charge_kwh: float
    electricity_cost: float
    total_cost: float


class PhevEfficiencyMetrics(BaseModel):
    fuel_l_per_100km: float | None = None
    ev_kwh_per_100km: float | None = None
    combined_l_per_100km_equiv: float | None = None
    combined_mpge: float | None = None


class PhevCostMetrics(BaseModel):
    cost_per_km: float | None = None
    cost_per_mile: float | None = None


class PhevAiInsight(BaseModel):
    type: Literal["recommendation", "alert", "savings"]
    title: str
    detail: str
    priority: Literal["low", "medium", "high"]


class PhevDashboardOut(BaseModel):
    vehicle_id: str
    powertrain: str
    period_days: int
    sources: dict[str, int]
    distance: PhevDistanceMetrics
    energy: PhevEnergyMetrics
    efficiency: PhevEfficiencyMetrics
    cost: PhevCostMetrics
    ai_insights: list[PhevAiInsight]


class PhevTimelineEventOut(BaseModel):
    id: str
    event_type: str  # fuel | ev_trip
    title: str
    occurred_on: date
    odometer_km: int | None = None
    amount: float | None = None
    source_id: str | None = None
    # PHEV-specific fields
    ev_distance_km: float | None = None
    ice_distance_km: float | None = None
    charge_kwh: float | None = None
    litres: float | None = None

    model_config = {"from_attributes": True}


class PhevTimelineOut(BaseModel):
    vehicle_id: str
    events: list[PhevTimelineEventOut]


class PhevExportRequest(BaseModel):
    fy: int | None = None  # Australian financial year (default: current)
    fmt: Literal["csv"] = "csv"


class PhevExportResponse(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
