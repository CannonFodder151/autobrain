"""Deterministic GPS sample cleaning utilities (AUT-395).

Shared by schemas and service layers so GPS sample normalization lives in one
place and does not create a dependency from schemas into the ``services``
package. Accepts dicts or objects exposing ``t``/``lat``/``lon`` (pydantic
already coerced the payload by the time the schema validator runs)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class _Sample(BaseModel):
    """Normalized GPS sample shape — one fix on a trip route."""
    t: int
    lat: float
    lon: float


# Server-side cap on stored samples per trip, mirroring the client's
# `maxGpsSamples` (2400) with headroom for longer trips (AUT-852, AUT-786).
MAX_GPS_SAMPLES = 5000


def clean_samples(samples: list | None) -> list[_Sample] | None:
    """Drop invalid ``0,0`` (no-fix) and out-of-range samples, deterministically.

    Keeps the same list/None shape as the input so Create/Update payloads round
    trip without surprises. Accepts dicts or objects exposing ``t``/``lat``/``lon``
    (pydantic already coerced the payload by the time the schema validator runs).

    Returns at most ``MAX_GPS_SAMPLES`` samples, keeping the earliest fixes, so
    per-trip payload size stays bounded even if a client sends more.
    """
    if samples is None:
        return None
    cleaned: list[_Sample] = []
    for s in samples:
        if isinstance(s, dict):
            t, lat, lon = s.get("t"), s.get("lat"), s.get("lon")
        else:
            t = getattr(s, "t", None)
            lat = getattr(s, "lat", None)
            lon = getattr(s, "lon", None)
        if not isinstance(t, (int, float)) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        t = int(t)
        lat = float(lat)
        lon = float(lon)
        if lat == 0 and lon == 0:
            continue  # no fix
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue
        cleaned.append(_Sample(t=t, lat=round(lat, 7), lon=round(lon, 7)))
    # Drop GPS jitter: consecutive identical fixes add no route information.
    deduped: list[_Sample] = []
    for s in cleaned:
        if not deduped or (s.lat, s.lon) != (deduped[-1].lat, deduped[-1].lon):
            deduped.append(s)
    # Cap payload size: keep the earliest fixes past the cap (AUT-852).
    return deduped[:MAX_GPS_SAMPLES]