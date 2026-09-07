"""Deterministic car-check baseline (AUT-2651).

The AI car-check module composes structured listing fields and a deal score
into a readable narrative. This module is the *baseline*: it always runs and
returns a well-formed response. When 9Router is reachable its response is
shallow-merged on top (see ``ai/app/router_client.enhance``).

The baseline is deliberately simple and explicit so the contract is auditable
and never invents numbers. Every numeric in the output comes from the
caller-provided payload; the baseline only chooses which fields to surface
in plain-English narration.
"""

from __future__ import annotations

from typing import Any

_SUMMARY_MAX = 280
_FLAG_MAX = 120


def _clip(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def _score_label(score: float | None) -> str:
    if score is None:
        return "not available"
    if score >= 75:
        return "strong"
    if score >= 50:
        return "fair"
    return "weak"


def _parse_listing(payload: dict[str, Any]) -> dict[str, Any]:
    listing = payload.get("listing") or {}
    if not isinstance(listing, dict):
        listing = {}
    return {
        "title": str(listing.get("title") or "").strip() or "not available",
        "price": listing.get("price"),
        "year": listing.get("year"),
        "odometer_km": listing.get("odometer_km"),
        "make": str(listing.get("make") or "").strip() or "not available",
        "model": str(listing.get("model") or "").strip() or "not available",
        "listing_url": str(listing.get("listing_url") or "").strip() or "not available",
    }


def _price_str(price: Any) -> str:
    if price is None:
        return "not available"
    try:
        return f"${float(price):,.0f}"
    except (TypeError, ValueError):
        return "not available"


def _year_str(year: Any) -> str:
    if year is None:
        return "not available"
    try:
        return str(int(year))
    except (TypeError, ValueError):
        return "not available"


def _odo_str(odo: Any) -> str:
    if odo is None:
        return "not available"
    try:
        return f"{int(odo):,} km"
    except (TypeError, ValueError):
        return "not available"


def _red_flags(listing: dict[str, Any], deal_score: float | None) -> list[str]:
    flags: list[str] = []
    if deal_score is not None and deal_score < 50:
        flags.append(f"Deal score {deal_score:.0f}/100 — well below the strong threshold.")
    if listing.get("price") is None:
        flags.append("No price listed.")
    if listing.get("odometer_km") is None:
        flags.append("Odometer reading not provided.")
    return flags[:_FLAG_MAX][:5]


def _green_flags(listing: dict[str, Any], deal_score: float | None) -> list[str]:
    flags: list[str] = []
    if deal_score is not None and deal_score >= 75:
        flags.append(f"Deal score {deal_score:.0f}/100 — strong value proposition.")
    elif deal_score is not None and deal_score >= 50:
        flags.append(f"Deal score {deal_score:.0f}/100 — fair value.")
    if listing.get("price") is not None:
        flags.append(f"Listed at {_price_str(listing['price'])}.")
    if listing.get("year") is not None:
        flags.append(f"{_year_str(listing['year'])} model.")
    if listing.get("listing_url") and listing["listing_url"] != "not available":
        flags.append("Direct listing link available.")
    return flags[:_FLAG_MAX][:5]


def _build_summary(listing: dict[str, Any], deal_score: float | None) -> str:
    score_text = _score_label(deal_score)
    parts = [
        f"{listing['make']} {listing['model']} ({_year_str(listing['year'])})",
        f"listed at {_price_str(listing['price'])}",
        f"with {_odo_str(listing.get('odometer_km'))}",
        f"has a {score_text} deal score.",
    ]
    return _clip(" ".join(parts), _SUMMARY_MAX)


def car_check_fallback(payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic car-check baseline (AUT-2651).

    ``payload`` shape:
        {
            "deal_score": number (0-100) | None,
            "listing": {
                "title": str | None,
                "price": number | None,
                "year": int | None,
                "odometer_km": int | None,
                "make": str | None,
                "model": str | None,
                "listing_url": str | None,
            } | None,
        }

    Returns the contract dict (summary / red_flags / green_flags / deal_score)
    — the same shape the router returns, so callers can render either path
    through a single parser.
    """
    payload = payload if isinstance(payload, dict) else {}
    deal_score = payload.get("deal_score")
    try:
        deal_score_f = float(deal_score) if deal_score is not None else None
    except (TypeError, ValueError):
        deal_score_f = None

    listing = _parse_listing(payload)
    reds = _red_flags(listing, deal_score_f)
    greens = _green_flags(listing, deal_score_f)
    summary = _build_summary(listing, deal_score_f)
    return {
        "summary": summary,
        "red_flags": reds,
        "green_flags": greens,
        "deal_score": deal_score_f,
        "model": "rule-based-fallback",
    }


def validate_car_check_response(result: dict[str, Any]) -> dict[str, Any]:
    """Clamp/clean the car-check response so callers always get a valid
    contract regardless of how sloppy the router was.
    """
    out = dict(result) if isinstance(result, dict) else {}

    deal_score = out.get("deal_score")
    try:
        ds = float(deal_score) if deal_score is not None else None
    except (TypeError, ValueError):
        ds = None
    if ds is not None:
        ds = max(0.0, min(100.0, ds))
    out["deal_score"] = ds

    out["summary"] = _clip(str(out.get("summary") or ""), _SUMMARY_MAX)

    for key in ("red_flags", "green_flags"):
        raw = out.get(key)
        if not isinstance(raw, list):
            raw = []
        cleaned: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                continue
            s = item.strip()
            if not s:
                continue
            cleaned.append(_clip(s, _FLAG_MAX))
            if len(cleaned) >= 5:
                break
        out[key] = cleaned

    out["model"] = str(out.get("model") or "rule-based-fallback")
    return out
