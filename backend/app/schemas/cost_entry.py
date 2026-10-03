"""Cost tracking schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.cost_entry import CostCategory


class CostEntryCreate(BaseModel):
    category: CostCategory
    amount: float = Field(..., gt=0, description="Cost amount in the specified currency")
    currency: str = "AUD"
    date: date
    odometer_km: int | None = None
    description: str | None = Field(None, max_length=500)
    vendor: str | None = Field(None, max_length=255)
    receipt_id: str | None = None
    track_name: str | None = Field(None, max_length=255)
    laps_completed: int | None = Field(None, ge=0)


class CostEntryUpdate(BaseModel):
    category: CostCategory | None = None
    amount: float | None = Field(None, gt=0)
    currency: str | None = None
    date: date | None = None
    odometer_km: int | None = None
    description: str | None = None
    vendor: str | None = None
    receipt_id: str | None = None
    track_name: str | None = None
    laps_completed: int | None = Field(None, ge=0)


class CostEntryOut(BaseModel):
    id: str
    vehicle_id: str
    category: CostCategory
    amount: float
    currency: str
    date: date
    odometer_km: int | None
    description: str | None
    vendor: str | None
    receipt_id: str | None
    track_name: str | None
    laps_completed: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CategoryBreakdown(BaseModel):
    category: CostCategory
    total: float
    count: int


class CostDashboard(BaseModel):
    total_spent: float
    category_breakdown: list[CategoryBreakdown]
    cost_per_track_day: float | None
    cost_per_lap: float | None
    track_days_count: int
    total_laps: int
    monthly_trend: list[dict]
    budget_vs_actual: dict | None = None


class BudgetCreate(BaseModel):
    category: CostCategory
    monthly_budget: float
    year_month: str  # Format: YYYY-MM


class BudgetOut(BaseModel):
    id: str
    vehicle_id: str
    category: CostCategory
    monthly_budget: float
    year_month: str
    created_at: datetime

    model_config = {"from_attributes": True}
