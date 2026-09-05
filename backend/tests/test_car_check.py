"""Tests for the Car Check module (AUT-2630).

Tests the pure helpers and the listing URL parser. The DB-backed
``compute_car_check`` integration is covered by the integration test
environment (docker-compose). Following the same pattern as
``test_advisor_value.py`` (env var setup before import).
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_USER", "test-postgres-user")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_DB", "test-postgres-db")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-minio-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret-key")
os.environ.setdefault("MINIO_BUCKET", "test-minio-bucket")

from app.services.car_check import (  # noqa: E402
    parse_listing_url,
    _verdict,
    _band,
)


class TestVerdict:
    def test_no_data_returns_risky(self):
        verdict, note = _verdict(None, 0)
        assert verdict == "risky"
        assert note is not None

    def test_low_sample_returns_risky(self):
        verdict, note = _verdict(-20.0, 2)
        assert verdict == "risky"
        assert "insufficient" in note.lower()

    def test_great_deal_negative_10(self):
        verdict, _ = _verdict(-10.0, 5)
        assert verdict == "great_deal"

    def test_great_deal_deep_discount(self):
        verdict, _ = _verdict(-25.0, 5)
        assert verdict == "great_deal"

    def test_fair_at_zero(self):
        verdict, _ = _verdict(0.0, 5)
        assert verdict == "fair"

    def test_fair_boundary(self):
        verdict, _ = _verdict(5.0, 5)
        assert verdict == "fair"

    def test_overpriced_at_6(self):
        verdict, _ = _verdict(6.0, 5)
        assert verdict == "overpriced"

    def test_overpriced_boundary(self):
        verdict, _ = _verdict(15.0, 5)
        assert verdict == "overpriced"

    def test_risky_above_15(self):
        verdict, _ = _verdict(16.0, 5)
        assert verdict == "risky"

    def test_low_sample_overrides_great_deal(self):
        verdict, _ = _verdict(-25.0, 2)
        assert verdict == "risky"

    def test_none_delta_returns_risky(self):
        verdict, _ = _verdict(None, 5)
        assert verdict == "risky"


class TestBand:
    def test_mid_100(self):
        low, high = _band(100.0)
        assert low == 95.0
        assert high == 105.0

    def test_mid_250(self):
        low, high = _band(250.0)
        assert low == 237.5
        assert high == 262.5

    def test_mid_123(self):
        low, high = _band(123.45)
        assert low == 117.28
        assert high == 129.62


class TestParseListingUrl:
    def test_carsguide(self):
        result = parse_listing_url("https://www.carsguide.com.au/buy/2018-mazda-3-touring/abc123")
        assert result is not None
        assert result["make"] == "mazda"
        assert result["model"] == "3-touring"
        assert result["year"] == 2018

    def test_carsales(self):
        result = parse_listing_url("https://www.carsales.com.au/cars/details/2020-Toyota-Corolla-Ascent/xyd")
        assert result is not None
        assert result["make"] == "toyota"
        assert result["model"] == "corolla-ascent"
        assert result["year"] == 2020

    def test_multi_model_tokens(self):
        result = parse_listing_url("https://example.com/2019-subaru-forester-2.5i-L/p123")
        assert result is not None
        assert result["make"] == "subaru"
        assert "forester" in result["model"]
        assert result["year"] == 2019

    def test_missing_year_returns_none(self):
        result = parse_listing_url("https://example.com/listing/mazda-3-touring/abc")
        assert result is None

    def test_unknown_make_returns_none(self):
        result = parse_listing_url("https://example.com/2020-unknown-brand-some-model/abc")
        assert result is None

    def test_empty_url_returns_none(self):
        assert parse_listing_url("") is None
        assert parse_listing_url(None) is None

    def test_mercedes_canonical(self):
        result = parse_listing_url("https://example.com/2019-mercedes-c200/abc")
        assert result is not None
        assert result["make"] == "mercedes-benz"

    def test_mercedes_benz_slug(self):
        result = parse_listing_url("https://example.com/2019-mercedes-benz-c200/abc")
        assert result is not None
        assert result["make"] == "mercedes-benz"

    def test_bmwg(self):
        result = parse_listing_url("https://example.com/2020-bmw-320i/abc")
        assert result is not None
        assert result["make"] == "bmw"

    def test_no_url_no_path(self):
        result = parse_listing_url("not-a-url")
        assert result is None
