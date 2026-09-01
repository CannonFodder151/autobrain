"""Fuel price feeds — deterministic, no AI.

This module hosts two independent, offline-safe price integrations:

* 7-Eleven (projectzerothree.info) — a public, keyless, server-side cached
  JSON snapshot of every 7-Eleven store's best price per fuel type. Pure
  fetch+parse (Phase 1c: deterministic path, zero AI spend).
* NSW Fuel API (Transport for NSW) — AUT-1813. Polls the official NSW feed
  once per day per instance, caches results in ``fuel_prices``, and serves the
  last cached snapshot offline. Deterministic-first: no AI in the path.

Both paths are pure mappings of upstream payloads, so every run behaves the
same. Nothing here guesses a price; on upstream failure we serve the last good
snapshot (or surface a clean error for the caller to fall back on).
"""

from __future__ import annotations

import base64
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.fuel_price import NSWFuelPrice, NSWFuelPricePollState

logger = get_logger(__name__)

FUEL_TYPES = ("E10", "U91", "U95", "U98", "Diesel", "LPG")

# ---------------------------------------------------------------------------
# 7-Eleven (projectzerothree.info)
# ---------------------------------------------------------------------------

# Module-level snapshot cache (process-wide). Single-flight guarded by _fetch_lock.
_cache: dict[str, Any] = {"data": None, "fetched_at": 0.0}
_fetch_lock = None  # lazily created inside async funcs to avoid import-time loop


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Plain spherical-earth formula, good enough for
    "which 7-Eleven is closest" (errors <0.5% at AU distances)."""
    r = 6371.0088
    rad = math.pi / 180
    p1, p2 = lat1 * rad, lat2 * rad
    dphi = (lat2 - lat1) * rad
    dlmb = (lng2 - lng1) * rad
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _normalise_price(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return round(float(raw), 2)
    except (TypeError, ValueError):
        return None


def _region_block(data: dict, region: str) -> dict | None:
    return next((r for r in data.get("regions", []) if r.get("region") == region), None)


def _quote(price: dict, *, rank: int | None = None, distance_km: float | None = None) -> dict:
    return {
        "fuel_type": str(price.get("type", "")),
        "price_cpl": _normalise_price(price.get("price")),
        "station": str(price.get("name", "")),
        "suburb": str(price.get("suburb", "")),
        "state": str(price.get("state", "")),
        "postcode": str(price.get("postcode", "")),
        "lat": _normalise_price(price.get("lat")),
        "lng": _normalise_price(price.get("lng")),
        "rank": rank,
        "distance_km": round(distance_km, 2) if distance_km is not None else None,
    }


async def fetch_7eleven_prices(*, force: bool = False) -> dict:
    """Return the cached (or freshly fetched) projectzerothree snapshot.

    Serves last-good cache on upstream failure; raises RuntimeError only when we
    have never successfully fetched (caller should then fall back to manual entry).
    """
    import asyncio

    global _fetch_lock
    if _fetch_lock is None:
        _fetch_lock = asyncio.Lock()

    fresh = _cache["data"] is not None and (
        _now_ts() - _cache["fetched_at"] < settings.SEVEN_ELEVEN_CACHE_TTL_MINUTES * 60
    )
    if fresh and not force:
        return _cache["data"]

    async with _fetch_lock:
        # Re-check after acquiring the lock (another coroutine may have refreshed).
        if (
            not force
            and _cache["data"] is not None
            and _now_ts() - _cache["fetched_at"] < settings.SEVEN_ELEVEN_CACHE_TTL_MINUTES * 60
        ):
            return _cache["data"]
        try:
            async with httpx.AsyncClient(
                timeout=30, follow_redirects=True, headers={"User-Agent": settings.SEVEN_ELEVEN_USER_AGENT}
            ) as client:
                resp = await client.get(settings.SEVEN_ELEVEN_API_URL)
                resp.raise_for_status()
                data = resp.json()
            if not isinstance(data, dict) or "regions" not in data:
                raise ValueError("unexpected 7-Eleven payload shape")
            _cache["data"] = data
            _cache["fetched_at"] = _now_ts()
            logger.info("seven_eleven_prices_fetched", updated=data.get("updated"))
            return data
        except Exception as exc:
            if _cache["data"] is not None:
                logger.warning("seven_eleven_fetch_failed_serving_cache", error=str(exc))
                return _cache["data"]
            logger.error("seven_eleven_fetch_failed", error=str(exc))
            raise RuntimeError("7-Eleven fuel prices unavailable and no cached snapshot") from exc


async def cheapest_7eleven(region: str = "All", fuel_type: str = "U91") -> list[dict]:
    """Up to 3 cheapest 7-Eleven prices (rank 1/2/3) for a region + fuel type."""
    if fuel_type not in FUEL_TYPES:
        raise ValueError(f"unknown fuel type {fuel_type!r}; expected one of {FUEL_TYPES}")
    region = region.upper()
    data = await fetch_7eleven_prices()
    out: list[dict] = []
    for rank, suffix in ((1, ""), (2, "-2"), (3, "-3")):
        block = _region_block(data, region + suffix)
        if not block:
            continue
        p = next((x for x in block.get("prices", []) if x.get("type") == fuel_type), None)
        if p:
            out.append(_quote(p, rank=rank))
    return out


async def nearest_7eleven(
    lat: float, lng: float, fuel_type: str = "U91", max_results: int = 5, max_km: float | None = None
) -> list[dict]:
    """Closest 7-Eleven stores selling `fuel_type`, by great-circle distance."""
    if fuel_type not in FUEL_TYPES:
        raise ValueError(f"unknown fuel type {fuel_type!r}; expected one of {FUEL_TYPES}")
    data = await fetch_7eleven_prices()
    block = _region_block(data, "All") or _region_block(data, "VIC")
    if not block:
        return []
    scored = []
    for p in block.get("prices", []):
        if p.get("type") != fuel_type:
            continue
        try:
            plat, plng = float(p["lat"]), float(p["lng"])
        except (TypeError, ValueError, KeyError):
            continue
        d = _haversine_km(lat, lng, plat, plng)
        if max_km is None or d <= max_km:
            scored.append(_quote(p, distance_km=d))
    scored.sort(key=lambda q: q["distance_km"])
    return scored[:max_results]


# ---------------------------------------------------------------------------
# NSW Fuel API (Transport for NSW) — AUT-1813
# ---------------------------------------------------------------------------

DEFAULT_API_URL = "https://api.transport.nsw.gov.au/v2/fuel/prices"
# A cached snapshot older than this is treated as stale (fallback still serves it).
CACHE_MAX_AGE_HOURS = 48
STATES = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"}


def enabled() -> bool:
    """True only when the feature is switched on AND credentials are present.

    Keeps self-hosted instances from polling an external feed they haven't
    configured; the hosted stack scopes the key to a secret file.
    """
    return bool(
        settings.FUEL_NSW_ENABLED
        and settings.FUEL_NSW_API_KEY
        and settings.FUEL_NSW_API_SECRET
    )


def _basic_auth_header() -> str:
    token = f"{settings.FUEL_NSW_API_KEY}:{settings.FUEL_NSW_API_SECRET}".encode()
    return "Basic " + base64.b64encode(token).decode()


def _normalise(payload: dict) -> list[dict]:
    """Map the NSW feed JSON to flat petrol-price records (pure, no side effects)."""
    stations = {s.get("code"): s for s in payload.get("stations", [])}
    out: list[dict] = []
    for p in payload.get("prices", []):
        st = stations.get(p.get("stationcode"))
        if not st:
            continue
        loc = st.get("location") or {}
        out.append(
            {
                "station_code": p.get("stationcode"),
                "station_name": st.get("name"),
                "brand": st.get("brand"),
                "address": st.get("address"),
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "fuel_type": p.get("fueltype"),
                "price": p.get("price"),
                "currency": "AUD",
                "updated_at": p.get("lastupdated"),
            }
        )
    return out


async def fetch_nsw_prices() -> list[dict]:
    """Fetch + normalise the live NSW price feed. Raises on transport/HTTP error."""
    url = settings.FUEL_NSW_API_URL or DEFAULT_API_URL
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url,
            headers={"Authorization": _basic_auth_header(), "Accept": "application/json"},
        )
        resp.raise_for_status()
        return _normalise(resp.json())


def poll_due(last_poll_at: datetime | None, *, hours: int) -> bool:
    """Pure guard: True when no poll has happened or the last was >= hours ago.

    Nathan's constraint: poll at most once per `hours` (default 24) per instance.
    """
    if last_poll_at is None:
        return True
    return (datetime.now(timezone.utc) - last_poll_at) >= timedelta(hours=hours)


async def should_poll(db: AsyncSession, instance_id: str, state: str = "NSW") -> bool:
    """Enforce at most one successful poll per instance per FUEL_NSW_POLL_HOURS.

    Nathan's constraint: poll once per day per instance to stay inside quota.
    """
    row = await db.scalar(
        select(NSWFuelPricePollState).where(
            NSWFuelPricePollState.instance_id == instance_id,
            NSWFuelPricePollState.state == state,
        )
    )
    return poll_due(row.last_poll_at if row else None, hours=settings.FUEL_NSW_POLL_HOURS)


async def store_nsw_prices(db: AsyncSession, records: list[dict], state: str = "NSW") -> int:
    """Upsert one row per (state, station_code, fuel_type). Returns row count."""
    fetched_at = datetime.now(timezone.utc)
    for r in records:
        fuel_type = r.get("fuel_type")
        station_code = r.get("station_code")
        if not fuel_type or not station_code:
            continue
        existing = await db.scalar(
            select(NSWFuelPrice).where(
                NSWFuelPrice.state == state,
                NSWFuelPrice.station_code == station_code,
                NSWFuelPrice.fuel_type == fuel_type,
            )
        )
        if existing:
            existing.station_name = r.get("station_name")
            existing.brand = r.get("brand")
            existing.address = r.get("address")
            existing.latitude = r.get("latitude")
            existing.longitude = r.get("longitude")
            existing.price = r.get("price")
            existing.currency = r.get("currency", "AUD")
            existing.updated_at = r.get("updated_at")
            existing.fetched_at = fetched_at
        else:
            db.add(
                NSWFuelPrice(
                    state=state,
                    station_code=station_code,
                    station_name=r.get("station_name"),
                    brand=r.get("brand"),
                    address=r.get("address"),
                    latitude=r.get("latitude"),
                    longitude=r.get("longitude"),
                    fuel_type=fuel_type,
                    price=r.get("price"),
                    currency=r.get("currency", "AUD"),
                    updated_at=r.get("updated_at"),
                )
            )
    await db.commit()
    return len(records)


async def mark_polled(db: AsyncSession, instance_id: str, state: str = "NSW") -> None:
    row = await db.scalar(
        select(NSWFuelPricePollState).where(
            NSWFuelPricePollState.instance_id == instance_id,
            NSWFuelPricePollState.state == state,
        )
    )
    if not row:
        row = NSWFuelPricePollState(instance_id=instance_id, state=state)
        db.add(row)
    row.last_poll_at = datetime.now(timezone.utc)
    await db.commit()


async def get_cached_prices(db: AsyncSession, state: str, max_age_hours: int = CACHE_MAX_AGE_HOURS) -> list[NSWFuelPrice]:
    """Return the latest cached snapshot for a state (offline-safe read path)."""
    return list(
        (await db.scalars(select(NSWFuelPrice).where(NSWFuelPrice.state == state))).all()
    )
