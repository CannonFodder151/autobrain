"""Parts schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class PartCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str | None = None
    category: str = "other"
    quantity: int = 0
    min_quantity: int = 0
    unit_cost: float = 0.0
    supplier: str | None = None
    location: str | None = None
    notes: str | None = None
    warranty_months: int | None = None


class PartUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    category: str | None = None
    quantity: int | None = None
    min_quantity: int | None = None
    unit_cost: float | None = None
    supplier: str | None = None
    location: str | None = None
    notes: str | None = None
    warranty_months: int | None = None


class PartOut(BaseModel):
    id: str
    vehicle_id: str
    name: str
    sku: str | None
    category: str
    quantity: int
    min_quantity: int
    unit_cost: float
    supplier: str | None
    location: str | None
    notes: str | None
    warranty_months: int | None
    ai_reorder_suggestion: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PartMovementCreate(BaseModel):
    delta: int
    reason: str = "adjust"
    service_id: str | None = None


class ReorderSuggestion(BaseModel):
    part_id: str
    name: str
    quantity: int
    min_quantity: int
    suggested_order_qty: int
    reason: str
