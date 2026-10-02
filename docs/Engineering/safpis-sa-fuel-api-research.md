# SA Fuel Pricing Scheme (SAFPIS) — API Research (AUT-2372)

## Summary

The South Australian Fuel Pricing Information Scheme (SAFPIS) is a **mandatory real-time** fuel price reporting scheme, live since 19 March 2021. It is run by **Informed Sources** (the same aggregator as QLD FuelPricesQLD) on behalf of the SA Government's Consumer & Business Services (CBS). **Servo Spy is already listed as an authorised data publisher** on the CBS fuel-pricing-apps page.

## Endpoint & Auth

| Field | Detail |
|-------|--------|
| **API Provider** | Informed Sources (SAFPIS Direct API OUT) |
| **Swagger (UAT)** | `https://fppdirectapi-uat.safuelpricinginformation.com.au/swagger` |
| **Production base** | `https://fppdirectapi.safuelpricinginformation.com.au` (to be confirmed from registration) |
| **Auth scheme** | `Authorization: FPDAPI SubscriberToken=<GUID>` (same pattern as QLD FuelPricesQLD) |
| **Protocol** | HTTPS only; JSON content-type required |
| **CountryId** | `21` (Australia) |
| **GeoRegionLevel** | `3` (state level) |
| **GeoRegionId** | `4` (South Australia) |

## Registration

| Step | Detail |
|------|--------|
| **Sign-up URL (retailers)** | `https://forms.office.com/Pages/ResponsePage.aspx?id=XbdJc0AKKUSHYhmf2mnq-9XqCWIciN5Osw2Y74gWzu9UMjdEOFhJSTE0UU9RVENOWjhBNTAxQ1VYSyQlQCN0PWcu` |
| **Sign-up URL (data publishers)** | `https://forms.office.com/Pages/ResponsePage.aspx?id=XbdJc0AKKUSHYhmf2mnq-9XqCWIciN5Osw2Y74gWzu9UQzZKMDVSVzJZWlZSUDFJSVYzUFQ1WDJZTyQlQCN0PWcu` |
| **T&Cs** | `https://www.safuelpricinginformation.com.au/documents/TermsandConditions.pdf` (DEHAA Digital Data Licence) |
| **API Guide** | `https://www.safuelpricinginformation.com.au/documents/SAFPIS_API Out_v1.2.pdf` |
| **Support** | support@safuelpricinginformation.com.au / 08 8356 1020 |
| **Cost** | Free (government scheme; no fee for data publishers) |
| **Approach** | Submit MS Forms registration; wait for Subscriber Token (GUID); connect to production API |

## Pricing Data Shape

### Get Prices (production endpoint)

```
GET /api/v1/FuelPrices
  Query: CountryId=21&GeoRegionLevel=3&GeoRegionId=4
  Header: Authorization: FPDAPI SubscriberToken=<GUID>
```

Response (simplified):

```json
{
  "fuelPrices": [
    {
      "stationCode": "12345",
      "stationName": "Shell Port Adelaide",
      "brand": "Shell",
      "address": "123 Commercial Rd, Port Adelaide SA 5015",
      "latitude": -34.8456,
      "longitude": 138.5123,
      "fuelType": "ULP",
      "price": 189.9,
      "lastUpdated": "2026-09-28T10:30:00Z"
    }
  ],
  "lastUpdated": "2026-09-28T10:30:00Z"
}
```

### Fuel types

| FuelType | Display |
|----------|---------|
| `ULP` | Unleaded 91 |
| `PULP` | Premium 95 |
| `UPULP` | Premium 98 |
| `E10` | E10 |
| `DIESEL` | Diesel |
| `LPG` | LPG |

## Integration plan

1. **Secret management:** Add `FUEL_SA_API_KEY_FILE` (SubscriberToken GUID) to `docker-compose.hosted.yml` backend env (AUT-2610). Seed via `scripts/seed-secrets.sh`.
2. **Backend ingest task:** New Celery task `ingest_safpis_prices` (mirror `ingest_nsw_prices` pattern) that polls the SAFPIS endpoint every 5 min, upserts into `fuel_price_snapshots` (table created by migration after `aut1859_fuel_price_alerts`).
3. **Schema:** Reuse `fuel_price_snapshots` with columns matching `FuelPriceSnapshot` model (state, station_code, station_name, brand, address, latitude, longitude, fuel_type, price, currency, updated_at, fetched_at, previous_price, previous_price_at) + unique constraint `uq_fuel_price_snapshot_station_fuel` on (state, station_code, fuel_type).
4. **Frontend:** Servo Spy map (`/api/fuel`) already reads from `fuel_price_snapshots` — no UI change needed.
5. **Attribution:** `GET /api/v1/fuel/attribution` returns open-data attribution for all feeds (WA FuelWatch, NSW FuelCheck, QLD FuelPricesQLD, SAFPIS).

## Risks / notes

- **AUT-5072 (2026-10-02):** both Direct API hosts below are NXDOMAIN from
  AutoBrain networks (`fppdirectapi.safuelpricinginformation.com.au`,
  `fppdirectapi-uat.safuelpricinginformation.com.au`); only the marketing site
  `www.safuelpricinginformation.com.au` resolves. `FUEL_SA_ENABLED` is therefore
  `"false"` in both compose files and no `ingest_sa_*` parser is wired. Re-open
  this research once a subscriber token from a contracted aggregator comes with a
  reachable production host, then follow the integration plan below.
- UAT endpoint is a sandbox; production base URL confirmed only after registration approval.
- Same `FPDAPI SubscriberToken` auth as QLD — code can share the client wrapper.
- Free for data publishers; no rate limits documented but implement exponential backoff.
- SA is a smaller market (~1.8M pop) — lower station count than NSW/QLD, less polling load.