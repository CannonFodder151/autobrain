"""Deterministic Ownership Advisor baseline (AUT-2450).

The AI Advisor composes structured outputs from five deterministic
modules (Value, Replace, Upgrade, Finance, Dream) and reasons over them.
This module is the *baseline*: a small rule tree that always runs and
returns a well-formed decision. When 9Router is reachable its response
is shallow-merged on top (see ``ai/app/router_client.enhance``).

The baseline is deliberately simple and explicit so the contract is
auditable and never invents numbers. Every numeric in the output comes
from the caller-provided module outputs; the baseline only chooses
``decision``, computes ``confidence`` from the signal-strength
heuristic, and writes a short rationale + concrete next_actions.

Decision rules (in priority order):

  1. ``upgrade`` — if Value vs Replace/Upgrade shows a clear trade-up
     (upgrade saves >= 15% on 5-year TCO or funding_gap <= 0.25 *
     estimated_value).
  2. ``delay`` — if Value/Finance signals are weak (missing inputs, low
     sample size) or the funding_gap is unbridgeable (> 0.75 *
     estimated_value) and no clear upgrade exists.
  3. ``strategy`` — if the user supplied a Dream and it's affordable
     (within 1.2× of upgrade affordability) but not strictly cheaper
     than upgrading the current car. Captures "novated / lease-to-buy /
     wait for new model" style plays.
  4. ``keep`` — the default. Current car is the smart money move.
"""

from __future__ import annotations

from typing import Any

from app.fallbacks.utils import (
    _f,
    _clip,
    _signal_strength,
    _funding_gap,
    _estimated_value,
    _monthly_finance,
    _dream_affordable,
    _decide,
    _rationale,
    _next_actions,
    _based_on,
    validate_confidence,
)

_DECISIONS = ("keep", "upgrade", "delay", "strategy")

_UPGRADE_TCO_SAVING = 0.15
_UPGRADE_GAP_RATIO = 0.25
_DELAY_GAP_RATIO = 0.75
_STRATEGY_AFFORDABILITY_RATIO = 1.2

_RATIONALE_MAX = 280
_NEXT_ACTIONS_MAX = 3


def advisor_fallback(payload: dict) -> dict:
    """Deterministic AI-Advisor baseline.

    ``payload`` shape (see ``docs/ownership-advisor.md``):
        {
            "question": str | None,
            "value":     {mid, low, high, ...} | None,
            "replace":   {used_replacement_cost, new_replacement_cost, funding_gap} | None,
            "upgrade":   {...} | None,
            "finance":   {monthly, ...} | None,
            "dream":     {affordability, ...} | None,
        }

    Returns the contract dict (decision / confidence / rationale /
    next_actions / based_on) — the same shape the router returns, so
    callers can render either path through a single parser.
    """
    modules = payload if isinstance(payload, dict) else {}
    decision = _decide(modules)
    strength, missing = _signal_strength(modules)
    base_conf = 0.5 + 0.4 * strength
    if decision == "delay" and missing:
        base_conf = min(base_conf, 0.55)
    confidence = round(max(0.0, min(1.0, base_conf)), 2)
    rationale = _rationale(decision, modules, missing)
    actions = _next_actions(decision, modules)
    return {
        "decision": decision,
        "confidence": confidence,
        "rationale": rationale,
        "next_actions": actions,
        "based_on": _based_on(modules),
        "model": "rule-based-fallback",
    }


def validate_advisor_response(result: dict) -> dict:
    """Clamp/clean the AI Advisor response so callers always get a valid
    contract regardless of how sloppy the router was.
    """
    out = dict(result) if isinstance(result, dict) else {}
    decision = str(out.get("decision") or "keep").strip().lower()
    if decision not in _DECISIONS:
        decision = "keep"
    out["decision"] = decision
    try:
        conf = float(out.get("confidence"))
    except (TypeError, ValueError):
        conf = 0.5
    if conf != conf:
        conf = 0.5
    out["confidence"] = round(max(0.0, min(1.0, conf)), 2)
    out["rationale"] = _clip(str(out.get("rationale") or ""), _RATIONALE_MAX)
    actions = out.get("next_actions")
    if not isinstance(actions, list):
        actions = []
    cleaned: list[str] = []
    for a in actions:
        if not isinstance(a, str):
            continue
        if not a.strip():
            continue
        cleaned.append(_clip(a.strip(), 200))
        if len(cleaned) >= _NEXT_ACTIONS_MAX:
            break
    out["next_actions"] = cleaned
    based_on = out.get("based_on")
    if not isinstance(based_on, dict):
        based_on = _based_on({})
    out["based_on"] = {k: bool(based_on.get(k)) for k in ("value", "replace", "upgrade", "finance", "dream")}
    out["model"] = str(out.get("model") or "rule-based-fallback")
    return out