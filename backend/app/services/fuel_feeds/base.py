"""Shared utilities for the Servo Spy fuel-price pipeline (AUT-1817).

Constants, type helpers, and the network boundary live here so each state
provider module stays focused on its own feed shape.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_FUEL_TYPES = ["E10", "91", "95", "98", "Diesel", "LPG"]

PRICE_HISTORY_DAYS = 30

BRAND_LOGOS: dict[str, str] = {}

_FUEL_TYPE_MAP: dict[str, str] = {
    "ulp": "91", "unleaded": "91", "unleaded 91": "91", "91": "91", "u91": "91",
    "pulp": "95", "premium unleaded": "95", "premium unleaded 95": "95", "95": "95", "u95": "95",
    "pulp98": "98", "premium unleaded 98": "98", "98": "98", "u98": "98",
    "e10": "E10", "ethanol": "E10",
    "diesel": "Diesel", "premium diesel": "Diesel", "diesel premium": "Diesel",
    "lpg": "LPG",
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


def _normalise_fuel_type(raw: Any) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if key in _FUEL_TYPE_MAP:
        return _FUEL_TYPE_MAP[key]
    up = str(raw).strip()
    if up in DEFAULT_FUEL_TYPES:
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


async def _fetch_json(
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    if client is not None:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": settings.FUEL_INGEST_USER_AGENT}) as c:
        resp = await c.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
