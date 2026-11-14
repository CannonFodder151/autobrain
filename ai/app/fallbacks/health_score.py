"""Deterministic fallback for Vehicle Health Score computation."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class VehicleInputs:
    """Input parameters for health score computation."""
    mileage: int
    age_years: int
    accident_count: int
    service_records: int
    tire_tread_mm: float
    brake_pad_mm: float
    battery_health_pct: int
    fluid_levels_ok: bool
    check_engine_light: bool
    recall_count: int


def compute_health_score(inputs: VehicleInputs) -> int:
    """
    Compute deterministic vehicle health score (0-100).

    Rules:
    - Base score starts at 100
    - Mileage penalty: -1 per 10k miles over 50k
    - Age penalty: -2 per year over 5 years
    - Accident penalty: -15 per accident
    - Service bonus: +2 per service record (max +20)
    - Tire tread: -10 if < 3mm, -5 if < 5mm
    - Brake pads: -10 if < 3mm, -5 if < 5mm
    - Battery: -15 if < 50%, -5 if < 70%
    - Fluids: -10 if not OK
    - Check engine light: -20 if on
    - Recalls: -5 per recall
    """
    score = 100

    if inputs.mileage > 50000:
        score -= (inputs.mileage - 50000) // 10000

    if inputs.age_years > 5:
        score -= (inputs.age_years - 5) * 2

    score -= inputs.accident_count * 15

    service_bonus = min(inputs.service_records * 2, 20)
    score += service_bonus

    if inputs.tire_tread_mm < 3:
        score -= 10
    elif inputs.tire_tread_mm < 5:
        score -= 5

    if inputs.brake_pad_mm < 3:
        score -= 10
    elif inputs.brake_pad_mm < 5:
        score -= 5

    if inputs.battery_health_pct < 50:
        score -= 15
    elif inputs.battery_health_pct < 70:
        score -= 5

    if not inputs.fluid_levels_ok:
        score -= 10

    if inputs.check_engine_light:
        score -= 20

    score -= inputs.recall_count * 5

    return max(0, min(100, score))


def compute_health_score_from_dict(data: dict) -> int:
    """Convenience function accepting a dictionary."""
    inputs = VehicleInputs(
        mileage=data.get("mileage", 0),
        age_years=data.get("age_years", 0),
        accident_count=data.get("accident_count", 0),
        service_records=data.get("service_records", 0),
        tire_tread_mm=data.get("tire_tread_mm", 8.0),
        brake_pad_mm=data.get("brake_pad_mm", 8.0),
        battery_health_pct=data.get("battery_health_pct", 100),
        fluid_levels_ok=data.get("fluid_levels_ok", True),
        check_engine_light=data.get("check_engine_light", False),
        recall_count=data.get("recall_count", 0),
    )
    return compute_health_score(inputs)


if __name__ == "__main__":
    # Self-test
    test_cases = [
        VehicleInputs(30000, 3, 0, 5, 6.0, 6.0, 90, True, False, 0),
        VehicleInputs(120000, 10, 2, 2, 2.0, 2.0, 40, False, True, 3),
        VehicleInputs(50000, 5, 0, 10, 8.0, 8.0, 100, True, False, 0),
    ]

    for i, tc in enumerate(test_cases):
        score = compute_health_score(tc)
        print(f"Test {i+1}: score={score}")

    assert compute_health_score(test_cases[0]) > compute_health_score(test_cases[1])
    assert compute_health_score(test_cases[2]) == 100
    print("All tests passed")