"""Deterministic GPS ingestion for logbook trip routes (AUT-395).

The trip-logging board (NEO-8M GPS — see AUT-386 + the autobrain-obd2-diy repo)
emits CSV rows of `epoch,...,lat,lon` where lat/lon are raw degrees x10^7 and
`0,0` means "no fix". This module accepts that schema directly and normalises it
into the stored sample shape `[{"t": epoch, "lat": deg, "lon": deg}, ...]`.

Pure, raw-coordinates-only — no AI involved.
"""

from pydantic import BaseModel


class _Sample(BaseModel):
    t: int
    lat: float
    lon: float


# Server-side cap on stored samples per trip, mirroring the client's
# `maxGpsSamples` (2400) with headroom for longer trips (AUT-852, AUT-786).
MAX_GPS_SAMPLES = 5000


def clean_samples(samples: list | None) -> list[_Sample] | None:
    """Drop invalid `0,0` (no-fix) and out-of-range samples, deterministically.

    Keeps the same list/None shape as the input so Create/Update payloads round
    trip without surprises. Accepts dicts or objects exposing `t`/`lat`/`lon`
    (pydantic already coerced the payload by the time the schema validator runs).

    Returns at most `MAX_GPS_SAMPLES` samples, keeping the earliest fixes, so
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


def parse_board_csv(text: str) -> list[dict]:
    """Parse a board CSV dump into GPS samples.

    Accepted schema: `epoch,rpm,speed,coolant,throttle,odo_km,ev_mode,lat,lon` or
    `epoch,...,lat,lon` — first field is the epoch seconds, the last two fields
    are raw NEO-8M lat/lon as degrees x10^7 integers. Intermediate EV columns
    (soc_pct, pack_v, pack_a, pack_temp_c, odo_km, ev_mode) are ignored.
    Rows with a `0,0` fix and non-numeric/garbage rows are skipped.

    Returns samples ready to store: `[{"t": int, "lat": float, "lon": float}]`.
    """
    samples: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "epoch", "time")):
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            epoch = int(float(parts[0]))
            raw_lat = float(parts[-2])
            raw_lon = float(parts[-1])
        except ValueError:
            continue
        if raw_lat == 0 and raw_lon == 0:
            continue  # no fix
        lat = raw_lat / 10_000_000.0
        lon = raw_lon / 10_000_000.0
        samples.append({"t": epoch, "lat": round(lat, 7), "lon": round(lon, 7)})
    return [s.model_dump() for s in (clean_samples(samples) or [])]
