"""AUT-2406: SA SAFPIS ingester tests (DB-free, no network).

Mirrors the QLD DirectAPI parser test style. Verifies the SA-specific
tenths-of-a-cent -> cents/litre conversion and the 9999.0 unavailable sentinel.
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

SA_DIRECT_BRANDS = [
    {"BrandId": 1, "Name": "BP"},
    {"BrandId": 10, "Name": "Shell"},
]
SA_DIRECT_FUELS = [
    {"FuelId": 1, "Name": "Unleaded 91"},
    {"FuelId": 2, "Name": "Premium Unleaded 95"},
    {"FuelId": 3, "Name": "Ethanol"},
    {"FuelId": 4, "Name": "Diesel"},
]
SA_DIRECT_SITES = {"S": [
    {"S": 54321, "A": "123 King St", "N": "BP Adelaide CBD", "B": 1,
     "P": "5000", "G1": "AU", "G2": "SA", "G3": "Adelaide",
     "Lat": -34.9285, "Lng": 138.6007, "LastModified": "2024-03-01T00:00:00"},
    {"S": 54322, "A": "456 Rundle St", "N": "Shell Rundle Mall", "B": 10,
     "P": "5000", "G1": "AU", "G2": "SA", "G3": "Adelaide",
     "Lat": -34.9207, "Lng": 138.6104, "LastModified": "2024-03-01T00:00:00"},
]}
# Prices in tenths of a cent (SAFPIS v1.2). 99990 tenths -> 9999.0 c/L = unavailable.
SA_DIRECT_PRICES = {"S": [
    {"S": 54321, "P1": 13560, "P2": 14560, "P3": 99990,
     "LastUpdated": "2024-03-01T12:00:00"},
    {"S": 54322, "P1": 13900, "P4": 15020, "LastUpdated": "2024-03-01T12:00:00"},
]}


def test_parse_sa_brands_fuels_match_qld() -> None:
    assert feeds._parse_qld_brands(SA_DIRECT_BRANDS) == {1: "BP", 10: "Shell"}
    assert feeds._parse_qld_fuel_types(SA_DIRECT_FUELS) == {
        1: "Unleaded 91", 2: "Premium Unleaded 95", 3: "Ethanol", 4: "Diesel"
    }


def test_parse_sa_direct_sites_resolves_brand() -> None:
    sites = feeds._parse_qld_direct_sites(SA_DIRECT_SITES, {1: "BP", 10: "Shell"})
    assert sites == [{
        "source": "qld", "source_id": "54321", "brand": "BP",
        "name": "BP Adelaide CBD", "address": "123 King St",
        "lat": -34.9285, "lon": 138.6007,
    }, {
        "source": "qld", "source_id": "54322", "brand": "Shell",
        "name": "Shell Rundle Mall", "address": "456 Rundle St",
        "lat": -34.9207, "lon": 138.6104,
    }]


def test_parse_sa_direct_prices_tenths_of_a_cent_to_cpl_and_drops_unavailable() -> None:
    prices = feeds._parse_sa_direct_prices(
        SA_DIRECT_PRICES,
        {1: "Unleaded 91", 2: "Premium Unleaded 95", 3: "Ethanol", 4: "Diesel"},
    )
    pairs_54321 = {(ft, price) for (ft, price, _) in prices["54321"]}
    assert ("91", 1356.0) in pairs_54321       # 13560 tenths -> 1356.0 c/L
    assert ("95", 1456.0) in pairs_54321       # 14560 tenths -> 1456.0 c/L
    # Ethanol at site 54321 = 99990 tenths = 9999.0 c/L sentinel — must be dropped.
    assert "E10" not in {ft for (ft, _, _) in prices["54321"]}
    pairs_54322 = {(ft, price) for (ft, price, _) in prices["54322"]}
    assert ("91", 1390.0) in pairs_54322       # 13900 tenths -> 1390.0 c/L
    assert ("Diesel", 1502.0) in pairs_54322   # 15020 tenths -> 1502.0 c/L
    for _, _, ts in prices["54321"]:
        assert ts.tzinfo is not None


def test_ingest_sa_skips_when_no_key(monkeypatch) -> None:
    monkeypatch.setattr(feeds.settings, "FUEL_SA_API_KEY", "")
    import asyncio
    res = asyncio.run(feeds.ingest_sa_fuel(db=None))  # type: ignore[arg-type]
    assert res["skipped"] == "no_api_key"
    assert res["stations"] == 0
    assert res["prices"] == 0
