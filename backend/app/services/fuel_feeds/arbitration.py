"""Source arbitration pass for the Servo Spy fuel-price pipeline (AUT-2386).

After per-source ingests, run the arbitration pass so the per-day winner
table is up to date for the next /history and /stations read.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel_station import FuelPrice, FuelPriceArbitration
from app.services.fuel_source_arbitration import (
    RawSourceObservation,
    arbitrate,
    source_authority,
)

from .base import PRICE_HISTORY_DAYS


def _day_bucket(ts: datetime) -> datetime:
    """Truncate a timestamp to its UTC day (00:00:00 UTC) for arbitration keys."""
    return ts.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


async def arbitrate_station_day(
    db: AsyncSession, station_id: str, fuel_type: str, day: datetime
) -> FuelPriceArbitration | None:
    """Pick the deterministic winner for one (station, fuel_type, UTC day).

    Reads every raw FuelPrice row that falls in that day bucket across all
    sources, runs :func:`app.services.fuel_source_arbitration.arbitrate`, and
    upserts the resulting FuelPriceArbitration row. Returns the row, or
    ``None`` if no source reported a price that day.
    """
    day_start = day.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    rows = list((await db.scalars(
        select(FuelPrice).where(
            FuelPrice.station_id == station_id,
            FuelPrice.fuel_type == fuel_type,
            FuelPrice.effective_at >= day_start,
            FuelPrice.effective_at < day_end,
            FuelPrice.source_id.isnot(None),
        )
    )).all())
    if not rows:
        return None

    obs = [
        RawSourceObservation(
            source_id=r.source_id,
            price=r.price,
            authority=source_authority(r.source_id),
            updated_at=r.effective_at,
        )
        for r in rows
        if r.source_id is not None
    ]
    result = arbitrate(obs)

    existing = await db.scalar(
        select(FuelPriceArbitration).where(
            FuelPriceArbitration.station_id == station_id,
            FuelPriceArbitration.fuel_type == fuel_type,
            FuelPriceArbitration.day == day_start,
        )
    )
    if existing is None:
        existing = FuelPriceArbitration(
            station_id=station_id,
            fuel_type=fuel_type,
            day=day_start,
        )
        db.add(existing)
    existing.source_id = result.winner_source
    existing.price = result.winner_price
    existing.arbitration_score = result.score
    existing.candidate_count = len(result.candidates)
    return existing


async def arbitrate_all_recent(
    db: AsyncSession, *, lookback_days: int = PRICE_HISTORY_DAYS
) -> int:
    """Re-run arbitration across every (station, fuel_type, day) in the cache.

    Called after a per-source ingest so the arbitration table reflects the
    latest set of overlapping sources. Cheap: one SELECT per station+fuel
    group, scoped to the 30-day history window. Returns the number of
    arbitration rows written.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    pairs = list((await db.execute(
        select(FuelPrice.station_id, FuelPrice.fuel_type, FuelPrice.effective_at)
        .where(FuelPrice.effective_at >= cutoff, FuelPrice.source_id.isnot(None))
    )).all())
    if not pairs:
        return 0
    written = 0
    seen: set[tuple[str, str, datetime]] = set()
    for station_id, fuel_type, eff in pairs:
        day = _day_bucket(eff)
        key = (station_id, fuel_type, day)
        if key in seen:
            continue
        seen.add(key)
        if await arbitrate_station_day(db, station_id, fuel_type, day) is not None:
            written += 1
    return written