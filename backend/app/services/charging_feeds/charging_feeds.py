"""Electric Spy charging-station price pipeline (AUT-412) — deterministic, no AI.

Ingests public open-data feeds into ``charging_stations`` / ``charging_prices``:

  * WA: ChargeUp WA / WA government EV charging data
  * QLD: QLD Government EV charging station data
  * NSW: NSW Transport EV charging data (future)

Design: pure fetch + parse + upsert. Nothing is guessed, so the whole pipeline
is deterministic and costs zero 9Router spend. Radius queries use great-circle
distance in Python rather than PostGIS.

ponytail: WA + QLD shapes are pinned to documented schemas; VIC/SA/TAS/NT
are intentionally out of MVP — they need a paid aggregator, wired later as a
premium enhancement.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.charging_station import (
    ChargingPrice,
    ChargingPriceArbitration,
    ChargingStation,
)
from app.services.charging_source_arbitration import (
    RawSourceObservation,
    arbitrate,
    source_authority,
)

logger = get_logger(__name__)

DEFAULT_CONNECTOR_TYPES = ["CCS2", "CHAdeMO", "Type2"]

# 30-day rolling window for the /history endpoint.
PRICE_HISTORY_DAYS = 30

# Canonical connector type map. Keys are lowercased raw labels seen across feeds.
_CONNECTOR_TYPE_MAP: dict[str, str] = {
    "ccs": "CCS2",
    "ccs2": "CCS2",
    "ccs combo 2": "CCS2",
    "chademo": "CHAdeMO",
    "chade mo": "CHAdeMO",
    "type 2": "Type2",
    "type2": "Type2",
    "mennekes": "Type2",
    "j1772": "J1772",
}

# Best-effort brand -> logo (frontend still maps by brand; null when unknown).
BRAND_LOGOS: dict[str, str] = {
    "chargefox": "https://cdn.autobrainservice.app/brands/chargefox.png",
    "evie": "https://cdn.autobrainservice.app/brands/evie.png",
    "bp pulse": "https://cdn.autobrainservice.app/brands/bp_pulse.png",
    "bp": "https://cdn.autobrainservice.app/brands/bp_pulse.png",
    "ampol": "https://cdn.autobrainservice.app/brands/ampcharge.png",
    "ampcharge": "https://cdn.autobrainservice.app/brands/ampcharge.png",
    "jolt": "https://cdn.autobrainservice.app/brands/jolt.png",
    "tesla": "https://cdn.autobrainservice.app/brands/tesla.png",
    "nrma": "https://cdn.autobrainservice.app/brands/nrma.png",
    "r_ac": "https://cdn.autobrainservice.app/brands/rac.png",
    "rac": "https://cdn.autobrainservice.app/brands/rac.png",
    "synergy": "https://cdn.autobrainservice.app/brands/synergy.png",
    "western power": "https://cdn.autobrainservice.app/brands/western_power.png",
    "chargeup": "https://cdn.autobrainservice.app/brands/chargeup.png",
    "qld transport": "https://cdn.autobrainservice.app/brands/qld_transport.png",
    "nrma energy": "https://cdn.autobrainservice.app/brands/nrma.png",
}

def _now() -> datetime:
    return datetime.now(timezone.utc)

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Spherical-earth, <0.5% error at AU distances."""
    r = 6371.0088
    rad = math.pi / 180
    p1, p2 = lat1 * rad, lat2 * rad
    dphi = (lat2 - lat1) * rad
    dlmb = (lng2 - lng1) * rad
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def _normalise_connector_type(raw: Any) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if key in _CONNECTOR_TYPE_MAP:
        return _CONNECTOR_TYPE_MAP[key]
    up = str(raw).strip()
    if up in DEFAULT_CONNECTOR_TYPES:
        return up
    return None

def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    digits = "".join(ch for ch in str(raw) if ch.isdigit() or ch in ".-")
    try:
        return float(digits) if digits not in ("", "-", ".") else None
    except ValueError:
        return None

def _to_dt(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, timezone.utc)
    if isinstance(raw, str) and raw:
        s = raw.replace("Z", "+00:00")
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                d = datetime.strptime(s[:26], fmt)
                return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
            except ValueError:
                continue
    return _now()

