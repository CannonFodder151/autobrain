"""AI module: vehicle-condition estimate.

Input:  vehicle context, diagnostics, service history, mods.
Output: condition label (excellent/good/fair/poor), confidence, evidence.

Deterministic-first: the rule-based estimator (app/fallbacks/condition.py)
produces the label and it is never overridden; 9Router only adds a human-
readable narrative summary of the evidence.
"""

from app.fallbacks.condition import estimate_condition
from app.router_client import enhance

async def run(payload: dict) -> dict:
    baseline = estimate_condition(payload)
    return await enhance("condition", payload, baseline)
