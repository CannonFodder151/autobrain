"""Unit + property-based tests for the deterministic Vehicle Health Score engine.

Covers the rule-based fallback in app/fallbacks/health_score.py:
  compute_health_score(VehicleInputs) -> int  (0-100)
  compute_health_score_from_dict(dict) -> int

Rules (source of truth: app/fallbacks/health_score.py:22-75):
  base 100
  - mileage:   -1 per 10k miles over 50k
  - age:       -2 per year over 5 years
  - accidents: -15 per accident
  - service:   +2 per record, capped at +20
  - tires:     -10 if <3mm, -5 if <5mm
  - brakes:    -10 if <3mm, -5 if <5mm
  - battery:   -15 if <50%, -5 if <70%
  - fluids:    -10 if not OK
  - CEL:       -20 if on
  - recalls:   -5 per recall
  clamped to [0, 100]
"""

import random
import time

from app.fallbacks.health_score import (
    VehicleInputs,
    compute_health_score,
    compute_health_score_from_dict,
)


def _score(**overrides) -> int:
    base = dict(
        mileage=0,
        age_years=0,
        accident_count=0,
        service_records=0,
        tire_tread_mm=8.0,
        brake_pad_mm=8.0,
        battery_health_pct=100,
        fluid_levels_ok=True,
        check_engine_light=False,
        recall_count=0,
    )
    base.update(overrides)
    return compute_health_score(VehicleInputs(**base))


# ---------------------------------------------------------------------------
# Unit tests — each scoring rule in isolation
# ---------------------------------------------------------------------------


def test_base_perfect_vehicle_clamped_to_100():
    assert _score() == 100


def test_service_bonus_capped_at_20():
    # Start from a penalised baseline (2 accidents => 70) so the bonus is
    # observable below the 100 clamp: +2/record up to a +20 cap.
    assert _score(accident_count=2, service_records=0) == 70
    assert _score(accident_count=2, service_records=5) == 80    # +10
    assert _score(accident_count=2, service_records=10) == 90   # +20 (cap hit)
    assert _score(accident_count=2, service_records=20) == 90   # still capped
    assert _score(accident_count=2, service_records=100) == 90  # cap holds


def test_mileage_penalty_over_50k():
    assert _score(mileage=50000) == 100      # boundary: not > 50k
    assert _score(mileage=50001) == 100      # still < 10k over => 0
    assert _score(mileage=60000) == 99       # (10000)//10000 = 1
    assert _score(mileage=150000) == 90      # (100000)//10000 = 10


def test_age_penalty_over_5_years():
    assert _score(age_years=5) == 100        # boundary: not > 5
    assert _score(age_years=6) == 98         # -2
    assert _score(age_years=10) == 90        # 5 * 2 = 10


def test_accident_penalty():
    assert _score(accident_count=0) == 100
    assert _score(accident_count=1) == 85    # -15
    assert _score(accident_count=3) == 55    # -45


def test_tire_tread_penalty_boundaries():
    assert _score(tire_tread_mm=8.0) == 100  # no penalty
    assert _score(tire_tread_mm=5.0) == 100  # boundary: 5 not < 5
    assert _score(tire_tread_mm=4.9) == 95   # -5 (>=3, <5)
    assert _score(tire_tread_mm=3.0) == 95   # -5 (3 < 5)
    assert _score(tire_tread_mm=2.9) == 90   # -10 (<3)


def test_brake_pad_penalty_boundaries():
    assert _score(brake_pad_mm=8.0) == 100
    assert _score(brake_pad_mm=5.0) == 100
    assert _score(brake_pad_mm=4.9) == 95
    assert _score(brake_pad_mm=3.0) == 95
    assert _score(brake_pad_mm=2.9) == 90


def test_battery_health_penalty_boundaries():
    assert _score(battery_health_pct=100) == 100
    assert _score(battery_health_pct=70) == 100  # boundary: 70 not < 70
    assert _score(battery_health_pct=69) == 95   # -5 (<70)
    assert _score(battery_health_pct=50) == 95   # -5 (<70, not <50)
    assert _score(battery_health_pct=49) == 85   # -15 (<50)


def test_fluid_levels_and_check_engine_light():
    assert _score(fluid_levels_ok=True) == 100
    assert _score(fluid_levels_ok=False) == 90   # -10
    assert _score(check_engine_light=False) == 100
    assert _score(check_engine_light=True) == 80   # -20


def test_recall_penalty():
    assert _score(recall_count=0) == 100
    assert _score(recall_count=1) == 95    # -5
    assert _score(recall_count=4) == 80    # -20


