"""AI module: Car Check (AUT-2651).

Composes structured listing fields and a deterministic deal score into a
human-readable summary, red flags, and green flags.

Deterministic-first: the rule-based fallback (app.fallbacks.car_check) runs
first and its output is authoritative. 9Router is consulted via ``enhance``
and may refine the narrative, but never invents numbers or overrides
``deal_score`` (listed in ``_AI_IMMUTABLE`` for the ``car-check`` module
so the router cannot change it).
"""

from app.fallbacks.car_check import car_check_fallback, validate_car_check_response
from app.router_client import enhance


async def run(payload: dict) -> dict:
    baseline = car_check_fallback(payload or {})
    merged = await enhance("car-check", payload or {}, baseline)
    return validate_car_check_response(merged)
