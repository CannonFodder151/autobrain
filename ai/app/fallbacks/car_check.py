"""Deterministic fallback for the Car Check AI module (AUT-2630).

Mirrors the backend's ``compute_car_check`` summary in a way the AI
gateway can also produce. When 9Router is reachable the router enriches
the ``ai_summary``, ``red_flags`` and ``green_flags``; the verdict +
fair-value band are produced by the backend and treated as immutable.
"""


_SUMMARY_MAX = 280
_FLAGS_MAX = 6


def _clip(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def _summary(payload: dict) -> str:
    verdict = (payload.get("verdict") or "risky").lower()
    delta = payload.get("delta_pct")
    asking = payload.get("asking_price")
    fair = payload.get("fair_value_mid")
    if asking is None or fair is None:
        return "We couldn't compare this listing to market data."
    if delta is None:
        return "Insufficient comparable listings to score this listing."
    if verdict == "great_deal":
        return _clip(
            f"Asking ${asking:,.0f} is {abs(delta):.1f}% below the fair-value band (${fair:,.0f}). Strong buy if the listing checks out mechanically.",
            _SUMMARY_MAX,
        )
    if verdict == "fair":
        return _clip(
            f"Asking ${asking:,.0f} is within the fair-value band (${fair:,.0f}). Reasonable buy.",
            _SUMMARY_MAX,
        )
    if verdict == "overpriced":
        return _clip(
            f"Asking ${asking:,.0f} is {delta:.1f}% above the fair-value band (${fair:,.0f}). Try negotiating or pass.",
            _SUMMARY_MAX,
        )
    return _clip(
        f"Asking ${asking:,.0f} is {delta:.1f}% above the fair-value band (${fair:,.0f}). Significant premium — verify condition carefully.",
        _SUMMARY_MAX,
    )


def _red_flags(payload: dict) -> list[str]:
    flags: list[str] = []
    sample = int(payload.get("sample_size") or 0)
    delta = payload.get("delta_pct")
    if sample < 3:
        flags.append("Few comparable listings available — verdict is provisional.")
    if delta is not None and delta > 15:
        flags.append("Asking price sits well above the market band.")
    asking = payload.get("asking_price")
    fair = payload.get("fair_value_mid")
    if asking and fair and asking > 100000 and delta is not None and delta > 20:
        flags.append("High-value listing with a large premium — arrange a pre-purchase inspection.")
    return flags[:_FLAGS_MAX]


def _green_flags(payload: dict) -> list[str]:
    flags: list[str] = []
    delta = payload.get("delta_pct")
    if delta is not None and delta <= -10:
        flags.append("Asking price sits well below the market band.")
    sample = int(payload.get("sample_size") or 0)
    if sample >= 10 and delta is not None and abs(delta) <= 5:
        flags.append(f"Strong sample size ({sample} comparables) and fair pricing.")
    return flags[:_FLAGS_MAX]


def car_check_fallback(payload: dict) -> dict:
    """Deterministic Car Check baseline.

    Returns a dict with the verdict + fair-value band carried through
    (the backend produced them; we never re-derive them) plus a
    short ``ai_summary`` and a couple of ``red_flags`` / ``green_flags``
    so the user gets *something* on screen when 9Router is unreachable.
    """
    return {
        "verdict": payload.get("verdict") or "risky",
        "ai_summary": _summary(payload),
        "red_flags": _red_flags(payload),
        "green_flags": _green_flags(payload),
        "model": "rule-based-fallback",
    }


def validate_car_check_response(result: dict) -> dict:
    """Clamp/clean the AI gateway response so the contract stays valid."""
    out = dict(result) if isinstance(result, dict) else {}
    verdict = str(out.get("verdict") or "risky").strip().lower()
    if verdict not in ("great_deal", "fair", "overpriced", "risky"):
        verdict = "risky"
    out["verdict"] = verdict
    out["ai_summary"] = _clip(str(out.get("ai_summary") or ""), _SUMMARY_MAX)
    for key in ("red_flags", "green_flags"):
        items = out.get(key)
        if not isinstance(items, list):
            items = []
        cleaned = []
        for item in items:
            if not isinstance(item, str) or not item.strip():
                continue
            cleaned.append(_clip(item.strip(), 200))
            if len(cleaned) >= _FLAGS_MAX:
                break
        out[key] = cleaned
    out["model"] = str(out.get("model") or "rule-based-fallback")
    return out
