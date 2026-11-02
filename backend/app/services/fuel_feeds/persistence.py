"""Persistence layer for the Servo Spy fuel-price pipeline (AUT-1817).

Station upsert + price replacement logic shared by all state providers.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel_station import FuelPrice, FuelStation

from .base import _now


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
