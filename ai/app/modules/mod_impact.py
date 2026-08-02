"""AI module: modification impact.

Input:  mod name, category, vehicle context, notes.
Output: performance/value/reliability impact summary.
"""

from app.fallbacks import mod_impact_fallback
from app.router_client import route


async def run(payload: dict) -> dict:
    result = await route("mod-impact", payload)
    if result is not None and isinstance(result, dict):
        result.setdefault("model", "9router")
        return result
    return mod_impact_fallback(payload)