# ---------------------------------------------------------------------------
# Combined / historical-data scenarios
# ---------------------------------------------------------------------------


def test_high_mileage_old_vehicle_many_accidents_clamped_to_zero():
    # mileage 200k (-15), age 20 (-30), accidents 3 (-45), tires/brakes/battery
    # poor (-10-10-15), fluids not ok (-10), CEL on (-20), recalls 10 (-50)
    assert _score(
        mileage=200000, age_years=20, accident_count=3, service_records=0,
        tire_tread_mm=2.0, brake_pad_mm=2.0, battery_health_pct=30,
        fluid_levels_ok=False, check_engine_light=True, recall_count=10,
    ) == 0


def test_excellent_vehicle_stays_at_100_despite_service_bonus():
    # Service bonus pushes raw above 100; clamp keeps it at 100.
    assert _score(service_records=100) == 100


# ---------------------------------------------------------------------------
# dict-based entry point — edge cases (no data / partial data / defaults)
# ---------------------------------------------------------------------------


def test_from_dict_empty_uses_sensible_defaults_score_100():
    assert compute_health_score_from_dict({}) == 100


def test_from_dict_partial_mileage_only():
    assert compute_health_score_from_dict({"mileage": 60000}) == 99


def test_from_dict_partial_missing_fields_treated_as_best_case():
    # Only a bad battery supplied; everything else defaults to best-case.
    assert compute_health_score_from_dict({"battery_health_pct": 40}) == 85


def test_from_dict_full_payload_matches_dataclass():
    payload = {
        "mileage": 120000, "age_years": 10, "accident_count": 2,
        "service_records": 2, "tire_tread_mm": 2.0, "brake_pad_mm": 2.0,
        "battery_health_pct": 40, "fluid_levels_ok": False,
        "check_engine_light": True, "recall_count": 3,
    }
    assert compute_health_score_from_dict(payload) == 0
    assert compute_health_score_from_dict(payload) == compute_health_score(
        VehicleInputs(**payload)
    )


# ---------------------------------------------------------------------------
# Property-based: score is always within [0, 100]
# ---------------------------------------------------------------------------


def test_score_always_within_bounds():
    rng = random.Random(20260101)
    for _ in range(2000):
        inputs = VehicleInputs(
            mileage=rng.randint(0, 500000),
            age_years=rng.randint(0, 30),
            accident_count=rng.randint(0, 10),
            service_records=rng.randint(0, 50),
            tire_tread_mm=rng.uniform(0, 10),
            brake_pad_mm=rng.uniform(0, 10),
            battery_health_pct=rng.randint(0, 100),
            fluid_levels_ok=rng.choice([True, False]),
            check_engine_light=rng.choice([True, False]),
            recall_count=rng.randint(0, 20),
        )
        score = compute_health_score(inputs)
        assert 0 <= score <= 100, score


def test_from_dict_score_always_within_bounds():
    rng = random.Random(20260202)
    for _ in range(2000):
        payload = {
            "mileage": rng.randint(0, 500000),
            "age_years": rng.randint(0, 30),
            "accident_count": rng.randint(0, 10),
            "service_records": rng.randint(0, 50),
            "tire_tread_mm": rng.uniform(0, 10),
            "brake_pad_mm": rng.uniform(0, 10),
            "battery_health_pct": rng.randint(0, 100),
            "fluid_levels_ok": rng.choice([True, False]),
            "check_engine_light": rng.choice([True, False]),
            "recall_count": rng.randint(0, 20),
        }
        score = compute_health_score_from_dict(payload)
        assert 0 <= score <= 100, score


# ---------------------------------------------------------------------------
# Performance benchmark
# ---------------------------------------------------------------------------


def test_compute_health_score_performance():
    rng = random.Random(20260303)
    inputs = [
        VehicleInputs(
            mileage=rng.randint(0, 500000),
            age_years=rng.randint(0, 30),
            accident_count=rng.randint(0, 10),
            service_records=rng.randint(0, 50),
            tire_tread_mm=rng.uniform(0, 10),
            brake_pad_mm=rng.uniform(0, 10),
            battery_health_pct=rng.randint(0, 100),
            fluid_levels_ok=rng.choice([True, False]),
            check_engine_light=rng.choice([True, False]),
            recall_count=rng.randint(0, 20),
        )
        for _ in range(2000)
    ]

    start = time.perf_counter()
    for inp in inputs:
        compute_health_score(inp)
    elapsed = time.perf_counter() - start

    # Pure-python rule engine should compute thousands of scores well under
    # this generous ceiling; fail loudly if it regresses.
    assert elapsed < 5.0, f"too slow: {elapsed:.3f}s for {len(inputs)} scores"