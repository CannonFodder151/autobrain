from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class FuelState(str, Enum):
    WA = "WA"
    QLD = "QLD"
    NSW = "NSW"
    ACT = "ACT"
    VIC = "VIC"


class FeedStatus(str, Enum):
    OK = "ok"
    DOWN = "down"
    PENDING = "pending"


class FeedHealth(BaseModel):
    state: str
    feed: str
    status: FeedStatus
    last_success: Optional[str] = None
    last_error: Optional[str] = None


class Station(BaseModel):
    id: str
    name: str
    state: str
    suburb: Optional[str] = None
    price_cpl: Optional[float] = None
    fuel_type: Optional[str] = None
    updated_at: Optional[str] = None
    freshness_minutes: Optional[int] = None


class FuelPriceResponse(BaseModel):
    state: str
    available: bool
    message: Optional[str] = None
    stations: List[Station] = Field(default_factory=list)
    feed_status: Optional[FeedHealth] = None


class FeedHealthResponse(BaseModel):
    feeds: List[FeedHealth] = Field(default_factory=list)
