"""Analytics schemas."""

from pydantic import BaseModel


class SpendSummary(BaseModel):
    fuel_total: float
    service_total: float
    mod_total: float
    parts_total: float
    total_cost_of_ownership: float
    cost_per_km: float | None
    total_km_tracked: float | None
    count_fuel: int
    count_services: int
    count_mods: int


class MonthlySpend(BaseModel):
    month: str
    fuel: float
    service: float
    mod: float


class CostForecast(BaseModel):
    next_12_months: float
    predicted_services: list[dict]
    confidence: float
    basis: str


class AnalyticsResponse(BaseModel):
    summary: SpendSummary
    monthly: list[MonthlySpend]
    forecast: CostForecast
    insights: list[str]
