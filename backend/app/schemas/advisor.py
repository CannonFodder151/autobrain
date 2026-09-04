"""Schemas for the Ownership Advisor surface (AUT-2425 / AUT-2445-VALUE).

Envelope is shared across all six sub-modules (value / replace / upgrade /
finance / dream / ai) per ADR 0001 (docs/adr/0001-ownership-advisor.md):
every response is a flat envelope with the module's structured output in
``data`` and provenance / signals in ``factors``. The envelope is
deliberately uniform so the frontend can render any module with the same
parser and so the AI Advisor module can compose the others as opaque
``data`` blobs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AdvisorModule = Literal["value", "replace", "upgrade", "finance", "dream", "ai"]
AdvisorModel = Literal["rule-based-fallback", "rule-based+ai", "9router/<combo>"]


class ComparableListing(BaseModel):
    title: str = ""
    price: float
    year: int | None = None
    odometer_km: int | None = None
    source: str = ""
    url: str = ""


class TradeInBand(BaseModel):
    currency: str = "AUD"
    low: float | None = None
    mid: float | None = None
    high: float | None = None
    ratios: dict[str, float] = Field(
        default_factory=lambda: {"low": 0.75, "mid": 0.82, "high": 0.90},
    )


class AdvisorValueData(BaseModel):
    """Structured output for ``GET /advisor/value`` (AUT-2445).

    The value module is deterministic: anchored on the cached
    ``market_listing_cache`` median, adjusted for vehicle condition and
    odometer, and presented as a tight low / mid / high band with a
    trade-in band and a list of comparables (same make/model, year ±3).
    """

    currency: str = "AUD"
    low: float | None = None
    mid: float | None = None
    high: float | None = None
    source: str = "fallback"
    as_of: str | None = None
    stale: bool = False
    sample_size: int = 0
    condition_multiplier: float = 1.0
    km_multiplier: float = 1.0
    comparable_count: int = 0
    comparable_window_years: int = 3
    comparables: list[ComparableListing] = Field(default_factory=list)
    trade_in: TradeInBand = Field(default_factory=TradeInBand)
    note: str | None = None


class AdvisorResponse(BaseModel):
    """Universal Ownership Advisor response envelope."""

    module: AdvisorModule
    vehicle_id: str | None = None
    generated_at: datetime
    model: AdvisorModel = "rule-based-fallback"
    data: dict[str, Any]
    factors: dict[str, Any] = Field(default_factory=dict)
