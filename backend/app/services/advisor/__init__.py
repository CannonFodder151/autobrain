"""Ownership Advisor — deterministic modules for market valuation, replace/upgrade planning,
finance / lease modelling, dream-car affordability, and the AI-advisor baseline.

All public names are re-exported from this package so existing
``from app.services.advisor import X`` imports continue to work unchanged.
"""

# ── re-exports from sub-modules ──────────────────────────────────────────
from app.services.advisor.value import (  # noqa: F401
    _MIN_VALUE,
    _MAX_VALUE,
    CURRENCY,
    _CONDITION_MULTIPLIER,
    condition_multiplier,
    km_adjustment,
    _band,
    COMPARABLES_MAX,
    COMPARABLES_YEAR_WINDOW,
    compute_market_value,
    find_comparables,
    trade_in_band,
)

from app.services.advisor.replace import (  # noqa: F401
    NEW_USED_PREMIUM_MAX,
    REPLACE_DEFAULT_HORIZON_MONTHS,
    REPLACE_HORIZON_MIN_MONTHS,
    REPLACE_HORIZON_MAX_MONTHS,
    _REPLACE_PREMIUM_BREAKPOINTS,
    age_years,
    new_used_premium,
    _clamp_horizon,
)

from app.services.advisor.upgrade import (  # noqa: F401
    SIMILAR_MAX,
    SIMILAR_YEAR_WINDOW,
    UPGRADE_DEFAULT_DEPOSIT_PCT,
    UPGRADE_DEFAULT_FINANCE_TERM_MONTHS,
    UPGRADE_DEFAULT_RATE_PCT,
    UPGRADE_FINANCE_TERM_MAX,
    UPGRADE_FINANCE_TERM_MIN,
    _UPGRADE_TIER_WEIGHT,
    _clamp_finance_term,
    _clamp_rate_pct,
    _clamp_deposit_pct,
    _median_for,
    find_upgrade_options,
    _tier_label,
    find_similar_vehicles,
    _similarity_score,
    _amortize_monthly,
    build_trade_up,
    compute_upgrade,
)

from app.services.advisor.finance import (  # noqa: F401
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

from app.services.advisor.dream import (  # noqa: F401
    DREAM_DSR_CEILING,
    DREAM_FINANCE_TERM_MIN,
    DREAM_FINANCE_TERM_MAX,
    DREAM_RATE_PCT_MIN,
    DREAM_RATE_PCT_MAX,
    DREAM_DEPOSIT_PCT_MIN,
    DREAM_DEPOSIT_PCT_MAX,
    DREAM_DEFAULT_FINANCE_TERM_MONTHS,
    DREAM_DEFAULT_RATE_PCT,
    DREAM_DEFAULT_DEPOSIT_PCT,
    compute_dream,
    _dream_clamp_term,
    _dream_clamp_rate,
    _dream_clamp_deposit,
)

from app.services.advisor.advisor_baseline import (  # noqa: F401
    _advisor_f,
    _advisor_clip,
    _advisor_funding_gap,
    _advisor_estimated_value,
    _advisor_monthly,
    _advisor_decision,
    _advisor_rationale,
    _advisor_actions,
    compute_advisor_recommendation,
    _ADVISOR_UPGRADE_GAP_RATIO,
    _ADVISOR_DELAY_GAP_RATIO,
    _ADVISOR_UPGRADE_TCO_SAVING,
    _ADVISOR_RATIONALE_MAX,
    _ADVISOR_NEXT_ACTIONS_MAX,
)

# Re-export get_market_data so tests can monkeypatch via app.services.advisor.get_market_data
from app.services.market_data import get_market_data  # noqa: F401