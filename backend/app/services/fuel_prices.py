"""7-Eleven fuel prices (projectzerothree.info) — deterministic, no AI.

The upstream is a public, keyless, server-side *cached* JSON snapshot of every
7-Eleven store's best price per fuel type. There is nothing to "guess", so this
is a pure fetch+parse integration (Phase 1c: deterministic path, zero AI spend).

Two query modes:
  * cheapest(region, fuel_type) -> up to 3 best prices for a state/region
    (region "VIC" = cheapest in VIC, "VIC-2"/"VIC-3" = 2nd/3rd cheapest, the API
    ships them as separate region blocks).
  * nearest(lat, lng, fuel_type) -> closest stores by great-circle distance,
    using the "All" region block which holds every store's best price.

The snapshot is fetched with redirects followed and cached in-process for
SEVEN_ELEVEN_CACHE_TTL_MINUTES (the source is itself already a cached copy, so
re-fetching hourly per worker is plenty). On any upstream failure we serve the
last good snapshot if we have one, otherwise surface a clean error so the caller
can fall back to manual price entry rather than inventing a number.

ponytail: in-memory cache is fine because the source is already a shared cached
snapshot and staleness of <1h is acceptable; move to the DB cache pattern
(like market_data) only if cross-replica consistency / request coalescing matters.
"""

import math
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

FUEL_TYPES = ("E10", "U91", "U95", "U98", "Diesel", "LPG")

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
