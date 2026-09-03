"""Unit tests for the Servo Spy fuel ingest parsers (AUT-1817).

Pure + deterministic: the only network boundary (``_fetch_json``) is never hit;
we feed parser helpers real fixture shapes mirroring each open-data feed and
assert the canonical normalisation. No AI, no DB, no network.
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

import asyncio  # noqa: E402

from app.services import fuel_feeds as feeds  # noqa: E402

WA_SITES = [
    {"Sitedid": 1, "Name": "Caltex Perth", "Brand": "Caltex", "Address": "10 Main St",
     "Suburb": "Perth", "PostCode": "6000", "Latitude": -31.95, "Longitude": 115.86},
]
WA_PRICES = [
    {"SiteId": 1, "FuelCode": "ULP", "Price": 189.9, "PriceUpdatedDate": "2024-01-01T00:00:00"},
    {"SiteId": 1, "FuelCode": "Diesel", "Price": 199.9, "PriceUpdatedDate": "2024-01-01T00:00:00"},
    {"SiteId": 1, "FuelCode": "Banana", "Price": 1.0, "PriceUpdatedDate": "2024-01-01T00:00:00"},
]

NSW = {"features": [
    {"properties": {"stationcode": "S1", "name": "Metro X", "brand": "Metro",
                    "address": "1 St", "latitude": -33.8, "longitude": 151.2,
                    "fueltype": "E10", "price": 170.0, "lastupdated": "2024-01-01T00:00:00"}},
]}

QLD = {"stations": [
    {"id": "Q1", "name": "BP Y", "brand": "BP", "address": "2 St",
     "latitude": -27.4, "longitude": 153.0, "prices": {"91": 165.5, "Diesel": 180.0}},
]}


def test_normalise_fuel_type_wa_and_nsw_labels() -> None:
    assert feeds._normalise_fuel_type("ULP") == "91"
    assert feeds._normalise_fuel_type("PULP") == "95"
    assert feeds._normalise_fuel_type("PULP98") == "98"
    assert feeds._normalise_fuel_type("E10") == "E10"
    assert feeds._normalise_fuel_type("Diesel") == "Diesel"
    assert feeds._normalise_fuel_type("LPG") == "LPG"
    assert feeds._normalise_fuel_type("Premium Unleaded 95") == "95"
    assert feeds._normalise_fuel_type("Banana") is None
    assert feeds._normalise_fuel_type(None) is None


def test_haversine_known_distance() -> None:
    d = feeds.haversine_km(-33.8688, 151.2093, -37.8136, 144.9631)
    assert 690 < d < 740


def test_parse_wa_sites_and_prices() -> None:
    sites = feeds._parse_wa_sites(WA_SITES)
    assert sites == [{
        "source": "wa", "source_id": "1", "brand": "Caltex", "name": "Caltex Perth",
        "address": "10 Main St", "lat": -31.95, "lon": 115.86,
    }]
    prices = feeds._parse_wa_prices(WA_PRICES)
    fts = {ft for (ft, _, _) in prices["1"]}
    assert fts == {"91", "Diesel"}  # Banana dropped


def test_parse_nsw_features() -> None:
    stations, prices = feeds._parse_nsw(NSW)
    assert stations[0]["source"] == "nsw"
    assert stations[0]["source_id"] == "S1"
    assert ("E10", 170.0, prices["S1"][0][2]) in prices["S1"]


def test_parse_qld_stations_with_nested_prices() -> None:
    stations, prices = feeds._parse_qld(QLD)
    assert stations[0]["source"] == "qld"
    assert stations[0]["source_id"] == "Q1"
    assert {ft for (ft, _, _) in prices["Q1"]} == {"91", "Diesel"}


def test_ingest_all_is_tolerant_to_feed_failure() -> None:
    async def boom(db):  # noqa: ANN001
        raise RuntimeError("upstream down")

    class FakeDB:
        pass

    real_wa = feeds.ingest_wa_fuelwatch
    feeds.ingest_wa_fuelwatch = boom  # type: ignore[assignment]
    try:
        res = asyncio.run(feeds.ingest_all_fuel(FakeDB()))
        assert res["wa"]["error"] == "upstream down"
    finally:
        feeds.ingest_wa_fuelwatch = real_wa  # type: ignore[assignment]


# QLD DirectAPI v1.5 sample shapes (mirrors page 8 of the FuelPricesQLDDirectAPI
# v1.5 PDF — see comment in app/services/fuel_feeds.py for the contract).
QLD_DIRECT_BRANDS = [
    {"BrandId": 1, "Name": "BP"},
    {"BrandId": 2, "Name": "Caltex"},
]
QLD_DIRECT_FUELS = [
    {"FuelId": 1, "Name": "Unleaded 91"},
    {"FuelId": 2, "Name": "Premium Unleaded 95"},
    {"FuelId": 4, "Name": "Diesel"},
]
QLD_DIRECT_REGIONS = [
    {"GeoRegionLevel": 1, "GeoRegionId": 10, "Name": "Australia", "Abbrev": "AU"},
    {"GeoRegionLevel": 3, "GeoRegionId": 33, "Name": "Queensland", "Abbrev": "QLD"},
]
QLD_DIRECT_SITES = {"S": [
    {"S": 12345, "A": "123 Queen St", "N": "BP Brisbane CBD", "B": 1,
     "P": "4000", "G1": "AU", "G2": "QLD", "G3": "Brisbane",
     "Lat": -27.4698, "Lng": 153.0251, "LastModified": "2024-01-01T00:00:00"},
]}
QLD_DIRECT_PRICES = {"S": [
    {"S": 12345, "P1": 16500, "P2": 17500, "P4": 18000,
     "LastUpdated": "2024-01-01T00:00:00"},
]}


def test_parse_qld_direct_brands_and_fuels() -> None:
    assert feeds._parse_qld_brands(QLD_DIRECT_BRANDS) == {1: "BP", 2: "Caltex"}
    assert feeds._parse_qld_fuel_types(QLD_DIRECT_FUELS) == {1: "Unleaded 91", 2: "Premium Unleaded 95", 4: "Diesel"}
    assert feeds._parse_qld_geo_regions(QLD_DIRECT_REGIONS, level=3) == 33
    assert feeds._parse_qld_geo_regions(QLD_DIRECT_REGIONS, level=1) == 10
    assert feeds._parse_qld_geo_regions(QLD_DIRECT_REGIONS, level=99) is None


def test_parse_qld_direct_sites_resolves_brand() -> None:
    sites = feeds._parse_qld_direct_sites(QLD_DIRECT_SITES, {1: "BP", 2: "Caltex"})
    assert sites == [{
        "source": "qld", "source_id": "12345", "brand": "BP",
        "name": "BP Brisbane CBD", "address": "123 Queen St",
        "lat": -27.4698, "lon": 153.0251,
    }]


def test_parse_qld_direct_prices_normalises_cents_to_dollars() -> None:
    prices = feeds._parse_qld_direct_prices(
        QLD_DIRECT_PRICES,
        {1: "Unleaded 91", 2: "Premium Unleaded 95", 4: "Diesel"},
    )
    pairs = {(ft, price) for (ft, price, _) in prices["12345"]}
    assert pairs == {("91", 165.0), ("95", 175.0), ("Diesel", 180.0)}
    for _, _, ts in prices["12345"]:
        assert ts.tzinfo is not None


def test_parse_qld_direct_prices_handles_unknown_fuel_keys() -> None:
    # Unknown fuel id / non-numeric key should be silently ignored.
    raw = {"S": [{"S": 1, "P1": 15000, "P999": 20000, "PX": 100, "LastUpdated": "2024-01-01T00:00:00"}]}
    prices = feeds._parse_qld_direct_prices(raw, {1: "Unleaded 91"})
    assert {(ft, price) for (ft, price, _) in prices["1"]} == {("91", 150.0)}


def test_ingest_qld_skips_when_no_key() -> None:
    feeds.settings.FUEL_QLD_API_KEY = ""
    res = asyncio.run(feeds.ingest_qld_fuel_prices(db=None))  # type: ignore[arg-type]
    assert res["skipped"] == "no_api_key"
    assert res["stations"] == 0
