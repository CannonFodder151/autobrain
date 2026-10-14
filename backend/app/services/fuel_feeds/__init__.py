"""Servo Spy fuel-price pipeline (AUT-1817) — deterministic, no AI.

Ingests public open-data feeds into ``fuel_stations`` / ``fuel_prices``:

  * WA FuelWatch  : industryprd.fuelwatch.wa.gov.au (public, no key).
  * NSW FuelCheck : api.transport.nsw.gov.au/v1/fuel (free API key).
  * VIC Fuel Saver: api.servosaver.com.au/v1/prices (approved partner API).
  * QLD Fuel Prices: FuelPricesQLD DirectAPI v1.5 (Bearer subscription token;
    AUT-2195). Optional open-data fallback (www.fuelpricesqld.com.au) for one
    cycle behind FUEL_QLD_USE_OPEN_FALLBACK so a partial direct-API outage
    does not break Servo Spy.

Design: pure fetch + parse + upsert. Nothing is guessed, so the whole pipeline
is deterministic and costs zero 9Router spend (Phase 1c: deterministic first).
The only network boundary is ``_fetch_json`` (stubbed in tests). Radius queries
use great-circle distance in Python rather than PostGIS.

ponytail: WA + NSW + QLD direct shapes are pinned to documented schemas; QLD
open-data parser kept behind a flag for one cycle then removed (AUT-2200+).
VIC/SA/TAS/NT are intentionally out of MVP — they need a paid aggregator
(Informed Sources / MotorMouth), wired later as a premium enhancement.
"""

from __future__ import annotations

from app.core.config import settings

from sqlalchemy.ext.asyncio import AsyncSession

from .arbitration import arbitrate_all_recent, arbitrate_station_day
from .base import (
    BRAND_LOGOS,
    DEFAULT_FUEL_TYPES,
    PRICE_HISTORY_DAYS,
    _fetch_json,
    _first,
    _normalise_fuel_type,
    _now,
    _to_dt,
    _to_float,
    haversine_km,
)
from .nsw import _parse_nsw, ingest_nsw_fuelcheck
from .persistence import _ingest, _replace_station_prices, _upsert_station
from .qld import (
    _parse_qld,
    _parse_qld_brands,
    _parse_qld_direct_prices,
    _parse_qld_direct_sites,
    _parse_qld_fuel_types,
    _parse_qld_geo_regions,
    ingest_qld_fuel_prices,
)
from .vic import _parse_vic, ingest_vic_fuel_saver
from .wa import _parse_wa_prices, _parse_wa_sites, ingest_wa_fuelwatch

__all__ = [
    "BRAND_LOGOS",
    "DEFAULT_FUEL_TYPES",
    "PRICE_HISTORY_DAYS",
    "_fetch_json",
    "_first",
    "_ingest",
    "_normalise_fuel_type",
    "_now",
    "_parse_nsw",
    "_parse_qld",
    "_parse_qld_brands",
    "_parse_qld_direct_prices",
    "_parse_qld_direct_sites",
    "_parse_qld_fuel_types",
    "_parse_qld_geo_regions",
    "_parse_vic",
    "_parse_wa_prices",
    "_parse_wa_sites",
    "_replace_station_prices",
    "_to_dt",
    "_to_float",
    "_upsert_station",
    "arbitrate_all_recent",
    "arbitrate_station_day",
    "haversine_km",
    "ingest_all_fuel",
    "ingest_nsw_fuelcheck",
    "ingest_qld_fuel_prices",
    "ingest_vic_fuel_saver",
    "ingest_wa_fuelwatch",
    "settings",
]


async def ingest_all_fuel(db: AsyncSession) -> dict:
    """Run every enabled feed; never let one feed's failure abort the others.

    AUT-2386: after the per-source ingests, run the arbitration pass so the
    per-day winner table is up to date for the next /history and /stations
    read. Arbitration failures are logged but do not poison the ingest
    summary — a station with no arbitration row simply falls back to the
    "latest row from any source" behaviour on the read path.
    """
    from app.core.logging import get_logger

    logger = get_logger(__name__)

    summary: dict = {}
    for name, fn in (
        ("wa", ingest_wa_fuelwatch),
        ("nsw", ingest_nsw_fuelcheck),
        ("vic", ingest_vic_fuel_saver),
        ("qld", ingest_qld_fuel_prices),
    ):
        try:
            summary[name] = await fn(db)
        except Exception as exc:  # noqa: BLE001 — one bad feed must not sink the rest
            logger.error("fuel_ingest_failed", source=name, error=str(exc))
            summary[name] = {"source": name, "stations": 0, "prices": 0, "error": str(exc)}
    try:
        summary["arbitration"] = {
            "source": "arbitration",
            "rows": await arbitrate_all_recent(db),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("fuel_arbitration_failed", error=str(exc))
        summary["arbitration"] = {"source": "arbitration", "rows": 0, "error": str(exc)}
    return summary