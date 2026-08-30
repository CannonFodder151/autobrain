"""Diagnostic schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class DiagnosticRequest(BaseModel):
    symptoms: str = Field(min_length=3, max_length=4000)
    vehicle_context: dict | None = None
    obd_codes: list[str] = []


class DiagnosticItem(BaseModel):
    cause: str
    confidence: float
    severity: str  # low/medium/high/critical
    parts_needed: list[str] = []
    parts: list[dict] = []  # [{"name": str, "part_number": str|None}]
    repair_notes: str | None = None
    estimated_cost: float | None = None
    cost_range: list[float] | None = None


class DiagnosticResponse(BaseModel):
    summary: str
    severity: str = "medium"
    estimated_cost: float | None = None
    cost_range: list[float] | None = None
    items: list[DiagnosticItem] = []
    parts_needed: list[str] = []
    recommended_actions: list[str] = []
    model: str  # which AI path produced it


class DiagnosticOut(BaseModel):
    id: str
    vehicle_id: str
    symptoms: str
    ai_response: str
    summary: str | None
    severity: str | None
    estimated_cost: float | None
    parts_needed: str | None
    added_to_service: bool
    linked_service_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AddToServiceRequest(BaseModel):
    service_date: datetime | None = None
    notes: str | None = None