def _first(d: dict, aliases: list[str]) -> Any:
    for a in aliases:
        v = d.get(a)
        if v not in (None, "", []):
            return v
    return None


# --------------------------------------------------------------------------- #
# WA ChargeUp WA / Government EV data
# --------------------------------------------------------------------------- #

def _parse_wa_sites(raw: Any) -> list[dict]:
    """Parse WA charging station sites.

    Expected format (ChargeUp WA / WA gov open data):
    - SiteId, Brand, Name, Address, Latitude, Longitude, ConnectorTypes, MaxPowerKW
    """
    rows = raw if isinstance(raw, list) else []
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["SiteId", "site_id", "id"])
        if sid is None:
            continue
        out.append({
            "source": "wa",
            "source_id": str(sid),
            "brand": (_first(r, ["Brand", "brand", "Operator", "operator"]) or None),
            "name": str(_first(r, ["Name", "name", "StationName", "station_name"]) or ""),
            "address": str(_first(r, ["Address", "address", "Location", "location"]) or ""),
            "lat": _to_float(_first(r, ["Latitude", "latitude", "lat"])),
            "lon": _to_float(_first(r, ["Longitude", "longitude", "lng", "lon"])),
            "connector_types": (_first(r, ["ConnectorTypes", "connector_types", "Connectors", "connectors"]) or None),
            "max_power_kw": _to_float(_first(r, ["MaxPowerKW", "max_power_kw", "PowerKW", "power_kw"])),
        })
    return out

def _parse_wa_prices(raw: Any) -> dict[str, list[tuple[str, float, datetime]]]:
    """Map WA SiteId -> list of (connector_type, price_per_kwh_cents, effective_at).

    Expected format:
    - SiteId, ConnectorType, PricePerKWh (cents), PriceUpdatedDate
    """
    rows = raw if isinstance(raw, list) else []
    out: dict[str, list[tuple[str, float, datetime]]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["SiteId", "site_id"])
        if sid is None:
            continue
        ct = _normalise_connector_type(_first(r, ["ConnectorType", "connector_type", "Connector", "connector"]))
        price = _to_float(_first(r, ["PricePerKWh", "price_per_kwh", "Price", "price"]))
        if not ct or price is None:
            continue
        out.setdefault(str(sid), []).append((ct, price, _to_dt(_first(r, ["PriceUpdatedDate", "price_updated_date", "lastupdated", "effective_at"]))))
    return out


# --------------------------------------------------------------------------- #
# QLD Government EV charging data
# --------------------------------------------------------------------------- #

def _parse_qld(raw: Any) -> tuple[list[dict], dict[str, list[tuple[str, float, datetime]]]]:
    """Parse QLD government EV charging station data.

    Expected format (QLD open data portal):
    - SiteCode, Brand, Name, Address, Latitude, Longitude, ConnectorTypes, MaxPowerKW
    - Price rows: SiteCode, ConnectorType, PricePerKWh, LastUpdated
    """
    # QLD data may come as a single object with "sites" and "prices" keys,
    # or as separate arrays. Handle both.
    sites_raw = []
    prices_raw = []

    if isinstance(raw, dict):
        sites_raw = raw.get("sites", raw.get("stations", []))
        prices_raw = raw.get("prices", raw.get("price_data", []))
    elif isinstance(raw, list):
        # Heuristic: if objects have 'connector_type' they're prices, else sites
        for item in raw:
            if isinstance(item, dict):
                if "connector_type" in item or "ConnectorType" in item:
                    prices_raw.append(item)
                else:
                    sites_raw.append(item)

    stations: list[dict] = []
    prices: dict[str, list[tuple[str, float, datetime]]] = {}

    for r in sites_raw:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["SiteCode", "site_code", "StationCode", "station_code", "id"])
        if sid is None:
            continue
        sid = str(sid)
        stations.append({
            "source": "qld",
            "source_id": sid,
            "brand": (_first(r, ["Brand", "brand", "Operator", "operator"]) or None),
            "name": str(_first(r, ["Name", "name", "StationName", "station_name"]) or ""),
            "address": str(_first(r, ["Address", "address", "Location", "location"]) or ""),
            "lat": _to_float(_first(r, ["Latitude", "latitude", "lat"])),
            "lon": _to_float(_first(r, ["Longitude", "longitude", "lng", "lon"])),
            "connector_types": (_first(r, ["ConnectorTypes", "connector_types", "Connectors", "connectors"]) or None),
            "max_power_kw": _to_float(_first(r, ["MaxPowerKW", "max_power_kw", "PowerKW", "power_kw"])),
        })

    for r in prices_raw:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["SiteCode", "site_code", "StationCode", "station_code"])
        if sid is None:
            continue
        ct = _normalise_connector_type(_first(r, ["ConnectorType", "connector_type", "Connector", "connector"]))
        price = _to_float(_first(r, ["PricePerKWh", "price_per_kwh", "Price", "price"]))
        if not ct or price is None:
            continue
        prices.setdefault(str(sid), []).append((ct, price, _to_dt(_first(r, ["LastUpdated", "last_updated", "lastupdated", "effective_at"]))))

    return stations, prices


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #

