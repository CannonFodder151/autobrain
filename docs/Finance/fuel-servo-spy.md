# Servo Spy Fuel Price Map (AUT-1817)

A deterministic, **no-AI** feed of public open-data fuel prices for the Servo
Spy station map. Data is ingested on a Celery beat schedule
(`ingest_fuel_prices`, every 6h) and served through premium-gated read routes at
`/api/fuel/*`. No 9Router spend — nothing is guessed, it's a fetch + parse + upsert.

## Sources

| Feed | URL | Key | Coverage |
|------|-----|-----|----------|
| WA FuelWatch | `industryprd.fuelwatch.wa.gov.au` | none (public) | WA |
| NSW FuelCheck | `api.transport.nsw.gov.au/v1/fuel` | free key (`FUEL_NSW_API_KEY`) | NSW + ACT |
| VIC Fuel Saver (Servo Saver) | `api.servosaver.com.au/v1/prices` | approved partner key+secret (`FUEL_VIC_API_KEY`, `FUEL_VIC_API_SECRET`, AUT-1932) | VIC |
| QLD Fuel Prices | `fuelpricesqld.com.au` | DirectAPI subscription token (`FUEL_QLD_API_KEY`) | QLD |

WA + NSW/ACT + VIC + QLD cover ~80% of the Australian population.
**SA/TAS/NT have no feed** — SA (SAFPIS) and TAS/NT need a paid aggregator
(MotorMouth / Informed Sources, ~$2–3k/mo). SA has a reserved key in the
compose config (`FUEL_SA_*`, AUT-2610) but no backend ingester yet, so those env
vars are inert until the feed lands. Not an MVP blocker.

QLD note: `FUEL_QLD_API_KEY` is the DirectAPI subscription token.
`FUEL_QLD_USE_OPEN_FALLBACK` keeps the open-data site usable during a partial
DirectAPI outage.

## Data model

```
fuel_stations(id, source, source_id, brand, lat, lon, name, address, updated_at)
fuel_prices(station_id, fuel_type, price, effective_at)
```

`source` is one of `wa`, `nsw`, `vic`, `qld`. Stations are upserted on `(source,
`source_id)` and their price snapshot is refreshed each ingest (latest per
`fuel_type` is served). Radius queries use a **great-circle distance in Python**
— no PostGIS column is required for MVP.

## Fuel type normalisation

Every feed ships fuel codes/labels in its own dialect. The pipeline maps them to
a canonical catalogue for the vehicle fuel dropdown:

```
91  95  98  E10  Diesel  LPG
```

| Raw (WA) | Raw (NSW) | Canonical |
|----------|-----------|-----------|
| ULP / Unleaded | Unleaded 91 | 91 |
| PULP | Premium Unleaded 95 | 95 |
| PULP98 | Premium Unleaded 98 | 98 |
| E10 | E10 | E10 |
| Diesel | Diesel | Diesel |
| LPG | LPG | LPG |

Unknown/raw codes are dropped (never fabricated).

## API

`GET /api/fuel/*` — every route depends on `require_fuel_access`
(`Depends(get_current_user)` then `403` for `free_account` with
`"Fuel prices are a premium feature. Upgrade to enable it."`). Free accounts
receive no station or price data. Each response includes the
`X-Fuel-Data-Attribution` header.

| Route | Description |
|-------|-------------|
| `GET /fuel/types` | Distinct fuel types observed across feeds (falls back to the canonical catalogue if no data yet) — drives the vehicle fuel dropdown. |
| `GET /fuel/brands` | Distinct brands (for station logos). |
| `GET /fuel/stations?lat=&lon=&radiusKm=&fuelType=` | Stations within `radiusKm` (1–2000, default 25) of `(lat,lon)`, each carrying its prices. `fuelType` filters to one canonical type. |
| `GET /fuel/station/{id}/prices` | All fuel prices at a station, for the detail sheet. |
| `GET /fuel/attribution` | Open-data attribution for the aggregated feeds. |

## Reliability

- Each feed is independent — a single feed's failure is logged and does **not**
  abort the others (`ingest_all_fuel`).
- The Celery worker embeds beat (`-B`); the task is registered in
  `celery_app.conf.beat_schedule` as `ingest-fuel-prices`.
- NSW FuelCheck is opt-in via `FUEL_NSW_ENABLED` / `FUEL_NSW_API_KEY`; when the key
  is absent the NSW step is skipped (the other feeds still run).
- VIC is opt-in via `FUEL_VIC_ENABLED` / `FUEL_VIC_API_KEY` and is **disabled on every
  deployed stack** (AUT-4976): `api.servosaver.com.au` is NXDOMAIN (AUT-4143), so the
  step would raise `FuelFeedError` on every beat. Re-enable once a paid VIC aggregator
  is available. QLD is skipped when
  `FUEL_QLD_API_KEY` is absent.
- On managed tiers every feed credential arrives as a `*_FILE` secret
  (`FUEL_NSW_API_KEY_FILE`, `FUEL_VIC_API_KEY_FILE`, …); Pydantic settings load
  the plain name at startup. See `scripts/seed-secrets.sh`.

## Configuration (.env / deployment secrets)

```
FUEL_NSW_API_KEY=            # free key from api.nsw.gov.au → api.transport.nsw.gov.au
FUEL_NSW_API_SECRET=         # (kept for parity; NSW uses the apikey header)
FUEL_NSW_ENABLED=false
FUEL_NSW_URL=https://api.transport.nsw.gov.au/v1/fuel
FUEL_VIC_ENABLED=false
FUEL_VIC_API_KEY=            # approved Servo Saver partner key (AUT-1932)
FUEL_VIC_API_SECRET=         # sent as the X-Secret header
FUEL_VIC_URL=https://api.servosaver.com.au/v1/prices
FUEL_WA_SITES_URL=https://industryprd.fuelwatch.wa.gov.au/api/sites
FUEL_WA_PRICES_URL=https://industryprd.fuelwatch.wa.gov.au/api/report/weekly-retail-prices
FUEL_QLD_API_KEY=            # QLD DirectAPI subscription token
FUEL_QLD_API_URL=https://www.fuelpricesqld.com.au/
FUEL_QLD_USE_OPEN_FALLBACK=false
FUEL_INGEST_USER_AGENT=AutoBrain Servo Spy (+https://autobrainservice.app)
```

Credentials are secrets — they live on the deployment env / secret files, never in
the repo. The hosted per-instance values are recorded in the Outline
`Deployment & Infrastructure` section.

## Related Finance Docs

- **[fuel-pricing.md](./fuel-pricing.md)** — 7-Eleven fuel prices (deterministic, no AI)
- **[market-data.md](./market-data.md)** — market data scrapers and caches
