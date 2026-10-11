"""Fuel Feeds — public ingest entrypoints."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger

from app.services.fuel_feeds.common import _fetch_json
from app.services.fuel_feeds.wa import _parse_wa_sites, _parse_wa_prices
from app.services.fuel_feeds.nsw import _parse_nsw
from app.services.fuel_feeds.vic import _parse_vic
from app.services.fuel_feeds.qld import _fetch_qld_direct, _parse_qld
from app.services.fuel_feeds.persistence import _ingest, arbitrate_all_recent

logger = get_logger(__name__)


async def ingest_wa_fuelwatch(db: AsyncSession, *, client: Any | None = None) -> dict:
    sites = await _fetch_json(settings.FUEL_WA_SITES_URL, client=client)
    prices = await _fetch_json(settings.FUEL_WA_PRICES_URL, client=client)
    return await _ingest(db, "wa", _parse_wa_sites(sites), _parse_wa_prices(prices))


async def ingest_nsw_fuelcheck(db: AsyncSession, *, client: Any | None = None) -> dict:
    if not settings.FUEL_NSW_API_KEY:
        logger.info("fuel_nsw_skipped_no_key")
        return {"source": "nsw", "stations": 0, "prices": 0, "skipped": "no_api_key"}
    headers = {"apikey": settings.FUEL_NSW_API_KEY, "Authorization": f"apikey {settings.FUEL_NSW_API_KEY}"}
    raw = await _fetch_json(settings.FUEL_NSW_URL, headers=headers, client=client)
    stations, prices = _parse_nsw(raw)
    return await _ingest(db, "nsw", stations, prices)


async def ingest_vic_fuel_saver(db: AsyncSession, *, client: Any | None = None) -> dict:
    """VIC Fuel Saver (Servo Saver) ingest.

    Calls ``FUEL_VIC_URL`` (``https://api.servosaver.com.au/v1/prices``) with
    Bearer auth using ``FUEL_VIC_API_KEY`` / ``FUEL_VIC_API_SECRET``.
    Skipped when either credential is missing or ``FUEL_VIC_ENABLED`` is False.

    AUT-4143: the endpoint is NXDOMAIN — the feed is dead. When enabled but the
    host does not resolve, this raises ``FuelFeedError`` instead of silently
    returning 0 stations, so the 6h beat logs the failure and the operator
    sees it rather than a stale/empty map.
    """
    if not settings.FUEL_VIC_ENABLED:
        logger.info("fuel_vic_skipped_disabled")
        return {"source": "vic", "stations": 0, "prices": 0, "skipped": "disabled"}
    if not settings.FUEL_VIC_API_KEY:
        logger.info("fuel_vic_skipped_no_key")
        return {"source": "vic", "stations": 0, "prices": 0, "skipped": "no_api_key"}
    headers = {"Authorization": f"Bearer {settings.FUEL_VIC_API_KEY}"}
    if settings.FUEL_VIC_API_SECRET:
        headers["X-Secret"] = settings.FUEL_VIC_API_SECRET
    raw = await _fetch_json(settings.FUEL_VIC_URL, headers=headers, client=client)
    stations, prices = _parse_vic(raw)
    return await _ingest(db, "vic", stations, prices)


async def ingest_qld_fuel_prices(db: AsyncSession, *, client: Any | None = None) -> dict:
    """QLD Servo Spy feed.

    Primary path: FuelPricesQLD DirectAPI v1.5 (Bearer subscription token).
    Falls back to the public open-data feed (www.fuelpricesqld.com.au) when
    ``settings.FUEL_QLD_USE_OPEN_FALLBACK`` is true, e.g. during a partial
    DirectAPI outage. Skipped entirely when ``FUEL_QLD_API_KEY`` is empty.
    """
    if not settings.FUEL_QLD_API_KEY:
        logger.info("fuel_qld_skipped_no_key")
        return {"source": "qld", "stations": 0, "prices": 0, "skipped": "no_api_key"}
    try:
        _, _, geo_id, stations, prices = await _fetch_qld_direct(client)
        logger.info("fuel_qld_direct_ok", geo_region_id=geo_id, stations=len(stations), prices=sum(len(v) for v in prices.values()))
        return await _ingest(db, "qld", stations, prices)
    except Exception as exc:  # noqa: BLE001
        if not settings.FUEL_QLD_USE_OPEN_FALLBACK:
            logger.error("fuel_qld_direct_failed", error=str(exc))
            return {"source": "qld", "stations": 0, "prices": 0, "error": str(exc)}
        logger.warning("fuel_qld_direct_failed_fallback_open", error=str(exc))
        raw = await _fetch_json(settings.FUEL_QLD_OPEN_DATA_URL, client=client)
        stations, prices = _parse_qld(raw)
        return await _ingest(db, "qld", stations, prices)


async def ingest_all_fuel(db: AsyncSession) -> dict:
    """Run every enabled feed; never let one feed's failure abort the others.

    AUT-2386: after the per-source ingests, run the arbitration pass so the
    per-day winner table is up to date for the next /history and /stations
    read. Arbitration failures are logged but do not poison the ingest
    summary — a station with no arbitration row simply falls back to the
    "latest row from any source" behaviour on the read path.
    """
    summary: dict[str, Any] = {}
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