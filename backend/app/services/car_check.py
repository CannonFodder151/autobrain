"""Car Check — deterministic deal scoring for an arbitrary used-car listing (AUT-2630).

Pure-function module that scores a public listing against the same
``market_listing_cache`` the Ownership Advisor / Value module already
uses. No 9Router, no LLM, no DB read beyond the existing cache helper.

Public surface (one function):

    compute_car_check(
        make, model, year, asking_price, odometer_km=None, condition=None
    ) -> dict

The return shape matches ``AdvisorCarCheckData`` in
``backend/app/schemas/advisor.py`` so the route layer can hand it
straight to the Pydantic envelope. Deterministic — repeated calls
with the same inputs return the same verdict / delta_pct / fair_value
band, which is what the user expects from a "is this a fair price"
tool.

The optional AI summary is *layered on top* by the route via the AI
gateway (see ``app.services.ai_client.run_car_check_ai``). This module
never touches the AI gateway.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.advisor import (
    condition_multiplier,
    km_adjustment,
)
from app.services.market_data import get_market_data

CURRENCY = "AUD"

# Verdict thresholds (deterministic, documented in schemas/advisor.py).
GREAT_DEAL_PCT = -10.0   # asking <= fair - 10%   -> great_deal
FAIR_DEAL_PCT = 5.0      # asking <= fair + 5%    -> fair
OVERPRICE_PCT = 15.0     # asking <= fair + 15%   -> overpriced
                            # else                    -> risky
# A listing is "risky" if the ask is > OVERPRICE_PCT above fair, OR the
# sample size is too small to call it. The risky verdict is what we
# return when market data is missing entirely too (with a `note`).
MIN_SAMPLE_FOR_VERDICT = 3

# Per-condition adjustment is reused from the Value module so a Car
# Check verdict for "2018 Mazda 3 Touring, $20k" is the same number the
# Value tab would produce for the same car. Constants live in
# ``app.services.advisor`` — never duplicated here.


def _safe(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _band(mid: float) -> tuple[float, float]:
    """Documented tight band around the fair-value mid (matches Value module)."""
    low = round(mid * 0.95, 2)
    high = round(mid * 1.05, 2)
    return low, high


def _verdict(delta_pct: float | None, sample_size: int) -> tuple[str, str | None]:
    """Map (delta_pct, sample_size) to one of great_deal|fair|overpriced|risky.

    ``delta_pct`` is (asking - fair_mid) / fair_mid * 100. Negative = asking
    below fair, positive = asking above fair. ``sample_size`` is the
    number of comparables the cache returned; below
    ``MIN_SAMPLE_FOR_VERDICT`` we downgrade to ``risky`` so we never
    overclaim on a thin market.
    """
    if delta_pct is None or sample_size < MIN_SAMPLE_FOR_VERDICT:
        return "risky", "insufficient market data to score this listing"
    if delta_pct <= GREAT_DEAL_PCT:
        return "great_deal", None
    if delta_pct <= FAIR_DEAL_PCT:
        return "fair", None
    if delta_pct <= OVERPRICE_PCT:
        return "overpriced", None
    return "risky", "asking price is well above comparable listings"


def _fallback_summary(verdict: str, asking_price: float | None, fair_mid: float | None, delta_pct: float | None) -> str:
    """Short, deterministic narrative the AI gateway can be skipped over.

    Kept short and factual so it's useful even without the LLM. The AI
    gateway replaces this with a richer summary when 9Router is
    reachable; when 9Router is down the user still gets *something*
    readable on the screen.
    """
    if asking_price is None or fair_mid is None:
        return "We couldn't compare this listing to market data. Try again when the cache refreshes."
    if delta_pct is None:
        return "Insufficient market data to score this listing."
    if verdict == "great_deal":
        return f"Asking price is {abs(delta_pct):.1f}% below the fair-value band. Strong buy."
    if verdict == "fair":
        return "Asking price is within the fair-value band. Reasonable buy."
    if verdict == "overpriced":
        return f"Asking price is {delta_pct:.1f}% above the fair-value band. Negotiate or pass."
    return f"Asking price is {delta_pct:.1f}% above the fair-value band. Significant premium."


def _red_flags(delta_pct: float | None, sample_size: int) -> list[str]:
    flags: list[str] = []
    if sample_size < MIN_SAMPLE_FOR_VERDICT:
        flags.append("Few comparable listings available — verdict is provisional.")
    if delta_pct is not None and delta_pct > OVERPRICE_PCT:
        flags.append("Asking price sits well above the market band.")
    return flags


def _green_flags(delta_pct: float | None) -> list[str]:
    flags: list[str] = []
    if delta_pct is not None and delta_pct <= GREAT_DEAL_PCT:
        flags.append("Asking price sits well below the market band.")
    return flags


async def compute_car_check(
    db: AsyncSession,
    *,
    make: str,
    model: str,
    year: int | None,
    asking_price: float,
    odometer_km: int | None = None,
    condition: str | None = None,
    vehicle_type: str = "car",
) -> dict:
    """Deterministic Car Check score for an arbitrary listing.

    Anchors on the same ``market_listing_cache`` row the Value module
    reads; applies the same condition multiplier + km adjustment
    documented in ``app.services.advisor`` so the verdict is
    internally consistent with the rest of the advisor surface.

    Returns a dict that matches ``AdvisorCarCheckData``. When the
    cache has no row for the vehicle the verdict is ``risky`` and a
    ``note`` explains the gap, so the UI renders a graceful "no
    market data" state instead of fabricating a score.
    """
    asking = _safe(asking_price) or 0.0
    if asking <= 0:
        return {
            "currency": CURRENCY,
            "verdict": "risky",
            "asking_price": None,
            "fair_value_low": None,
            "fair_value_mid": None,
            "fair_value_high": None,
            "delta_pct": None,
            "delta_amount": None,
            "sample_size": 0,
            "condition_multiplier": 1.0,
            "km_multiplier": 1.0,
            "ai_summary": "Asking price was missing or zero — cannot score.",
            "red_flags": ["Asking price was not provided."],
            "green_flags": [],
            "model": "rule-based-fallback",
            "note": "asking_price is required and must be > 0",
        }

    market = await get_market_data(
        db,
        make or "",
        model or "",
        year,
        vehicle_type or "car",
    )
    raw_median = _safe(market.get("median_price"))
    sample_size = int(market.get("sample_size") or 0)

    # Apply the SAME condition + km adjustments the Value module uses
    # so the "fair value" surfaced here is identical to the Value tab's.
    # We pass a lightweight stub Vehicle via the module-level helpers
    # — they only read .condition / .year / .odometer_km.
    class _StubVehicle:
        pass

    stub = _StubVehicle()
    stub.condition = condition
    stub.year = year
    stub.odometer_km = odometer_km
    cond_mult = condition_multiplier(getattr(stub, "condition", None))
    km_mult = km_adjustment(stub, odometer_km)

    fair_mid: float | None = None
    if raw_median is not None and raw_median > 0:
        fair_mid = round(raw_median * cond_mult * km_mult, 2)

    if fair_mid is not None and fair_mid > 0:
        delta_amount = round(asking - fair_mid, 2)
        delta_pct = round((delta_amount / fair_mid) * 100.0, 2)
        fair_low, fair_high = _band(fair_mid)
    else:
        delta_amount = None
        delta_pct = None
        fair_low, fair_high = None, None

    verdict, verdict_note = _verdict(delta_pct, sample_size)
    note = verdict_note or market.get("note")

    return {
        "currency": CURRENCY,
        "verdict": verdict,
        "asking_price": round(asking, 2),
        "fair_value_low": fair_low,
        "fair_value_mid": fair_mid,
        "fair_value_high": fair_high,
        "delta_pct": delta_pct,
        "delta_amount": delta_amount,
        "sample_size": sample_size,
        "condition_multiplier": round(cond_mult, 4),
        "km_multiplier": round(km_mult, 4),
        "ai_summary": _fallback_summary(verdict, asking, fair_mid, delta_pct),
        "red_flags": _red_flags(delta_pct, sample_size),
        "green_flags": _green_flags(delta_pct),
        "model": "rule-based-fallback",
        "note": note,
    }


def parse_listing_url(url: str) -> dict | None:
    """Best-effort extract of make/model/year/price from a public listing URL.

    Deterministic and pure: no network call, no LLM. Real sites encode
    make/model in the slug (CarsGuide: ``/buy/2018-mazda-3-touring/``,
    CarSales: ``/cars/details/2018-Mazda-3-GT/...``). When the slug
    doesn't carry enough info we return ``None`` so the route layer
    falls back to the manual form rather than guessing.

    The list of recognised makes is the same one the value module
    already uses (top-30 AU makes); importing it from the cache
    service is overkill for a slug parser, so we keep a minimal
    in-module alias table. New makes are easy to add here.
    """
    if not url or not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw:
        return None
    try:
        from urllib.parse import urlparse
        path = urlparse(raw).path.lower()
    except Exception:
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None

    import re
    year_match: int | None = None
    slug_parts: list[str] = []
    for p in parts:
        m = re.match(r"^(19\d{2}|20\d{2})(?:[-_]|$)", p)
        if m and year_match is None:
            try:
                year_match = int(m.group(1))
                rest = p[m.end():]
                if rest:
                    slug_parts.append(rest)
            except ValueError:
                pass
        else:
            slug_parts.append(p)

    slug = "-".join(slug_parts)
    slug = re.sub(r"[^a-z0-9 -]", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip()
    tokens = [t for t in slug.replace("-", " ").split() if t]
    if not tokens:
        return None

    known_makes = {
        "toyota", "honda", "mazda", "ford", "holden", "hyundai", "kia",
        "subaru", "mitsubishi", "nissan", "volkswagen", "vw", "bmw",
        "mercedes", "mercedes-benz", "audi", "lexus", "tesla", "jeep",
        "isuzu", "landrover", "land-rover", "suzuki", "volvo", "skoda",
        "peugeot", "renault", "fiat", "mini", "porsche", "jaguar",
    }
    make_token: str | None = None
    model_tokens: list[str] = []
    for t in tokens:
        if make_token is None and t in known_makes:
            canonical = "mercedes-benz" if t == "mercedes" else ("land-rover" if t == "landrover" else t)
            if canonical == "vw":
                canonical = "volkswagen"
            make_token = canonical
        elif make_token is not None:
            model_tokens.append(t)
        if len(model_tokens) >= 3:
            break

    if not make_token or not model_tokens or year_match is None:
        return None

    model = "-".join(model_tokens[:2])
    return {
        "make": make_token,
        "model": model,
        "year": year_match,
    }
