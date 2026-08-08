"""AI module: diagnostics.

Input:  symptoms text, optional vehicle context and OBD codes.
Output: likely causes with severity, parts, cost estimate, actions.

Deterministic-first: the rule engine (OBD codes + symptom keyword rules) always
runs and its baseline is returned; 9Router only enriches repair notes / part
numbers when reachable.
"""

from app.fallbacks import diagnose_fallback
from app.router_client import enhance


async def run(payload: dict) -> dict:
    baseline = diagnose_fallback(
        payload.get("symptoms", ""),
        payload.get("vehicle"),
        payload.get("obd_codes"),
    )
    return await enhance("diagnostics", payload, baseline)
