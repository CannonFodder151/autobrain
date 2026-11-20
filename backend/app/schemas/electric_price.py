"""Electric charging station price schemas (AUT-412 + AUT-466).

Premium-gated read endpoints for EV charging station prices and watchlist.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ChargingStationPriceOut(BaseModel):
    """A cached EV charging station price row."""

    station_id: str
    station_name: str | None = None
    brand: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    connector_type: str
    price_per_kwh: float | None = None
    currency: str = "AUD"
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChargingStationPriceWatchlistIn(BaseModel):
    """Per-user Electric Spy charging station price watch (AUT-466)."""

    station_id: str
    station_name: str | None = None
    brand: str | None = None
    connector_type: str
    direction: str = "both"  # "up" | "down" | "both"
    threshold_pct: float = 5.0

    @field_validator("direction")
    @classmethod
    def _direction_in_set(cls, v: str) -> str:
        if v not in ("up", "down", "both"):
            raise ValueError("direction must be one of up, down, both")
        return v

    @field_validator("threshold_pct")
    @classmethod
    def _threshold_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("threshold_pct must be > 0")
        return v


class ChargingStationPriceWatchlistOut(BaseModel):
    """Persisted Electric Spy watch row (AUT-466)."""

    id: str
    user_id: str
    station_id: str
    station_name: str | None = None
    brand: str | None = None
    connector_type: str
    direction: str
    threshold_pct: float
    created_at: datetime | None = None

    model_config = {"from_attributes": True}