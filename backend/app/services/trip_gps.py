"""Deterministic GPS ingestion for logbook trip routes (AUT-395).

The trip-logging board (NEO-8M GPS — see AUT-386 + the autobrain-obd2-diy repo)
emits CSV rows of `epoch,...,lat,lon` where lat/lon are raw degrees x10^7 and
`0,0` means "no fix". This module accepts that schema directly and normalises it
into the stored sample shape `[{"t": epoch, "lat": deg, "lon": deg}, ...]`.

Pure, raw-coordinates-only — no AI involved.

Uses the shared cleaning logic from ``core.gps`` so schemas and services share
the same normalization.
"""

from app.core.gps import MAX_GPS_SAMPLES, clean_samples


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
