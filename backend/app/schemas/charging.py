"""Electric Spy charging-station price schemas (AUT-412)."""

from datetime import datetime

from pydantic import BaseModel, Field


class AttributionOut(BaseModel):
    attribution: list[str]
    sources: list[str]


class ChargingBrandOut(BaseModel):
    brand: str
    logo: str | None = None


class ChargingStationOut(BaseModel):
    id: str
    source: str
    brand: str | None = None
    name: str
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    connector_types: str | None = None
    max_power_kw: float | None = None
    logo: str | None = None
    distance_km: float | None = None
    prices: list["ChargingPriceOut"] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChargingPriceOut(BaseModel):
    connector_type: str
    price_per_kwh: float  # cents per kWh
    effective_at: datetime
    cost_per_km: float | None = None  # $/km for this price vs vehicle Wh/km (AUT-412)
    # AUT-2386-style: which feed produced this price + its arbitration score.
    source: str | None = None
    arbitration_score: float | None = None

    model_config = {"from_attributes": True}


class ChargingHistoryRawSource(BaseModel):
    source: str
    price_per_kwh: float
    effective_at: datetime
    score: float


class ChargingHistoryPoint(BaseModel):
    connector_type: str
    price_per_kwh: float
    effective_at: datetime
    source: str | None = None
    score: float | None = None
    raw_sources: list[ChargingHistoryRawSource] = Field(default_factory=list)


class ChargingStationHistoryOut(BaseModel):
    station_id: str
    source: str
    connector_type: str | None = None
    days: int
    series: list[ChargingHistoryPoint]


class ChargingWatchlistIn(BaseModel):
    station_id: str
    connector_type: str
    target_price_per_kwh: float | None = Field(
        default=None, description="Optional alert threshold in cents/kWh."
    )


class ChargingWatchlistOut(BaseModel):
    id: str
    user_id: str
    station_id: str
    connector_type: str
    target_price_per_kwh: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


ChargingStationOut.model_rebuild()