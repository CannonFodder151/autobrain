"""Schemas for the Ownership Advisor surface (AUT-2425 / AUT-2445-VALUE / AUT-2448-FINANCE / AUT-2450-AI).

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

AdvisorModule = Literal["value", "replace", "upgrade", "finance", "dream", "ai", "car-check"]
AdvisorModel = Literal["rule-based-fallback", "rule-based+ai", "9router/<combo>"]
AdvisorDecision = Literal["keep", "upgrade", "delay", "strategy"]
AdvisorFinanceMode = Literal["buy", "finance", "lease", "novated"]


class ComparableListing(BaseModel):
    title: str = ""
    price: float
    year: int | None = None
    odometer_km: int | None = None
    source: str = ""
    url: str = ""


class CarCheckRequest(BaseModel):
    """Request body for ``POST /advisor/car-check`` (AUT-2651)."""

    listing: dict[str, Any] = Field(..., description="Parsed market listing to evaluate.")
    reference_price: float | None = Field(default=None, ge=0, description="Reference price for deal-score anchoring.")
    vehicle_year: int | None = Field(default=None, ge=1900, le=2100, description="User's vehicle year for age-based scoring.")


class CarCheckData(BaseModel):
    """Structured output for ``POST /advisor/car-check`` (AUT-2651)."""

    deal_score: float | None = Field(default=None, description="0-100 deal score (None when insufficient data).")
    summary: str = ""
    red_flags: list[str] = Field(default_factory=list)
    green_flags: list[str] = Field(default_factory=list)
    model: str = "rule-based-fallback"


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


class AdvisorAIBasedOn(BaseModel):
    """Which sub-modules contributed structured data to the AI decision.

    Booleans only; no numbers invented here. Lets the UI surface
    "Based on: Value, Replace, Finance" instead of guessing.
    """

    value: bool = False
    replace: bool = False
    upgrade: bool = False
    finance: bool = False
    dream: bool = False


class AdvisorAIData(BaseModel):
    """Structured output for ``POST /advisor/ai`` (AUT-2450).

    The AI advisor is the only module that hits 9Router. The decision
    is deterministic (rule-based baseline); 9Router may add a richer
    rationale and sharper next_actions but never invents numbers and
    never changes the decision.
    """

    decision: AdvisorDecision = "keep"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = ""
    next_actions: list[str] = Field(default_factory=list)
    based_on: AdvisorAIBasedOn = Field(default_factory=AdvisorAIBasedOn)


class AdvisorAIRequest(BaseModel):
    """Request body for ``POST /advisor/ai``.

    The caller (frontend) supplies structured outputs from the other
    sub-modules — typically fetched via their GET/POST endpoints in the
    same render. The AI never re-fetches them and never invents numbers.
    """

    question: str | None = Field(default=None, max_length=500)
    value: dict[str, Any] | None = None
    replace: dict[str, Any] | None = None
    upgrade: dict[str, Any] | None = None
    finance: dict[str, Any] | None = None
    dream: dict[str, Any] | None = None


class AdvisorDreamRequest(BaseModel):
    """Request body for ``POST /advisor/dream`` (AUT-2449).

    Target vehicle identification is the only required input. The
    finance profile is optional (all fields default to ``None``) — when
    any of ``annual_income``, ``monthly_expenses``, ``cash_on_hand``
    is supplied, the affordability block uses them; otherwise the
    affordability block returns a well-formed ``note`` explaining the
    gap (ADR 0001 §2.4: finance inputs are ephemeral, no DB migration).
    """

    make: str = Field(..., min_length=1, max_length=80)
    model: str = Field(..., min_length=1, max_length=80)
    year: int = Field(..., ge=1900, le=2100)
    vehicle_type: str = Field("car", pattern=r"^(car|bike|motorcycle|truck|van)$")
    finance_term_months: int | None = Field(
        None, ge=12, le=84,
        description="Indicative finance term. Server clamps to [12, 84].",
    )
    rate_pct: float | None = Field(
        None, ge=0.0, le=30.0,
        description="Indicative rate % p.a. Clamped to [0, 30].",
    )
    deposit_pct: float | None = Field(
        None, ge=0.0, le=100.0,
        description="Deposit % funded up front. Clamped to [0, 100].",
    )
    annual_income: float | None = Field(
        None, ge=0.0,
        description="Annual gross income (currency: AUD). Optional.",
    )
    monthly_expenses: float | None = Field(
        None, ge=0.0,
        description="Average monthly living expenses (currency: AUD). Optional.",
    )
    cash_on_hand: float | None = Field(
        None, ge=0.0,
        description="Cash available for deposit + on-road costs. Optional.",
    )


class DreamTarget(BaseModel):
    """Market-data lookup for the user's dream vehicle.

    Reuses the cached ``market_listing_cache`` row for (make, model,
    year) — same key shape as the Value/Upgrade modules, no duplicate
    storage (ADR 0001 §2.5).
    """

    make: str
    model: str
    year: int
    vehicle_type: str = "car"
    currency: str = "AUD"
    low: float | None = None
    mid: float | None = None
    high: float | None = None
    source: str = "fallback"
    as_of: str | None = None
    stale: bool = False
    sample_size: int = 0
    note: str | None = None


class DreamAffordability(BaseModel):
    """Gap between the dream vehicle and the user's stated finances.

    Pure arithmetic on the request-body inputs — no DB read. When any
    of ``annual_income``, ``monthly_expenses``, ``cash_on_hand`` is
    missing, ``note`` explains the gap and the numeric fields stay
    ``None``. The surplus flag fires when the user can comfortably fund
    the dream vehicle (positive disposable + enough cash for the
    deposit).
    """

    currency: str = "AUD"
    target_price_mid: float | None = None
    deposit_required: float | None = None
    annual_income: float | None = None
    monthly_disposable_income: float | None = None
    cash_on_hand: float | None = None
    cash_gap: float | None = None  # cash_on_hand - deposit_required (negative = shortfall)
    surplus: bool = False
    note: str | None = None


class DreamRepayments(BaseModel):
    """Indicative finance on the unfunded portion of the dream vehicle.

    Wraps the existing ``_loan_monthly_payment`` helper from
    ``app.services.advisor`` so the Dream module never re-derives a
    number the Upgrade module already published. Same constants
    (default term 60, rate 7.5% p.a., deposit 20%) — clamped via the
    existing helpers so neither the UI nor the AI fallback has to
    invent them.
    """

    currency: str = "AUD"
    finance_term_months: int = 60
    rate_pct: float = 7.5
    deposit_pct: float = 20.0
    principal: float | None = None  # target_price_mid * (1 - deposit_pct/100)
    monthly_repayment: float | None = None
    total_interest: float | None = None
    note: str | None = None


class AdvisorDreamData(BaseModel):
    """Structured output for ``POST /advisor/dream`` (AUT-2449).

    Three blocks: target lookup (reuses ``market_listing_cache``),
    affordability (pure arithmetic on the request-body finance profile),
    and indicative repayments (reuses ``_loan_monthly_payment``). All
    deterministic — no 9Router, no AI.
    """

    currency: str = "AUD"
    target: DreamTarget
    affordability: DreamAffordability
    repayments: DreamRepayments
    note: str | None = None


class FundingGapBand(BaseModel):
    """Funding-gap band for the Replace module (AUT-2446).

    ``gap`` = ``replacement_cost - current_value - trade_in``.
    ``monthly_target`` is the per-month saving needed to close it over the
    user-supplied ``horizon_months`` (default 36, i.e. 3 years). When the
    gap is negative (replacement costs less than current value + trade-in)
    the response surfaces a zero target and a ``surplus`` flag instead.
    """

    currency: str = "AUD"
    horizon_months: int = 36
    gap: float | None = None
    monthly_target: float | None = None
    surplus: bool = False
    note: str | None = None


class AdvisorReplaceData(BaseModel):
    """Structured output for ``GET /advisor/replace`` (AUT-2446).

    All three costs share the same currency and are anchored on the
    existing value module so the Replace surface never re-derives a number
    that the Value surface already published. Used replacement cost ==
    current private-sale mid (a buyer for your car is a buyer for a similar
    car of the same vintage/condition). New replacement cost applies a
    documented age-based new-vs-used premium on top of the same anchor. The
    funding-gap band is computed exactly as the AC specifies:

        gap = replacement_cost - current_value - trade_in
    """

    currency: str = "AUD"
    current_value: float | None = None
    trade_in: TradeInBand = Field(default_factory=TradeInBand)
    used_replacement_cost: float | None = None
    new_replacement_cost: float | None = None
    age_years: int | None = None
    new_used_premium: float = 1.0
    horizon_months: int = 36
    funding_gap: FundingGapBand = Field(default_factory=FundingGapBand)
    note: str | None = None


class UpgradeOption(BaseModel):
    """Next-tier option for the same model (AUT-2447).

    ``score`` is a deterministic 0..1 relevance ranking (higher = closer
    tier fit). ``price_mid`` is the cached market median for that year,
    adjusted by the existing condition + odometer pipeline; ``price_delta``
    is the cost of stepping up from the user's current vehicle to this
    option (positive = costs more; negative = cheaper tier / older year).
    """

    make: str
    model: str
    year: int
    tier_label: str  # "newer (nxt)", "newer (+2)", "older (-1)"
    price_low: float | None = None
    price_mid: float | None = None
    price_high: float | None = None
    price_delta: float | None = None
    score: float = 0.0
    note: str | None = None

class SimilarVehicleSuggestion(BaseModel):
    """Cross-brand suggestion in the same segment (AUT-2447).

    Ranked by a deterministic relevance score: body_type match × age
    proximity × price-band proximity (all normalised to [0, 1] and
    averaged). Excludes the user's current make/model so the list never
    duplicates the upgrade-options block.
    """

    make: str
    model: str
    year: int | None = None
    body_type: str | None = None
    price_mid: float | None = None
    score: float = 0.0
    note: str | None = None

class TradeUpDelta(BaseModel):
    """Current -> upgrade delta + indicative finance delta (AUT-2447).

    The finance delta is a simple indicative repayment using a flat-rate
    amortization over ``finance_term_months`` (default 60) at ``rate_pct``
    (default 7.5% p.a.) on ``(upgrade_price - trade_in_mid) * (1 -
    deposit_pct)``. Deposit default 20%. Constants chosen to match the
    AU new-car floor (RACV / ATO guides) and documented here so neither
    the UI nor the AI fallback has to invent them.
    """

    currency: str = "AUD"
    finance_term_months: int = 60
    rate_pct: float = 7.5
    deposit_pct: float = 20.0
    principal: float | None = None  # upgrade_price - trade_in_mid
    monthly_repayment: float | None = None
    total_interest: float | None = None
    surplus: bool = False
    note: str | None = None

class AdvisorUpgradeData(BaseModel):
    """Structured output for ``GET /advisor/upgrade`` (AUT-2447).

    Three blocks: same-model upgrade options (next 1-2 tiers), similar
    cross-brand suggestions, and a per-upgrade trade-up delta table
    (price delta + indicative monthly). All deterministic — anchors on
    the cached market median the Value module already uses, no AI.
    """

    currency: str = "AUD"
    current_value: float | None = None
    upgrade_options: list[UpgradeOption] = Field(default_factory=list)
    similar_vehicles: list[SimilarVehicleSuggestion] = Field(default_factory=list)
    trade_up: list[TradeUpDelta] = Field(default_factory=list)
    finance_term_months: int = 60
    rate_pct: float = 7.5
    deposit_pct: float = 20.0
    note: str | None = None


class AdvisorCarCheckData(BaseModel):
    """Structured output for ``POST /advisor/car-check`` (AUT-2630).

    The Car Check module is fully deterministic: it anchors on the
    existing ``market_listing_cache`` (the same cache the Value module
    uses — no duplicate storage), applies the documented condition and
    odometer multipliers from ``app.services.advisor``, and returns a
    one-line verdict with the fair-value band and delta.

    The AI summary and ``red_flags`` / ``green_flags`` are layered on
    top by 9Router via the AI gateway (``ai/app/modules/car_check.py``)
    when reachable; the ``model`` field records the source. When 9Router
    is unreachable the route falls back to the rule-based
    ``ai_summary`` produced by ``app.services.car_check`` so the
    frontend always has readable copy. The ``verdict``, ``fair_value_*``
    and ``delta_pct`` fields are *never* invented by the AI — they come
    entirely from ``compute_car_check``.
    """

    currency: str = "AUD"
    verdict: str = "risky"
    asking_price: float | None = None
    fair_value_low: float | None = None
    fair_value_mid: float | None = None
    fair_value_high: float | None = None
    delta_pct: float | None = None
    delta_amount: float | None = None
    sample_size: int = 0
    condition_multiplier: float = 1.0
    km_multiplier: float = 1.0
    ai_summary: str = ""
    red_flags: list[str] = Field(default_factory=list)
    green_flags: list[str] = Field(default_factory=list)
    note: str | None = None


class CarCheckRequest(BaseModel):
    """Request body for ``POST /advisor/car-check``.

    Either ``listing_url`` (best-effort parser) or the inline
    ``make``/``model``/``year`` + ``asking_price`` fields are required.
    The listing_url path runs the slug parser; if it can't extract
    all three fields the route falls back to the manual form with a
    ``note`` on the response explaining the gap so the frontend can
    prompt the user.
    """

    listing_url: str = Field(default="", description="Public listing URL (CarsGuide, CarSales, FB Marketplace, etc.)")
    make: str = Field("", description="Vehicle make")
    model: str = Field("", description="Vehicle model")
    year: int | None = Field(None, ge=1900, le=2100)
    asking_price: float = Field(..., gt=0, description="Listing asking price (AUD)")
    odometer_km: int | None = Field(None, ge=0, description="Odometer reading (km)")
    condition: str | None = Field(None, description="Vehicle condition: excellent|good|fair|poor")
    vehicle_type: str = Field("car", pattern=r"^(car|bike|motorcycle|truck|van)$")


class AdvisorResponse(BaseModel):
    """Universal Ownership Advisor response envelope."""

    module: AdvisorModule
    vehicle_id: str | None = None
    generated_at: datetime
    model: AdvisorModel = "rule-based-fallback"
    data: dict[str, Any]
    factors: dict[str, Any] = Field(default_factory=dict)
