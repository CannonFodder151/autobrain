"""AI module: Second Hand Car Check (AUT-2630).

Enriches the deterministic deal score produced by the backend's
``compute_car_check`` with a short natural-language
``ai_summary``, ``red_flags`` and ``green_flags``. The verdict,
fair-value band and delta_pct are produced by the backend's
deterministic engine and are listed in ``_AI_IMMUTABLE`` so 9Router
can never override them.

When 9Router is unreachable, the deterministic
``ai_summary`` produced by ``compute_car_check`` is returned as-is.
"""

from app.fallbacks.car_check import car_check_fallback, validate_car_check_response
from app.router_client import enhance


async def run(payload: dict) -> dict:
    baseline = car_check_fallback(payload or {})
    merged = await enhance("car-check", payload or {}, baseline)
    return validate_car_check_response(merged)
