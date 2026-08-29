"""Servo Spy fuel-price API (AUT-1817).

Read-only, deterministic, PREMIUM-GATED. Every route depends on
``require_fuel_access`` (free/demo accounts get 403, see the gating comment on
AUT-1813). No 9Router/AI — the data is the normalised ``fuel_stations`` /
``fuel_prices`` tables populated by the Celery ingest task.

Open-data attribution is attached to every response via the
``X-Fuel-Data-Attribution`` header and the ``/attribution`` endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.fuel_station import FuelPrice, FuelStation
from app.models.user import User
from app.schemas.fuel_servo import (
    AttributionOut,
    FuelBrandOut,
    FuelPriceOut,
    FuelStationOut,
)
from app.services import fuel_feeds as feeds

logger = get_logger(__name__)

router = APIRouter(prefix="/fuel", tags=["fuel"])

FUEL_ATTRIBUTION = [
    "WA FuelWatch - Government of Western Australia (CC BY 4.0)",
    "NSW FuelCheck - Transport for NSW Open Data",
    "QLD Fuel Prices - Queensland Government",
]
ATTRIBUTION_HEADER = "X-Fuel-Data-Attribution"


async def require_fuel_access(user: User = Depends(get_current_user)) -> User:
    """Servo Spy is a paid-tier feature (founder ruling on AUT-1813).

    Free accounts get no station or price data — same gate as the premium social
    routes, but with the fuel-specific message.
    """
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Fuel prices are a premium feature. Upgrade to enable it.",
        )
    return user


def _set_attribution(response: Response) -> None:
    response.headers[ATTRIBUTION_HEADER] = "; ".join(FUEL_ATTRIBUTION)


@router.get("/types")
async def fuel_types(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_fuel_access),
):
    """Catalogue of fuel types observed across feeds (data-driven dropdown)."""
    _set_attribution(response)
    rows = list((await db.scalars(select(distinct(FuelPrice.fuel_type)).order_by(FuelPrice.fuel_type))).all())
    types = [t for t in rows if t]
    if not types:
        types = list(feeds.DEFAULT_FUEL_TYPES)
    return types


@router.get("/brands", response_model=list[FuelBrandOut])
async def fuel_brands(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_fuel_access),
):
    """Brand list for station logos."""
    _set_attribution(response)
    rows = list((await db.scalars(
        select(distinct(FuelStation.brand))
        .where(FuelStation.brand.isnot(None))
        .order_by(FuelStation.brand)
    )).all())
    return [FuelBrandOut(brand=b, logo=feeds.BRAND_LOGOS.get((b or "").lower())) for b in rows if b]


@router.get("/stations", response_model=list[FuelStationOut])
async def fuel_stations(
    response: Response,
    lat: float = Query(..., description="Search centre latitude"),
    lon: float = Query(..., description="Search centre longitude"),
    radius_km: float = Query(25, gt=0, le=2000, description="Search radius in km"),
    fuel_type: str | None = Query(default=None, description="Filter to a canonical fuel type (91/95/98/E10/Diesel/LPG)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_fuel_access),
):
    """Stations within ``radius_km`` of (lat,lon), each with its prices.

    Radius filter is a great-circle distance in Python (no PostGIS needed for
    MVP). When ``fuel_type`` is given, only stations with a price for that fuel
    are returned, and each carries just that fuel's latest price.
    """
    _set_attribution(response)
    stations = list((await db.scalars(select(FuelStation))).all())
    hits: list[tuple[float, FuelStation]] = []
    for s in stations:
        if s.lat is None or s.lon is None:
            continue
        d = feeds.haversine_km(lat, lon, s.lat, s.lon)
        if d <= radius_km:
            hits.append((d, s))
    hits.sort(key=lambda x: x[0])

    out: list[FuelStationOut] = []
    for dist, s in hits[:limit]:
        prices: list[FuelPrice] = []
        if fuel_type:
            price = await _latest_price(db, s.id, fuel_type)
            if price is None:
                continue
            prices = [price]
        else:
            prices = list((await db.scalars(
                select(FuelPrice).where(FuelPrice.station_id == s.id)
                .order_by(FuelPrice.fuel_type, FuelPrice.effective_at.desc())
            )).all())
        out.append(_station_out(s, prices, dist))
    return out


@router.get("/station/{station_id}/prices", response_model=FuelStationOut)
async def station_prices(
    station_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_fuel_access),
):
    """All fuel prices at a station (detail sheet)."""
    _set_attribution(response)
    station = await db.get(FuelStation, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    prices = list((await db.scalars(
        select(FuelPrice).where(FuelPrice.station_id == station_id)
        .order_by(FuelPrice.fuel_type, FuelPrice.effective_at.desc())
    )).all())
    return _station_out(station, prices, None)


@router.get("/attribution", response_model=AttributionOut)
async def fuel_attribution(
    response: Response,
    _: User = Depends(require_fuel_access),
):
    """Open-data attribution for the aggregated feeds."""
    _set_attribution(response)
    return AttributionOut(attribution=FUEL_ATTRIBUTION, sources=["wa", "nsw", "qld"])


async def _latest_price(db: AsyncSession, station_id: str, fuel_type: str) -> FuelPrice | None:
    return (await db.scalars(
        select(FuelPrice)
        .where(FuelPrice.station_id == station_id, FuelPrice.fuel_type == fuel_type)
        .order_by(FuelPrice.effective_at.desc())
    )).first()


def _station_out(s: FuelStation, prices: list[FuelPrice], dist: float | None) -> FuelStationOut:
    return FuelStationOut(
        id=s.id,
        source=s.source,
        brand=s.brand,
        name=s.name,
        address=s.address,
        lat=s.lat,
        lon=s.lon,
        logo=feeds.BRAND_LOGOS.get((s.brand or "").lower()),
        distance_km=round(dist, 2) if dist is not None else None,
        prices=[FuelPriceOut(fuel_type=p.fuel_type, price=p.price, effective_at=p.effective_at) for p in prices],
    )
