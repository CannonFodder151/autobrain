"""Unit tests for the SA SAFPIS fuel ingest (AUT-2406).

DB-free, network-free, deterministic: feed ``_parse_sa_*`` helpers real
fixture shapes mirroring the SAFPIS v1.2 API and assert the canonical
normalisation, including the tenths-of-a-cent conversion and the 9999.0
drop sentinel.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MINIO_ACCESS_KEY"] = "a"
os.environ["MINIO_SECRET_KEY"] = "b"
os.environ["MINIO_BUCKET"] = "c"
os.environ["POSTGRES_USER"] = "u"
os.environ["POSTGRES_PASSWORD"] = "p"
os.environ["POSTGRES_DB"] = "d"
os.environ["ENVIRONMENT"] = "development"

from app.services import fuel_feeds as feeds  # noqa: E402

SA_BRANDS = [
    {"BrandId": 1, "Name": "BP"},
    {"BrandId": 2, "Name": "Shell"},
]
SA_FUELS = [
    {"FuelId": 1, "Name": "Unleaded 91"},
    {"FuelId": 2, "Name": "Premium Unleaded 95"},
    {"FuelId": 4, "Name": "Diesel"},
]
SA_REGIONS = [
    {"GeoRegionLevel": 1, "GeoRegionId": 10, "Name": "Australia", "Abbrev": "AU"},
    {"GeoRegionLevel": 3, "GeoRegionId": 4, "Name": "South Australia", "Abbrev": "SA"},
]
SA_SITES = {"S": [
    {"S": 50001, "A": "1 King Wm St", "N": "Shell Adelaide CBD", "B": 2,
     "P": "5000", "G1": "AU", "G2": "SA", "G3": "Adelaide",
     "Lat": -34.9285, "Lng": 138.6007, "LastModified": "2024-06-01T00:00:00"},
]}
# SA prices in TENTHS OF A CENT: 1356.0 → 135.6 c/L → 1.356 $/L
# (AUT-2406: "prices are in tenths of a cent, divide by 10 to get c/L").
# Sentinel 9999.0 → product unavailable (drop, not stored as 0).
SA_PRICES = {"S": [
    {"S": 50001, "P1": 1356.0, "P2": 1460.0, "P4": 1527.0,
     "LastUpdated": "2024-06-01T00:00:00"},
    {"S": 50001, "P3": 9999.0,  # sentinel → drop (E10 unavailable at this site)
     "LastUpdated": "2024-06-01T00:00:00"},
]}


def test_parse_sa_brands_and_fuels() -> None:
    assert feeds._parse_qld_brands(SA_BRANDS) == {1: "BP", 2: "Shell"}
    assert feeds._parse_qld_fuel_types(SA_FUELS) == {1: "Unleaded 91", 2: "Premium Unleaded 95", 4: "Diesel"}
    assert feeds._parse_qld_geo_regions(SA_REGIONS, level=3) == 4
    assert feeds._parse_qld_geo_regions(SA_REGIONS, level=1) == 10


def test_parse_sa_sites_resolves_brand() -> None:
    sites = feeds._parse_qld_direct_sites(SA_SITES, {1: "BP", 2: "Shell"})
    assert sites == [{
        "source": "qld",  # shared parser uses "qld"; ingest_sa_fuel rewrites source via _ingest db arg
        "source_id": "50001", "brand": "Shell",
        "name": "Shell Adelaide CBD", "address": "1 King Wm St",
        "lat": -34.9285, "lon": 138.6007,
    }]


def test_parse_sa_prices_tenths_of_cent_converts_and_drops_sentinel() -> None:
    prices = feeds._parse_sa_direct_prices(
        SA_PRICES,
        {1: "Unleaded 91", 2: "Premium Unleaded 95", 3: "E10", 4: "Diesel"},
    )
    pairs = {(ft, round(price, 3)) for (ft, price, _) in prices["50001"]}
    assert pairs == {("91", 1.356), ("95", 1.46), ("Diesel", 1.527)}
    assert "E10" not in [ft for ft, _, _ in prices["50001"]]


def test_parse_sa_prices_unknown_fuel_keys_ignored() -> None:
    raw = {"S": [{"S": 1, "P1": 1356.0, "P999": 20000, "PX": 100,
                   "LastUpdated": "2024-06-01T00:00:00"}]}
    prices = feeds._parse_sa_direct_prices(raw, {1: "Unleaded 91"})
    assert {ft for (ft, _, _) in prices["1"]} == {"91"}
    assert round(prices["1"][0][1], 3) == 1.356


def test_ingest_sa_skips_when_no_key() -> None:
    feeds.settings.FUEL_SA_API_KEY = ""
    feeds.settings.FUEL_SA_ENABLED = False
    # No DB needed for the no-key guard; ingest_sa_fuel returns a summary dict.
    res = feeds.ingest_sa_fuel.__wrapped__ if hasattr(feeds.ingest_sa_fuel, "__wrapped__") else feeds.ingest_sa_fuel
    # ingest_sa_fuel is async; just confirm the skip path matches the NSW pattern.
    import asyncio
    skipped = asyncio.run(feeds.ingest_sa_fuel(None))  # type: ignore[arg-type]
    assert skipped["skipped"] == "no_api_key"
    assert skipped["stations"] == 0


def test_sa_tenths_cent_conversion() -> None:
    assert feeds._sa_tenths_cent_to_dollars(1356.0) == 1.356
    assert feeds._sa_tenths_cent_to_dollars(0.0) == 0.0
    assert feeds._sa_tenths_cent_to_dollars(9999.0) is None
    assert feeds._sa_tenths_cent_to_dollars(None) is None
    assert feeds._sa_tenths_cent_to_dollars("") is None
