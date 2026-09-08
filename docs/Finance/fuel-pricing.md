# 7-Eleven Fuel Prices (projectzerothree.info)

Accurate 7-Eleven fuel prices for auto-filling a fill-up, sourced from the
public, keyless, server-cached snapshot at <https://projectzerothree.info>.

**Design principle: deterministic, zero AI.** There is nothing to guess about a
published price list, so this integration is a pure fetch + parse (Phase 1c:
deterministic path first, AI only where it earns its cost). No 9Router spend,
no API key.

## Endpoint

`GET /api/v1/vehicles/{vehicle_id}/fuel/prices/7eleven`

Two mutually exclusive modes:

| Param | Mode | Meaning |
|-------|------|---------|
| `region` + `fuel_type` | cheapest | Top-3 prices (rank 1/2/3) for a state/region. `region` ∈ `All, VIC, NSW, QLD, WA, ACT` (default `All`). `fuel_type` ∈ `E10, U91, U95, U98, Diesel, LPG` (default `U91`). |
| `lat` + `lng` + `fuel_type` | nearest | Closest stores selling `fuel_type`, by great-circle distance. `max_results` (≤25), `max_km` filters. |

Example:

```bash
curl "$API/v1/vehicles/$VID/fuel/prices/7eleven?region=VIC&fuel_type=U91"
curl "$API/v1/vehicles/$VID/fuel/prices/7eleven?lat=-37.81&lng=144.96&fuel_type=U91&max_km=50"
```

The frontend calls this when a user selects *fuel at 7-Eleven* and pre-fills
`price_per_litre` from the returned `price_cpl` (cents per litre).

## Reliability

- The upstream is a **server-cached** snapshot; the service caches it in-process
  for `SEVEN_ELEVEN_CACHE_TTL_MINUTES` (default 60) and follows redirects.
- On upstream failure the **last good snapshot is served** — the client never
  shows a fabricated number. If there is no cached snapshot, the endpoint returns
  503 so the UI falls back to manual price entry.
- `User-Agent` is set (CloudFlare-friendly). No PII is sent.

## Config

| Env | Default | Notes |
|-----|---------|-------|
| `SEVEN_ELEVEN_API_URL` | `https://projectzerothree.info/api.php?format=json` | Override only for a self-hosted mirror. |
| `SEVEN_ELEVEN_CACHE_TTL_MINUTES` | `60` | Snapshot cache lifetime. |
| `SEVEN_ELEVEN_USER_AGENT` | `AutoBrain/1.0 ...` | Sent on fetch. |

## Code map

- `backend/app/services/fuel_prices.py` — client, parse, haversine, cache.
- `backend/app/schemas/fuel.py` — `FuelPriceQuote`, `SevenElevenPricesOut`.
- `backend/app/api/v1/fuel.py` — `/prices/7eleven` route.
- `backend/tests/test_fuel_prices.py` — offline parse/geo tests (no network).
