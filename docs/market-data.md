# Market data & stable valuations (AUT-287)

The resale valuation feeds on live used-car market data from **CarsGuide** and
**CarSales** so the estimate matches what buyers are actually paying — and
stays *stable* between runs.

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
{ "query": "toyota crown", "make": "toyota", "model": "crown", "year": 1997 }
```

Expected response (alias-resilient parsing — field names may vary):

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
+ AI advice). Everything works offline; the search UI shows "provider not
configured".
