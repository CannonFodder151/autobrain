"""Electric Spy charging-price API (AUT-412).

Read-only, deterministic, PREMIUM-GATED. Every route depends on
``require_charging_access`` (free/demo accounts get 403). No 9Router/AI — the
data is the normalised ``charging_stations`` / ``charging_prices`` tables
populated by the Celery ingest task.

Open-data attribution is attached to every response via the
``X-Charging-Data-Attribution`` header and the ``/attribution`` endpoint.

Arbitration: ``/stations/{id}/history`` joins ``charging_prices`` to
``charging_price_arbitrations`` so each point shows the chosen source + score
plus every raw source observation for that day, and the /stations live list
picks the arbitration winner per (station, connector_type, day) when one
exists so the live list and the history chart tell the same story.
"""

from datetime import datetime, timedelta, timezone
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.charging_station import (
    ChargingPrice,
    ChargingPriceArbitration,
    ChargingPriceWatchlist,
    ChargingStation,
)
from app.models.user import User
from app.schemas.charging import (
    AttributionOut,
    ChargingBrandOut,
    ChargingHistoryPoint,
    ChargingHistoryRawSource,
    ChargingPriceOut,
    ChargingStationHistoryOut,
    ChargingStationOut,
    ChargingWatchlistIn,
    ChargingWatchlistOut,
)
from app.services import charging_feeds as feeds
from app.services.charging_servo import (
    annotate_station,
    _latest_price_arbitrated,
    _latest_price,
    should_alert_charging_price,
)
from app.services.charging_source_arbitration import source_authority

logger = get_logger(__name__)

router = APIRouter(prefix="/charging", tags=["charging"])

CHARGING_ATTRIBUTION = [
    "ChargeUp WA - Government of Western Australia (CC BY 4.0)",
    "QLD Government EV Charging Data - Queensland Government",
]
ATTRIBUTION_HEADER = "X-Charging-Data-Attribution"

async def require_charging_access(user: User = Depends(get_current_user)) -> User:
    """Electric Spy is a paid-tier feature."""
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Charging prices are a premium feature. Upgrade to enable it.",
        )
    return user

def _set_attribution(response: Response) -> None:
    response.headers[ATTRIBUTION_HEADER] = "; ".join(CHARGING_ATTRIBUTION)

@router.get("/types")
async def charging_types(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_charging_access),
):
    """Catalogue of connector types observed across feeds (data-driven dropdown)."""
    _set_attribution(response)
    rows = list((await db.scalars(
        select(distinct(ChargingPrice.connector_type)).order_by(ChargingPrice.connector_type)
    )).all())
    types = [t for t in rows if t]
    if not types:
        types = list(feeds.DEFAULT_CONNECTOR_TYPES)
    return types

@router.get("/brands", response_model=list[ChargingBrandOut])
async def charging_brands(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_charging_access),
):
    """Brand list for station logos."""
    _set_attribution(response)
    rows = list((await db.scalars(
        select(distinct(ChargingStation.brand))
        .where(ChargingStation.brand.isnot(None))
        .order_by(ChargingStation.brand)
    )).all())
    return [ChargingBrandOut(brand=b, logo=feeds.BRAND_LOGOS.get((b or "").lower())) for b in rows if b]

