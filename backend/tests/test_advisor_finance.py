"""Tests for the Ownership Advisor Finance module (AUT-2448).

Pure-helper tests for ``app.services.advisor.compute_finance_plan`` and
the amortisation / lease primitives, plus envelope-shape checks for
``POST /api/v1/advisor/finance``. Same import discipline as the Value
tests (no FastAPI app import) so we don't drag in the pre-existing
``fuel_prices.py`` syntax bug.
"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_USER", "test-postgres-user")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_DB", "test-postgres-db")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-minio-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret-key")
os.environ.setdefault("MINIO_BUCKET", "test-minio-bucket")

from app.schemas.advisor import (  # noqa: E402
    AdvisorFinanceData,
    AdvisorFinanceRequest,
    AdvisorFinanceModeBuy,
    AdvisorFinanceModeFinance,
    AdvisorFinanceModeLease,
    AdvisorFinanceModeNovated,
)
from app.services.advisor import (  # noqa: E402
    LEASE_MAX_TERM_MONTHS,
    LEASE_MIN_TERM_MONTHS,
    LEASE_MONEY_FACTOR_DIVISOR,
    _amortization_schedule,
    _clamp_term,
    _lease_monthly,
    _lease_residual_pct,
    _loan_monthly_payment,
    compute_finance_plan,
)


# --- pure helpers ----------------------------------------------------------

def test_clamp_term_keeps_legal_range_finance() -> None:
    assert _clamp_term(60, lease=False) == 60
    assert _clamp_term(6, lease=False) == 12  # lower bound
    assert _clamp_term(120, lease=False) == 84  # upper bound


def test_clamp_term_keeps_legal_range_lease() -> None:
    assert _clamp_term(36, lease=True) == 36
    assert _clamp_term(6, lease=True) == LEASE_MIN_TERM_MONTHS
    assert _clamp_term(120, lease=True) == LEASE_MAX_TERM_MONTHS


def test_loan_monthly_payment_zero_rate_is_principal_over_term() -> None:
    # 0% finance promo: equal principal each month.
    assert _loan_monthly_payment(12_000.0, 0.0, 12) == 1000.0
    assert _loan_monthly_payment(0.0, 7.5, 12) == 0.0
    assert _loan_monthly_payment(10_000.0, 7.5, 0) == 0.0


def test_loan_monthly_payment_matches_textbook_formula() -> None:
    # Standard annuity: P=10,000, i=1%/mo (12% APR), n=12 -> ~888.49.
    pmt = _loan_monthly_payment(10_000.0, 12.0, 12)
    assert 888.0 < pmt < 889.0


def test_amortization_schedule_balances_to_zero() -> None:
    pmt = _loan_monthly_payment(10_000.0, 12.0, 12)
    rows = _amortization_schedule(10_000.0, 12.0, 12, pmt)
    assert len(rows) == 12
    assert rows[0]["period"] == 1
    assert rows[-1]["balance_end"] == 0.0
    # Sum of principal paid across the schedule == original principal.
    total_principal = sum(r["principal"] for r in rows)
    assert abs(total_principal - 10_000.0) < 0.05


def test_amortization_schedule_zero_rate_equal_principal() -> None:
    rows = _amortization_schedule(12_000.0, 0.0, 12, 1000.0)
    assert len(rows) == 12
    assert all(r["interest"] == 0.0 for r in rows)
    assert rows[-1]["balance_end"] == 0.0
    assert all(r["payment"] == 1000.0 for r in rows[:-1]) or rows[-1]["payment"] == 1000.0


def test_amortization_schedule_handles_zero_principal() -> None:
    assert _amortization_schedule(0.0, 7.5, 12, 0.0) == []


def test_lease_residual_decreases_with_term() -> None:
    r24 = _lease_residual_pct(24)
    r36 = _lease_residual_pct(36)
    r60 = _lease_residual_pct(60)
    assert r24 > r36 > r60
    # Floor / ceiling clamps.
    assert _lease_residual_pct(LEASE_MIN_TERM_MONTHS) <= 0.75
    assert _lease_residual_pct(LEASE_MAX_TERM_MONTHS) >= 0.25


def test_lease_monthly_matches_money_factor_formula() -> None:
    # 100k vehicle, 36m, 0% rate -> depreciation-only monthly.
    monthly, mf = _lease_monthly(50_000.0, 23_000.0, 36, 0.0)
    assert mf == 0.0
    # depreciation = (50000 - 23000)/36 = 750
    assert abs(monthly - 750.0) < 0.01
    # Non-zero rate adds (P+R)/2 * money_factor per month.
    monthly2, mf2 = _lease_monthly(50_000.0, 23_000.0, 36, 12.0)
    assert abs(mf2 - (0.12 / LEASE_MONEY_FACTOR_DIVISOR)) < 1e-6
    assert monthly2 > monthly


# --- compute_finance_plan ---------------------------------------------------

def test_compute_finance_plan_returns_three_modes_by_default() -> None:
    plan = compute_finance_plan(
        vehicle_price=40_000.0,
        down_payment=5_000.0,
        term_months=60,
        rate_pct=7.5,
    )
    data = AdvisorFinanceData(**plan)
    assert data.currency == "AUD"
    assert data.vehicle_price == 40_000.0
    assert data.down_payment == 5_000.0
    assert len(data.modes) == 3
    assert all(m.mode in ("buy", "finance", "lease") for m in data.modes)


def test_compute_finance_plan_buy_block_shape() -> None:
    plan = compute_finance_plan(
        vehicle_price=30_000.0,
        down_payment=0.0,
        term_months=36,
        rate_pct=6.0,
    )
    data = AdvisorFinanceData(**plan)
    buy = next(m for m in data.modes if m.mode == "buy")
    assert isinstance(buy, AdvisorFinanceModeBuy)
    assert buy.status == "ok"
    assert buy.purchase_price == 30_000.0
    assert buy.total_cost == 30_000.0
    assert buy.effective_monthly == 0.0
    assert buy.total_interest == 0.0


def test_compute_finance_plan_finance_block_shape() -> None:
    plan = compute_finance_plan(
        vehicle_price=50_000.0,
        down_payment=10_000.0,
        term_months=60,
        rate_pct=7.5,
    )
    data = AdvisorFinanceData(**plan)
    fin = next(m for m in data.modes if m.mode == "finance")
    assert isinstance(fin, AdvisorFinanceModeFinance)
    assert fin.principal == 40_000.0
    assert fin.term_months == 60
    assert fin.annual_rate_pct == 7.5
    assert fin.monthly_payment > 0
    assert fin.total_interest > 0
    assert len(fin.amortization) == 60
    assert fin.amortization[-1].balance_end == 0
    # Total cost = down + sum of payments.
    payments_total = sum(row.payment for row in fin.amortization)
    assert abs(fin.total_cost - (10_000.0 + round(payments_total, 2))) < 0.05


def test_compute_finance_plan_lease_block_shape() -> None:
    plan = compute_finance_plan(
        vehicle_price=50_000.0,
        down_payment=5_000.0,
        term_months=36,
        rate_pct=6.0,
    )
    data = AdvisorFinanceData(**plan)
    lease = next(m for m in data.modes if m.mode == "lease")
    assert isinstance(lease, AdvisorFinanceModeLease)
    assert lease.term_months == 36
    assert 0.25 <= lease.residual_pct <= 0.75
    assert lease.residual_value > 0
    assert lease.money_factor > 0
    assert lease.effective_monthly > 0
    assert lease.total_cost > lease.effective_monthly  # includes down payment


def test_compute_finance_plan_novated_included_only_when_requested() -> None:
    plan_default = compute_finance_plan(
        vehicle_price=40_000.0, down_payment=0.0, term_months=36, rate_pct=6.0,
    )
    plan_with = compute_finance_plan(
        vehicle_price=40_000.0, down_payment=0.0, term_months=36, rate_pct=6.0, novated=True,
    )
    assert len(plan_default["modes"]) == 3
    assert len(plan_with["modes"]) == 4
    novated = plan_with["modes"][3]
    AdvisorFinanceModeNovated(**novated)  # shape check
    assert novated["status"] == "coming_soon"
    assert novated["effective_monthly"] is None
    assert "coming soon" in novated["note"].lower()


def test_compute_finance_plan_down_payment_caps_at_price() -> None:
    plan = compute_finance_plan(
        vehicle_price=20_000.0,
        down_payment=25_000.0,  # overpay
        term_months=48,
        rate_pct=5.0,
    )
    data = AdvisorFinanceData(**plan)
    assert data.down_payment == 20_000.0
    fin = next(m for m in data.modes if m.mode == "finance")
    assert fin.principal == 0.0
    assert fin.monthly_payment == 0.0
    assert plan["note"] is not None  # explanatory note surfaced


def test_compute_finance_plan_zero_price_emits_note() -> None:
    plan = compute_finance_plan(
        vehicle_price=0.0,
        down_payment=0.0,
        term_months=36,
        rate_pct=7.5,
    )
    assert plan["vehicle_price"] == 0.0
    assert plan["note"] is not None
    data = AdvisorFinanceData(**plan)
    fin = next(m for m in data.modes if m.mode == "finance")
    assert fin.principal == 0.0


def test_compute_finance_plan_term_is_clamped_per_mode() -> None:
    plan = compute_finance_plan(
        vehicle_price=30_000.0,
        down_payment=0.0,
        term_months=120,  # > lease max 60
        rate_pct=6.0,
    )
    data = AdvisorFinanceData(**plan)
    fin = next(m for m in data.modes if m.mode == "finance")
    lease = next(m for m in data.modes if m.mode == "lease")
    assert fin.term_months == 84  # finance cap
    assert lease.term_months == 60  # lease cap


def test_request_schema_defaults() -> None:
    req = AdvisorFinanceRequest(down_payment=1000, term_months=36, rate_pct=6.5)
    assert req.novated is False


# --- self-check: hand-rolled calc matches the helper ------------------------

def test_self_check_hand_rolled_matches_helper_for_simple_case() -> None:
    # P=24k, 0% rate, 24m -> monthly = 1000 exactly.
    plan = compute_finance_plan(
        vehicle_price=24_000.0, down_payment=0.0, term_months=24, rate_pct=0.0,
    )
    fin = next(m for m in AdvisorFinanceData(**plan).modes if m.mode == "finance")
    assert fin.monthly_payment == 1000.0
    assert fin.total_interest == 0.0
    assert fin.total_cost == 24_000.0
    assert len(fin.amortization) == 24
    assert all(row.payment == 1000.0 for row in fin.amortization)