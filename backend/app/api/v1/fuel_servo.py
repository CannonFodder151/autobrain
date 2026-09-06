"""Servo Spy fuel-price API (AUT-1817).

Read-only, deterministic, PREMIUM-GATED. Every route depends on
``require_fuel_access`` (free/demo accounts get 403, see the gating comment on
AUT-1813). No 9Router/AI — the data is the normalised ``fuel_stations`` /
``fuel_prices`` tables populated by the Celery ingest task.

Open-data attribution is attached to every response via the
``X-Fuel-Data-Attribution`` header and the ``/attribution`` endpoint.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.fuel_station import FuelPrice, FuelStation
from app.models.user import User
from app.schemas.fuel import FuelStats  # noqa: F401  (type hint in _station_out)
from app.schemas.fuel_servo import (
    AttributionOut,
    FuelBrandOut,
    FuelHistoryPoint,
    FuelPriceHistoryOut,
    FuelPriceOut,
    FuelStationHistoryOut,
    FuelStationOut,
)
from app.services import fuel_feeds as feeds
from app.services.fuel import compute_fuel_stats
from app.services.fuel_servo import annotate_price
from app.services.ownership import get_accessible_vehicle

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
    vehicle_id: str | None = Query(default=None, description="Annotate prices with this vehicle's per-station cost (AUT-2201)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_fuel_access),
):
    """Stations within ``radius_km`` of (lat,lon), each with its prices.

    Radius filter is a great-circle distance in Python (no PostGIS needed for
    MVP). When ``fuel_type`` is given, only stations with a price for that fuel
    are returned, and each carries just that fuel's latest price.

    When ``vehicle_id`` is given (must be accessible to ``user``), every price
    carries ``cost_per_km`` ($/km, from avg L/100km) and ``avg_fill_cost`` ($,
    from avg litres/fill) — deterministic, no AI.
    """
    _set_attribution(response)
    stats = None
    if vehicle_id is not None:
        await get_accessible_vehicle(db, vehicle_id, user)
        stats = await compute_fuel_stats(db, vehicle_id)
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
        out.append(_station_out(s, prices, dist, stats))
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
    return _station_out(station, prices, None, None)


@router.get("/attribution", response_model=AttributionOut)
async def fuel_attribution(
    response: Response,
    _: User = Depends(require_fuel_access),
):
    """Open-data attribution for the aggregated feeds."""
    _set_attribution(response)
    return AttributionOut(attribution=FUEL_ATTRIBUTION, sources=["wa", "nsw", "qld"])


@router.get("/stations/{station_id}/history", response_model=FuelStationHistoryOut)
async def station_history(
    station_id: str,
    response: Response,
    fuel_type: str | None = Query(default=None, description="Optional canonical fuel filter (91/95/98/E10/Diesel/LPG)"),
    days: int = Query(default=feeds.PRICE_HISTORY_DAYS, ge=1, le=feeds.PRICE_HISTORY_DAYS),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_fuel_access),
):
    """AUT-2375: 30-day price history for a single station, served from cache.

    Reads exclusively from ``fuel_prices`` — never fans out to the upstream
    fuel APIs. The daily Celery beat task (``fuel-ingest-all-daily``) is the
    only thing that refreshes these rows.
    """
    _set_attribution(response)
    station = await db.get(FuelStation, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = (
        select(FuelPrice)
        .where(
            FuelPrice.station_id == station_id,
            FuelPrice.effective_at >= cutoff,
        )
        .order_by(FuelPrice.fuel_type, FuelPrice.effective_at.asc())
    )
    if fuel_type:
        q = q.where(FuelPrice.fuel_type == fuel_type)
    rows = list((await db.scalars(q)).all())
    return FuelStationHistoryOut(
        station_id=station_id,
        source=station.source,
        fuel_type=fuel_type,
        days=days,
        series=[
            FuelHistoryPoint(
                fuel_type=p.fuel_type,
                price=p.price,
                effective_at=p.effective_at,
            )
            for p in rows
        ],
    )


async def _latest_price(db: AsyncSession, station_id: str, fuel_type: str) -> FuelPrice | None:
    return (await db.scalars(
        select(FuelPrice)
        .where(FuelPrice.station_id == station_id, FuelPrice.fuel_type == fuel_type)
        .order_by(FuelPrice.effective_at.desc())
    )).first()


def _station_out(
    s: FuelStation,
    prices: list[FuelPrice],
    dist: float | None,
    stats: "FuelStats | None" = None,
) -> FuelStationOut:
    # AUT-2319: thin compat wrapper; real implementation lives in
    # ``app.services.fuel_servo.annotate_station`` so unit tests can import
    # it without pulling in the full FastAPI router chain.
    return annotate_station(s, prices, dist, stats)


@router.get(
    "/stations/{station_id}/history",
    response_model=list[FuelPriceHistoryOut],
)
async def station_price_history(
    station_id: str,
    response: Response,
    fuel_type: str | None = Query(default=None, description="Filter to one canonical fuel type"),
    days: int = Query(default=30, ge=1, le=90, description="Look-back window in days"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_fuel_access),
) -> list[FuelPriceHistoryOut]:
    """Price history (per source) for a station.

    AUT-2374: price-history endpoint, last N days per station.
    AUT-2381: every row carries ``best_source`` and ``source_score`` so the
    frontend can badge the day's reading (trusted / government / chain).

    Returns one row per (fuel_type, source, day) — newest first. Rows without
    arbitration metadata (legacy rows from before AUT-2381) still come back;
    the UI treats missing fields as "uncertified".
    """
    _set_attribution(response)
    station = await db.get(FuelStation, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = (
        select(FuelPrice)
        .where(FuelPrice.station_id == station_id, FuelPrice.effective_at >= since)
        .order_by(FuelPrice.effective_at.desc(), FuelPrice.fuel_type, FuelPrice.source)
    )
    if fuel_type:
        q = q.where(FuelPrice.fuel_type == fuel_type)
    rows = list((await db.scalars(q)).all())
    return [FuelPriceHistoryOut.model_validate(r) for r in rows]
