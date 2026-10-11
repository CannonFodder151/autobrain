"""AI module: vehicle health score.

Input:  vehicle data + diagnostics, service records, fuel logs, OBD codes, parts.
Output: unified health score (0-100) with breakdown, label, confidence, alerts.

Deterministic-first: rule engine always runs; 9Router only enriches alerts
and narrative when reachable.
"""

from ..fallbacks.health_score import health_score_fallback
from ..router_client import enhance


async def run(payload: dict) -> dict:
    baseline = health_score_fallback(
        payload.get("vehicle", {}),
        payload.get("diagnostics", []),
        payload.get("services", []),
        payload.get("fuel_logs", []),
        payload.get("obd_codes", []),
        payload.get("parts", []),
    )
    return await enhance("health-score", payload, baseline)