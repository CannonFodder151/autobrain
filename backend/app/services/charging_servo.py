"""Electric Spy charging-price API helpers (AUT-412).

Pure helpers for the Electric Spy charging-price API. Deterministic, no AI.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.charging_station import ChargingPrice, ChargingStation
    from app.schemas.charging import ChargingPriceOut, ChargingStationOut
    from app.services.ev_stats import VehicleEVStats  # hypothetical future type


def annotate_price(
    price_per_kwh: float,
    *,
    avg_wh_per_km: float | None,
) -> float | None:
    """Per-station cost annotation for one charging price against a vehicle's stats.

    Inputs:
      price_per_kwh      station price in cents per kWh
      avg_wh_per_km      vehicle's mean Wh/km efficiency across its charging sessions,
                         or None if unknown

    Outputs:
      cost_per_km     $/km = avg_wh_per_km * price_per_kwh / 100000
                           (avg Wh/km * cents/kWh * 1 kWh / 1000 Wh = cents/km; /100 -> $/km)
    """
    if avg_wh_per_km is None or avg_wh_per_km <= 0:
        return None
    return round(avg_wh_per_km * price_per_kwh / 100000, 4)


def annotate_station(
    station: "ChargingStation",
    prices: list["ChargingPrice"],
    dist: float | None,
    *,
    avg_wh_per_km: float | None = None,
) -> "ChargingStationOut":
    """Build a ChargingStationOut with per-price cost annotations.

    Pure: no DB, no AI.
    """
    from app.schemas.charging import ChargingPriceOut, ChargingStationOut
    from app.services.charging_feeds import BRAND_LOGOS

    out_prices: list[ChargingPriceOut] = []
    for p in prices:
        cost_per_km = annotate_price(p.price_per_kwh, avg_wh_per_km=avg_wh_per_km)
        out_prices.append(
            ChargingPriceOut(
                connector_type=p.connector_type,
                price_per_kwh=p.price_per_kwh,
                effective_at=p.effective_at,
                cost_per_km=cost_per_km,
                source=p.source_id,
                arbitration_score=p.arbitration_score,
            )
        )
    return ChargingStationOut(
        id=station.id,
        source=station.source,
        brand=station.brand,
        name=station.name,
        address=station.address,
        lat=station.lat,
        lon=station.lon,
        connector_types=station.connector_types,
        max_power_kw=station.max_power_kw,
        logo=BRAND_LOGOS.get((station.brand or "").lower()),
        distance_km=round(dist, 2) if dist is not None else None,
        prices=out_prices,
    )


async def _latest_price_arbitrated(
    db,
    station_id: str,
    connector_type: str,
    *,
    today: datetime,
):
    """Latest price for a (station, connector_type) using the arbitration winner."""
    from app.models.charging_station import ChargingPriceArbitration, ChargingPrice
    from sqlalchemy import select

    arb = await db.scalar(
        select(ChargingPriceArbitration).where(
            ChargingPriceArbitration.station_id == station_id,
            ChargingPriceArbitration.connector_type == connector_type,
            ChargingPriceArbitration.day == today,
        )
    )
    if arb is not None:
        synthetic = ChargingPrice(
            id=arb.id,
            station_id=station_id,
            connector_type=connector_type,
            price_per_kwh=arb.price_per_kwh,
            effective_at=arb.day,
            source_id=arb.source_id,
            arbitration_score=arb.arbitration_score,
        )
        return synthetic
    return await _latest_price(db, station_id, connector_type)


async def _latest_price(db, station_id: str, connector_type: str):
    from app.models.charging_station import ChargingPrice
    from sqlalchemy import select
    return (await db.scalars(
        select(ChargingPrice)
        .where(ChargingPrice.station_id == station_id, ChargingPrice.connector_type == connector_type)
        .order_by(ChargingPrice.effective_at.desc())
    )).first()


# --- Watchlist price comparison (AUT-731) ------------------------------------

def should_alert_charging_price(
    current_price_cpkwh: float | None,
    target_price_cpkwh: float | None,
) -> tuple[bool, str]:
    """Decide whether a watchlist entry should fire an alert.

    Pure logic, no DB / no AI. Returns ``(should_alert, reason)``.

    Rules:
      * No current price or no target  →  no alert, reason "no_data"
      * current <= target               →  alert,   reason "threshold_met"
      * current  > target               →  no alert, reason "above_target"

    ``current_price_cpkwh`` is the latest arbitrated price in cents/kWh.
    ``target_price_cpkwh`` is the user's target (also cents/kWh, may be None
    if the user just wants a favourite without a price trigger).
    """
    if current_price_cpkwh is None or target_price_cpkwh is None:
        return (False, "no_data")
    if current_price_cpkwh <= target_price_cpkwh:
        return (True, "threshold_met")
    return (False, "above_target")