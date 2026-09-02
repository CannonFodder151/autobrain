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
    # Per-station projection of the vehicle's own fuel stats (AUT-2053). Null
    # when the request omits ?vehicle_id or the vehicle has no stats yet.
    cost_per_km: float | None = None  # $/km at this station's price
    avg_fill_cost: float | None = None  # $ for one avg fill at this station

    model_config = {"from_attributes": True}


class FuelBrandOut(BaseModel):
    brand: str
    logo: str | None = None


class AttributionOut(BaseModel):
    attribution: list[str]
    sources: list[str]


class FuelHistoryPoint(BaseModel):
    """AUT-2375: one historical price point in the 30-day series."""

    fuel_type: str
    price: float
    effective_at: datetime

    model_config = {"from_attributes": True}


class FuelStationHistoryOut(BaseModel):
    """AUT-2375: 30-day price history for a single station (one series per fuel).

    Served exclusively from the ``fuel_prices`` cache populated by the daily
    Celery ingest — never fans out to the upstream API on a client request.
    """

    station_id: str
    source: str
    fuel_type: str | None = None  # if set, only the matching series is returned
    days: int
    series: list[FuelHistoryPoint]


FuelStationOut.model_rebuild()
