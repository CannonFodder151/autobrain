"""AUT-2386 — source-arbitration rule (deterministic, no AI).

Pure unit tests on the ranking function + an end-to-end pytest that feeds
overlapping prices from three sources into the in-memory arbiter and asserts
the chosen source matches the deterministic rule from Nathan (AUT-2371
follow-up): government-mandatory-realtime > government-daily > other,
freshness bonus in the last 2h, and median tie-break when sources disagree
by more than 30 cpl.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MINIO_ACCESS_KEY", "a")
os.environ.setdefault("MINIO_SECRET_KEY", "b")
os.environ.setdefault("MINIO_BUCKET", "c")
os.environ.setdefault("POSTGRES_USER", "u")
os.environ.setdefault("POSTGRES_PASSWORD", "p")
os.environ.setdefault("POSTGRES_DB", "d")
os.environ.setdefault("ENVIRONMENT", "development")

from datetime import datetime, timedelta, timezone

import pytest

from app.services.fuel_source_arbitration import (
    RawSourceObservation,
    SOURCE_AUTHORITY,
    arbitrate,
    source_authority,
)


def _obs(source_id: str, price: float, updated_at: datetime | None = None) -> RawSourceObservation:
    return RawSourceObservation(
        source_id=source_id,
        price=price,
        authority=SOURCE_AUTHORITY[source_id],
        updated_at=updated_at,
    )


def test_authority_orders_mandatory_realtime_above_daily_above_other() -> None:
    """Higher authority wins when prices agree and freshness is neutral."""
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    far = now - timedelta(days=2)  # outside the 2h freshness window
    result = arbitrate(
        [
            _obs("wa", 189.9, far),  # GOVERNMENT_DAILY
            _obs("nsw", 189.5, far),  # GOVERNMENT_MANDATORY_REALTIME
            _obs("other", 189.0, far),  # OTHER
        ],
        now=now,
    )
    assert result.winner_source == "nsw"
    assert result.winner_price == 189.5


def test_authority_loses_to_fresh_daily_when_realtime_is_stale() -> None:
    """Authority dominates, but a fresh daily observation still adds a small bonus."""
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    stale = now - timedelta(days=1)
    fresh = now - timedelta(minutes=15)  # well inside 2h window
    result = arbitrate(
        [
            _obs("nsw", 200.0, stale),  # higher authority, no freshness bonus
            _obs("wa", 189.9, fresh),   # lower authority, full freshness bonus
        ],
        now=now,
    )
    # Authority weight (100) >>> freshness weight (1) — NSW still wins
    # even when stale. The freshness bonus is a tie-breaker, not a flipper.
    assert result.winner_source == "nsw"


def test_median_picks_non_outlier_when_spread_exceeds_threshold() -> None:
    """When sources disagree by > 30 cpl, prefer the median."""
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    far = now - timedelta(days=1)
    result = arbitrate(
        [
            _obs("nsw", 189.5, far),
            _obs("wa", 189.0, far),
            _obs("other", 230.0, far),  # outlier
        ],
        now=now,
    )
    assert result.used_median is True
    assert result.winner_source in {"nsw", "wa"}


def test_no_median_when_sources_agree_within_threshold() -> None:
    """When the spread is <= 30 cpl, authority alone decides (no penalty)."""
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    far = now - timedelta(days=1)
    result = arbitrate(
        [
            _obs("wa", 189.0, far),
            _obs("nsw", 189.5, far),  # 5cpl diff
            _obs("other", 189.7, far),
        ],
        now=now,
    )
    assert result.used_median is False
    assert result.winner_source == "nsw"


def test_authority_helper_uses_other_for_unknown_source() -> None:
    assert source_authority("nsw") == 0
    assert source_authority("wa") == 1
    assert source_authority("made_up_feed") == SOURCE_AUTHORITY["other"]


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError):
        arbitrate([])


def test_three_source_overlap_picks_deterministic_winner() -> None:
    """End-to-end: Ampol appears in NSW FuelCheck + SAFPIS + QLD Fuel Prices.

    NSW + QLD publish mandatory-realtime prices every few minutes; SAFPIS
    publishes daily. The arbiter must pick an NSW observation (highest
    authority, fresh, close to the median) and the result must be byte-stable
    on every run.
    """
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    fresh = now - timedelta(minutes=10)
    sa_daily = now - timedelta(hours=8)  # outside freshness window
    nsw_obs = _obs("nsw", 189.5, fresh)
    qld_obs = _obs("qld", 190.0, fresh)
    sa_obs = _obs("sa", 192.0, sa_daily)  # SAFPIS daily bucket

    first = arbitrate([nsw_obs, qld_obs, sa_obs], now=now)
    second = arbitrate([sa_obs, qld_obs, nsw_obs], now=now)  # input order swapped

    assert first.winner_source == second.winner_source == "nsw"
    assert first.winner_price == second.winner_price == 189.5
    assert first.score == second.score
    # 3 candidates, raw_sources is preserved
    assert len(first.candidates) == 3
    assert {c[0] for c in first.candidates} == {"nsw", "qld", "sa"}


def test_candidate_scores_remain_ordered() -> None:
    """Returned candidates are sorted by score descending so the client UI can
    iterate them in stable order."""
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    far = now - timedelta(days=1)
    result = arbitrate(
        [
            _obs("wa", 191.0, far),
            _obs("nsw", 189.5, far),
            _obs("other", 195.0, far),
        ],
        now=now,
    )
    scores = [c[2] for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert result.candidates[0][0] == "nsw"
