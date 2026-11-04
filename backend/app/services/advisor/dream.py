"""Dream Car module (AUT-2449): deterministic affordability for a target vehicle.

Reuses the cached ``market_listing_cache`` for the target (make, model, year)
and the existing ``_loan_monthly_payment`` helper from the Finance module.
All arithmetic is pure and deterministic — no AI, no 9Router.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.advisor._common import CURRENCY, _safe

# ── constants ─────────────────────────────────────────────────────────────
DREAM_DSR_CEILING = 0.30  # 30% of monthly disposable income (AU bank ceiling)

DREAM_FINANCE_TERM_MIN = 12
DREAM_FINANCE_TERM_MAX = 84
DREAM_RATE_PCT_MIN = 0.0
DREAM_RATE_PCT_MAX = 30.0
DREAM_DEPOSIT_PCT_MIN = 0.0
DREAM_DEPOSIT_PCT_MAX = 100.0

DREAM_DEFAULT_FINANCE_TERM_MONTHS = 60
DREAM_DEFAULT_RATE_PCT = 7.5
DREAM_DEFAULT_DEPOSIT_PCT = 20.0


# ── clamp helpers ─────────────────────────────────────────────────────────

def _dream_clamp_term(months: int | None) -> int:
    if months is None:
        return DREAM_DEFAULT_FINANCE_TERM_MONTHS
    try:
        m = int(months)
    except (TypeError, ValueError):
        return DREAM_DEFAULT_FINANCE_TERM_MONTHS
    return max(DREAM_FINANCE_TERM_MIN, min(DREAM_FINANCE_TERM_MAX, m))


def _dream_clamp_rate(rate: float | None) -> float:
    if rate is None:
        return DREAM_DEFAULT_RATE_PCT
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return DREAM_DEFAULT_RATE_PCT
    return max(DREAM_RATE_PCT_MIN, min(DREAM_RATE_PCT_MAX, r))


def _dream_clamp_deposit(pct: float | None) -> float:
    if pct is None:
        return DREAM_DEFAULT_DEPOSIT_PCT
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return DREAM_DEFAULT_DEPOSIT_PCT
    return max(DREAM_DEPOSIT_PCT_MIN, min(DREAM_DEPOSIT_PCT_MAX, p))


# ── main entry point ──────────────────────────────────────────────────────

async def compute_dream(
    db: AsyncSession | None,
    *,
    make: str,
    model: str,
    year: int,
    vehicle_type: str = "car",
    finance_term_months: int | None = None,
    rate_pct: float | None = None,
    deposit_pct: float | None = None,
    annual_income: float | None = None,
    monthly_expenses: float | None = None,
    cash_on_hand: float | None = None,
) -> dict:
    """Deterministic dream-car affordability plan.

    Returns a dict matching ``AdvisorDreamData`` in schemas/advisor.py.
    Three blocks: target (market lookup), affordability (pure arithmetic on
    the request-body finance profile), and repayments (reuses
    ``_loan_monthly_payment``).
    """
    term = _dream_clamp_term(finance_term_months)
    rate = _dream_clamp_rate(rate_pct)
    deposit = _dream_clamp_deposit(deposit_pct)

    # ── Target lookup (reuse market cache) ────────────────────────────
    from app.services import advisor as _advisor
    market = await _advisor.get_market_data(db, make, model, year, vehicle_type)
    median = _safe(market.get("median_price"))

    target = {
        "make": make,
        "model": model,
        "year": year,
        "vehicle_type": vehicle_type,
        "currency": CURRENCY,
        "low": _safe(market.get("low_price")),
        "mid": median,
        "high": _safe(market.get("high_price")),
        "source": market.get("source", "fallback"),
        "as_of": market.get("as_of"),
        "stale": bool(market.get("stale")),
        "sample_size": int(market.get("sample_size") or 0),
        "note": market.get("note"),
    }

    # ── Repayments block ──────────────────────────────────────────────
    if median is None:
        repayments = {
            "currency": CURRENCY,
            "finance_term_months": term,
            "rate_pct": rate,
            "deposit_pct": deposit,
            "principal": None,
            "monthly_repayment": None,
            "total_interest": None,
            "note": "no market listings available for target — cannot estimate finance",
        }
    else:
        principal = round(median * (1 - deposit / 100.0), 2)
        monthly = _advisor._loan_monthly_payment(principal, rate, term)
        total_paid = monthly * term
        total_interest = round(total_paid - principal, 2) if principal > 0 else 0.0
        repayments = {
            "currency": CURRENCY,
            "finance_term_months": term,
            "rate_pct": rate,
            "deposit_pct": deposit,
            "principal": principal,
            "monthly_repayment": monthly,
            "total_interest": total_interest,
            "note": None,
        }

    # ── Affordability block ───────────────────────────────────────────
    if annual_income is not None and monthly_expenses is not None:
        monthly_disposable = max(0.0, annual_income / 12.0 - monthly_expenses)
        dsr_ceiling = monthly_disposable * DREAM_DSR_CEILING
    else:
        monthly_disposable = None
        dsr_ceiling = None

    if median is not None:
        deposit_required = round(median * deposit / 100.0, 2)
    else:
        deposit_required = None

    if cash_on_hand is not None and deposit_required is not None:
        cash_gap = round(cash_on_hand - deposit_required, 2)
    else:
        cash_gap = None

    cash_ok = cash_gap is not None and cash_gap >= 0
    dsr_ok = (
        monthly_disposable is not None
        and dsr_ceiling is not None
        and repayments.get("monthly_repayment") is not None
        and repayments["monthly_repayment"] <= dsr_ceiling
    )

    surplus = cash_ok and dsr_ok

    affordability_note = None
    if annual_income is None or monthly_expenses is None:
        affordability_note = "annual income and monthly expenses required to compute affordability"
    elif not dsr_ok and monthly_disposable is not None:
        affordability_note = f"indicative monthly repayment exceeds 30% of disposable income ({monthly_disposable:.0f} * 30% = {dsr_ceiling:.0f})"

    affordability = {
        "currency": CURRENCY,
        "target_price_mid": median,
        "deposit_required": deposit_required,
        "annual_income": annual_income,
        "monthly_disposable_income": monthly_disposable,
        "cash_on_hand": cash_on_hand,
        "cash_gap": cash_gap,
        "surplus": surplus,
        "note": affordability_note,
    }

    # ── Plan-level note ───────────────────────────────────────────────
    plan_note = None
    if median is None:
        plan_note = target.get("note")

    return {
        "currency": CURRENCY,
        "target": target,
        "affordability": affordability,
        "repayments": repayments,
        "note": plan_note,
    }