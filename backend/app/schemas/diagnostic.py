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
    # --- AUT-397: Trustworthy AI Diagnostics ---
    evidence: dict | None = None  # raw DTC/freeze-frame/PID context
    confidence_rationale: str | None = None  # why this confidence level
    known_vs_inferred: dict | None = None  # "what we know" vs "what we infer"
    limitations: str | None = None  # safe disclaimer / limitation text


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
    status: str
    resolved_at: datetime | None
    created_at: datetime
    # --- AUT-397: Trustworthy AI Diagnostics ---
    evidence: str | None = None
    confidence_rationale: str | None = None
    known_vs_inferred: str | None = None
    limitations: str | None = None
    feedback_helpful: bool | None = None
    feedback_comment: str | None = None
    feedback_at: datetime | None = None

    model_config = {"from_attributes": True}


class AddToServiceRequest(BaseModel):
    service_date: datetime | None = None
    notes: str | None = None


class DiagnosticFeedbackRequest(BaseModel):
    helpful: bool
    comment: str | None = None


class DiagnosticFeedbackResponse(BaseModel):
    id: str
    feedback_helpful: bool | None
    feedback_comment: str | None
    feedback_at: datetime | None
    updated_at: datetime
