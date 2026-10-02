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
       ├─ app/services/market_scraper/   (local CarsGuide/BikesGuide/SCA)
       │    ├─ carsguide.py             (Nuxt SSR __NUXT_DATA__ over plain HTTP)
       │    ├─ bikesguide.py            (same Nuxt parser + parked/gate detection)
       │    ├─ sca.py                   (SCA parts-guide taxonomy + browser flow)
       │    └─ browser.py               (Playwright subprocess for gated portals)
       ├─ market_listing_cache table   (24h TTL, keyed make|model|year)
       └─ fallback (source=fallback, sample_size=0) — pipeline never 404s
  └─ payload["market"]  →  ai resale module (ai/app/modules/resale.py)
       ├─ sample_size >= 3  → median_price anchors the estimate
       │     value = max(median × cond_mult × km_mult + mods_value,
       │                  rule_based × 0.5) — the rule-based number is a 0.5×
       │     sanity floor so a bad median can't collapse the value.
       └─ otherwise → AI-supplied current selling price refines the estimate,
             clamped to ±15% of the rule-based band
```

The median is **cached for 24h**, so consecutive valuations return identical
market numbers → identical estimates. No more call-to-call wobble.

## Provider protocol (local market_scraper)

The market-data scraper now runs **locally inside the backend container** (no separate
`MARKET_DATA_URL` service). Celery tasks call `app.services.market_scraper` directly:

- `search_carsguide(query, year)` — Nuxt SSR `__NUXT_DATA__` extraction (plain HTTP)
- `search_bikesguide(query, year)` — reuses CarsGuide parser; detects FingerprintJS
  gate and parked page; optional Playwright channel (`browser.py`) for live gates
- `search_sca(rego, state, make, model, year)` — SSR parts-guide taxonomy +
  optional Playwright rego→vehicle resolution

The backend no longer requires `MARKET_DATA_URL` / `MARKET_DATA_API_KEY`. If set,
they are ignored in favour of the local scrapers. The local scrapers are
deterministic-first: plain HTTP first, Playwright subprocess only for gated
portals, and graceful degradation (empty listings + `note`) when gates don't
clear.

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

## Deploying the scraper (AUT-4113 / AUT-3843)

The scraper source lives in the monorepo under `backend/app/services/market_scraper/`
and is bundled into the **backend image** (not the AI image). The backend Dockerfile
installs Playwright + Chromium system deps and sets `PLAYWRIGHT_BROWSERS_PATH`.

- **No compose service.** There is no `market-data` service in `docker-compose.yml`,
  `docker-compose.prod.yml` or `docker-compose.hosted.yml`. The earlier "one image,
  two uvicorn processes (`:8001` gateway + `:8000` scraper)" shape (AUT-1242-C3) is
  retired. Hosted goes from 12 → 11 containers.
- **Celery beat drives it.** `refresh_market_data` (`app.workers.tasks`) runs daily
  at 03:00 and sweeps up to 1000 distinct `(make, model, year, vehicle_type)` rows
  from the `vehicles` table, forcing a fresh scrape per vehicle. Per-vehicle
  failures are logged and skipped so one bad vehicle never aborts the sweep.
  Progress is logged as `market_data_refresh_done`.
- **`MARKET_DATA_URL` is gone** from the backend config — the Celery worker calls
  `search_carsguide` / `search_bikesguide` in-process. When a scrape fails the
  pipeline degrades deterministically (`source=fallback`, `sample_size=0`) and the
  valuation uses the deterministic depreciation model + AI used-price advice.
- **Resource:** the backend service declares `shm_size: "256m"` so the Chromium
  sandbox has enough shared memory.
- **Gotcha:** the backend runs as non-root user `autobrain` (CWE-250 hardening).
  The Chromium SUID sandbox helper (`chrome-sandbox` / `chrome_sandbox`) is
  re-owned to `root:root 4755` at build time (AUT-1739 / AUT-2258) so the
  scraper can sandbox untrusted third-party content; it falls back to
  `--no-sandbox` only if the sandboxed launch fails.
- **Legacy:** the Portainer `market-data` stack on the dev box (`<DEV_BOX_IP>`,
  Portainer endpoint 6) is leftover from
  before the consolidation and should be removed when convenient.

### Provider cost profile

| Tier | Live listings? | Marginal cost |
|------|-----------------|---------------|
| Hosted (prod) | Yes — local beat sweep | Scrape CPU inside the backend container; 24h cache absorbs repeat valuations |
| Dev / Prod compose | Yes — same local path | Scrape CPU only, no egress |
| Motorcycle (BikeGuide/SCA) | Partial — both gated/parked | None; degrades to deterministic fallback |

- **Gotcha (deployment, not scraper-specific):** the backend config refuses
  *default* credentials outside `development` (`POSTGRES_PASSWORD`/`MINIO_SECRET_KEY`
  = `autobrain`, `SECRET_KEY` = `change-me`). The stack's postgres role and MinIO
  root password must be real values reflected in the stack env — rotate the Postgres
  role with `ALTER USER ... PASSWORD '...'` and MinIO with
  `mc admin user set-password`, then redeploy.

## Supercheap Auto parts-guide scraper (AUT-1792)

The parts-guide scraper also feeds the **Supercheap Auto parts-guide** so
AutoBrain can suggest real parts for a vehicle. Source: `market-data/sca.py`,
invoked in-process by the backend.

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
- **Two backend endpoints** sit on top of this (see
  [`../Engineering/api-spec.md`](../Engineering/api-spec.md)):
  - `POST /vehicles/{id}/parts/sca-lookup` → Inventory-formatted SCA parts.
  - `POST /vehicles/{id}/parts/suggest-for-service` → parts prefill for an
    AI-suggested service, **inventory-first then SCA**.
- **Config:** no new env var. The SCA scraper now lives in `backend/app/services/market_scraper/sca.py`
  and is called directly by `backend/app/services/parts_guide.py` (no `MARKET_DATA_URL` needed).
  Playwright + Chromium are installed in the backend image (`docker/backend/Dockerfile`),
  and the backend service runs with `shm_size: "256m"` (needed for the Chromium sandbox).
- **Caching:** results are cached in `sca_parts_cache` (keyed by
  `make|model|year`, 24h TTL) so repeat lookups are stable and cheap. A nightly
  Celery beat task (`refresh_sca_parts_cache`, AUT-2419) pre-warms the cache so
  the first user click returns from cache; failures are logged and never abort
  the rest.

## Related Finance Docs

- **[index.md](./index.md)** — Finance section index
- **[infrastructure-costs.md](./infrastructure-costs.md)** — per-service spend and optimisation
- **[fuel-pricing.md](./fuel-pricing.md)** / **[fuel-servo-spy.md](./fuel-servo-spy.md)** — deterministic fuel price paths

## Sanitisation

Public repo mirror. `MARKET_DATA_API_KEY` is a deployment secret recorded in
the internal Outline `Deployment & Infrastructure` section and is never
committed; env var *names* above are safe to publish, values are not. Host
addresses are placeholders from the sanctioned set (`<HOSTED_VM_IP>`,
`<DEV_BOX_IP>`, `<PORTENER_HOST_IP>`). See
[Documentation Policy](../Company/documentation-policy.md).

## Finding the code

Use the repo context graph rather than grepping — see the Graft section in the
root `AGENTS.md` (`graft ask "market data median anchor"`,
`graft callers get_market_data`).

---

*Last updated: 2026-10-02 | Owner: CFO + Backend | Reviewed by: Documentation Manager (AUT-4397) | Sources: backend/app/services/market_data.py, backend/app/services/parts_guide.py, ai/app/fallbacks/resale.py, docker-compose.hosted.yml | Next review: 2026-11-01*