async def _upsert_station(db: AsyncSession, s: dict) -> ChargingStation:
    existing = (await db.scalars(
        select(ChargingStation).where(
            ChargingStation.source == s["source"],
            ChargingStation.source_id == s["source_id"]
        )
    )).first()
    if existing:
        existing.brand = s["brand"]
        existing.name = s["name"]
        existing.address = s["address"]
        existing.lat = s["lat"]
        existing.lon = s["lon"]
        existing.connector_types = s["connector_types"]
        existing.max_power_kw = s["max_power_kw"]
        existing.updated_at = _now()
        return existing
    station = ChargingStation(**s, updated_at=_now())
    db.add(station)
    await db.flush()
    return station

async def _replace_station_prices(
    db: AsyncSession,
    station_id: str,
    prices: list[tuple[str, float, datetime]],
    *,
    source_id: str,
) -> int:
    """Replace this source's price rows for a station with the new snapshot.

    Per arbitration design, we only delete rows from THIS source so that a
    re-ingest does not blow away another source's observation of the same point.
    """
    await db.execute(
        delete(ChargingPrice).where(
            ChargingPrice.station_id == station_id,
            ChargingPrice.source_id == source_id
        )
    )
    for ct, price, eff in prices:
        db.add(
            ChargingPrice(
                station_id=station_id,
                connector_type=ct,
                price_per_kwh=price,
                effective_at=eff,
                source_id=source_id,
            )
        )
    return len(prices)

async def _ingest(db: AsyncSession, source: str, stations: list[dict], prices: dict[str, list]) -> dict:
    count_s, count_p = 0, 0
    for s in stations:
        station = await _upsert_station(db, s)
        ps = prices.get(s["source_id"], [])
        count_p += await _replace_station_prices(db, station.id, ps, source_id=source)
        count_s += 1
    return {"source": source, "stations": count_s, "prices": count_p}


# --------------------------------------------------------------------------- #
# Arbitration pass (mirrors fuel_source_arbitration)
# --------------------------------------------------------------------------- #

def _day_bucket(ts: datetime) -> datetime:
    """Truncate a timestamp to its UTC day (00:00:00 UTC) for arbitration keys."""
    return ts.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

async def arbitrate_station_day(
    db: AsyncSession, station_id: str, connector_type: str, day: datetime
) -> ChargingPriceArbitration | None:
    """Pick the deterministic winner for one (station, connector_type, UTC day)."""
    day_start = day.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    rows = list((await db.scalars(
        select(ChargingPrice).where(
            ChargingPrice.station_id == station_id,
            ChargingPrice.connector_type == connector_type,
            ChargingPrice.effective_at >= day_start,
            ChargingPrice.effective_at < day_end,
            ChargingPrice.source_id.isnot(None),
        )
    )).all())
    if not rows:
        return None

    obs = [
        RawSourceObservation(
            source_id=r.source_id,
            price=r.price_per_kwh,
            authority=source_authority(r.source_id),
            updated_at=r.effective_at,
        )
        for r in rows
        if r.source_id is not None
    ]
    result = arbitrate(obs)

    existing = await db.scalar(
        select(ChargingPriceArbitration).where(
            ChargingPriceArbitration.station_id == station_id,
            ChargingPriceArbitration.connector_type == connector_type,
            ChargingPriceArbitration.day == day_start,
        )
    )
    if existing is None:
        existing = ChargingPriceArbitration(
            station_id=station_id,
            connector_type=connector_type,
            day=day_start,
        )
        db.add(existing)
    existing.source_id = result.winner_source
    existing.price_per_kwh = result.winner_price
    existing.arbitration_score = result.score
    existing.candidate_count = len(result.candidates)
    return existing

