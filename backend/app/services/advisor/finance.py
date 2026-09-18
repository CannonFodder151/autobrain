"""Finance module (AUT-2448): deterministic loan / lease modelling.

Pure-arithmetic helpers for the ``POST /advisor/finance`` endpoint.
No AI, no 9Router. Accepts ``{vehicle_price, down_payment, term_months,
rate_pct}`` and returns four mode blocks (buy, finance, lease, novated).
"""

from __future__ import annotations

from app.services.advisor._common import CURRENCY, _safe

# ── constants ─────────────────────────────────────────────────────────────
LEASE_MIN_TERM_MONTHS = 12
LEASE_MAX_TERM_MONTHS = 60
LEASE_MONEY_FACTOR_DIVISOR = 24.0

FINANCE_MIN_TERM_MONTHS = 12
FINANCE_MAX_TERM_MONTHS = 84


# ── helpers ───────────────────────────────────────────────────────────────

def _clamp_term(months: int | None, *, lease: bool = False) -> int:
    """Clamp a term in months to the legal range for the given mode."""
    lo = LEASE_MIN_TERM_MONTHS if lease else FINANCE_MIN_TERM_MONTHS
    hi = LEASE_MAX_TERM_MONTHS if lease else FINANCE_MAX_TERM_MONTHS
    if months is None:
        return hi if lease else 60
    try:
        m = int(months)
    except (TypeError, ValueError):
        return hi if lease else 60
    return max(lo, min(hi, m))


def _loan_monthly_payment(principal: float, rate_pct: float, term_months: int) -> float:
    """Standard amortisation: monthly payment for a flat-rate loan.

    Returns 0.0 for zero/negative principal or term.
    """
    if principal <= 0 or term_months <= 0:
        return 0.0
    r = rate_pct / 100.0 / 12.0
    if r <= 0:
        return round(principal / term_months, 2)
    monthly = principal * r / (1 - (1 + r) ** -term_months)
    return round(monthly, 2)


def _amortization_schedule(
    principal: float, rate_pct: float, term_months: int, monthly: float,
) -> list[dict]:
    """Build a month-by-month amortization schedule.

    Returns a list of dicts matching ``AmortizationRow`` in schemas/advisor.py.
    The schedule reduces ``balance_end`` to exactly 0.0 in the final period.
    """
    if principal <= 0 or term_months <= 0:
        return []
    r = rate_pct / 100.0 / 12.0
    balance = principal
    rows: list[dict] = []
    for period in range(1, term_months + 1):
        interest = round(balance * r, 2)
        if period == term_months:
            payment = round(balance + interest, 2)
            principal_paid = balance
            balance = 0.0
        else:
            payment = monthly
            principal_paid = round(payment - interest, 2)
            balance = round(balance - principal_paid, 2)
        rows.append({
            "period": period,
            "payment": payment,
            "interest": interest,
            "principal": principal_paid,
            "balance_end": balance,
        })
    return rows


def _lease_residual_pct(term_months: int) -> float:
    """Residual % of the vehicle's value at lease end.

    Industry-standard AU chattel mortgage residual: starts at ~75% for
    24-month terms, declines linearly to ~25% for 60-month terms.
    """
    lo = LEASE_MIN_TERM_MONTHS
    hi = LEASE_MAX_TERM_MONTHS
    m = max(lo, min(hi, term_months))
    # Linear interpolation: 24 -> 0.75, 60 -> 0.25
    t = (m - lo) / (hi - lo) if hi > lo else 0.0
    return round(0.75 - 0.50 * t, 4)


def _lease_monthly(
    capital: float, residual: float, term_months: int, rate_pct: float,
) -> tuple[float, float]:
    """Lease monthly payment using the money-factor method.

    Returns ``(monthly, money_factor)``.
    """
    depreciation = (capital - residual) / term_months
    money_factor = (rate_pct / 100.0) / LEASE_MONEY_FACTOR_DIVISOR if rate_pct > 0 else 0.0
    finance_charge = (capital + residual) * money_factor
    monthly = round(depreciation + finance_charge, 2)
    return monthly, money_factor


# ── main entry point ─────────────────────────────────────────────────────

def compute_finance_plan(
    *,
    vehicle_price: float,
    down_payment: float,
    term_months: int,
    rate_pct: float,
    novated: bool = False,
) -> dict:
    """Deterministic finance plan: buy / finance / lease / novated.

    Returns a dict matching ``AdvisorFinanceData`` in schemas/advisor.py.
    """
    dp = max(0.0, min(down_payment, vehicle_price)) if vehicle_price > 0 else 0.0
    effective_price = vehicle_price

    # ── Buy mode ──────────────────────────────────────────────────────
    buy = {
        "mode": "buy",
        "status": "ok",
        "currency": CURRENCY,
        "purchase_price": effective_price,
        "effective_monthly": 0.0,
        "total_cost": effective_price,
        "total_interest": 0.0,
        "note": None,
    }

    # ── Finance mode ──────────────────────────────────────────────────
    fin_term = _clamp_term(term_months, lease=False)
    principal = max(0.0, effective_price - dp)
    monthly = _loan_monthly_payment(principal, rate_pct, fin_term)
    sched = _amortization_schedule(principal, rate_pct, fin_term, monthly)
    total_interest = round(sum(r["interest"] for r in sched), 2)
    payments_total = sum(r["payment"] for r in sched)
    total_cost = round(dp + payments_total, 2) if principal > 0 else dp

    finance = {
        "mode": "finance",
        "status": "ok",
        "currency": CURRENCY,
        "principal": round(principal, 2),
        "term_months": fin_term,
        "annual_rate_pct": rate_pct,
        "monthly_payment": monthly,
        "effective_monthly": monthly,
        "total_cost": total_cost,
        "total_interest": total_interest,
        "amortization": sched,
        "note": None,
    }

    # ── Lease mode ────────────────────────────────────────────────────
    lease_term = _clamp_term(term_months, lease=True)
    residual_pct = _lease_residual_pct(lease_term)
    residual_value = round(effective_price * residual_pct, 2)
    lease_monthly, money_factor = _lease_monthly(effective_price, residual_value, lease_term, rate_pct)
    lease_total = round(dp + lease_monthly * lease_term, 2)

    lease = {
        "mode": "lease",
        "status": "ok",
        "currency": CURRENCY,
        "principal": round(effective_price, 2),
        "term_months": lease_term,
        "residual_pct": residual_pct,
        "residual_value": residual_value,
        "effective_monthly": lease_monthly,
        "total_cost": lease_total,
        "money_factor": round(money_factor, 8),
        "note": None,
    }

    modes: list[dict] = [buy, finance, lease]

    # ── Novated mode ──────────────────────────────────────────────────
    if novated:
        modes.append({
            "mode": "novated",
            "status": "coming_soon",
            "currency": CURRENCY,
            "effective_monthly": None,
            "total_cost": None,
            "note": "Novated lease calculator is coming soon. The toggle is reserved in the UI.",
        })

    note = None
    if vehicle_price <= 0:
        note = "vehicle price is zero or negative — finance terms cannot be computed"
    elif down_payment > vehicle_price:
        note = "down payment exceeds vehicle price — capped to vehicle price"

    return {
        "currency": CURRENCY,
        "vehicle_price": effective_price,
        "down_payment": dp,
        "modes": modes,
        "note": note,
    }