@router.get("/stations", response_model=list[ChargingStationOut])
async def charging_stations(
    response: Response,
    lat: float = Query(..., description="Search centre latitude"),
    lon: float = Query(..., description="Search centre longitude"),
    radius_km: float = Query(25, gt=0, le=2000, description="Search radius in km"),
    connector_type: str | None = Query(default=None, description="Filter to a connector type (CCS2/CHAdeMO/Type2)"),
    vehicle_id: str | None = Query(
        default=None,
        description="Annotate each price with cost-per-km for this vehicle's efficiency.",
    ),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_charging_access),
):
    """Stations within ``radius_km`` of (lat,lon), each with its prices.

    Radius filter is a great-circle distance in Python (no PostGIS needed for
    MVP). When ``connector_type`` is given, only stations with a price for that
    connector are returned, and each carries just that connector's latest price.

    If ``vehicle_id`` is provided and the user can access that vehicle, each
    price is annotated with the cost-per-km (price × avg Wh/km / 100000)
    derived from the vehicle's own EV stats — fully deterministic, no AI.
    """
    _set_attribution(response)

    # Fetch vehicle EV stats if vehicle_id provided
    avg_wh_per_km = None
    if vehicle_id is not None:
        from app.services.ownership import get_accessible_vehicle
        from app.services.ev_stats import get_vehicle_ev_stats
        try:
            await get_accessible_vehicle(db, vehicle_id, user)
            ev_stats = await get_vehicle_ev_stats(db, vehicle_id)
            avg_wh_per_km = ev_stats.get("avg_efficiency_wh_per_km")
        except HTTPException:
            avg_wh_per_km = None

    stations = list((await db.scalars(select(ChargingStation))).all())
    hits: list[tuple[float, ChargingStation]] = []
    for s in stations:
        if s.lat is None or s.lon is None:
            continue
        d = feeds.haversine_km(lat, lon, s.lat, s.lon)
        if d <= radius_km:
            hits.append((d, s))
    hits.sort(key=lambda x: x[0])

    today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    out: list[ChargingStationOut] = []
    for dist, s in hits[:limit]:
        if connector_type:
            price = await _latest_price_arbitrated(db, s.id, connector_type, today=today_utc)
            if price is None:
                continue
            prices = [price]
        else:
            prices = list((await db.scalars(
                select(ChargingPrice).where(ChargingPrice.station_id == s.id)
                .order_by(ChargingPrice.connector_type, ChargingPrice.effective_at.desc())
            )).all())
        out.append(await annotate_station(s, prices, dist, avg_wh_per_km=avg_wh_per_km))
    return out

