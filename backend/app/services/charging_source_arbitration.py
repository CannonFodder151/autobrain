"""Source-arbitration rule for the Electric Spy charging-price pipeline (AUT-412).

Mirrors Servo Spy fuel_source_arbitration (AUT-2386) but for connector types
instead of fuel types. Some stations appear in more than one government feed.
When the same station reports a price from multiple sources, we need one
deterministic winner per station+day so the /history chart and the live list
tell a consistent story.

Rule:

  1. Source authority (higher wins):
       GOVERNMENT_MANDATORY_REALTIME > GOVERNMENT_DAILY > OTHER.
  2. Freshness: an observation updated in the last 2h gets a bonus.
  3. Consistency: if the same station appears in 2+ sources and prices
     differ by more than 30 cpl (cents per kWh), prefer the source whose
     price sits closest to the daily median across all sources for that
     station (avoids one single-source feed that publishes wildly
     out-of-band numbers).

The function is pure (no DB, no I/O, no AI) so it is trivial to unit test.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

# Source authority ordering. Lower number = higher authority.
# QLD and WA publish continuously so they are mandatory-realtime.
SOURCE_AUTHORITY: dict[str, int] = {
    "qld": 0,  # GOVERNMENT_MANDATORY_REALTIME
    "wa": 0,   # GOVERNMENT_MANDATORY_REALTIME (ChargeUp WA)
    "nsw": 0,  # GOVERNMENT_MANDATORY_REALTIME (future)
    "vic": 0,  # GOVERNMENT_MANDATORY_REALTIME (future)
    "sa": 0,   # GOVERNMENT_MANDATORY_REALTIME (future)
    "other": 2,  # OTHER (e.g. Tesla, Chargefox app, community scrapes).
}

# Tunable weights. Authority dominates, freshness is a small tie-breaker, and
# the spread penalty only matters when sources disagree by more than 30 c/kWh.
WEIGHT_AUTHORITY = 100.0
WEIGHT_FRESHNESS = 1.0
WEIGHT_SPREAD = 50.0

# Freshness window = 2 hours.
FRESHNESS_WINDOW_HOURS = 2.0

# > 30 cents/kWh disagreement triggers median-based tie-break.
SPREAD_THRESHOLD_CPKWH = 30.0

@dataclass(frozen=True)
class RawSourceObservation:
    """One source's reading for a (station, connector_type, day) bucket.

    `authority` is an int from SOURCE_AUTHORITY (lower = more authoritative).
    Pass ``None`` for ``updated_at`` to skip the freshness bonus.
    """

    source_id: str
    price: float  # cents per kWh
    authority: int
    updated_at: datetime | None = None

@dataclass(frozen=True)
class ArbitrationResult:
    """Output of :func:`arbitrate`."""

    winner_source: str
    winner_price: float
    winner_authority: int
    score: float
    rank: int
    candidates: tuple[tuple[str, float, float], ...]  # (source, price, score)
    used_median: bool

def _authority_score(authority: int) -> float:
    """Higher authority (lower int) -> higher score."""
    return (1 - authority) * WEIGHT_AUTHORITY

def _freshness_bonus(updated_at: datetime | None, *, now: datetime) -> float:
    if updated_at is None:
        return 0.0
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_hours = (now - updated_at).total_seconds() / 3600.0
    if age_hours < 0 or age_hours > FRESHNESS_WINDOW_HOURS:
        return 0.0
    return WEIGHT_FRESHNESS * (1.0 - age_hours / FRESHNESS_WINDOW_HOURS)

def _spread_penalty(price: float, median: float) -> float:
    """Distance from the daily median in cents/kWh, scaled into a score penalty."""
    return abs(price - median) / SPREAD_THRESHOLD_CPKWH * WEIGHT_SPREAD

def arbitrate(
    observations: Iterable[RawSourceObservation],
    *,
    now: datetime | None = None,
) -> ArbitrationResult:
    """Pick the winning source observation for one (station, connector_type, day)."""
    obs = list(observations)
    if not obs:
        raise ValueError("arbitrate() called with no observations")

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    prices = [o.price for o in obs]
    median = statistics.median(prices)
    max_spread = max(prices) - min(prices)
    used_median = max_spread > SPREAD_THRESHOLD_CPKWH and len(obs) >= 2

    scored: list[tuple[RawSourceObservation, float]] = []
    for o in obs:
        score = (
            _authority_score(o.authority)
            + _freshness_bonus(o.updated_at, now=now)
            - (_spread_penalty(o.price, median) if used_median else 0.0)
        )
        scored.append((o, score))

    scored.sort(key=lambda row: (-row[1], row[0].authority, row[0].source_id))

    winner, winner_score = scored[0]
    return ArbitrationResult(
        winner_source=winner.source_id,
        winner_price=winner.price,
        winner_authority=winner.authority,
        score=round(winner_score, 4),
        rank=0,
        candidates=tuple(
            (o.source_id, o.price, round(s, 4)) for o, s in scored
        ),
        used_median=used_median,
    )

def source_authority(source_id: str) -> int:
    """Look up the authority bucket for a given source tag."""
    return SOURCE_AUTHORITY.get(source_id, SOURCE_AUTHORITY["other"])