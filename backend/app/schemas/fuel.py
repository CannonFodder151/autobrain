"""Fuel schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class FuelLogCreate(BaseModel):
    fill_date: date
    odometer_km: int
    litres: float = Field(gt=0)
    price_per_litre: float = Field(gt=0)
    total_cost: float | None = None
    is_full_tank: bool = True
    notes: str | None = None
    receipt_id: str | None = None


class FuelLogUpdate(BaseModel):
    fill_date: date | None = None
    odometer_km: int | None = None
    litres: float | None = Field(default=None, gt=0)
    price_per_litre: float | None = Field(default=None, gt=0)
    total_cost: float | None = None
    is_full_tank: bool | None = None
    notes: str | None = None
    receipt_id: str | None = None


class FuelLogOut(BaseModel):
    id: str
    vehicle_id: str
    fill_date: date
    odometer_km: int
    litres: float
    price_per_litre: float
    total_cost: float
    is_full_tank: bool
    notes: str | None
    distance_km: float | None
    l_per_100km: float | None
    cost_per_km: float | None
    receipt_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FuelStats(BaseModel):
    total_litres: float
    total_cost: float
    avg_l_per_100km: float | None
    avg_cost_per_km: float | None
    last_log: FuelLogOut | None
    series: list[dict]


class FuelReceiptResult(BaseModel):
    receipt_id: str
    file_url: str
    vendor: str | None = None
    date: str | None = None
    litres: float | None = None
    price_per_litre: float | None = None
    total_cost: float | None = None
    currency: str = "AUD"
    ai_used: bool = False


class FuelPriceQuote(BaseModel):
    """One 7-Eleven price quote (cents per litre)."""

    fuel_type: str
    price_cpl: float
    station: str
    suburb: str
    state: str
    postcode: str
    lat: float | None = None
    lng: float | None = None
    rank: int | None = None  # 1=cheapest, 2/3 for region mode
    distance_km: float | None = None  # set in nearest mode


class SevenElevenPricesOut(BaseModel):
    """Accurate 7-Eleven fuel prices (projectzerothree.info). Deterministic, no AI."""

    source: str = "projectzerothree"
    updated: int | None = None  # upstream snapshot timestamp (unix)
    as_of: str | None = None  # when we fetched/cached (ISO)
    mode: str  # "cheapest" | "nearest"
    fuel_type: str
    region: str | None = None
    quotes: list[FuelPriceQuote]