@router.get("/station/{station_id}/prices", response_model=ChargingStationOut)
async def station_prices(
    station_id: str,
    response: Response,
    vehicle_id: str | None = Query(
        default=None,
        description="Annotate each price with cost-per-km for this vehicle's efficiency.",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_charging_access),
):
    """All connector prices at a station (detail sheet)."""
    _set_attribution(response)
    station = await db.get(ChargingStation, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    prices = list((await db.scalars(
        select(ChargingPrice).where(ChargingPrice.station_id == station_id)
        .order_by(ChargingPrice.connector_type, ChargingPrice.effective_at.desc())
    )).all())

    avg_wh_per_km = None
    if vehicle_id is not None:
        from app.services.ownership import get_accessible_vehicle
        from app.services.ev_stats import get_vehicle_ev_stats
        try:
            await get_accessible_vehicle(db, vehicle_id, user)
            ev_stats = await get_vehicle_ev_stats(db, vehicle_id)
            avg_wh_per_km = ev_stats.get("avg_efficiency_wh_per_km")
        except HTTPException:
            avg_wh_per_km = None

    return await annotate_station(station, prices, None, avg_wh_per_km=avg_wh_per_km)

@router.get("/attribution", response_model=AttributionOut)
async def charging_attribution(
    response: Response,
    _: User = Depends(require_charging_access),
):
    """Open-data attribution for the aggregated feeds."""
    _set_attribution(response)
    return AttributionOut(attribution=CHARGING_ATTRIBUTION, sources=["wa", "qld"])

@router.get("/stations/{station_id}/history", response_model=ChargingStationHistoryOut)
async def station_history(
    station_id: str,
    response: Response,
    connector_type: str | None = Query(default=None, description="Optional connector filter (CCS2/CHAdeMO/Type2)"),
    days: int = Query(default=feeds.PRICE_HISTORY_DAYS, ge=1, le=feeds.PRICE_HISTORY_DAYS),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_charging_access),
):
    """30-day price history for a single station.

    Reads exclusively from the ``charging_prices`` cache and the
    ``charging_price_arbitrations`` arbitration table — never fans out to the
    upstream charging APIs. The daily Celery beat task is the only thing that
    refreshes these rows.

    Each series point carries the winning ``source`` + ``score`` for the
    (station, connector_type, day) bucket, plus a ``raw_sources`` array of
    every contributing feed so the client can show the user the inputs.
    """
    _set_attribution(response)
    station = await db.get(ChargingStation, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = (
        select(ChargingPrice)
        .where(
            ChargingPrice.station_id == station_id,
            ChargingPrice.effective_at >= cutoff,
        )
        .order_by(ChargingPrice.connector_type, ChargingPrice.effective_at.asc())
    )
    if connector_type:
        q = q.where(ChargingPrice.connector_type == connector_type)
    rows = list((await db.scalars(q)).all())

    arb_q = (
        select(ChargingPriceArbitration)
        .where(
            ChargingPriceArbitration.station_id == station_id,
            ChargingPriceArbitration.day >= cutoff - timedelta(days=1),
        )
        .order_by(ChargingPriceArbitration.connector_type, ChargingPriceArbitration.day.asc())
    )
    if connector_type:
        arb_q = arb_q.where(ChargingPriceArbitration.connector_type == connector_type)
    arb_rows = list((await db.scalars(arb_q)).all())
    arb_by_key: dict[tuple[str, datetime], ChargingPriceArbitration] = {
        (a.connector_type, a.day): a for a in arb_rows
    }

    grouped: dict[tuple[str, datetime], list[ChargingPrice]] = {}
    for p in rows:
        if p.effective_at is None:
            continue
        day = p.effective_at.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        grouped.setdefault((p.connector_type, day), []).append(p)

    series: list[ChargingHistoryPoint] = []
    for (ct, day), day_prices in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        arb = arb_by_key.get((ct, day))
        if arb is not None:
            price = arb.price_per_kwh
            effective_at = day
            source = arb.source_id
            score = arb.arbitration_score
        else:
            latest = max(day_prices, key=lambda p: p.effective_at)
            price = latest.price_per_kwh
            effective_at = latest.effective_at
            source = latest.source_id
            score = latest.arbitration_score
        raw = [
            ChargingHistoryRawSource(
                source=p.source_id or "unknown",
                price_per_kwh=p.price_per_kwh,
                effective_at=p.effective_at,
                score=_candidate_score(p, day_prices, effective_at),
            )
            for p in day_prices
        ]
        series.append(
            ChargingHistoryPoint(
                connector_type=ct,
                price_per_kwh=price,
                effective_at=effective_at,
                source=source,
                score=score,
                raw_sources=raw,
            )
        )
    return ChargingStationHistoryOut(
        station_id=station_id,
        source=station.source,
        connector_type=connector_type,
        days=days,
        series=series,
    )

def _candidate_score(p: ChargingPrice, day_prices: list[ChargingPrice], now: datetime) -> float:
    """Re-derive an approximate score for one raw source on a history point."""
    if not p.source_id:
        return 0.0
    authority = source_authority(p.source_id)
    authority_score = (1 - authority) * feeds.WEIGHT_AUTHORITY
    age_hours = max(0.0, (now - p.effective_at).total_seconds() / 3600.0)
    freshness = 0.0
    if age_hours <= feeds.FRESHNESS_WINDOW_HOURS:
        freshness = feeds.WEIGHT_FRESHNESS * (1.0 - age_hours / feeds.FRESHNESS_WINDOW_HOURS)
    prices = [q.price_per_kwh for q in day_prices if q.price_per_kwh is not None]
    spread = 0.0
    if len(prices) >= 2:
        spread_penalty = abs(p.price_per_kwh - median(prices)) / feeds.SPREAD_THRESHOLD_CPKWH * feeds.WEIGHT_SPREAD
        if (max(prices) - min(prices)) > feeds.SPREAD_THRESHOLD_CPKWH:
            spread = spread_penalty
    return round(authority_score + freshness - spread, 4)


# --- Watchlist (price alerts) ----------------------------------------------

@router.get("/watchlist", response_model=list[ChargingWatchlistOut])
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_charging_access),
) -> list[ChargingWatchlistOut]:
    """The current user's Electric Spy watch list."""
    rows = await db.scalars(
        select(ChargingPriceWatchlist)
        .where(ChargingPriceWatchlist.user_id == user.id)
        .order_by(ChargingPriceWatchlist.created_at.desc())
    )
    return list(rows)


