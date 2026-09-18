"""Shared utilities for AI fallback modules."""

from __future__ import annotations

from typing import Any

_UPGRADE_TCO_SAVING = 0.15
_UPGRADE_GAP_RATIO = 0.25
_DELAY_GAP_RATIO = 0.75
_STRATEGY_AFFORDABILITY_RATIO = 1.2
_RATIONALE_MAX = 280
_NEXT_ACTIONS_MAX = 3


def to_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _f(value: Any) -> float | None:
    """Alias for to_float for backward compatibility."""
    return to_float(value)


def _clip(text: str, limit: int) -> str:
    """Truncate text to a limit with ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def _signal_strength(modules: dict[str, Any]) -> tuple[float, list[str]]:
    """Return a (0..1, list_of_missing) tuple for signal strength."""
    required = ("value", "replace", "upgrade", "finance", "dream")
    present = [m for m in required if modules.get(m)]
    ratio = len(present) / len(required)
    missing = [m for m in required if not modules.get(m)]
    return ratio, missing


def _funding_gap(modules: dict[str, Any]) -> float | None:
    """Calculate funding gap from replace and value modules."""
    replace = modules.get("replace") or {}
    val = modules.get("value") or {}
    gap = _f(replace.get("funding_gap"))
    if gap is not None:
        return gap
    used = _f(replace.get("used_replacement_cost"))
    mid = _f(val.get("mid") or val.get("estimated_value"))
    if used is None or mid is None:
        return None
    return used - mid


def _estimated_value(modules: dict[str, Any]) -> float | None:
    """Get estimated value from value module."""
    val = modules.get("value") or {}
    return _f(val.get("mid") or val.get("estimated_value"))


def _monthly_finance(modules: dict[str, Any]) -> float | None:
    """Get monthly finance payment from finance module."""
    fin = modules.get("finance") or {}
    for key in ("monthly", "effective_monthly", "payment"):
        v = _f(fin.get(key))
        if v is not None:
            return v
    return None


def _dream_affordable(modules: dict[str, Any]) -> bool | None:
    """Check if dream is affordable from dream module."""
    dream = modules.get("dream") or {}
    aff = dream.get("affordability")
    if isinstance(aff, str):
        s = aff.strip().lower()
        if s in ("affordable", "yes", "within_budget", "ok"):
            return True
        if s in ("unaffordable", "no", "out_of_budget", "stretch"):
            return False
    if isinstance(aff, bool):
        return aff
    return None


def _decide(modules: dict[str, Any]) -> str:
    """Make decision based on module outputs."""
    gap = _funding_gap(modules)
    est = _estimated_value(modules)
    gap_ratio = None
    if gap is not None and est not in (None, 0):
        gap_ratio = gap / est

    if gap_ratio is not None:
        if gap_ratio <= _UPGRADE_GAP_RATIO:
            return "upgrade"
        if gap_ratio > _DELAY_GAP_RATIO:
            return "delay"

    monthly = _monthly_finance(modules)
    if monthly is not None and est is not None and est > 0:
        annual = monthly * 12
        if annual < est * _UPGRADE_TCO_SAVING:
            return "upgrade"

    dream = modules.get("dream") or {}
    dream_aff = _dream_affordable(modules)
    if dream and dream_aff is True:
        return "strategy"

    return "keep"


def _rationale(decision: str, modules: dict[str, Any], missing: list[str]) -> str:
    """Generate rationale based on decision and available data."""
    parts: list[str] = []
    est = _estimated_value(modules)
    gap = _funding_gap(modules)
    if est is not None:
        parts.append(f"current value ~${est:,.0f}")
    if gap is not None:
        parts.append(f"replacement gap ~${gap:,.0f}")
    base = ""
    if decision == "keep":
        base = "Your current car is the smart money move."
    elif decision == "upgrade":
        base = "A clear trade-up is within reach."
    elif decision == "delay":
        base = "Wait — the numbers aren't in your favour yet."
    elif decision == "strategy":
        base = "A non-binary play fits this scenario."
    summary = base
    if parts:
        summary = f"{base} " + ", ".join(parts) + "."
    if missing:
        summary += f" (limited data: {', '.join(missing)}.)"
    return _clip(summary, _RATIONALE_MAX)


def _next_actions(decision: str, modules: dict[str, Any]) -> list[str]:
    """Generate next actions based on decision."""
    actions: list[str] = []
    if decision == "keep":
        actions.append("Stick with the current car; revisit in 6 months.")
        actions.append("Keep up scheduled services to protect residual value.")
    elif decision == "upgrade":
        actions.append("Shortlist 2-3 concrete upgrade candidates from the Upgrade tab.")
        actions.append("Get a pre-purchase inspection budget for each shortlist.")
    elif decision == "delay":
        actions.append("Re-run the advisor after your next service or in 3 months.")
        actions.append("Track market median for your model weekly on the Value tab.")
    elif decision == "strategy":
        actions.append("Compare a novated lease vs outright purchase on the Finance tab.")
        actions.append("Talk to a broker about a 2-3 year hold before committing.")
    return actions[:_NEXT_ACTIONS_MAX]


def _based_on(modules: dict[str, Any]) -> dict[str, Any]:
    """Record which sub-modules contributed structured data."""
    return {
        m: bool(modules.get(m))
        for m in ("value", "replace", "upgrade", "finance", "dream")
    }


def parse_listing(listing: dict | None) -> dict[str, Any]:
    """Normalize listing data for deterministic output."""
    if not isinstance(listing, dict):
        listing = {}
    return {
        "title": str(listing.get("title") or "").strip() or "not available",
        "price": listing.get("price"),
        "year": listing.get("year"),
        "odometer_km": listing.get("odometer_km"),
        "make": str(listing.get("make") or "").strip() or "not available",
        "model": str(listing.get("model") or "").strip() or "not available",
        "listing_url": str(listing.get("listing_url") or "").strip() or "not available",
    }


def format_price(price: Any) -> str:
    """Format a price value as AUD string."""
    if price is None:
        return "not available"
    try:
        return f"${float(price):,.0f}"
    except (TypeError, ValueError):
        return "not available"


def format_year(year: Any) -> str:
    """Format a year value as string."""
    if year is None:
        return "not available"
    try:
        return str(int(year))
    except (TypeError, ValueError):
        return "not available"


def format_odometer(odo: Any) -> str:
    """Format an odometer value as string with km suffix."""
    if odo is None:
        return "not available"
    try:
        return f"{int(odo):,} km"
    except (TypeError, ValueError):
        return "not available"


def validate_confidence(conf: Any, default: float = 0.5) -> float:
    """Validate and clamp a confidence value to [0, 1]."""
    f = to_float(conf)
    if f is None:
        return default
    return max(0.0, min(1.0, round(f, 2)))