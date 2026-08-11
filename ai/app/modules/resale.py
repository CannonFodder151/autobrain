"""AI module: resale value estimation.

Input:  vehicle attributes, service history, mods, condition, market data.
Output: value range, factor breakdown, recommendations, trend.

Deterministic-first: the depreciation-curve baseline is always returned and its
value numbers are never overridden by the AI. 9Router supplies market facts —
the new-car RRP and a typical current used selling price — which are run
through the deterministic model (used_price clamped to a sane band), plus
advice/trend enrichment. The AI never writes the number directly.

The output is validated and clamped so estimates stay sane and consistent:
low <= estimated <= high, values bounded to a realistic AUD range.
"""

from app.fallbacks.condition import estimate_condition
from app.fallbacks.resale import estimate_value_fallback, rrp_for
from app.router_client import enhance

_MIN_VAL, _MAX_VAL = 500.0, 5_000_000.0


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return max(_MIN_VAL, min(_MAX_VAL, f))


def _validate(result: dict) -> dict:
    est = _f(result.get("estimated_value"))
    low = _f(result.get("low"))
    high = _f(result.get("high"))
    if est is None:
        # Infer from range if estimate missing, else reject the response.
        est = low or high
    if est is None:
        raise ValueError("no usable valuation numbers")
    if low is None:
        low = round(est * 0.9, 2)
    if high is None:
        high = round(est * 1.1, 2)
    if low > est:
        low = round(est * 0.9, 2)
    if high < est:
        high = round(est * 1.1, 2)
    result["estimated_value"] = round(est, 2)
    result["low"] = round(low, 2)
    result["high"] = round(high, 2)
    result.setdefault("currency", "AUD")
    factors = result.get("factors")
    result["factors"] = factors if isinstance(factors, dict) else {}
    return result


async def run(payload: dict) -> dict:
    # Router first: 9Router may supply market facts (rrp/used_price) and
    # advice/trend. The deterministic number is computed exactly once at the
    # end with whatever facts are available — never twice.
    merged = await enhance("resale", payload, {})
    vehicle = payload.get("vehicle", {})
    market = payload.get("market") if isinstance(payload.get("market"), dict) else {}
    # Deterministic market data (CarsGuide/CarSales listings median) wins over
    # the AI's guessed used_price: real, cached, stable across calls. The AI
    # guess only fills in when no live listings are available.
    used_price = market.get("median_price") or merged.get("used_price")
    # Deterministic table RRP wins; AI rrp fills gaps for unknown recent models.
    rrp = rrp_for(vehicle)
    if rrp is None:
        rrp = _f(merged.get("rrp"))
    # Condition: rule-based estimate from diagnostics + service history when
    # the user hasn't supplied one — never an AI guess. The AI may later add a
    # narrative summary but the label stays deterministic.
    condition_estimate = None
    if isinstance(vehicle, dict) and not vehicle.get("condition"):
        condition_estimate = estimate_condition(payload)
        vehicle = dict(vehicle)
        vehicle["condition"] = condition_estimate["condition"]
        payload = dict(payload)
        payload["vehicle"] = vehicle
    try:
        result = estimate_value_fallback(payload, rrp=rrp, used_price=used_price)
        if condition_estimate is not None:
            result.setdefault("factors", {})["condition_estimate"] = condition_estimate["condition"]
            result["factors"]["condition_confidence"] = condition_estimate["confidence"]
            result["factors"]["condition_score"] = condition_estimate["score"]
            result["factors"]["condition_signals"] = ", ".join(condition_estimate["factors"].get("signals", []))
        if market.get("sample_size"):
            result.setdefault("factors", {})["market_median"] = market.get("median_price")
            result["factors"]["market_source"] = market.get("source")
            result["factors"]["market_sample"] = market.get("sample_size")
        # Preserve AI-enriched advice/trend where provided.
        for key in ("recommendations", "trend"):
            if merged.get(key) is not None:
                result[key] = merged[key]
        return _validate(result)
    except (ValueError, KeyError, TypeError):
        return estimate_value_fallback(payload)
