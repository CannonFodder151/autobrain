"""Unit tests for Ownership Advisor service."""

from backend.app.services.ownership_advisor import run_all, run_advisor, AdvisorInput


def test_all_modes():
    i = AdvisorInput(vehicle_id="VIN1")
    res = run_all(i)
    modes = [r.mode for r in res]
    assert modes == ["value", "replace", "upgrade", "finance", "dream", "ai_advisor"]


def test_run_advisor_unknown():
    i = AdvisorInput(vehicle_id="VIN1")
    try:
        run_advisor(i, "nope")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_deterministic_values():
    i = AdvisorInput(vehicle_id="VIN1", current_value=10000.0, replacement_cost=20000.0)
    r = run_advisor(i, "finance")
    assert r.value > 0
    assert "monthly_payment" in r.breakdown