@router.post("/watchlist", response_model=ChargingWatchlistOut, status_code=201)
async def add_watchlist(
    payload: ChargingWatchlistIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_charging_access),
) -> ChargingWatchlistOut:
    """Add a station + connector to the user's Electric Spy watch list."""
    existing = await db.scalar(
        select(ChargingPriceWatchlist).where(
            ChargingPriceWatchlist.user_id == user.id,
            ChargingPriceWatchlist.station_id == payload.station_id,
            ChargingPriceWatchlist.connector_type == payload.connector_type,
        )
    )
    if existing:
        existing.target_price_per_kwh = payload.target_price_per_kwh
        await db.commit()
        await db.refresh(existing)
        return existing

    station = await db.get(ChargingStation, payload.station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    row = ChargingPriceWatchlist(
        user_id=user.id,
        station_id=payload.station_id,
        connector_type=payload.connector_type,
        target_price_per_kwh=payload.target_price_per_kwh,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/watchlist/{watch_id}", status_code=204)
async def remove_watchlist(
    watch_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_charging_access),
) -> None:
    """Remove a favourite from the user's Electric Spy watch list."""
    row = await db.scalar(
        select(ChargingPriceWatchlist).where(
            ChargingPriceWatchlist.id == watch_id,
            ChargingPriceWatchlist.user_id == user.id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    await db.delete(row)
    await db.commit()


# --- Manual price-check + push notification (AUT-731) ----------------------

@router.post("/watchlist/notify", status_code=200)
async def notify_watchlist(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_charging_access),
) -> dict:
    """Check every watched station+connector against its target price and
    push an alert when the price meets or beats the threshold.

    Mirrors the periodic Celery task ``check_charging_price_alerts`` but can
    be triggered on demand by the mobile app (pull-to-refresh for price
    alerts). Dedupes per (user, station, connector_type, day) via the
    notification_deliveries table so the same alert isn't re-sent all day.
    """
    from app.services.notify import deliver_charging_price_alert

    watches = await db.scalars(
        select(ChargingPriceWatchlist).where(
            ChargingPriceWatchlist.user_id == user.id
        ).order_by(ChargingPriceWatchlist.created_at.desc())
    )
    watchlist = list(watches)

    triggered = []
    skipped_no_price = []
    skipped_no_target = []

    from datetime import date

    for w in watchlist:
        price = await _latest_price_arbitrated(
            db, w.station_id, w.connector_type,
            today=datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        current = price.price_per_kwh if price else None

        if current is None:
            skipped_no_price.append(w.station_id)
            continue
        if w.target_price_per_kwh is None:
            skipped_no_target.append(w.station_id)
            continue

        should_alert, reason = should_alert_charging_price(
            current, w.target_price_per_kwh
        )
        if not should_alert:
            continue

        station = await db.get(ChargingStation, w.station_id)
        label = station.name if station else w.station_id
        kind = f"charging_price:{w.station_id}:{w.connector_type}:{date.today().isoformat()}"
        title = f"{label} EV price alert"
        description = (
            f"{label} ({w.connector_type}) is now {current:.1f}¢/kWh — "
            f"at or below your target of {w.target_price_per_kwh:.1f}¢/kWh."
        )
        await deliver_charging_price_alert(db, user.id, kind, title, description)
        triggered.append({
            "station_id": w.station_id,
            "connector_type": w.connector_type,
            "current_price_cpkwh": current,
            "target_price_cpkwh": w.target_price_per_kwh,
        })

    await db.commit()
    return {
        "checked": len(watchlist),
        "triggered": len(triggered),
        "skipped_no_price": len(skipped_no_price),
        "skipped_no_target": len(skipped_no_target),
        "alerts": triggered,
    }