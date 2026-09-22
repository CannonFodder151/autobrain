"""AI module: VASS mod-legality check.

Input:  mod name, category, vehicle context, state_territory, notes.
Output: is_legal, status, summary, relevant_references, restrictions, confidence, model.

Deterministic-first: the category lookup table produces the baseline and its
scores are never overridden; 9Router only adds a narrative summary and
regulatory insight.
"""

from app.fallbacks.mod_legality import mod_legality_fallback
from app.router_client import enhance


async def run(payload: dict) -> dict:
    baseline = mod_legality_fallback(payload)
    return await enhance("mod-legality", payload, baseline)