async def arbitrate_all_recent(
    db: AsyncSession, *, lookback_days: int = PRICE_HISTORY_DAYS
) -> int:
    """Re-run arbitration across every (station, connector_type, day) in the cache."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    pairs = list((await db.execute(
        select(ChargingPrice.station_id, ChargingPrice.connector_type, ChargingPrice.effective_at)
        .where(ChargingPrice.effective_at >= cutoff, ChargingPrice.source_id.isnot(None))
    )).all())
    if not pairs:
        return 0
    written = 0
    seen: set[tuple[str, str, datetime]] = set()
    for station_id, connector_type, eff in pairs:
        day = _day_bucket(eff)
        key = (station_id, connector_type, day)
        if key in seen:
            continue
        seen.add(key)
        if await arbitrate_station_day(db, station_id, connector_type, day) is not None:
            written += 1
    return written


# --------------------------------------------------------------------------- #
# Network boundary (single point — stubbed in tests)
# --------------------------------------------------------------------------- #

async def _fetch_json(url: str, *, headers: dict | None = None, params: dict | None = None, client: httpx.AsyncClient | None = None) -> Any:
    if client is not None:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": getattr(settings, 'CHARGING_INGEST_USER_AGENT', 'AutoBrain Electric Spy')}) as c:
        resp = await c.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


# --------------------------------------------------------------------------- #
# Public ingest entrypoints
# --------------------------------------------------------------------------- #

async def ingest_wa_charging(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    """WA charging station feed (ChargeUp WA / WA Gov)."""
    if not getattr(settings, "CHARGING_WA_SITES_URL", None):
        logger.info("charging_wa_skipped_no_url")
        return {"source": "wa", "stations": 0, "prices": 0, "skipped": "no_url"}
    try:
        sites = await _fetch_json(settings.CHARGING_WA_SITES_URL, client=client)
        prices = await _fetch_json(settings.CHARGING_WA_PRICES_URL, client=client)
        return await _ingest(db, "wa", _parse_wa_sites(sites), _parse_wa_prices(prices))
    except Exception as exc:  # noqa: BLE001
        logger.error("charging_wa_failed", error=str(exc))
        return {"source": "wa", "stations": 0, "prices": 0, "error": str(exc)}

async def ingest_qld_charging(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    """QLD charging station feed (QLD Gov open data)."""
    if not getattr(settings, "CHARGING_QLD_URL", None):
        logger.info("charging_qld_skipped_no_url")
        return {"source": "qld", "stations": 0, "prices": 0, "skipped": "no_url"}
    try:
        raw = await _fetch_json(settings.CHARGING_QLD_URL, client=client)
        stations, prices = _parse_qld(raw)
        return await _ingest(db, "qld", stations, prices)
    except Exception as exc:  # noqa: BLE001
        logger.error("charging_qld_failed", error=str(exc))
        return {"source": "qld", "stations": 0, "prices": 0, "error": str(exc)}

async def ingest_all_charging(db: AsyncSession) -> dict:
    """Run every enabled charging feed; never let one feed's failure abort the others."""
    summary: dict[str, Any] = {}
    for name, fn in (
        ("wa", ingest_wa_charging),
        ("qld", ingest_qld_charging),
    ):
        try:
            summary[name] = await fn(db)
        except Exception as exc:  # noqa: BLE001
            logger.error("charging_ingest_failed", source=name, error=str(exc))
            summary[name] = {"source": name, "stations": 0, "prices": 0, "error": str(exc)}
    try:
        summary["arbitration"] = {
            "source": "arbitration",
            "rows": await arbitrate_all_recent(db),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("charging_arbitration_failed", error=str(exc))
        summary["arbitration"] = {"source": "arbitration", "rows": 0, "error": str(exc)}
    return summary