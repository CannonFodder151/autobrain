# Market data & stable valuations (AUT-287 / AUT-298)

The resale valuation feeds on live used-vehicle market data — **CarsGuide** and
**CarSales** for cars, **BikeGuide / BikesSales** for motorcycles — so the
estimate matches what buyers are actually paying, and stays *stable* between
runs.

## Why this exists

Before this feature the resale number was the deterministic depreciation model
refined by an **AI-guessed** `used_price`. The guess changed every inference,
so a Toyota Crown could value at $11k then $13k two minutes later (real market
≈ $15k). The fix, per the deterministic-first policy: real listings data is
now the ground truth, cached, and the AI only supplies advice/trend.

## Architecture

```
backend valuation route
  └─ app/services/market_data.py        (provider → cache → fallback)
       ├─ POST {MARKET_DATA_URL}/search  (self-hosted scraper, X-API-Key)
       ├─ market_listing_cache table     (24h TTL, keyed make|model|year)
       └─ fallback (source=fallback, sample_size=0) — pipeline never 404s
  └─ payload["market"]  →  ai resale module
       ├─ sample_size >= 3  → median_price anchors the estimate
       │     value = median × condition × km_mult; deterministic model is a
       │     0.5× sanity floor so a bad median can't collapse the number.
       └─ otherwise → AI used_price path (clamped ±15% as before)
```

The median is **cached for 24h**, so consecutive valuations return identical
market numbers → identical estimates. No more call-to-call wobble.

## Provider protocol (same pattern as rego-lookup)

Self-hosted scraper (e.g. `carguide-api`/`carsales-api`), configured via
`MARKET_DATA_URL` + `MARKET_DATA_API_KEY` in the backend `.env`. It is never
called directly from AutoBrain — the backend POSTs:

```
POST {MARKET_DATA_URL}/search
X-API-Key: <key>
{ "query": "toyota crown", "make": "toyota", "model": "crown", "year": 1997,
  "vehicle_type": "car" }
```

`vehicle_type` (`car` | `motorcycle`) routes the scraper to the right portal
(CarsGuide for cars, BikeGuide for motorcycles). The backend sends its
`vehicle.vehicle_type` field. Expected response (alias-resilient parsing —
field names may vary):

```json
{
  "source": "carsguide|carsales|combined",
  "listings": [
    {"title": "1997 Toyota Crown Royal", "price": 15000,
     "year": 1997, "odometer_km": 120000, "source": "carsguide", "url": "..."}
  ]
}
```

Aggregates (median / low / high / sample_size) are computed server-side.

## Providers & scraping status

| Portal | Protocol | Status |
|--------|----------|--------|
| CarsGuide | Nuxt SSR `__NUXT_DATA__` over plain HTTP | ✅ live |
| CarSales | Akamai-protected | ⏳ needs a browser/undetected channel |
| BikeGuide (motorcycles) | same Nuxt stack as CarsGuide, but behind a **FingerprintJS redirect gate** — and the domain is now parked ("may be for sale", AboveDomains host) | 🔴 **parked** — no listings exist; browser channel (Playwright) is wired but deterministically returns an empty set + `note` |
| BikeSales (motorcycles) | PerimeterX hold-to-confirm + browser fingerprinting | 🔴 **gated** — real browser was verified against it (AUT-314); the challenge does not clear for this infra, so the provider stays deterministic-degraded |

`market-data/bikesguide.py` reuses the CarsGuide Nuxt parser and detects the
FingerprintJS gate (no `__NUXT_DATA__` + fingerprint/`tr_uuid` markers) and the
parked page ("may be for sale"/`abovedomains`), returning
`{"source": "bikesguide", "listings": [], "note": "parked|gated: ..."}` so
valuations still complete offline. A Playwright channel
(`market-data/browser.py`, subprocess worker mirroring the rego-lookup-api
pattern) is wired behind the provider: plain HTTP runs first (fast, catches the
parked page without spawning a browser), then the browser worker when the page
looks like a live gate. BikesSales' PerimeterX challenge was probed with a real
Chromium browser (hold gesture + fingerprint) and does not clear from the
dev/hosted networks; that remains a documented blocker, not a data source.

### Motorcycle valuation reality (AUT-314)

