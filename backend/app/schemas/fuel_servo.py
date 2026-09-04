"""Servo Spy fuel-price API schemas (AUT-1817 + AUT-2386). Premium-gated read endpoints."""

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
    # AUT-2386: which feed produced this price + its arbitration score, when
    # the value comes from the per-day arbitration table. Null on legacy rows
    # ingested before the column existed.
    source: str | None = None
    arbitration_score: float | None = None

    model_config = {"from_attributes": True}

class FuelBrandOut(BaseModel):
    brand: str
    logo: str | None = None


class AttributionOut(BaseModel):
    attribution: list[str]
    sources: list[str]


class FuelHistoryRawSource(BaseModel):
    """AUT-2386: one contributing source for a history point.

    Returned in the ``raw_sources`` array so the chart can show, e.g.
    "NSW FuelCheck 189.9, WA FuelWatch 191.5" and the client knows why the
    winning value was chosen.
    """

    source: str
    price: float
    effective_at: datetime
    score: float


class FuelHistoryPoint(BaseModel):
    """AUT-2375 + AUT-2386: one history point with the winning source + score.

    ``source`` and ``score`` are the per-day arbitration result;
    ``raw_sources`` is every source that reported a price on the same UTC day
    for the same fuel so the client can see the inputs.
    """

    fuel_type: str
    price: float
    effective_at: datetime
    source: str | None = None
    score: float | None = None
    raw_sources: list[FuelHistoryRawSource] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FuelStationHistoryOut(BaseModel):
    """AUT-2375 + AUT-2386: 30-day price history for a single station.

    Served exclusively from the ``fuel_prices`` cache populated by the daily
    Celery ingest — never fans out to the upstream API on a client request.
    The per-point ``source``/``score``/``raw_sources`` come from
    ``fuel_price_arbitrations`` so /history and the live list tell the same
    story.
    """

    station_id: str
    source: str
    fuel_type: str | None = None  # if set, only the matching series is returned
    days: int
    series: list[FuelHistoryPoint]


FuelStationOut.model_rebuild()
