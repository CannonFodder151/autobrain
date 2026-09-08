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

_DECISIONS = ("keep", "upgrade", "delay", "strategy")

_UPGRADE_TCO_SAVING = 0.15
_UPGRADE_GAP_RATIO = 0.25
_DELAY_GAP_RATIO = 0.75
_STRATEGY_AFFORDABILITY_RATIO = 1.2

_RATIONALE_MAX = 280
_NEXT_ACTIONS_MAX = 3


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _clip(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def _signal_strength(modules: dict[str, Any]) -> tuple[float, list[str]]:
    """Return a (0..1, list_of_missing) tuple.

    Stronger signal = more modules answered with usable numerics. Missing
    modules drop confidence so the router can compensate with its
    reasoning — but the deterministic baseline never overclaims.
    """
    required = ("value", "replace", "upgrade", "finance", "dream")
    present = [m for m in required if modules.get(m)]
    ratio = len(present) / len(required)
    missing = [m for m in required if not modules.get(m)]
    return ratio, missing


def _funding_gap(modules: dict[str, Any]) -> float | None:
    replace = modules.get("replace") or {}
    val = modules.get("value") or {}
    gap = _f(replace.get("funding_gap"))
    if gap is not None:
        return gap
    used = _f(replace.get("used_replacement_cost"))
    mid = _f(val.get("mid") or val.get("estimated_value"))
    if used is None or mid is None:
        return None
    return used - mid


def _estimated_value(modules: dict[str, Any]) -> float | None:
    val = modules.get("value") or {}
    return _f(val.get("mid") or val.get("estimated_value"))


def _monthly_finance(modules: dict[str, Any]) -> float | None:
    fin = modules.get("finance") or {}
    for key in ("monthly", "effective_monthly", "payment"):
        v = _f(fin.get(key))
        if v is not None:
            return v
    return None


def _dream_affordable(modules: dict[str, Any]) -> bool | None:
    dream = modules.get("dream") or {}
    aff = dream.get("affordability")
    if isinstance(aff, str):
        s = aff.strip().lower()
        if s in ("affordable", "yes", "within_budget", "ok"):
            return True
        if s in ("unaffordable", "no", "out_of_budget", "stretch"):
            return False
    if isinstance(aff, bool):
        return aff
    return None


def _decide(modules: dict[str, Any]) -> str:
    gap = _funding_gap(modules)
    est = _estimated_value(modules)
    gap_ratio = None
    if gap is not None and est not in (None, 0):
        gap_ratio = gap / est

    if gap_ratio is not None:
        if gap_ratio <= _UPGRADE_GAP_RATIO:
            return "upgrade"
        if gap_ratio > _DELAY_GAP_RATIO:
            return "delay"

    monthly = _monthly_finance(modules)
    if monthly is not None and est is not None and est > 0:
        annual = monthly * 12
        if annual < est * _UPGRADE_TCO_SAVING:
            return "upgrade"

    dream = modules.get("dream") or {}
    dream_aff = _dream_affordable(modules)
    if dream and dream_aff is True:
        return "strategy"

    return "keep"


def _rationale(decision: str, modules: dict[str, Any], missing: list[str]) -> str:
    parts: list[str] = []
    est = _estimated_value(modules)
    gap = _funding_gap(modules)
    if est is not None:
        parts.append(f"current value ~${est:,.0f}")
    if gap is not None:
        parts.append(f"replacement gap ~${gap:,.0f}")
    base = ""
    if decision == "keep":
        base = "Your current car is the smart money move."
    elif decision == "upgrade":
        base = "A clear trade-up is within reach."
    elif decision == "delay":
        base = "Wait — the numbers aren't in your favour yet."
    elif decision == "strategy":
        base = "A non-binary play fits this scenario."
    summary = base
    if parts:
        summary = f"{base} " + ", ".join(parts) + "."
    if missing:
        summary += f" (limited data: {', '.join(missing)}.)"
    return _clip(summary, _RATIONALE_MAX)


def _next_actions(decision: str, modules: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if decision == "keep":
        actions.append("Stick with the current car; revisit in 6 months.")
        actions.append("Keep up scheduled services to protect residual value.")
    elif decision == "upgrade":
        actions.append("Shortlist 2-3 concrete upgrade candidates from the Upgrade tab.")
        actions.append("Get a pre-purchase inspection budget for each shortlist.")
    elif decision == "delay":
        actions.append("Re-run the advisor after your next service or in 3 months.")
        actions.append("Track market median for your model weekly on the Value tab.")
    elif decision == "strategy":
        actions.append("Compare a novated lease vs outright purchase on the Finance tab.")
        actions.append("Talk to a broker about a 2-3 year hold before committing.")
    return actions[:_NEXT_ACTIONS_MAX]


def _based_on(modules: dict[str, Any]) -> dict[str, Any]:
    """Record which sub-modules contributed structured data.

    Lets the caller (and the audit log) trace any number in the rationale
    back to its source module. Booleans only; nothing in here is invented.
    """
    return {
        m: bool(modules.get(m))
        for m in ("value", "replace", "upgrade", "finance", "dream")
    }


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
