"""Car Check service (AUT-2651).

Deterministic deal evaluation for a market listing. Given a listing dict and
the user's vehicle reference price (mid from the Value module), computes a
0-100 deal score and returns the structured payload that ``run_car_check_ai``
feeds to 9Router.

When 9Router is unreachable ``run_car_check_ai`` returns ``None`` and the
caller falls back to the rule-based summary generated here.
"""

from __future__ import annotations

from typing import Any


_DEAL_SCORE_MAX = 100
_PRICE_WEIGHT = 0.6
_KM_WEIGHT = 0.3
_YEAR_WEIGHT = 0.1


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _score_from_price(listing_price: float | None, reference_price: float | None) -> float | None:
    """Price vs reference: 100 when listing < reference, 0 when >2× reference."""
    if listing_price is None or reference_price is None or reference_price <= 0:
        return None
    ratio = listing_price / reference_price
    if ratio >= 2.0:
        return 0.0
    if ratio >= 1.0:
        return max(0.0, 100.0 * (2.0 - ratio))
    return 100.0


def _score_from_km(listing_km: int | None, vehicle_year: int | None) -> float | None:
    """Lower km than benchmark for age = better. Returns 0-100."""
    if listing_km is None or vehicle_year is None:
        return None
    try:
        age = max(1, 2026 - int(vehicle_year))
    except (TypeError, ValueError):
        return None
    benchmark = age * 15_000
    if benchmark <= 0:
        return None
    ratio = listing_km / benchmark
    if ratio <= 0.5:
        return 100.0
    if ratio >= 2.0:
        return 0.0
    return max(0.0, 100.0 * (2.0 - ratio))


def _score_from_year(listing_year: int | None, vehicle_year: int | None) -> float | None:
    """Same year = 100, older = lower. 20+ year gap = 0."""
    if listing_year is None or vehicle_year is None:
        return None
    try:
        gap = abs(int(listing_year) - int(vehicle_year))
    except (TypeError, ValueError):
        return None
    if gap <= 0:
        return 100.0
    if gap >= 20:
        return 0.0
    return max(0.0, 100.0 * (1.0 - gap / 20.0))


def compute_deal_score(
    listing: dict[str, Any],
    reference_price: float | None = None,
    vehicle_year: int | None = None,
) -> float:
    """Compute a 0-100 deal score from listing fields + reference price.

    Weights: price 60%, km 30%, year 10%. Missing signals are skipped
    (score drops to the weighted average of what's available) so the
    function never crashes and always returns a float in [0, 100].
    """
    price = _safe_float(listing.get("price"))
    km = _safe_float(listing.get("odometer_km"))
    year = listing.get("year")
    if isinstance(year, bool) or not isinstance(year, (int, float, type(None))):
        year = None
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None

    scores: list[float] = []
    weights: list[float] = []
    total_weight = 0.0

    sp = _score_from_price(price, reference_price)
    if sp is not None:
        scores.append(sp)
        weights.append(_PRICE_WEIGHT)
        total_weight += _PRICE_WEIGHT

    sk = _score_from_km(int(km) if km is not None else None, vehicle_year)
    if sk is not None:
        scores.append(sk)
        weights.append(_KM_WEIGHT)
        total_weight += _KM_WEIGHT

    sy = _score_from_year(year, vehicle_year)
    if sy is not None:
        scores.append(sy)
        weights.append(_YEAR_WEIGHT)
        total_weight += _YEAR_WEIGHT

    if not scores:
        return 50.0

    if total_weight > 0:
        weighted = sum(s * w for s, w in zip(scores, weights)) / total_weight
    else:
        weighted = sum(scores) / len(scores)

    return round(max(0.0, min(100.0, weighted)), 1)


def build_car_check_payload(
    listing: dict[str, Any],
    reference_price: float | None = None,
    vehicle_year: int | None = None,
) -> dict[str, Any]:
    """Build the full car-check payload (deal score + listing) for the AI client."""
    deal_score = compute_deal_score(listing, reference_price=reference_price, vehicle_year=vehicle_year)
    clean_listing = {
        "title": listing.get("title"),
        "price": listing.get("price"),
        "year": listing.get("year"),
        "odometer_km": listing.get("odometer_km"),
        "make": listing.get("make"),
        "model": listing.get("model"),
        "listing_url": listing.get("listing_url"),
    }
    return {
        "deal_score": deal_score,
        "listing": clean_listing,
    }


# --- deterministic fallback -------------------------------------------------
# Mirror of ai/app/fallbacks/car_check.py so the backend API endpoint can
# produce the same output schema without importing the AI package.

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
