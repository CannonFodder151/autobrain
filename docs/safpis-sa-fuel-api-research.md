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

### GetCountryBrands(countryId=21)
```json
{"BrandId": 2, "Name": "Caltex"}
```
Call once per day; cache locally.

### GetFuelTypes(countryId=21) → `GetCountryFuelTypes`
```json
{"FuelId": 5, "Name": "Premium Unleaded 95"}
```
Call once per day; cache locally.

### GetCountryGeographicRegions(countryId=21)
```json
{
  "GeoRegionLevel": 2,
  "GeoRegionId": 189,
  "Name": "Adelaide",
  "Abbrev": "ADE",
  "GeoRegionParentId": 4
}
```
State = level 3, City = level 2, Suburb = level 1.

### GetFullSiteDetails(countryId=21, geoRegionLevel=3, geoRegionId=4)
```json
{
  "S": 61501045,
  "A": "20A Main North Rd & Carter St",
  "N": "OTR Thorngate",
  "B": 169,
  "P": "5082",
  "G1": 611, "G2": 189, "G3": 4, "G4": 0, "G5": 0,
  "Lat": -34.896251,
  "Lng": 138.599507,
  "M": "2020-12-02T22:45:20.35",
  "GPI": "",
  "MO": "06:00", "MC": "22:00",
  "TU": "06:00", "TC": "22:00",
  "WE": "06:00", "WC": "22:00",
  "TH": "06:00", "THC": "22:00",
  "FR": "06:00", "FC": "22:00",
  "SA": "08:00", "SC": "21:00",
  "SU": "08:00", "SUC": "21:00"
}
```
Fields: `S`=SiteId, `A`=Address, `N`=Name, `B`=BrandId, `P`=Postcode, `G1-G5`=GeoRegions, `Lat/Lng`=coords, `M`=LastModified UTC, `GPI`=GooglePlaceId, trading hours per day.
Call once per day.

### GetSitesPrices(countryId=21, geoRegionLevel=3, geoRegionId=4)
```json
{
  "SiteId": 61501045,
  "FuelId": 14,
  "CollectionMethod": "T",
  "TransactionDateUtc": "2021-01-06T22:55:00",
  "Price": 1356.0
}
```
**Critical:** prices are in **tenths of a cent** (1356.0 = $1.356/L). Must divide by 10 to get cents/L, or by 1000 to get dollars/L.
`CollectionMethod` = `T` (Aggregator collected).
`Price` = `9999.0` means product unavailable at that site.
Rate limit: do not poll more than once per minute.
Recommended cadence: once per day (same as AUT-2375 schedule).

## Integration into fuel_feeds.py

SAFPIS uses the **exact same API shape as QLD FuelPricesQLD DirectAPI v1.5** — Informed Sources is the same aggregator for both SA and QLD. The existing `_parse_qld_direct_sites` / `_parse_qld_direct_prices` / `_parse_qld_brands` / `_parse_qld_fuel_types` parsers can be **reused almost unchanged**:

1. Add `FUEL_SA_API_KEY` setting (Subscriber Token GUID).
2. Add `ingest_sa_fuel()` entry point: call `GetCountryBrands`, `GetFuelTypes`, `GetCountryGeographicRegions` (cache daily), then `GetFullSiteDetails` and `GetSitesPrices` with `geoRegionId=4`.
3. Reuse `_parse_qld_direct_sites(sites_raw, brand_map)` → prepend `source="sa"`.
4. Reuse `_parse_qld_direct_prices(prices_raw, fuel_map)` — **divide by 10** to get $/L (QLD prices come pre-converted; SA returns tenths of cents).
5. Wire into `ingest_all_fuel()` in the daily beat schedule.
6. Update `docs/fuel-servo-spy.md` Sources table.
7. Add `FUEL_SA_API_KEY` to `docker-compose.prod.yml`, `docker-compose.hosted.yml`, and env templates.

### Key difference from QLD
QLD DirectAPI prices appear to come as **integer cents per litre** (heuristic: ≥50 is integer → divide by 100). SAFPIS prices are in **tenths of a cent** — always divide by 10 to get cents/L, then by 100 for dollars/L. The `_parse_qld_direct_prices` heuristic (checking ≥50 and integer) would work for SAFPIS prices (1356 is integer ≥50 → divides by 100 → 13.56 — but that would be wrong! Actual correct conversion: 1356.0 tenths-of-cents = 135.6 cents = $1.356). Must adjust the parser to handle SA-specific divisor.

## Deployment Notes

- Nathan has already registered as a data publisher (confirmed in parent AUT-2371 comments 2026-09-04).
- FUEL_SA_API_KEY is needed in env vars for all three tiers (Demo, Default, Hosted).
- AUT-2374 branch exists (`origin/aut-2374-sa-tas-nt-fuel-feeds`) but contains **no SA ingester code** — the branch is empty (just release-bump commits). The CEO's claim that SA code is in fuel_feeds.py is incorrect.
- AUT-2375 (PR #471) adds the `ingest_fuel_all` hook where SA will plug in.
- The SA ingester must be written as a new PR off the branch, then merged to main, then deployed through the 3-tier promotion (Demo → Default → Hosted).

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/core/config.py` | Add `FUEL_SA_API_KEY`, `FUEL_SA_GEO_REGION_ID=4` settings |
| `backend/app/services/fuel_feeds.py` | Add `ingest_sa_fuel()` (reusing QLD parsers with SA divisor) |
| `backend/app/workers/tasks.py` | Wire `ingest_sa_fuel` into `ingest_fuel_all` + register as beat task |
| `docker-compose.prod.yml` | Add `FUEL_SA_API_KEY` to backend env |
| `docker-compose.hosted.yml` | Add `FUEL_SA_API_KEY` to backend env |
| `docs/fuel-servo-spy.md` | Add SA row to Sources table |
