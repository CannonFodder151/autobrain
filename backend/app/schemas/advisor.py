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
AdvisorFinanceMode = Literal["buy", "finance", "lease", "novated"]


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


class AmortizationRow(BaseModel):
    """One row of a loan amortization schedule.

    ``balance_end`` is the outstanding principal after the period's payment.
    All monetary values are in the response currency (AUD).
    """

    period: int = Field(ge=1, description="1-indexed payment period (month)")
    payment: float = Field(ge=0, description="Scheduled payment for this period")
    interest: float = Field(ge=0, description="Interest portion of the payment")
    principal: float = Field(ge=0, description="Principal portion of the payment")
    balance_end: float = Field(ge=0, description="Outstanding principal after this period")


class AdvisorFinanceModeBuy(BaseModel):
    mode: Literal["buy"] = "buy"
    status: Literal["ok"] = "ok"
    currency: str = "AUD"
    purchase_price: float
    effective_monthly: float
    total_cost: float
    total_interest: float = 0.0
    note: str | None = None


class AdvisorFinanceModeFinance(BaseModel):
    mode: Literal["finance"] = "finance"
    status: Literal["ok"] = "ok"
    currency: str = "AUD"
    principal: float
    term_months: int = Field(ge=1, le=120)
    annual_rate_pct: float
    monthly_payment: float
    effective_monthly: float
    total_cost: float
    total_interest: float
    amortization: list[AmortizationRow]
    note: str | None = None


class AdvisorFinanceModeLease(BaseModel):
    mode: Literal["lease"] = "lease"
    status: Literal["ok"] = "ok"
    currency: str = "AUD"
    principal: float
    term_months: int = Field(ge=12, le=60)
    residual_pct: float
    residual_value: float
    effective_monthly: float
    total_cost: float
    money_factor: float
    note: str | None = None


class AdvisorFinanceModeNovated(BaseModel):
    mode: Literal["novated"] = "novated"
    status: Literal["coming_soon"] = "coming_soon"
    currency: str = "AUD"
    effective_monthly: float | None = None
    total_cost: float | None = None
    note: str = "Novated lease calculator is coming soon. The toggle is reserved in the UI."


AdvisorFinanceModeResult = (
    AdvisorFinanceModeBuy | AdvisorFinanceModeFinance | AdvisorFinanceModeLease | AdvisorFinanceModeNovated
)


class AdvisorFinanceData(BaseModel):
    """Structured output for ``POST /advisor/finance`` (AUT-2448).

    Deterministic only: the body accepts ``{down_payment, term_months,
    rate_pct}`` (plus an optional ``novated`` toggle) and returns four mode
    blocks: buy, finance, lease, and novated. The novated mode is
    future-flagged and returns ``status="coming_soon"`` until the EV / FBT
    rules land in a later ADR.
    """

    currency: str = "AUD"
    vehicle_price: float
    down_payment: float
    modes: list[AdvisorFinanceModeResult]
    note: str | None = None


class AdvisorFinanceRequest(BaseModel):
    """Request body for ``POST /advisor/finance``.

    The same body shape is reused by the Dream Car module (AUT-2449) so the
    frontend can drive both screens with one form.
    """

    down_payment: float = Field(ge=0, description="Upfront cash contribution (AUD)")
    term_months: int = Field(ge=12, le=84, description="Loan / lease term in months")
    rate_pct: float = Field(
        ge=0,
        le=40,
        description="Nominal annual interest rate, percentage points (e.g. 7.5)",
    )
    novated: bool = Field(
        default=False,
        description="When true, also include the novated-lease block (currently coming_soon).",
    )


class AdvisorResponse(BaseModel):
    """Universal Ownership Advisor response envelope."""

    module: AdvisorModule
    vehicle_id: str | None = None
    generated_at: datetime
    model: AdvisorModel = "rule-based-fallback"
    data: dict[str, Any]
    factors: dict[str, Any] = Field(default_factory=dict)
