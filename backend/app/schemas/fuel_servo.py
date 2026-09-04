"""Servo Spy fuel-price API schemas (AUT-1817). Premium-gated read endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class FuelStationOut(BaseModel):
    id: str
    source: str
    brand: str | None = None
    name: str
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    logo: str | None = None
    distance_km: float | None = None  # populated by the /stations radius query
    prices: list["FuelPriceOut"] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FuelPriceOut(BaseModel):
    fuel_type: str
    price: float  # cents per litre
    effective_at: datetime
    cost_per_km: float | None = None  # $/km for this price vs vehicle avg L/100km (AUT-2201)
    avg_fill_cost: float | None = None  # $ per fill for this price vs vehicle avg litres/fill
    # AUT-2381: which upstream emitted this row + the arbitration result for
    # (station, fuel_type, day). The UI uses ``best_source`` to badge the
    # reading as "trusted" / "government" / "chain".
    source: str | None = None
    best_source: str | None = None
    source_score: float | None = None
    flag_reason: str | None = None

    model_config = {"from_attributes": True}


class FuelPriceHistoryOut(BaseModel):
    """One row of a station's per-(fuel_type, source, day) price history.

    Used by ``GET /api/v1/fuel/stations/{station_id}/history`` (AUT-2374 +
    AUT-2381). The UI shows one row per source so the user can see which
    upstream the day's price came from.
    """

    fuel_type: str
    source: str | None = None
    price: float
    effective_at: datetime
    best_source: str | None = None
    source_score: float | None = None
    flag_reason: str | None = None

    model_config = {"from_attributes": True}


class FuelBrandOut(BaseModel):
    brand: str
    logo: str | None = None


class AttributionOut(BaseModel):
    attribution: list[str]
    sources: list[str]


FuelStationOut.model_rebuild()
