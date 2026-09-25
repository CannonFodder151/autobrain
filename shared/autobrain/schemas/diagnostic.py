"""Shared Diagnostic schemas used by both backend and AI."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
DiagnosticStatus = Literal["open", "in_progress", "resolved"]


class DiagnosticBase(BaseModel):
    """Base diagnostic entry (minimal shared fields)."""
    vehicle_id: str
    dtc_code: Optional[str] = None
    description: str
    severity: Severity = "low"
    status: DiagnosticStatus = "open"


class DiagnosticOut(DiagnosticBase):
    """Diagnostic output schema."""
    id: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    embedding: Optional[list[float]] = None


class DTCCode(BaseModel):
    """Diagnostic Trouble Code with decode info."""
    code: str
    description: str
    severity: Severity
    system: Optional[str] = None
    is_common: bool = False


class OdometerReading(BaseModel):
    """Odometer reading from AI vision module."""
    odometer_km: Optional[int] = None
    confidence: float = 0.0
    model: str = "rule-based-fallback"