"""AI module: modification impact.

Input:  mod name, category, vehicle context, notes.
Output: performance/value/reliability impact summary.

Deterministic-first: the category lookup table produces the baseline and its
scores are never overridden; 9Router only adds a narrative summary.
"""

from app.fallbacks.mod_impact import mod_impact_fallback
from app.router_client import enhance


async def run(payload: dict) -> dict:
    baseline = mod_impact_fallback(payload)
    return await enhance("mod-impact", payload, baseline)
