"""Unit tests for multi-source data-quality arbitration (AUT-2381, AUT-2386).

Several government feeds publish a price for the same station + fuel type. The
arbitration rule picks one deterministic winner per (station, fuel_type, day):
source authority dominates, freshness is a small tie-breaker, and a wide spread
triggers a median-based penalty that keeps a single out-of-band source from
winning. No DB, no network, no AI — pure arithmetic.

These assertions target ``app.services.fuel_source_arbitration``, the module
that owns the rule today. (The pre-AUT-2386 in-``fuel_feeds`` helpers —
``SourceTrust`` / ``PriceCandidate`` / ``select_best_price`` — are gone; the
rule moved to its own module, so this suite tests the surviving behaviour.)
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

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

from app.services.fuel_source_arbitration import (  # noqa: E402
    FRESHNESS_WINDOW_HOURS,
    SPREAD_THRESHOLD_CPL,
    WEIGHT_AUTHORITY,
    WEIGHT_FRESHNESS,
    ArbitrationResult,
    RawSourceObservation,
    _authority_score,
    _freshness_bonus,
    _spread_penalty,
    arbitrate,
    source_authority,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
ONE_HOUR_AGO = NOW - timedelta(hours=1)
TWO_HOURS_AGO = NOW - timedelta(hours=FRESHNESS_WINDOW_HOURS)


def _obs(*specs: tuple[str, float, datetime | None]) -> list[RawSourceObservation]:
    """Shorthand: (source, price, updated_at) -> [RawSourceObservation]."""
    return [
        RawSourceObservation(
            source_id=src,
            price=price,
            authority=source_authority(src),
            updated_at=ts,
        )
        for src, price, ts in specs
    ]


class TestSourceAuthority:
    def test_mandatory_realtime_beats_daily_beats_other(self) -> None:
        assert source_authority("nsw") < source_authority("wa")
        assert source_authority("wa") < source_authority("other")

    def test_qld_and_sa_are_mandatory_realtime(self) -> None:
        assert source_authority("qld") == source_authority("nsw")
        assert source_authority("sa") == source_authority("nsw")

    def test_unknown_source_falls_back_to_other(self) -> None:
        assert source_authority("crowd") == source_authority("other")

    def test_authority_score_is_inverted(self) -> None:
        """Lower authority int (more authoritative) -> higher score."""
        assert _authority_score(source_authority("nsw")) == WEIGHT_AUTHORITY
        assert _authority_score(source_authority("wa")) == 0.0
        assert _authority_score(source_authority("other")) == -WEIGHT_AUTHORITY

    def test_one_authority_step_beats_the_whole_freshness_bonus(self) -> None:
        """Authority dominates: 100 per step vs at most 1.0 of freshness."""
        assert WEIGHT_AUTHORITY > WEIGHT_FRESHNESS


class TestFreshnessBonus:
    def test_just_updated_is_full_bonus(self) -> None:
        assert _freshness_bonus(NOW, now=NOW) == pytest.approx(WEIGHT_FRESHNESS)

    def test_half_window_is_half_bonus(self) -> None:
        assert _freshness_bonus(ONE_HOUR_AGO, now=NOW) == pytest.approx(
            WEIGHT_FRESHNESS * 0.5
        )

    def test_at_window_edge_is_zero(self) -> None:
        assert _freshness_bonus(TWO_HOURS_AGO, now=NOW) == pytest.approx(0.0)

    def test_older_than_window_is_zero(self) -> None:
        old = NOW - timedelta(hours=FRESHNESS_WINDOW_HOURS + 5)
        assert _freshness_bonus(old, now=NOW) == 0.0

    def test_none_timestamp_is_zero(self) -> None:
        assert _freshness_bonus(None, now=NOW) == 0.0

    def test_naive_timestamp_is_treated_as_utc(self) -> None:
        naive = datetime(2026, 9, 4, 12, 0, 0)  # no tzinfo
        assert _freshness_bonus(naive, now=NOW) == pytest.approx(WEIGHT_FRESHNESS)

    def test_future_timestamp_does_not_earn_a_bonus(self) -> None:
        """Clock skew must not inflate a stale source into the winner."""
        assert _freshness_bonus(NOW + timedelta(hours=1), now=NOW) == 0.0


class TestSpreadPenalty:
    def test_on_median_is_no_penalty(self) -> None:
        assert _spread_penalty(180.0, 180.0) == 0.0

    def test_scales_with_distance_from_median(self) -> None:
        near = _spread_penalty(180.0, 200.0)
        far = _spread_penalty(140.0, 200.0)
        assert 0 < near < far

    def test_symmetric(self) -> None:
        assert _spread_penalty(180.0, 200.0) == _spread_penalty(220.0, 200.0)


class TestArbitrate:
    def test_authority_wins_over_freshness(self) -> None:
        """A stale mandatory-realtime source still beats a fresh 'other'."""
        obs = _obs(
            ("nsw", 180.0, TWO_HOURS_AGO - timedelta(minutes=30)),
            ("other", 180.5, NOW),
        )
        result = arbitrate(obs, now=NOW)
        assert result.winner_source == "nsw"
        assert result.used_median is False

    def test_freshness_breaks_ties_within_one_authority_level(self) -> None:
        obs = _obs(
            ("nsw", 180.0, TWO_HOURS_AGO - timedelta(minutes=1)),
            ("qld", 180.0, NOW),
        )
        result = arbitrate(obs, now=NOW)
        assert result.winner_source == "qld"

    def test_tight_spread_keeps_the_most_authoritative(self) -> None:
        obs = _obs(
            ("nsw", 180.0, NOW),
            ("wa", 181.0, NOW),
            ("other", 179.0, NOW),
        )
        result = arbitrate(obs, now=NOW)
        assert result.winner_source == "nsw"
        assert result.used_median is False

    def test_wide_spread_penalises_the_outlier(self) -> None:
        """Spread > threshold pulls the score toward the daily median, so the
        out-of-band single-source price cannot win on freshness alone."""
        obs = _obs(
            ("nsw", 180.0, TWO_HOURS_AGO),
            ("wa", 181.0, TWO_HOURS_AGO),
            ("other", 400.0, NOW),
        )
        result = arbitrate(obs, now=NOW)
        assert result.used_median is True
        assert result.winner_source != "other"
        assert result.winner_price < 400.0

    def test_single_observation_always_wins(self) -> None:
        result = arbitrate(_obs(("nsw", 190.0, NOW)), now=NOW)
        assert result.winner_source == "nsw"
        assert result.winner_price == 190.0
        assert result.used_median is False

    def test_empty_input_raises(self) -> None:
        """Empty input must never produce a phantom winner row."""
        with pytest.raises(ValueError):
            arbitrate([], now=NOW)

    def test_tiebreak_is_deterministic_regardless_of_input_order(self) -> None:
        a = _obs(("nsw", 180.0, NOW), ("wa", 180.0, NOW), ("qld", 180.0, NOW))
        first = arbitrate(a, now=NOW)
        second = arbitrate(list(reversed(a)), now=NOW)
        assert first.winner_source == second.winner_source
        assert first.winner_source == "nsw"  # authority first, then source id

    def test_naive_now_is_treated_as_utc(self) -> None:
        obs = _obs(("nsw", 180.0, NOW), ("wa", 180.0, NOW - timedelta(days=1)))
        result = arbitrate(obs, now=datetime(2026, 9, 4, 12, 0, 0))
        assert result.winner_source == "nsw"


class TestArbitrationResult:
    def test_result_is_frozen(self) -> None:
        result = arbitrate(_obs(("nsw", 180.0, NOW)), now=NOW)
        with pytest.raises(Exception):
            result.winner_price = 1.0  # type: ignore[misc]

    def test_candidates_carry_scores(self) -> None:
        result = arbitrate(_obs(("nsw", 180.0, NOW), ("wa", 181.0, NOW)), now=NOW)
        assert len(result.candidates) == 2
        assert all(len(row) == 3 for row in result.candidates)
        assert isinstance(result, ArbitrationResult)
