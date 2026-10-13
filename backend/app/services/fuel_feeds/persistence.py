"""Fuel Feeds — persistence and arbitration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.fuel_station import FuelPrice, FuelPriceArbitration, FuelStation
from app.services.fuel_source_arbitration import (
    RawSourceObservation,
    arbitrate,
    source_authority,
)

from app.services.fuel_feeds.common import (
    _now,
    _day_bucket,
    PRICE_HISTORY_DAYS,
)

logger = get_logger(__name__)


async def _upsert_station(db: AsyncSession, s: dict) -> FuelStation:
    existing = (await db.scalars(
        select(FuelStation).where(FuelStation.source == s["source"], FuelStation.source_id == s["source_id"])
    )).first()
    if existing:
        existing.brand = s["brand"]
        existing.name = s["name"]
        existing.address = s["address"]
        existing.lat = s["lat"]
        existing.lon = s["lon"]
        existing.updated_at = _now()
        return existing
    station = FuelStation(**s, updated_at=_now())
    db.add(station)
    await db.flush()
    return station


async def _replace_station_prices(
    db: AsyncSession,
    station_id: str,
    prices: list[tuple[str, float, datetime]],
    *,
    source_id: str,
) -> int:
    """Replace this source's price rows for a station with the new snapshot.

    Per AUT-2386, we now tag each row with the source that produced it so the
    arbitration pass can pick a deterministic winner across overlapping feeds.
    We only delete rows from THIS source (not all sources for the station) so
    that a NSW re-ingest does not blow away a WA observation of the same point.
    """
    await db.execute(
        delete(FuelPrice).where(
            FuelPrice.station_id == station_id, FuelPrice.source_id == source_id
        )
    )
    for ft, price, eff in prices:
        db.add(
            FuelPrice(
                station_id=station_id,
                fuel_type=ft,
                price=price,
                effective_at=eff,
                source_id=source_id,
            )
        )
    return len(prices)


async def _ingest(db: AsyncSession, source: str, stations: list[dict], prices: dict[str, list]) -> dict:
    count_s, count_p = 0, 0
    for s in stations:
        station = await _upsert_station(db, s)
        ps = prices.get(s["source_id"], [])
        count_p += await _replace_station_prices(db, station.id, ps, source_id=source)
        count_s += 1
    return {"source": source, "stations": count_s, "prices": count_p}


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