"""Tests for the market-data service (deterministic parsing + aggregation).

DB caching is exercised via the AI-side resale tests; here we cover the
pure provider-parsing and aggregation logic that never touches the DB.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""


from app.services.market_data import _aggregate, _build, _fallback, _map_listing, _parse_provider_response  # noqa: E402


def test_aggregate_empty() -> None:
    out = _aggregate([])
    assert out["sample_size"] == 0
    assert out["median_price"] is None


def test_aggregate_median_odd() -> None:
    out = _aggregate([{"price": 10000}, {"price": 15000}, {"price": 20000}])
    assert out["median_price"] == 15000.0
    assert out["low_price"] == 10000
    assert out["high_price"] == 20000
    assert out["sample_size"] == 3


def test_aggregate_median_even() -> None:
    out = _aggregate([{"price": 10000}, {"price": 14000}])
    assert out["median_price"] == 12000.0


def test_aggregate_drops_missing_prices() -> None:
    out = _aggregate([{"price": None}, {"price": 9000}, {"price": 11000}])
    assert out["sample_size"] == 2
    assert out["median_price"] == 10000.0


def test_map_listing_alias_resilient() -> None:
    raw = {"asking_price": "15,000", "model_year": 1997, "ad_title": "Toyota Crown Royal",
           "portal": "carsguide", "link": "https://carsguide.com.au/123"}
    out = _map_listing(raw)
    assert out["price"] == 15000.0
    assert out["year"] == 1997
    assert out["title"] == "Toyota Crown Royal"
    assert out["source"] == "carsguide"
    assert out["url"] == "https://carsguide.com.au/123"


def test_map_listing_junk_skipped() -> None:
    assert _map_listing("not a dict") is None
    assert _map_listing({"foo": "bar"}) is None


def test_parse_provider_response_shapes() -> None:
    data = {
        "source": "combined",
        "listings": [
            {"title": "1997 Crown", "price": 15000, "year": 1997},
            {"title": "1997 Crown", "price": 13000, "year": 1997},
            {"title": "1997 Crown", "price": 17000, "year": 1997},
        ],
    }
    out = _parse_provider_response(data)
    assert out["source"] == "combined"
    assert len(out["listings"]) == 3


def test_parse_provider_response_nested_listings() -> None:
    data = {"results": {"items": [{"title": "A", "price": 10000}]}}
    out = _parse_provider_response(data)
    assert len(out["listings"]) == 1


def test_build_with_data() -> None:
    provider = {"source": "carsales", "listings": [
        {"title": "A", "price": 10000}, {"title": "B", "price": 12000}, {"title": "C", "price": 14000},
    ]}
    out = _build(provider)
    assert out["source"] == "carsales"
    assert out["median_price"] == 12000.0
    assert out["sample_size"] == 3


def test_build_empty_is_fallback() -> None:
    out = _build({"source": "carsales", "listings": []})
    assert out["source"] == "fallback"
    assert out["sample_size"] == 0


def test_fallback_always_valid() -> None:
    out = _fallback("no provider")
    assert out["source"] == "fallback"
    assert out["median_price"] is None
    assert out["listings"] == []
