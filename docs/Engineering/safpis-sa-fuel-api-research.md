# SA Fuel Pricing Scheme (SAFPIS) — API Research (AUT-2372)

> **STATUS: SUPERSEDED — do not implement (AUT-5072).**
> The SAFPIS Direct API does not exist. Both hosts —
> `fppdirectapi.safuelpricinginformation.com.au` and
> `fppdirectapi-uat.safuelpricinginformation.com.au` — are **NXDOMAIN**
> (re-verified 2026-10-03 against the authoritative nameserver via public
> DoH; the apex `safuelpricinginformation.com.au` still resolves, so this is
> not a resolver artefact). No subscriber token was ever contracted, and no
> SA ingest code was ever written.
>
> Outcome: `FUEL_SA_ENABLED` is `"false"` in `docker-compose.hosted.yml` and
> `docker-compose.prod.yml`; `/fuel/stations` and `/fuel/attribution` do not
> advertise SA. The `fuel_sa_api_key` secret file stays mounted so re-enabling
> is a one-line flip **once a working aggregator is contracted**. SA fuel
> coverage does not exist in Servo Spy today.
>
> This document is kept for the scheme background and registration path only.
> The endpoint table below is corrected to reflect what was actually verified.
> Do not re-litigate the integration on the strength of this research — see
> `docs/Finance/fuel-servo-spy.md` for the live feed list.

## Summary

The South Australian Fuel Pricing Information Scheme (SAFPIS) is a **mandatory real-time** fuel price reporting scheme, live since 19 March 2021. It is run by **Informed Sources** (the same aggregator as QLD FuelPricesQLD) on behalf of the SA Government's Consumer & Business Services (CBS). **Servo Spy is already listed as an authorised data publisher** on the CBS fuel-pricing-apps page.

## Endpoint & Auth

| Field | Detail |
|-------|--------|
| **API Provider** | Informed Sources (SAFPIS Direct API OUT) — feed unavailable (AUT-5072) |
| **Swagger (UAT)** | `fppdirectapi-uat.safuelpricinginformation.com.au` — **NXDOMAIN**, no such host (AUT-5072) |
| **Production base** | `fppdirectapi.safuelpricinginformation.com.au` — **NXDOMAIN**, no such host (AUT-5072). Never confirmed; never will be at this hostname |
| **Auth scheme** | `Authorization: FPDAPI SubscriberToken=<GUID>` (same pattern as QLD FuelPricesQLD) — no token ever issued to us |
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
| **Approach** | Submit MS Forms registration; wait for Subscriber Token (GUID); connect to production API. **Not pursued** — no token was ever issued, and the API host does not resolve (AUT-5072) |

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

## Integration plan — NOT EXECUTED (superseded by AUT-5072)

Historical plan kept for context. It was never started because no
subscriber token was contracted and no SAFPIS API host resolves. If
an aggregator is ever contracted, start from the QLD `ingest_*`
pattern, not from the steps below.

~~1. **Secret management:** Add `FUEL_SA_API_KEY_FILE` (SubscriberToken GUID) to `docker-compose.hosted.yml` backend env (AUT-2610). Seed via `scripts/seed-secrets.sh`.~~ — done in reverse: the secret file stays mounted but `FUEL_SA_ENABLED: "false"` gates it.
2. **Backend ingest task:** New Celery task `ingest_safpis_prices` (mirror `ingest_nsw_prices` pattern) that polls the SAFPIS endpoint every 5 min, upserts into `fuel_price_snapshots` (table created by migration after `aut1859_fuel_price_alerts`).
3. **Schema:** Reuse `fuel_price_snapshots` with columns matching `FuelPriceSnapshot` model (state, station_code, station_name, brand, address, latitude, longitude, fuel_type, price, currency, updated_at, fetched_at, previous_price, previous_price_at) + unique constraint `uq_fuel_price_snapshot_station_fuel` on (state, station_code, fuel_type).
4. **Frontend:** Servo Spy map (`/api/fuel`) already reads from `fuel_price_snapshots` — no UI change needed.
5. **Attribution:** `GET /api/v1/fuel/attribution` returns open-data attribution for all feeds (WA FuelWatch, NSW FuelCheck, QLD FuelPricesQLD, SAFPIS).

## Risks / notes

- ~~UAT endpoint is a sandbox; production base URL confirmed only after registration approval.~~ Resolved the other way in AUT-5072: neither host resolves, so there is nothing to confirm.
- Same `FPDAPI SubscriberToken` auth as QLD — code can share the client wrapper.
- Free for data publishers; no rate limits documented but implement exponential backoff.
- SA is a smaller market (~1.8M pop) — lower station count than NSW/QLD, less polling load.