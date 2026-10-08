"""Tests for the Car Check module (AUT-2630, AUT-2651).

Pure-helper tests for ``app.services.car_check``: the deterministic deal
score, the score label, the red/green flag builders and the fallback
contract. The DB-backed AI path is covered by the integration test
environment (docker-compose). Following the same pattern as
``test_advisor_value.py`` (env var setup before import).

These assertions target the AUT-2651 scoring API. (The pre-2651 helpers
— ``parse_listing_url`` / ``_verdict`` / ``_band`` — are gone: verdict
and band logic moved into the Value module, listing parsing into the
marketplace scrapers.)
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

import pytest  # noqa: E402

from app.services.car_check import (  # noqa: E402
    _clip,
    _green_flags,
    _red_flags,
    _score_from_km,
    _score_from_price,
    _score_from_year,
    _score_label,
    build_car_check_payload,
    car_check_fallback,
    compute_deal_score,
    validate_car_check_response,
)


class TestScoreFromPrice:
    def test_under_reference_is_perfect(self) -> None:
        assert _score_from_price(15_000, 20_000) == 100.0

    def test_at_reference_is_perfect(self) -> None:
        assert _score_from_price(20_000, 20_000) == 100.0

    def test_midway_to_double_is_fifty(self) -> None:
        assert _score_from_price(30_000, 20_000) == 50.0

    def test_at_double_is_zero(self) -> None:
        assert _score_from_price(40_000, 20_000) == 0.0

    def test_beyond_double_is_zero(self) -> None:
        assert _score_from_price(99_000, 20_000) == 0.0

    def test_missing_price_is_none(self) -> None:
        assert _score_from_price(None, 20_000) is None

    def test_missing_reference_is_none(self) -> None:
        assert _score_from_price(15_000, None) is None

    def test_non_positive_reference_is_none(self) -> None:
        assert _score_from_price(15_000, 0) is None


class TestScoreFromKm:
    def test_half_benchmark_is_perfect(self) -> None:
        # 2018 vehicle -> age 8 -> benchmark 120_000 km
        assert _score_from_km(60_000, 2018) == 100.0

    def test_at_benchmark_is_perfect(self) -> None:
        assert _score_from_km(120_000, 2018) == 100.0

    def test_half_again_benchmark_is_fifty(self) -> None:
        assert _score_from_km(180_000, 2018) == 50.0

    def test_double_benchmark_is_zero(self) -> None:
        assert _score_from_km(240_000, 2018) == 0.0

    def test_age_floor_of_one_year(self) -> None:
        """A 2026+ vehicle still gets a 15_000 km benchmark, not zero."""
        assert _score_from_km(7_500, 2026) == 100.0
        assert _score_from_km(30_000, 2026) == 0.0

    def test_missing_km_is_none(self) -> None:
        assert _score_from_km(None, 2018) is None

    def test_missing_year_is_none(self) -> None:
        assert _score_from_km(60_000, None) is None

    def test_non_numeric_year_is_none(self) -> None:
        assert _score_from_km(60_000, "abc") is None


class TestScoreFromYear:
    def test_same_year_is_perfect(self) -> None:
        assert _score_from_year(2018, 2018) == 100.0

    def test_ten_year_gap_is_fifty(self) -> None:
        assert _score_from_year(2008, 2018) == 50.0

    def test_twenty_year_gap_is_zero(self) -> None:
        assert _score_from_year(1998, 2018) == 0.0

    def test_missing_year_is_none(self) -> None:
        assert _score_from_year(None, 2018) is None

    def test_non_numeric_year_is_none(self) -> None:
        assert _score_from_year("abc", 2018) is None


class TestComputeDealScore:
    def test_perfect_listing_scores_100(self) -> None:
        listing = {"price": 15_000, "odometer_km": 60_000, "year": 2018}
        assert compute_deal_score(listing, reference_price=20_000, vehicle_year=2018) == 100.0

    def test_weights_price_sixty_km_thirty_year_ten(self) -> None:
        """price 50, km 100, year 100 -> 0.6*50 + 0.3*100 + 0.1*100 = 70."""
        listing = {"price": 30_000, "odometer_km": 60_000, "year": 2018}
        score = compute_deal_score(listing, reference_price=20_000, vehicle_year=2018)
        assert score == pytest.approx(70.0)

    def test_no_signals_scores_fifty(self) -> None:
        assert compute_deal_score({}) == 50.0

    def test_missing_reference_skips_the_price_signal(self) -> None:
        """Only km (100) and year (100) remain -> 100.0."""
        listing = {"price": 30_000, "odometer_km": 60_000, "year": 2018}
        assert compute_deal_score(listing, vehicle_year=2018) == 100.0

    def test_missing_km_skips_the_km_signal(self) -> None:
        """price 100, year 100 -> 100.0."""
        listing = {"price": 15_000, "year": 2018}
        assert compute_deal_score(listing, reference_price=20_000, vehicle_year=2018) == 100.0

    def test_score_is_clamped_to_the_0_100_range(self) -> None:
        listing = {"price": 1, "odometer_km": 1, "year": 2018}
        assert compute_deal_score(listing, reference_price=20_000, vehicle_year=2018) <= 100.0

    def test_boolean_year_is_ignored(self) -> None:
        listing = {"price": 15_000, "odometer_km": 60_000, "year": True}
        score = compute_deal_score(listing, reference_price=20_000, vehicle_year=2018)
        # Only price + km contribute; both 100 -> 100.0
        assert score == 100.0

    def test_result_is_rounded_to_one_decimal(self) -> None:
        """price 50, km 100, year 95 -> 0.6*50 + 0.3*100 + 0.1*95 = 69.5."""
        listing = {"price": 30_000, "odometer_km": 60_000, "year": 2017}
        score = compute_deal_score(listing, reference_price=20_000, vehicle_year=2018)
        assert score == pytest.approx(69.5)
        assert round(score, 1) == score


class TestScoreLabel:
    def test_none_is_not_available(self) -> None:
        assert _score_label(None) == "not available"

    def test_strong_at_seventy_five(self) -> None:
        assert _score_label(75) == "strong"

    def test_fair_at_fifty(self) -> None:
        assert _score_label(50) == "fair"

    def test_weak_below_fifty(self) -> None:
        assert _score_label(49.9) == "weak"


class TestRedGreenFlags:
    def test_low_deal_score_is_flagged(self) -> None:
        flags = _red_flags({"price": 100}, 40)
        assert any("40" in f for f in flags)

    def test_missing_price_and_odo_are_flagged(self) -> None:
        flags = _red_flags({}, 90)
        assert len(flags) == 2

    def test_no_red_flags_for_a_complete_good_deal(self) -> None:
        assert _red_flags({"price": 100, "odometer_km": 5}, 90) == []

    def test_strong_deal_score_is_a_green_flag(self) -> None:
        flags = _green_flags({"price": 100, "year": 2020}, 80)
        assert any("80" in f for f in flags)

    def test_fair_deal_score_is_a_green_flag(self) -> None:
        flags = _green_flags({"price": 100}, 60)
        assert any("60" in f for f in flags)

    def test_flags_capped_at_five(self) -> None:
        listing = {"price": 100, "year": 2020, "odometer_km": 5, "listing_url": "https://x"}
        assert len(_green_flags(listing, 90)) <= 5


class TestCarCheckFallback:
    def test_contract_shape(self) -> None:
        payload = {
            "deal_score": 82.0,
            "listing": {
                "title": "2018 Toyota Corolla",
                "price": 15_000,
                "year": 2018,
                "odometer_km": 60_000,
                "make": "Toyota",
                "model": "Corolla",
                "listing_url": "https://example.com/l",
            },
        }
        result = car_check_fallback(payload)
        assert result["deal_score"] == 82.0
        assert result["model"] == "rule-based-fallback"
        assert isinstance(result["summary"], str)
        assert "Toyota Corolla" in result["summary"]
        assert isinstance(result["red_flags"], list)
        assert isinstance(result["green_flags"], list)

    def test_none_deal_score_is_kept_as_none(self) -> None:
        result = car_check_fallback({"deal_score": None, "listing": {}})
        assert result["deal_score"] is None
        assert _score_label(result["deal_score"]) == "not available"

    def test_non_numeric_deal_score_is_none(self) -> None:
        result = car_check_fallback({"deal_score": "high", "listing": {}})
        assert result["deal_score"] is None

    def test_non_dict_payload_does_not_raise(self) -> None:
        result = car_check_fallback(None)  # type: ignore[arg-type]
        assert result["deal_score"] is None

    def test_summary_is_clipped_to_280_chars(self) -> None:
        listing = {
            "make": "V" * 200,
            "model": "M" * 200,
            "year": 2018,
            "price": 1,
            "odometer_km": 1,
        }
        result = car_check_fallback({"deal_score": 50, "listing": listing})
        assert len(result["summary"]) <= 280


class TestValidateCarCheckResponse:
    def test_clamps_deal_score_into_range(self) -> None:
        out = validate_car_check_response({"deal_score": 250.0})
        assert out["deal_score"] == 100.0
        out = validate_car_check_response({"deal_score": -5.0})
        assert out["deal_score"] == 0.0

    def test_non_numeric_deal_score_becomes_none(self) -> None:
        assert validate_car_check_response({"deal_score": "n/a"})["deal_score"] is None

    def test_flags_are_cleaned_to_strings(self) -> None:
        out = validate_car_check_response(
            {
                "red_flags": [1, "  ", "  real flag  ", "x" * 500],
                "green_flags": "not-a-list",
            }
        )
        assert out["red_flags"][0] == "real flag"
        assert out["red_flags"][1] == "x" * 119 + "…"
        assert out["green_flags"] == []

    def test_non_string_flags_are_dropped(self) -> None:
        out = validate_car_check_response({"red_flags": [1, None, "ok", 2.5]})
        assert out["red_flags"] == ["ok"]

    def test_flags_capped_at_five(self) -> None:
        out = validate_car_check_response({"red_flags": [str(i) for i in range(20)]})
        assert len(out["red_flags"]) == 5

    def test_missing_model_defaults_to_fallback(self) -> None:
        assert validate_car_check_response({})["model"] == "rule-based-fallback"

    def test_non_dict_input_returns_the_default_contract(self) -> None:
        out = validate_car_check_response(None)  # type: ignore[arg-type]
        assert out["model"] == "rule-based-fallback"
        assert out["deal_score"] is None


class TestBuildCarCheckPayload:
    def test_payload_keeps_only_the_clean_listing_fields(self) -> None:
        listing = {
            "title": "2018 Toyota Corolla",
            "price": 15_000,
            "year": 2018,
            "odometer_km": 60_000,
            "make": "Toyota",
            "model": "Corolla",
            "listing_url": "https://example.com/l",
            "secret_internal_field": "must not leak",
        }
        payload = build_car_check_payload(listing, reference_price=20_000, vehicle_year=2018)
        assert payload["deal_score"] == 100.0
        assert "secret_internal_field" not in payload["listing"]
        assert payload["listing"]["make"] == "Toyota"


class TestClip:
    def test_short_text_is_unchanged(self) -> None:
        assert _clip("hello", 280) == "hello"

    def test_long_text_is_clipped_with_ellipsis(self) -> None:
        long_text = "x" * 300
        clipped = _clip(long_text, 10)
        assert len(clipped) == 10
        assert clipped.endswith("…")

    def test_empty_text_is_empty(self) -> None:
        assert _clip("", 10) == ""
