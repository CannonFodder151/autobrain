# Servo Spy Fuel Price Map (AUT-1817)

A deterministic, **no-AI** feed of public open-data fuel prices for the Servo
Spy station map. Data is ingested by a Celery beat task
(`ingest_fuel_all`, once daily at 02:00 Australia/Sydney — beat key
`fuel-ingest-all-daily`, AUT-2375) and served through premium-gated read routes
at `/api/fuel/*`. No 9Router spend — nothing is guessed, it's a fetch + parse +
upsert.

## Sources

| Feed | URL | Key | Coverage |
|------|-----|-----|----------|
| WA FuelWatch | `industryprd.fuelwatch.wa.gov.au` | none (public) | WA |
| NSW FuelCheck | `api.transport.nsw.gov.au/v1/fuel` | free key (`FUEL_NSW_API_KEY`) | NSW + ACT |
| VIC Fuel Saver (Servo Saver) | `api.servosaver.com.au/v1/prices` — **dead, NXDOMAIN (AUT-4143)** | approved partner key+secret (`FUEL_VIC_API_KEY`, `FUEL_VIC_API_SECRET`, AUT-1932) | none — no live coverage |
| QLD Fuel Prices | `fuelpricesqld.com.au` | DirectAPI subscription token (`FUEL_QLD_API_KEY`) | QLD |

WA + NSW/ACT + QLD are the live feeds. **VIC is present in the codebase but dead**
— `api.servosaver.com.au` does not resolve (NXDOMAIN, AUT-4143; CHANGELOG
v0.3.285, 2026-09-28). `backend/app/services/fuel_feeds.py:265` documents this and
raises `FuelFeedError` when the feed is enabled and the host fails to resolve, so
the nightly beat logs the failure rather than serving an empty map.
`docker-compose.prod.yml:51` sets `FUEL_VIC_ENABLED: "false"` accordingly.

Both stacks disable it: `docker-compose.prod.yml:51` and
`docker-compose.hosted.yml:192` set `FUEL_VIC_ENABLED: "false"` (hosted fixed in
AUT-4976), so `ingest_fuel_vic` returns early and the nightly beat does not touch
the dead host.

**SA/TAS/NT have no ingester yet** — SA (SAFPIS) and TAS/NT need a paid aggregator
(MotorMouth / Informed Sources); the vendor quotes them a subscription, and this
page does not carry a price figure. AUT-5072 disabled the SA flag in both
compose files: `FUEL_SA_ENABLED: "false"` (the Informed Sources Direct API host
`fppdirectapi.safuelpricinginformation.com.au` is NXDOMAIN and there is no
`ingest_sa_*` function in `backend/app/services/fuel_feeds.py`, so the flag only
ever promised zero stations). `FUEL_SA_API_KEY_FILE` stays mounted and the
arbitration table keeps its `"sa"` authority entry so the feed can be switched
back on when a contracted aggregator exists. Not an MVP blocker.

QLD note: `FUEL_QLD_API_KEY` is the DirectAPI subscription token.
`FUEL_QLD_USE_OPEN_FALLBACK` keeps the open-data site usable during a partial
DirectAPI outage.

## Data model

```
fuel_stations(id, source, source_id, brand, lat, lon, name, address, updated_at)
fuel_prices(station_id, fuel_type, price, effective_at)
```

