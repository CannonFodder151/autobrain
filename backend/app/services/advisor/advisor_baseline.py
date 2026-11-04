"""AI Advisor baseline (AUT-2450): deterministic rule tree for the AI Advisor.

Pure-rule fallback for ``POST /advisor/ai``. No 9Router call — the AI
gateway may add a richer rationale and sharper next_actions but never
changes the decision or invents numbers.
"""

from __future__ import annotations

# ── constants ─────────────────────────────────────────────────────────────
_ADVISOR_UPGRADE_GAP_RATIO = 0.25   # funding_gap <= 25% of value -> upgrade
_ADVISOR_DELAY_GAP_RATIO = 0.75     # funding_gap > 75% of value -> delay
_ADVISOR_UPGRADE_TCO_SAVING = 0.10  # upgrade TCO saving threshold (10%)
_ADVISOR_RATIONALE_MAX = 280        # chars
_ADVISOR_NEXT_ACTIONS_MAX = 3


# ── helpers ───────────────────────────────────────────────────────────────

def _advisor_f(x: float | None, default: float = 0.0) -> float:
    """Safe float coercion."""
    if x is None:
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _advisor_clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp to [lo, hi]."""
    return max(lo, min(hi, x))


def _advisor_funding_gap(modules: dict) -> float | None:
    """Return the funding gap from the replace module."""
    replace = modules.get("replace") or {}
    gap = replace.get("funding_gap")
    if gap is not None:
        try:
            return float(gap)
        except (TypeError, ValueError):
            return None
    return None


def _advisor_estimated_value(modules: dict) -> float | None:
    """Return the current vehicle value (mid) from the value module."""
    value = modules.get("value") or {}
    mid = value.get("mid")
    if mid is not None:
        try:
            return float(mid)
        except (TypeError, ValueError):
            return None
    return None


def _advisor_monthly(modules: dict) -> float | None:
    """Return the finance monthly payment from the finance module."""
    finance = modules.get("finance") or {}
    modes = finance.get("modes")
    if isinstance(modes, list):
        for m in modes:
            if m.get("mode") == "finance":
                mp = m.get("monthly_payment")
                if mp is not None:
                    try:
                        return float(mp)
                    except (TypeError, ValueError):
                        return None
    return None


def _advisor_decision(modules: dict) -> str:
    """Deterministic decision tree.

    Rules (in priority order):
    1. If dream is affordable and upgrade isn't a clear win -> strategy
    2. If funding gap <= 25% of value -> upgrade
    3. If funding gap > 75% of value -> delay
    4. Else -> keep
    """
    value_mid = _advisor_estimated_value(modules)
    funding_gap = _advisor_funding_gap(modules)
    dream = modules.get("dream") or {}

    # Dream affordability check (only if dream module ran and has affordability)
    dream_affordable = False
    dream_raw = dream.get("affordability")
    if isinstance(dream_raw, dict):
        dream_affordable = dream_raw.get("surplus") is True
    elif isinstance(dream_raw, str):
        dream_affordable = dream_raw.lower() == "affordable"

    # 1. Dream affordable + no clear upgrade win -> strategy
    if dream_affordable:
        # Check if upgrade is a clear win (gap small)
        if value_mid and funding_gap is not None:
            ratio = funding_gap / value_mid if value_mid > 0 else 1.0
            if ratio > _ADVISOR_UPGRADE_GAP_RATIO:
                return "strategy"
        return "strategy"

    # 2. Funding gap <= 25% of value -> upgrade
    if value_mid and funding_gap is not None and value_mid > 0:
        ratio = funding_gap / value_mid
        if ratio <= _ADVISOR_UPGRADE_GAP_RATIO:
            return "upgrade"

    # 3. Funding gap > 75% of value -> delay
    if value_mid and funding_gap is not None and value_mid > 0:
        ratio = funding_gap / value_mid
        if ratio > _ADVISOR_DELAY_GAP_RATIO:
            return "delay"

    # 4. Default -> keep
    return "keep"


def _advisor_rationale(modules: dict, decision: str) -> str:
    """Generate a human-readable rationale <= 280 chars.

    Numbers must be derivable from the supplied modules (hard contract).
    """
    value_mid = _advisor_estimated_value(modules)
    funding_gap = _advisor_funding_gap(modules)
    monthly = _advisor_monthly(modules)
    dream = modules.get("dream") or {}
    dream_affordable = False
    dream_raw = dream.get("affordability")
    if isinstance(dream_raw, dict):
        dream_affordable = dream_raw.get("surplus") is True
    elif isinstance(dream_raw, str):
        dream_affordable = dream_raw.lower() == "affordable"

    parts: list[str] = []

    if decision == "upgrade":
        if value_mid and funding_gap is not None:
            parts.append(f"Gap ${funding_gap:,.0f} is ≤25% of value ${value_mid:,.0f}.")
        if monthly:
            parts.append(f"Finance ~${monthly:,.0f}/mo.")
    elif decision == "delay":
        if value_mid and funding_gap is not None:
            parts.append(f"Gap ${funding_gap:,.0f} exceeds 75% of value ${value_mid:,.0f}.")
        parts.append("Saving more before upgrading is prudent.")
    elif decision == "strategy":
        if dream_affordable:
            parts.append("Dream vehicle is affordable.")
        if value_mid and funding_gap is not None:
            ratio = funding_gap / value_mid if value_mid > 0 else 1.0
            if ratio > _ADVISOR_UPGRADE_GAP_RATIO:
                parts.append("Upgrade gap is large; plan for dream instead.")
    else:  # keep
        if value_mid and funding_gap is not None:
            parts.append(f"Gap ${funding_gap:,.0f} is mid-range ({value_mid:,.0f} value).")
        if monthly:
            parts.append(f"Current finance ~${monthly:,.0f}/mo manageable.")

    rationale = " ".join(parts)
    if len(rationale) > _ADVISOR_RATIONALE_MAX:
        rationale = rationale[:_ADVISOR_RATIONALE_MAX - 3] + "..."
    return rationale


def _advisor_actions(modules: dict, decision: str) -> list[str]:
    """Generate up to 3 concrete next actions."""
    actions: list[str] = []
    dream = modules.get("dream") or {}
    dream_affordable = False
    dream_raw = dream.get("affordability")
    if isinstance(dream_raw, dict):
        dream_affordable = dream_raw.get("surplus") is True
    elif isinstance(dream_raw, str):
        dream_affordable = dream_raw.lower() == "affordable"

    if decision == "upgrade":
        actions.append("shortlist 2-3 upgrade candidates")
        actions.append("get trade-in quotes for current vehicle")
        actions.append("compare finance offers")
    elif decision == "delay":
        actions.append("set a monthly savings target")
        actions.append("monitor market for price drops")
        actions.append("revisit in 6 months")
    elif decision == "strategy":
        if dream_affordable:
            actions.append("research dream vehicle ownership costs")
            actions.append("compare insurance quotes for dream vehicle")
        else:
            actions.append("define budget for next vehicle")
            actions.append("improve trade-in value with detailing")
        actions.append("schedule test drives for shortlist")
    else:  # keep
        actions.append("maintain service history")
        actions.append("monitor market value quarterly")
        actions.append("review at next major service")

    return actions[:_ADVISOR_NEXT_ACTIONS_MAX]


def _advisor_based_on(modules: dict) -> dict[str, bool]:
    """Return which modules contributed structured data."""
    return {
        "value": bool(modules.get("value")),
        "replace": bool(modules.get("replace")),
        "upgrade": bool(modules.get("upgrade")),
        "finance": bool(modules.get("finance")),
        "dream": bool(modules.get("dream")),
    }


# ── main entry point ──────────────────────────────────────────────────────

async def compute_advisor_recommendation(modules: dict) -> dict:
    """Deterministic AI Advisor recommendation.

    Returns a dict matching ``AdvisorAIData`` in schemas/advisor.py.
    """
    decision = _advisor_decision(modules)
    rationale = _advisor_rationale(modules, decision)
    next_actions = _advisor_actions(modules, decision)
    based_on = _advisor_based_on(modules)

    # Confidence heuristic
    value_mid = _advisor_estimated_value(modules)
    funding_gap = _advisor_funding_gap(modules)
    if decision == "upgrade" and value_mid and funding_gap is not None and value_mid > 0:
        ratio = funding_gap / value_mid
        confidence = _advisor_clip(1.0 - ratio * 2.0, 0.7, 0.95)
    elif decision == "delay" and value_mid and funding_gap is not None and value_mid > 0:
        ratio = funding_gap / value_mid
        confidence = _advisor_clip(0.55 - (ratio - 0.75) * 0.5, 0.3, 0.55)
    elif decision == "strategy":
        confidence = 0.75
    else:  # keep
        if value_mid and funding_gap is not None and value_mid > 0:
            ratio = funding_gap / value_mid
            confidence = _advisor_clip(0.5 + (0.5 - ratio) * 0.4, 0.5, 0.8)
        else:
            confidence = 0.5

    return {
        "decision": decision,
        "confidence": round(confidence, 2),
        "rationale": rationale,
        "next_actions": next_actions,
        "based_on": based_on,
        "model": "rule-based-fallback",
    }