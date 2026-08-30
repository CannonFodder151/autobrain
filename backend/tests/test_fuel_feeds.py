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
