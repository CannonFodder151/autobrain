"""Electric charging station price API (AUT-412 + AUT-466).

Serves cached EV charging station price snapshots and per-user "Electric Spy"
watchlist CRUD. Authenticated and premium-gated (free accounts get 403, same
as Servo Spy fuel prices). Alerts are evaluated by a scheduled task reusing
the user's existing notification channels.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.db.session import get_db
from app.models.electric_price import (
    ChargingStationPriceSnapshot,
    ChargingStationPriceWatchlist,
)
from app.models.user import User
from app.schemas.electric_price import (
    ChargingStationPriceOut,
    ChargingStationPriceWatchlistIn,
    ChargingStationPriceWatchlistOut,
)

router = APIRouter(prefix="/electric-prices", tags=["electric-prices"])


async def require_electric_price_access(
    user: User = Depends(get_current_user),
) -> User:
    """Electric Spy is a paid-tier feature (same gate as Servo Spy)."""
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Electricity price watch is a premium feature. Upgrade to enable it.",
        )
    return user


@router.get("/stations", response_model=list[ChargingStationPriceOut])
async def list_charging_station_prices(
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_electric_price_access),
) -> list[ChargingStationPriceOut]:
    """Latest cached EV charging station prices."""
    rows = await db.scalars(
        select(ChargingStationPriceSnapshot)
        .order_by(ChargingStationPriceSnapshot.price_per_kwh.asc().nullslast())
        .limit(limit)
    )
    return list(rows)


@router.get("/watchlist", response_model=list[ChargingStationPriceWatchlistOut])
async def list_electric_watchlist(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_electric_price_access),
) -> list[ChargingStationPriceWatchlistOut]:
    """The current user's Electric Spy favourites."""
    rows = await db.scalars(
        select(ChargingStationPriceWatchlist)
        .where(ChargingStationPriceWatchlist.user_id == user.id)
        .order_by(ChargingStationPriceWatchlist.created_at.desc())
    )
    return list(rows)


@router.post(
    "/watchlist",
    response_model=ChargingStationPriceWatchlistOut,
    status_code=201,
)
async def add_electric_watchlist(
    payload: ChargingStationPriceWatchlistIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> ChargingStationPriceWatchlist:
    """Add a charging station + connector type to the user's Electric Spy watch list."""
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Electricity price watch is a premium feature. Upgrade to enable it.",
        )
    existing = await db.scalar(
        select(ChargingStationPriceWatchlist).where(
            ChargingStationPriceWatchlist.user_id == user.id,
            ChargingStationPriceWatchlist.station_id == payload.station_id,
            ChargingStationPriceWatchlist.connector_type == payload.connector_type,
        )
    )
    if existing:
        existing.direction = payload.direction
        existing.threshold_pct = payload.threshold_pct
        existing.station_name = payload.station_name or existing.station_name
        existing.brand = payload.brand or existing.brand
        await db.commit()
        await db.refresh(existing)
        return existing

    row = ChargingStationPriceWatchlist(
        user_id=user.id,
        station_id=payload.station_id,
        station_name=payload.station_name,
        brand=payload.brand,
        connector_type=payload.connector_type,
        direction=payload.direction,
        threshold_pct=payload.threshold_pct,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/watchlist/{watch_id}", status_code=204)
async def remove_electric_watchlist(
    watch_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    """Remove a favourite from the user's Electric Spy watch list."""
    row = await db.scalar(
        select(ChargingStationPriceWatchlist).where(
            ChargingStationPriceWatchlist.id == watch_id,
            ChargingStationPriceWatchlist.user_id == user.id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    await db.delete(row)
    await db.commit()
