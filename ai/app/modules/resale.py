"""AI module: resale value estimation.

Input:  vehicle attributes, service history, mods, condition, market data.
Output: value range, factor breakdown, recommendations, trend.
"""

from app.fallbacks import estimate_value_fallback
from app.router_client import route


async def run(payload: dict) -> dict:
    result = await route("resale", payload)
    if result is not None and isinstance(result, dict):
        result.setdefault("model", "9router")
        return result
    return estimate_value_fallback(payload)
