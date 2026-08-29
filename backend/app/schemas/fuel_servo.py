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

    model_config = {"from_attributes": True}


class FuelBrandOut(BaseModel):
    brand: str
    logo: str | None = None


class AttributionOut(BaseModel):
    attribution: list[str]
    sources: list[str]


FuelStationOut.model_rebuild()