`source` is one of `wa`, `nsw`, `vic`, `qld`. Stations are upserted on `(source, source_id)` and their price snapshot is refreshed each ingest (latest per
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
| `GET /fuel/stations?lat=&lon=&radius_km=&fuel_type=` | Stations within `radius_km` (1–2000, default 25) of `(lat,lon)`, each carrying its prices. `fuel_type` filters to one canonical type. Also accepts `vehicle_id` (AUT-2053) and `limit` (1–200, default 50). |
| `GET /fuel/station/{id}/prices` | All fuel prices at a station, for the detail sheet. |
| `GET /fuel/stations/{id}/history` | Cached per-day price history from the AUT-2386 arbitration table. |
| `GET /fuel/attribution` | Open-data attribution for the aggregated feeds. |

## Reliability

- Each feed is independent — a single feed's failure is logged and does **not**
  abort the others (`ingest_all_fuel`).
- The Celery worker embeds beat (`-B`); the task is registered in
  `backend/app/workers/celery_app.py` `beat_schedule` as `fuel-ingest-all-daily`
  → `app.workers.tasks.ingest_fuel_all`, `crontab(hour=2, minute=0)` with
  `enable_utc=False` so it is 02:00 **Australia/Sydney**, not 02:00 UTC.
  `ingest_fuel_prices` survives only as a backwards-compat alias.
- After the per-source ingests, `ingest_all_fuel` runs the AUT-2386
  arbitration pass (`arbitrate_all_recent`) so the per-day winner table is
  current for `/fuel/stations` and `/fuel/stations/{id}/history`. A station
  with no arbitration row falls back to the latest row from any source.
- `ingest_nsw_fuelcheck` skips when `FUEL_NSW_API_KEY` is absent (the other
  feeds still run). `FUEL_NSW_ENABLED` gates a *different* path — the daily NSW
  Fuel API poll (`poll_nsw_fuel_prices`, petrol price map), which also requires
  `FUEL_NSW_API_SECRET`.
- VIC is opt-in via `FUEL_VIC_ENABLED` / `FUEL_VIC_API_KEY` and is **disabled on
  both stacks** (`docker-compose.prod.yml:51`, `docker-compose.hosted.yml:192`;
  AUT-4143 / AUT-4976 — endpoint is NXDOMAIN). With the flag off the VIC ingest
  returns early, so no `FuelFeedError` is logged. QLD is skipped when
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
FUEL_VIC_ENABLED=false       # feed is dead: endpoint is NXDOMAIN (AUT-4143)
FUEL_VIC_API_KEY=            # approved Servo Saver partner key (AUT-1932)
FUEL_VIC_API_SECRET=         # sent as the X-Secret header
FUEL_VIC_URL=https://api.servosaver.com.au/v1/prices   # NXDOMAIN (AUT-4143)
FUEL_WA_SITES_URL=https://industryprd.fuelwatch.wa.gov.au/api/sites
FUEL_WA_PRICES_URL=https://industryprd.fuelwatch.wa.gov.au/api/report/weekly-retail-prices
FUEL_QLD_API_KEY=            # QLD DirectAPI subscription token
FUEL_QLD_API_URL=https://fppdirectapi-prod.fuelpricesqld.com.au
FUEL_QLD_OPEN_DATA_URL=https://www.fuelpricesqld.com.au/
FUEL_QLD_USE_OPEN_FALLBACK=false
FUEL_INGEST_USER_AGENT=AutoBrain Servo Spy (+https://autobrainservice.app)
```

Credentials are secrets — they live on the deployment env / secret files, never in
the repo. The hosted per-instance values are recorded in the Outline
`Deployment & Infrastructure` section.

## Finding the code

Use the repo context graph rather than grepping — see the Graft section in the
root `AGENTS.md` (`graft ask "fuel feed ingest cadence"`,
`graft callers ingest_all_fuel`).

## Related Finance Docs

- **[fuel-pricing.md](./fuel-pricing.md)** — 7-Eleven fuel prices (deterministic, no AI)
- **[market-data.md](./market-data.md)** — market data scrapers and caches

## Sanitisation

Public repo mirror. Feed partner keys (`FUEL_NSW_API_KEY`, `FUEL_VIC_API_*`,
`FUEL_QLD_API_KEY`, `FUEL_SA_API_KEY`) are deployment secrets and are never
committed — hosted per-instance values live in the internal Outline
`Deployment & Infrastructure` section. See
[Documentation Policy](../Company/documentation-policy.md).

---

*Last updated: 2026-10-01 | Owner: CFO + Backend | Reviewed by: Documentation Manager (AUT-4397) | Sources: backend/app/services/fuel_feeds.py, backend/app/workers/celery_app.py, docker-compose.hosted.yml | Next review: 2026-11-01*
