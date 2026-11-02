"""Ownership Advisor: deterministic-first calculations for six modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AdvisorInput:
    vehicle_id: str
    make: str = "Toyota"
    model: str = "Corolla"
    year: int = 2018
    mileage: int = 60000
    current_value: float = 18000.0
    replacement_cost: float = 25000.0
    upgrade_budget: float = 10000.0
    interest_rate: float = 0.06
    loan_term_months: int = 60
    dream_price: float = 45000.0
    dream_monthly_budget: float = 600.0


@dataclass
class AdvisorResult:
    mode: str
    value: float
    detail: str
    breakdown: Dict[str, Any] = field(default_factory=dict)


def _value(i: AdvisorInput) -> AdvisorResult:
    depreciation = i.current_value * (0.05 if i.mileage < 50000 else 0.08)
    trade_in = round(i.current_value - depreciation * 0.3, 2)
    return AdvisorResult(
        "value", round(i.current_value, 2),
        f"Estimated market value ${i.current_value:,.0f}; trade-in ${trade_in:,.0f}.",
        {"market_value": i.current_value, "trade_in": trade_in, "depreciation": round(depreciation, 2)},
    )


def _replace(i: AdvisorInput) -> AdvisorResult:
    gap = round(i.replacement_cost - i.current_value, 2)
    return AdvisorResult(
        "replace", gap,
        f"Replacement cost ${i.replacement_cost:,.0f}; funding gap ${gap:,.0f}.",
        {"replacement_cost": i.replacement_cost, "trade_in": i.current_value, "funding_gap": gap},
    )


def _upgrade(i: AdvisorInput) -> AdvisorResult:
    affordable = round(i.current_value + i.upgrade_budget, 2)
    return AdvisorResult(
        "upgrade", affordable,
        f"Trade-up budget ${affordable:,.0f} (current value + ${i.upgrade_budget:,.0f}).",
        {"current_value": i.current_value, "upgrade_budget": i.upgrade_budget, "trade_up_ceiling": affordable},
    )


def _finance(i: AdvisorInput) -> AdvisorResult:
    r = i.interest_rate / 12
    n = i.loan_term_months
    if r == 0:
        payment = i.replacement_cost / n
    else:
        payment = i.replacement_cost * r * (1 + r) ** n / ((1 + r) ** n - 1)
    total = round(payment * n, 2)
    return AdvisorResult(
        "finance", round(payment, 2),
        f"Monthly repayment ${payment:,.2f} over {n} months; total ${total:,.2f}.",
        {"principal": i.replacement_cost, "rate": i.interest_rate, "term_months": n,
         "monthly_payment": round(payment, 2), "total_paid": total},
    )


def _dream(i: AdvisorInput) -> AdvisorResult:
    r = i.interest_rate / 12
    n = i.loan_term_months
    if r == 0:
        max_price = i.dream_monthly_budget * n
    else:
        max_price = i.dream_monthly_budget * ((1 + r) ** n - 1) / (r * (1 + r) ** n)
    affordable = i.dream_price <= max_price
    return AdvisorResult(
        "dream", round(max_price, 2),
        f"Dream car ${i.dream_price:,.0f}; max affordable ${max_price:,.0f}. {'Affordable.' if affordable else 'Not affordable.'}",
        {"dream_price": i.dream_price, "max_affordable": round(max_price, 2),
         "monthly_budget": i.dream_monthly_budget, "affordable": affordable},
    )


def _ai(i: AdvisorInput) -> AdvisorResult:
    # Deterministic recommendation; AI refinement optional.
    rec = "keep"
    if i.current_value < i.replacement_cost * 0.4:
        rec = "replace"
    elif i.upgrade_budget > i.current_value * 0.5:
        rec = "upgrade"
    return AdvisorResult(
        "ai_advisor", 0.0,
        f"Recommendation: {rec}. (Deterministic; AI refines when available.)",
        {"recommendation": rec, "used_fallback": True},
    )


MODES = {
    "value": _value,
    "replace": _replace,
    "upgrade": _upgrade,
    "finance": _finance,
    "dream": _dream,
    "ai_advisor": _ai,
}


def run_advisor(i: AdvisorInput, mode: str) -> AdvisorResult:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    return MODES[mode](i)


def run_all(i: AdvisorInput) -> List[AdvisorResult]:
    return [MODES[m](i) for m in ("value", "replace", "upgrade", "finance", "dream", "ai_advisor")]