Neither AU motorcycle portal is reachable for live listings right now:
`bikesguide.com.au` is parked (no data exists) and `bikesales.com.au` sits
behind a PerimeterX interactive challenge. Motorcycle valuations therefore
resolve via the deterministic degradation path (`sample_size=0` → AI used-price
path clamped ±15%), exactly as designed for a gated provider. The browser
channel ships so the moment either portal opens (or a clean IP / undetected
tier is available) real listings flow with no backend change.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/vehicles/{id}/valuation/market?refresh=` | Market data for the vehicle (24h cache) |
| GET | `/vehicles/{id}/valuation/market/search?q=` | Search live listings (24h cache per query) |
| POST | `/vehicles/{id}/valuation` | Valuation — response now includes a `market` block |

## Database

`market_listing_cache`: one row per (make, model, year). Columns: `source`,
`listings` (JSON), `median_price`, `low_price`, `high_price`, `sample_size`,
`fetched_at`. Unique constraint `uq_market_make_model_year`.

## Frontend

`valuation_screen.dart` shows a Live market data card (median, range, listing
count, up to 5 listings) plus a search field backed by the `/market/search`
endpoint. Market data is best-effort — never blocks the estimate.

## Without the provider configured

`MARKET_DATA_URL` unset → the service returns `source=fallback`,
`sample_size=0`, and valuation behaves exactly as before (deterministic model
+ AI advice). Everything still works; the search UI shows "provider not
configured".

## Deploying the scraper (AUT-290)

The scraper source lives in the monorepo as `market-data/` (FastAPI + `carsguide.py`) and is
bundled into the AI image (AUT-1242-C3). The `ai` container runs **two uvicorn processes**:
- **:8001** — the AI inference gateway (`app.main:app`).
- **:8000** — the CarsGuide/BikeGuide market-data scraper (`market-data/main:app`).

- **Hosted:** the `autobrain-hosted` stack (EP5) has no separate `market-data` service.
  The backend is wired via `MARKET_DATA_URL: http://ai:8000` / `MARKET_DATA_API_KEY` (stack env).
- **Prod/Dev compose:** uses the same image; `MARKET_DATA_URL` defaults to `http://ai:8000`
  when the env var is set in the deployment env file.
- **Dev box mirror:** Portainer stack `market-data` on EP6 (`:8003`) is legacy and
  should be removed when convenient.
- **Gotcha:** the current backend config refuses *default* credentials in
  `production` (`POSTGRES_PASSWORD`/`MINIO_SECRET_KEY` = `autobrain`,
  `SECRET_KEY` = `change-me`). Before the hosted backend can boot on the
  current image the stack's postgres role and MinIO root password must be
  rotated to real values AND reflected in the stack env — rotate the Postgres
  role with `ALTER USER ... PASSWORD '...'` and MinIO with
  `mc admin user set-password`, then redeploy. The demo/default tiers have the
  same latent debt.

## Supercheap Auto parts-guide scraper (AUT-1792)

The same market-data container also scrapes the **Supercheap Auto parts-guide**
so AutoBrain can suggest real parts for a vehicle. Source: `market-data/sca.py`.

- **Endpoint:** `POST /sca-parts` with `{rego, state, make, model, year}`
  (rego+state resolve the vehicle via the browser flow; make/model/year is the
  deterministic fallback). Returns `{source: "supercheap", vehicle, categories}`
  where each category is `{slug, name, service_group, part_category, url}`.
- **Pattern (deterministic-first):** plain HTTP to the SSR parts-guide page
  extracts the category taxonomy; if rego+state are supplied a **Playwright**
  subprocess (`browser.py scrape_sca`) drives the Demandware FindRegoVehicle
  form to resolve the real vehicle, then degrades to the taxonomy if the CSRF
  gate doesn't clear. Never raises — returns an empty `categories` + `note`.
- **Formatting:** the backend (`app/services/parts_guide.py`) posts the raw
  categories to the AI gateway `parts-guide` module, which normalises them into
  Inventory-shaped part suggestions and uses 9Router (only) to *tidy*
  descriptions / brands / categories — the deterministic classification is the
  ground truth and is never overwritten by the model.
- **Two backend endpoints** sit on top of this (see `docs/api-spec.md`):
  - `GET /vehicles/{id}/parts/sca-lookup` → Inventory-formatted SCA parts.
  - `POST /vehicles/{id}/parts/suggest-for-service` → parts prefill for an
    AI-suggested service, **inventory-first then SCA**.
- **Config:** no new env var — it reuses `MARKET_DATA_URL` / `MARKET_DATA_API_KEY`.
- **Caching:** results are cached in `sca_parts_cache` (keyed by
  `make|model|year`, 24h TTL) so repeat lookups are stable and cheap.
