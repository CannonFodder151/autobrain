"""AI module: diagnostics.

Input:  symptoms text, optional vehicle context and OBD codes.
Output: likely causes with severity, parts, cost estimate, actions.
"""

from app.fallbacks import diagnose_fallback
from app.router_client import route


async def run(payload: dict) -> dict:
    result = await route("diagnostics", payload)
    if result is not None and isinstance(result, dict):
        result.setdefault("model", "9router")
        return result
    symptoms = payload.get("symptoms", "")
    return diagnose_fallback(
        symptoms,
        payload.get("vehicle"),
        payload.get("obd_codes"),
    )
