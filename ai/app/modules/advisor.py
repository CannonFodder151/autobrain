"""AI module: Ownership Advisor (AUT-2450).

Composes structured outputs from the Value / Replace / Upgrade / Finance /
Dream sub-modules and returns a single decision (keep / upgrade / delay /
strategy) with confidence, rationale and next_actions.

Deterministic-first: the rule-based fallback (app.fallbacks.advisor) runs
first and its decision is authoritative. 9Router is consulted via
``enhance`` and may add a richer rationale / sharper next_actions, but the
``decision`` itself comes from the baseline (it is listed in
``_AI_IMMUTABLE`` for the ``advisor`` module so the router cannot override
it). Numeric values are never invented — the payload only carries numbers
produced by the deterministic Value/Replace/Upgrade/Finance/Dream modules
and the AI only reasons over those.
"""

from app.fallbacks.advisor import advisor_fallback, validate_advisor_response
from app.router_client import enhance


async def run(payload: dict) -> dict:
    baseline = advisor_fallback(payload or {})
    merged = await enhance("advisor", payload or {}, baseline)
    return validate_advisor_response(merged)
