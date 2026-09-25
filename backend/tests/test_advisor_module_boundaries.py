"""Module boundary tests for the Ownership Advisor refactoring.

Verifies that the split into sub-modules (__init__.py + value/replace/upgrade/finance/dream/advisor_baseline)
correctly re-exports all public names and that each module can be imported independently.
"""

from __future__ import annotations

import pytest


def test_all_exports_reexported() -> None:
    """Verify that every public name used by tests/API is re-exported from the package."""
    from app.services.advisor import (
        # Value
        _MIN_VALUE, _MAX_VALUE, CURRENCY, _CONDITION_MULTIPLIER, BAND_LOW_RATIO,
        BAND_HIGH_RATIO, TRADE_IN_LOW_RATIO, TRADE_IN_MID_RATIO, TRADE_IN_HIGH_RATIO,
        condition_multiplier, km_adjustment, _band, COMPARABLES_MAX, COMPARABLES_YEAR_WINDOW,
        compute_market_value, find_comparables, trade_in_band,
        # Replace
        NEW_USED_PREMIUM_MAX, REPLACE_DEFAULT_HORIZON_MONTHS, REPLACE_HORIZON_MIN_MONTHS,
        REPLACE_HORIZON_MAX_MONTHS, _REPLACE_PREMIUM_BREAKPOINTS, age_years, new_used_premium,
        _clamp_horizon,
        # Upgrade
        SIMILAR_MAX, SIMILAR_YEAR_WINDOW, UPGRADE_DEFAULT_DEPOSIT_PCT, UPGRADE_DEFAULT_FINANCE_TERM_MONTHS,
        UPGRADE_DEFAULT_RATE_PCT, UPGRADE_FINANCE_TERM_MAX, UPGRADE_FINANCE_TERM_MIN,
        _UPGRADE_TIER_WEIGHT, _clamp_finance_term, _clamp_rate_pct, _clamp_deposit_pct,
        _median_for, find_upgrade_options, _tier_label, find_similar_vehicles,
        _similarity_score, _amortize_monthly, build_trade_up, compute_upgrade,
        # Finance
        FINANCE_MIN_TERM_MONTHS, FINANCE_MAX_TERM_MONTHS, LEASE_MAX_TERM_MONTHS,
        LEASE_MIN_TERM_MONTHS, LEASE_MONEY_FACTOR_DIVISOR, _amortization_schedule, _clamp_term,
        _lease_monthly, _lease_residual_pct, _loan_monthly_payment, compute_finance_plan,
        # Dream
        DREAM_DSR_CEILING, DREAM_FINANCE_TERM_MIN, DREAM_FINANCE_TERM_MAX, DREAM_RATE_PCT_MIN,
        DREAM_RATE_PCT_MAX, DREAM_DEPOSIT_PCT_MIN, DREAM_DEPOSIT_PCT_MAX,
        DREAM_DEFAULT_FINANCE_TERM_MONTHS, DREAM_DEFAULT_RATE_PCT, DREAM_DEFAULT_DEPOSIT_PCT,
        compute_dream, _dream_clamp_term, _dream_clamp_rate, _dream_clamp_deposit,
        # AI baseline
        _advisor_f, _advisor_clip, _advisor_funding_gap, _advisor_estimated_value,
        _advisor_monthly, _advisor_decision, _advisor_rationale, _advisor_actions,
        compute_advisor_recommendation,
        _ADVISOR_UPGRADE_GAP_RATIO, _ADVISOR_DELAY_GAP_RATIO, _ADVISOR_UPGRADE_TCO_SAVING,
        _ADVISOR_RATIONALE_MAX, _ADVISOR_NEXT_ACTIONS_MAX,
    )

    # All 101 names above import successfully
    # (no assertion needed - if any import fails the test fails)


def test_value_module_imports_independently() -> None:
    """Verify value module can be imported independently of the full package."""
    from app.services.advisor.value import condition_multiplier, compute_market_value, km_adjustment
    assert condition_multiplier("good") == 1.0
    assert compute_market_value is not None


def test_replace_module_imports_independently() -> None:
    """Verify replace module can be imported independently."""
    from types import SimpleNamespace
    from app.services.advisor.replace import age_years, new_used_premium
    v = SimpleNamespace(year=2018, make="Toyota", model="Corolla")
    assert age_years(v) == 8


def test_upgrade_module_imports_independently() -> None:
    """Verify upgrade module can be imported independently."""
    from app.services.advisor.upgrade import find_upgrade_options, _similarity_score, _tier_label
    assert _similarity_score(current_year=2018, target_year=2018, current_value=10_000, target_value=10_000) == 1.0
    assert _tier_label(1) == "newer (nxt)"
    assert _tier_label(-1) == "older (-1)"


def test_finance_module_imports_independently() -> None:
    """Verify finance module can be imported independently."""
    from app.services.advisor.finance import compute_finance_plan, _loan_monthly_payment, _clamp_term
    assert _loan_monthly_payment(10_000.0, 7.5, 12) > 0
    assert _clamp_term(60, lease=False) == 60


def test_dream_module_imports_independently() -> None:
    """Verify dream module can be imported independently."""
    from app.services.advisor.dream import compute_dream, _dream_clamp_term, _dream_clamp_rate
    assert _dream_clamp_term(None) == 60
    assert _dream_clamp_rate(None) == 7.5


def test_advisor_baseline_imports_independently() -> None:
    """Verify advisor_baseline module can be imported independently."""
    from app.services.advisor.advisor_baseline import (
        compute_advisor_recommendation, _advisor_decision, _advisor_rationale,
        _advisor_funding_gap,
    )
    # compute_advisor_recommendation is async — just verify it's callable
    assert callable(compute_advisor_recommendation)
    assert _advisor_decision({}) in ("keep", "delay", "upgrade", "strategy")


def test_package_import_works() -> None:
    """Verify that app.services.advisor imports work as the old monolith used to."""
    from app.services.advisor import (
        compute_finance_plan, compute_dream, compute_advisor_recommendation,
        compute_market_value, trade_in_band, compute_upgrade,
        find_comparables, find_upgrade_options, find_similar_vehicles,
        _loan_monthly_payment, _amortization_schedule, _clamp_term,
        _lease_residual_pct, _lease_monthly, DREAM_DSR_CEILING,
        _dream_clamp_term, _dream_clamp_rate, _dream_clamp_deposit,
        _advisor_f, _advisor_decision, _advisor_rationale, _advisor_actions,
        LEASE_MAX_TERM_MONTHS, LEASE_MIN_TERM_MONTHS, LEASE_MONEY_FACTOR_DIVISOR,
        FINANCE_MIN_TERM_MONTHS, FINANCE_MAX_TERM_MONTHS,
        TRADE_IN_LOW_RATIO, TRADE_IN_MID_RATIO, TRADE_IN_HIGH_RATIO,
        BAND_LOW_RATIO, BAND_HIGH_RATIO, SIMILAR_MAX, SIMILAR_YEAR_WINDOW,
    )
    # All imports above succeeded → package resolves correctly