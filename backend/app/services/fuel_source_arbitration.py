"""Source-arbitration rule for the Servo Spy fuel-price pipeline (AUT-2386).

Some stations appear in more than one government feed (e.g. Ampol/BP/Costco
turn up in NSW FuelCheck, SA Fuel Price Information Service, and QLD Fuel
Prices). When the same station reports a price from multiple sources, we need
one deterministic winner per station+day so the /history chart and the live
fuel list tell a consistent story.

Rule (per Nathan, AUT-2371 follow-up):

  1. Source authority (higher wins):
       GOVERNMENT_MANDATORY_REALTIME > GOVERNMENT_DAILY > OTHER.
  2. Freshness: an observation updated in the last 2h gets a bonus.
  3. Consistency: if the same station appears in 2+ sources and prices
     differ by more than 30 cpl, prefer the source whose price sits closest
     to the daily median across all sources for that station (avoids one
     single-source feed that publishes wildly out-of-band numbers).

The function is pure (no DB, no I/O, no AI) so it is trivial to unit test.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


# Source authority ordering. Lower number = higher authority. NSW FuelCheck
# and QLD Fuel Prices publish continuously so they are mandatory-realtime;
# WA FuelWatch publishes a daily 6am snapshot so it is daily-only.
SOURCE_AUTHORITY: dict[str, int] = {
    "nsw": 0,  # GOVERNMENT_MANDATORY_REALTIME
    "qld": 0,  # GOVERNMENT_MANDATORY_REALTIME
    "sa": 0,   # GOVERNMENT_MANDATORY_REALTIME (SAFPIS — included for forward
               # compatibility, the SA feed is wired in a follow-up).
    "wa": 1,   # GOVERNMENT_DAILY (FuelWatch)
    "other": 2,  # OTHER (e.g. 7-Eleven, Caltex, or community scrapes).
}

# Tunable weights. Authority dominates, freshness is a small tie-breaker, and
# the spread penalty only matters when sources disagree by more than 30 cpl.
WEIGHT_AUTHORITY = 100.0
WEIGHT_FRESHNESS = 1.0
WEIGHT_SPREAD = 50.0

# Per Nathan: freshness window = 2 hours.
FRESHNESS_WINDOW_HOURS = 2.0

# Per Nathan: > 30 cpl disagreement triggers median-based tie-break.
SPREAD_THRESHOLD_CPL = 30.0


@dataclass(frozen=True)
class RawSourceObservation:
    """One source's reading for a (station, fuel_type, day) bucket.

    `authority` is an int from SOURCE_AUTHORITY (lower = more authoritative).
    Pass ``None`` for ``updated_at`` to skip the freshness bonus.
    """

    source_id: str
    price: float  # cents per litre
    authority: int
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ArbitrationResult:
    """Output of :func:`arbitrate`."""

    winner_source: str
    winner_price: float
    winner_authority: int
    score: float
    rank: int  # 0-based rank of the winner in the input list
    candidates: tuple[tuple[str, float, float], ...]  # (source, price, score)
    used_median: bool  # True if the spread exceeded the threshold


def _authority_score(authority: int) -> float:
    """Higher authority (lower int) -> higher score."""
    # authority 0 (mandatory realtime) -> 100
    # authority 1 (daily) -> 0
    # authority 2 (other) -> -100
    return (1 - authority) * WEIGHT_AUTHORITY


def _freshness_bonus(updated_at: datetime | None, *, now: datetime) -> float:
    if updated_at is None:
        return 0.0
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_hours = (now - updated_at).total_seconds() / 3600.0
    if age_hours < 0 or age_hours > FRESHNESS_WINDOW_HOURS:
        return 0.0
    # Linear decay across the window — fresher = higher bonus.
    return WEIGHT_FRESHNESS * (1.0 - age_hours / FRESHNESS_WINDOW_HOURS)


def _spread_penalty(price: float, median: float) -> float:
    """Distance from the daily median in cpl, scaled into a score penalty."""
    return abs(price - median) / SPREAD_THRESHOLD_CPL * WEIGHT_SPREAD


def arbitrate(
    observations: Iterable[RawSourceObservation],
    *,
    now: datetime | None = None,
) -> ArbitrationResult:
    """Pick the winning source observation for one (station, fuel_type, day).

    The rule is fully deterministic: same inputs -> same outputs. Empty input
    raises ``ValueError`` so the caller cannot accidentally persist a phantom
    winner; that case means we never saw a price that day and the caller
    should skip the row, not invent one.
    """
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
    used_median = max_spread > SPREAD_THRESHOLD_CPL and len(obs) >= 2

    scored: list[tuple[RawSourceObservation, float]] = []
    for o in obs:
        score = (
            _authority_score(o.authority)
            + _freshness_bonus(o.updated_at, now=now)
            - (_spread_penalty(o.price, median) if used_median else 0.0)
        )
        scored.append((o, score))

    # Tie-break: highest score, then higher authority (lower int), then
    # alphabetical source_id. Source-id ordering is deterministic and
    # independent of the caller's input order — the rule produces the same
    # winner for the same logical set no matter how the caller iterates.
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
