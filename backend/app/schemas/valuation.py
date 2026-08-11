"""Valuation schemas."""

from datetime import datetime

from pydantic import BaseModel


class ValuationRequest(BaseModel):
    odometer_km: int | None = None
    condition: str | None = None
    extra_context: dict | None = None


class MarketListing(BaseModel):
    title: str = ""
    price: float | None = None
    year: int | None = None
    odometer_km: int | None = None
    source: str = ""
    url: str = ""


class MarketDataResponse(BaseModel):
    query: str = ""
    source: str = "fallback"
    listings: list[MarketListing] = []
    median_price: float | None = None
    low_price: float | None = None
    high_price: float | None = None
    sample_size: int = 0
    as_of: str | None = None
    stale: bool = False
    note: str | None = None


class ValuationResponse(BaseModel):
    estimated_value: float
    low: float
    high: float
    currency: str
    factors: dict
    recommendations: list[str]
    trend: list[dict]
    model: str
    market: MarketDataResponse | None = None


class ValuationOut(BaseModel):
    id: str
    vehicle_id: str
    estimated_value: float
    low: float
    high: float
    currency: str
    factors: str | None
    recommendations: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
