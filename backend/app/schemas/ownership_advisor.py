from pydantic import BaseModel, Field
from typing import Optional


class OwnershipAdvisorInput(BaseModel):
    vehicle_id: str = Field(..., min_length=1, max_length=50)
    make: str = Field("Toyota", max_length=100)
    model: str = Field("Corolla", max_length=100)
    year: int = Field(2018, ge=1900, le=2100)
    mileage: int = Field(60000, ge=0, le=2_000_000)
    current_value: float = Field(18000.0, ge=0)
    replacement_cost: float = Field(25000.0, ge=0)
    upgrade_budget: float = Field(10000.0, ge=0)
    interest_rate: float = Field(0.06, ge=0, le=1.0)
    loan_term_months: int = Field(60, gt=0, le=360)
    dream_price: float = Field(45000.0, ge=0)
    dream_monthly_budget: float = Field(600.0, ge=0)


class AdvisorResultOut(BaseModel):
    mode: str
    value: float
    detail: str
    breakdown: dict = Field(default_factory=dict)


class OwnershipAdvisorResponse(BaseModel):
    vehicle_id: str
    results: list[AdvisorResultOut]
    used_fallback: bool = True
    ai_explanation: Optional[str] = None