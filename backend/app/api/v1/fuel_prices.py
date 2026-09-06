"""Petrol price map read API (AUT-1813) + servo-spy favourites (AUT-1859).

Serves the cached NSW Fuel API snapshot to the price-map frontend. Authenticated
(any user token) — prices are public data, the auth gate just bounds usage and
matches the rest of the API surface. The actual feed poll is a celery beat
task (poll_nsw_fuel_prices), not exposed here.

The ``/watchlist`` routes (AUT-1859) are per-user CRUD for a user's servo-spy
favourites. Alerts are evaluated by the daily ``check_fuel_price_alerts``
celery task, which reuses the user's existing notification channels.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.db.session import get_db
from app.models.fuel_price import FuelPriceSnapshot, FuelPriceWatchlist
from app.models.user import User
from app.schemas.fuel import (
    FuelPriceOut,
    FuelPriceWatchlistIn,
    FuelPriceWatchlistOut,
)

router = APIRouter(prefix="/fuel-prices", tags=["fuel-prices"])


def _price_delta_pct(price: float | None, previous: float | None) -> float | None:
    """Day-over-day % move. None until a prior distinct price exists."""
    if price is None or previous in (None, 0):
        return None
    return round((price - previous) / previous * 100, 2)


@router.get("", response_model=list[FuelPriceOut])
async def list_fuel_prices(
    state: str = Query(default="NSW", max_length=8),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[FuelPriceOut]:
    """Latest cached petrol prices for a state (map marker set)."""
    rows = await db.scalars(
        select(FuelPriceSnapshot)
        .where(FuelPriceSnapshot.state == state)
        .order_by(FuelPriceSnapshot.price.asc().nullslast())
        .limit(2000)
    )
    out = [FuelPriceOut.model_validate(r) for r in rows]
    for r, o in zip(rows, out, strict=False):
        o.price_delta_pct = _price_delta_pct(r.price, r.previous_price)
    return out


@router.get("/watchlist", response_model=list[FuelPriceWatchlistOut])
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FuelPriceWatchlistOut]:
    """The current user's servo-spy favourites."""
    rows = await db.scalars(
        select(FuelPriceWatchlist)
        .where(FuelPriceWatchlist.user_id == user.id)
        .order_by(FuelPriceWatchlist.created_at.desc())
    )
    return list(rows)


@router.post("/watchlist", response_model=FuelPriceWatchlistOut, status_code=201)
async def add_watchlist(
    payload: FuelPriceWatchlistIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> FuelPriceWatchlist:
    """Add a station + fuel type to the user's servo-spy watch list."""
    # Reuse an existing favourite if the same (user, state, station, fuel) exists.
    existing = await db.scalar(
        select(FuelPriceWatchlist).where(
            FuelPriceWatchlist.user_id == user.id,
            FuelPriceWatchlist.state == payload.state,
            FuelPriceWatchlist.station_code == payload.station_code,
            FuelPriceWatchlist.fuel_type == payload.fuel_type,
        )
    )
    if existing:
        existing.direction = payload.direction
        existing.threshold_pct = payload.threshold_pct
        await db.commit()
        await db.refresh(existing)
        return existing

    # Cache station name/brand from the latest price row when available.
    sample = await db.scalar(
        select(FuelPriceSnapshot).where(
            FuelPriceSnapshot.state == payload.state,
            FuelPriceSnapshot.station_code == payload.station_code,
            FuelPriceSnapshot.fuel_type == payload.fuel_type,
        )
    )
    row = FuelPriceWatchlist(
        user_id=user.id,
        state=payload.state,
        station_code=payload.station_code,
        fuel_type=payload.fuel_type,
        direction=payload.direction,
        threshold_pct=payload.threshold_pct,
        station_name=sample.station_name if sample else None,
        brand=sample.brand if sample else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/watchlist/{watch_id}", status_code=204)
async def remove_watchlist(
    watch_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    """Remove a favourite from the user's servo-spy watch list."""
    row = await db.scalar(
        select(FuelPriceWatchlist).where(
            FuelPriceWatchlist.id == watch_id,
            FuelPriceWatchlist.user_id == user.id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    await db.delete(row)
    await db.commit()
