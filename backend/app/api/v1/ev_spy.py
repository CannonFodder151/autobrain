"""Electric Spy charging-station API (AUT-2435).

Read-only, deterministic, PREMIUM-GATED — same gate as Servo Spy.
Data comes from Open Charge Map via ``app.services.ev_feeds``.
No 9Router / AI: parsing is rule-based, pricing falls back to None when the
upstream only carries free-text pricing.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.ev_station import ChargingConnector, ChargingStation
from app.models.user import User
from app.schemas.ev_spy import (
    ChargingConnectorOut,
    ChargingStationOut,
    EvAttributionOut,
)
from app.services import ev_feeds

logger = get_logger(__name__)

router = APIRouter(prefix="/ev", tags=["ev"])


async def require_ev_access(user: User = Depends(get_current_user)) -> User:
    """Electric Spy is a paid-tier feature (same gate as Servo Spy, AUT-1813)."""
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Charging station data is a premium feature. Upgrade to enable it.",
        )
    return user


def _set_attribution(response: Response) -> None:
    response.headers[ev_feeds.ATTRIBUTION_HEADER] = "; ".join(ev_feeds.EV_ATTRIBUTION)


@router.get("/types", response_model=list[str])
async def ev_connector_types(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_ev_access),
) -> list[str]:
    """Distinct connector types observed in cached data."""
    _set_attribution(response)
    rows = list((await db.scalars(
        select(distinct(ChargingConnector.connector_type))
        .order_by(ChargingConnector.connector_type)
    )).all())
    return [t for t in rows if t]


@router.get("/stations", response_model=list[ChargingStationOut])
async def ev_stations(
    response: Response,
    lat: float = Query(..., description="Search centre latitude"),
    lon: float = Query(..., description="Search centre longitude"),
    radius_km: float = Query(25, gt=0, le=2000),
    connector_type: str | None = Query(
        default=None, description="Filter to a connector type (CCS2, Type 2, ...)"
    ),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_ev_access),
) -> list[ChargingStationOut]:
    """Charging stations within ``radius_km`` of (lat, lon)."""
    _set_attribution(response)
    stations = list((await db.scalars(select(ChargingStation))).all())
    hits: list[tuple[float, ChargingStation]] = []
    for s in stations:
        if s.lat is None or s.lon is None:
            continue
        d = ev_feeds.haversine_km(lat, lon, s.lat, s.lon)
        if d <= radius_km:
            hits.append((d, s))
    hits.sort(key=lambda x: x[0])
    out: list[ChargingStationOut] = []
    for dist, s in hits[:limit]:
        if connector_type:
            connectors = [
                c for c in s.connectors if c.connector_type == connector_type
            ]
            if not connectors:
                continue
        else:
            connectors = list(s.connectors)
        out.append(
            ChargingStationOut(
                id=s.id,
                network=s.network,
                name=s.name,
                address=s.address,
                lat=s.lat,
                lon=s.lon,
                distance_km=round(dist, 2),
                connectors=[
                    ChargingConnectorOut(
                        connector_type=c.connector_type,
                        max_power_kw=c.max_power_kw,
                        cost_per_kwh=c.cost_per_kwh,
                        status=c.status,
                    )
                    for c in connectors
                ],
            )
        )
    return out


@router.post("/refresh", response_model=int)
async def ev_refresh(
    lat: float = Query(..., description="Search centre latitude"),
    lon: float = Query(..., description="Search centre longitude"),
    radius_km: float = Query(25, gt=0, le=2000),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_ev_access),
) -> int:
    """Force-refresh cached stations from Open Charge Map. Returns rows written."""
    return await ev_feeds.refresh_radius(
        db, lat=lat, lon=lon, radius_km=radius_km, limit=limit
    )


@router.get("/station/{station_id}", response_model=ChargingStationOut)
async def ev_station_detail(
    station_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_ev_access),
) -> ChargingStationOut:
    """Detail view for a single charging station."""
    _set_attribution(response)
    station = await db.get(ChargingStation, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return ChargingStationOut(
        id=station.id,
        network=station.network,
        name=station.name,
        address=station.address,
        lat=station.lat,
        lon=station.lon,
        distance_km=None,
        connectors=[
            ChargingConnectorOut(
                connector_type=c.connector_type,
                max_power_kw=c.max_power_kw,
                cost_per_kwh=c.cost_per_kwh,
                status=c.status,
            )
            for c in station.connectors
        ],
    )


@router.get("/attribution", response_model=EvAttributionOut)
async def ev_attribution(
    response: Response,
    _: User = Depends(require_ev_access),
) -> EvAttributionOut:
    """Open-data attribution for the EV feed."""
    _set_attribution(response)
    return EvAttributionOut(attribution=ev_feeds.EV_ATTRIBUTION, sources=["ocm"])
