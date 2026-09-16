"""AI module: vehicle health score.

Deterministic-first: the rule engine (health_score_fallback) always runs and
returns a baseline 0–100 score with per-category breakdown and predictive
failure alerts.  9Router enriches the result with a human-readable narrative
and additional failure predictions when reachable.

Module name: "health-score"
"""

from typing import TYPE_CHECKING

from app.fallbacks.health_score import health_score_fallback
from app.router_client import enhance


async def run(payload: dict) -> dict:
    baseline = health_score_fallback(payload)
    return await enhance("health-score", payload, baseline)