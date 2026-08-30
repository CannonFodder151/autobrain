"""Deterministic modification-impact fallback."""

from app.fallbacks.resale import _mod_value_impact

_MOD_IMPACT: dict[str, tuple[str, float, str]] = {
    "performance": ("Performance-focused upgrade; typically improves power output but can increase running costs.", 8.0, "Minor"),
    "engine": ("Engine modification; significant potential gain with reliability caveats.", 9.0, "Medium"),
    "exhaust": ("Exhaust upgrade; modest power gain, changes noise and emissions behaviour.", 6.0, "Minor"),
    "suspension": ("Suspension upgrade; improves handling, can reduce ride comfort.", 5.0, "Medium"),
    "brakes": ("Brake upgrade; improves safety and track performance.", 6.0, "None"),
    "audio": ("Audio system; entertainment value, minimal mechanical impact.", 2.0, "None"),
    "visual": ("Visual upgrade; cosmetic only.", 1.0, "None"),
    "interior": ("Interior upgrade; comfort and convenience.", 1.0, "None"),
    "exterior": ("Exterior upgrade; cosmetic value impact varies.", 2.0, "None"),
    "other": ("General modification; impact depends on installation quality.", 3.0, "Minor"),
}


def mod_impact_fallback(payload: dict) -> dict:
    cat = (payload.get("category") or "other").lower()
    known = cat in _MOD_IMPACT
    summary, score, reliability = _MOD_IMPACT.get(cat, _MOD_IMPACT["other"])
    name = payload.get("name") or "This modification"
    value_impact = _mod_value_impact({"category": cat, "cost": payload.get("cost")})
    return {
        "summary": f"{name}: {summary}",
        "performance_score": score,
        "value_impact": value_impact,
        "reliability_impact": reliability,
        "confidence": 0.9 if known else 0.5,
        "model": "rule-based-fallback",
    }
