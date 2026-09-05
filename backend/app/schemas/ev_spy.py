"""Electric Spy charging-station API schemas (AUT-2435).

Mirrors the fuel_servo schema pattern. Connector types and power ratings
replace fuel types and cents/L pricing.
"""

from pydantic import BaseModel, Field


class ChargingConnectorOut(BaseModel):
    connector_type: str  # Type 2, CCS2, CHAdeMO, Tesla, etc.
    max_power_kw: float | None = None
    cost_per_kwh: float | None = None
    status: str | None = None  # "Available", "In Use", "Unknown", etc.
    model_config = {"from_attributes": True}


class ChargingStationOut(BaseModel):
    id: str
    network: str | None = None
    name: str
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    distance_km: float | None = None
    connectors: list[ChargingConnectorOut] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class EvAttributionOut(BaseModel):
    attribution: list[str]
    sources: list[str]
