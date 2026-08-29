"""Petrol price map read API (AUT-1813).

Serves the cached NSW Fuel API snapshot to the price-map frontend. Authenticated
(any user token) — prices are public data, the auth gate just bounds usage and
matches the rest of the API surface. The actual feed poll is a celery beat
task (poll_nsw_fuel_prices), not exposed here.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.fuel_price import FuelPrice
from app.models.user import User
from app.schemas.fuel import FuelPriceOut

router = APIRouter(prefix="/fuel-prices", tags=["fuel-prices"])


@router.get("", response_model=list[FuelPriceOut])
async def list_fuel_prices(
    state: str = Query(default="NSW", max_length=8),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[FuelPrice]:
    """Latest cached petrol prices for a state (map marker set)."""
    rows = await db.scalars(
        select(FuelPrice)
        .where(FuelPrice.state == state)
        .order_by(FuelPrice.price.asc().nullslast())
        .limit(2000)
    )
    return list(rows)
