"""AI module: resale value estimation.

Input:  vehicle attributes, service history, mods, condition, market data.
Output: value range, factor breakdown, recommendations, trend.

The output is validated and clamped so estimates stay sane and consistent:
low <= estimated <= high, values bounded to a realistic AUD range.
"""

from app.fallbacks import estimate_value_fallback
from app.router_client import route

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
    result = await route("resale", payload)
    if result is not None and isinstance(result, dict):
        try:
            return _validate(result)
        except (ValueError, KeyError, TypeError):
            pass
    return estimate_value_fallback(payload)
