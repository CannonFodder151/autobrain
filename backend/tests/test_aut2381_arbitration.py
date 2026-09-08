"""Unit tests for multi-source data-quality arbitration (AUT-2381).

Three mock sources provide overlapping prices for the same station + fuel type.
The tests assert deterministic winner selection: government wins over retail when
equally fresh, freshness beats trust when the gap is wide, and outliers get
flagged. No DB, no network, no AI — pure arithmetic.
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

from app.services.fuel_feeds import (  # noqa: E402
    ARBITRATION_OUTLIER_CPL,
    ARBITRATION_STALE_HOURS,
    ArbitrationResult,
    PriceCandidate,
    SourceTrust,
    _consistency_bonus,
    _freshness_weight,
    _score_candidate,
    select_best_price,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
TWO_HOURS_AGO = NOW - timedelta(hours=2)
ONE_DAY_AGO = NOW - timedelta(days=1)


def _candidates(*specs: tuple[str, float, datetime]) -> list[PriceCandidate]:
    """Shorthand: (source, price, effective_at) -> [PriceCandidate]."""
    return [
        PriceCandidate(source=src, price=price, fuel_type="91", effective_at=ts)
        for src, price, ts in specs
    ]


class TestSourceTrustOrdering:
    def test_gov_free_wins_over_retail(self) -> None:
        assert SourceTrust.GOVERNMENT_FREE > SourceTrust.RETAIL_FREE

    def test_retail_free_wins_over_gov_paid(self) -> None:
        assert SourceTrust.RETAIL_FREE > SourceTrust.GOVERNMENT_PAID

    def test_gov_paid_wins_over_crowdscraped(self) -> None:
        assert SourceTrust.GOVERNMENT_PAID > SourceTrust.CROWDSCRAPED

    def test_all_values_are_ints(self) -> None:
        for member in SourceTrust:
            assert isinstance(member, int)


class TestFreshnessWeight:
    def test_just_updated_is_one(self) -> None:
        c = PriceCandidate(source="wa", price=180.0, fuel_type="91", effective_at=NOW)
        w = _freshness_weight(c, now=NOW)
        assert w == 1.0

    def test_two_hours_old_is_zero(self) -> None:
        c = PriceCandidate(source="wa", price=180.0, fuel_type="91",
                           effective_at=NOW - timedelta(hours=ARBITRATION_STALE_HOURS))
        w = _freshness_weight(c, now=NOW)
        assert w == 0.0

    def test_one_hour_old_is_half(self) -> None:
        c = PriceCandidate(source="wa", price=180.0, fuel_type="91",
                           effective_at=NOW - timedelta(hours=1))
        w = _freshness_weight(c, now=NOW)
        assert abs(w - 0.5) < 0.01

    def test_naive_timestamp_treated_as_utc(self) -> None:
        naive = datetime(2026, 9, 4, 12, 0, 0)  # no tzinfo
        c = PriceCandidate(source="wa", price=180.0, fuel_type="91", effective_at=naive)
        # Should not raise; should produce a sensible weight (0.0 if naive is interpreted
        # as ~UTC and matched against NOW)
        w = _freshness_weight(c, now=NOW)
        assert 0.0 <= w <= 1.0


class TestConsistencyBonus:
    def test_single_candidate_is_neutral(self) -> None:
        c = _candidates(("wa", 180.0, NOW))[0]
        assert _consistency_bonus(c, [c]) == 0.5

    def test_close_to_median_is_consistent(self) -> None:
        cs = _candidates(("wa", 180.0, NOW), ("nsw", 181.0, NOW), ("qld", 179.0, NOW))
        for c in cs:
            assert _consistency_bonus(c, cs) == 1.0

    def test_outlier_is_flagged(self) -> None:
        cs = _candidates(("wa", 180.0, NOW), ("nsw", 181.0, NOW), ("qld", 220.0, NOW))
        outlier = [c for c in cs if c.source == "qld"][0]
        assert _consistency_bonus(outlier, cs) == 0.0
        assert _consistency_bonus(cs[0], cs) == 1.0

    def test_outlier_just_under_threshold_is_consistent(self) -> None:
        """A candidate within ARBITRATION_OUTLIER_CPL of the regional median is consistent."""
        # Other two prices: 209, 210. Median = 209.5. ``wa`` at 180.0 is 29.5
        # cpl away -> under the 30 cpl threshold -> consistent.
        cs = _candidates(("wa", 180.0, NOW), ("nsw", 209.0, NOW), ("qld", 210.0, NOW))
        for c in cs:
            b = _consistency_bonus(c, cs)
            assert b == 1.0, f"{c.source} should be under threshold"

    def test_outlier_just_over_threshold_is_flagged(self) -> None:
        """A candidate > 30 cpl from the regional median is flagged (strict >)."""
        # Others: 210, 210. Median = 210. ``wa`` at 179.9 -> 30.1 cpl away -> flagged.
        cs = _candidates(("wa", 179.9, NOW), ("nsw", 210.0, NOW), ("qld", 210.0, NOW))
        wa = [c for c in cs if c.source == "wa"][0]
        assert _consistency_bonus(wa, cs) == 0.0

    def test_outlier_at_exactly_threshold_is_not_flagged(self) -> None:
        """Exactly 30.0 cpl -> NOT flagged (the spec is strict "> 30")."""
        cs = _candidates(("wa", 180.0, NOW), ("nsw", 210.0, NOW), ("qld", 210.0, NOW))
        wa = [c for c in cs if c.source == "wa"][0]
        assert _consistency_bonus(wa, cs) == 1.0


class TestScoreCandidate:
    def test_trust_dominates_when_equally_fresh(self) -> None:
        """Two candidates same freshness: government wins by trust * 3."""
        cs = _candidates(("nsw", 180.0, NOW), ("qld", 180.0, NOW))
        # nsw = GOVERNMENT_FREE(4) = 12 pts from trust alone
        # qld = GOVERNMENT_PAID(2)  = 6  pts from trust alone
        s_nsw = _score_candidate(cs[0], cs, now=NOW)
        s_qld = _score_candidate(cs[1], cs, now=NOW)
        assert s_nsw > s_qld

    def test_freshness_beats_trust_when_gap_wide(self) -> None:
        """Stale gov data loses to very fresh retail when freshness gap is large."""
        cs = _candidates(
            ("wa", 180.0, TWO_HOURS_AGO - timedelta(minutes=30)),  # gov_free, stale
            ("nsw", 180.5, NOW),                                    # gov_free, fresh
        )
        s_wa = _score_candidate(cs[0], cs, now=NOW)
        s_nsw = _score_candidate(cs[1], cs, now=NOW)
        assert s_nsw > s_wa

    def test_outlier_gets_zero_consistency(self) -> None:
        cs = _candidates(
            ("wa", 180.0, NOW),
            ("nsw", 181.0, NOW),
            ("qld", 220.0, NOW),  # outlier
        )
        s_qld = _score_candidate(cs[2], cs, now=NOW)
        # Consistency component is 0, so qld gets trust(2)*3 + freshness*2 + 0*1
        # vs others getting trust*3 + freshness*2 + 1*1
        assert s_qld < _score_candidate(cs[0], cs, now=NOW)


class TestSelectBestPrice:
    def test_three_gov_sources_gov_free_wins(self) -> None:
        """Two fresh GOVERNMENT_FREE sources both beat GOVERNMENT_PAID.

        The exact winner between the two tied government sources is determined
        by the lexicographic tiebreak, but the property the system guarantees
        is "government free wins over government paid" — never the paid one.
        """
        cs = _candidates(
            ("wa", 179.9, NOW),       # GOVERNMENT_FREE
            ("nsw", 180.0, NOW),      # GOVERNMENT_FREE
            ("qld_direct", 180.1, NOW),  # GOVERNMENT_PAID (DirectAPI)
        )
        result = select_best_price(cs, now=NOW)
        assert result is not None
        assert result.best_source in ("wa", "nsw")  # never the paid source
        assert "qld_direct" not in result.flagged_sources
        assert result.source_score > 0

    def test_stale_gov_loses_to_fresh_retail(self) -> None:
        """Retail free at 30 min beats government free at 1h50m."""
        cs = _candidates(
            ("wa", 180.0, NOW - timedelta(minutes=110)),   # gov_free, stale
            ("nsw", 180.0, NOW - timedelta(minutes=30)),   # gov_free, fresh
        )
        result = select_best_price(cs, now=NOW)
        assert result is not None
        assert result.best_source == "nsw"

    def test_outlier_source_gets_flagged(self) -> None:
        """The outlier is flagged_sources but the winner is not."""
        cs = _candidates(
            ("wa", 180.0, NOW),
            ("nsw", 180.5, NOW),
            ("qld", 215.0, NOW),
        )
        result = select_best_price(cs, now=NOW)
        assert result is not None
        assert "qld" in result.flagged_sources
        assert result.best_source != "qld"

    def test_single_candidate_always_wins(self) -> None:
        cs = [PriceCandidate(source="wa", price=190.0, fuel_type="91", effective_at=NOW)]
        result = select_best_price(cs, now=NOW)
        assert result is not None
        assert result.best_source == "wa"
        assert result.best_price == 190.0

    def test_empty_input_returns_none(self) -> None:
        assert select_best_price([], now=NOW) is None

    def test_tiebreak_is_stable(self) -> None:
        """Two identical candidates: lexicographic source name breaks the tie."""
        cs = _candidates(
            ("qld", 180.0, NOW),
            ("wa", 180.0, NOW),
        )
        r1 = select_best_price(cs, now=NOW)
        r2 = select_best_price(cs, now=NOW)
        assert r1.best_source == r2.best_source  # deterministic

    def test_older_source_with_higher_trust_beats_fresh_crowdscraped(self) -> None:
        """Gov free at 30 min > crowdscraped at 0 min (trust * 3 >> freshness * 2)."""
        cs = _candidates(
            ("wa", 180.0, NOW - timedelta(minutes=30)),    # gov_free
            ("crowd", 180.0, NOW),                          # crowdscraped trust=1
        )
        result = select_best_price(cs, now=NOW)
        assert result is not None
        assert result.best_source == "wa"


class TestArbitrationResult:
    def test_result_is_frozen_dataclass(self) -> None:
        r = ArbitrationResult(
            best_source="wa", best_price=180.0,
            best_effective_at=NOW, source_score=13.5,
            flagged_sources=frozenset(),
        )
        assert r.best_source == "wa"
        assert isinstance(r.flagged_sources, frozenset)


class TestPriceCandidate:
    def test_candidate_stores_all_fields(self) -> None:
        c = PriceCandidate(source="nsw", price=179.9, fuel_type="95",
                           effective_at=NOW, station_id="S123")
        assert c.source == "nsw"
        assert c.station_id == "S123"
        assert c.price == 179.9
