"""AUT-5318: deterministic next-due for the auto-suggested service.

The auto-suggest used to silently create nothing when the AI gateway
was unreachable or the vehicle had no canonical service history. The
deterministic interval must work standalone — no AI, no DB.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret")

from datetime import date, timedelta  # noqa: E402

from app.models.service import ServiceRecord  # noqa: E402
from app.services.odometer import deterministic_next_due  # noqa: E402


def _svc(odo: int, days_ago: int = 0, service_type: str = "scheduled") -> ServiceRecord:
    return ServiceRecord(
        vehicle_id="v",
        service_date=date.today() - timedelta(days=days_ago),
        odometer_km=odo,
        service_type=service_type,
        status="completed",
    )


def test_no_history_baselines_to_next_manufacturer_interval() -> None:
    next_km, next_due = deterministic_next_due([], 5_000)
    assert next_km == 20_000
    assert next_due == date.today() + timedelta(days=365)

    # Mid-interval odo still rounds up to the next full interval.
    assert deterministic_next_due([], 25_000)[0] == 40_000


def test_measured_gap_shortens_the_interval() -> None:
    history = [_svc(30_000, 700), _svc(40_000, 350), _svc(50_000, 10)]
    next_km, _ = deterministic_next_due(history, 50_000)
    assert next_km == 60_000  # 10,000 km measured gap, not the 20k default


def test_duplicate_and_tiny_gaps_are_ignored() -> None:
    history = [_svc(30_000), _svc(30_000), _svc(30_200)]
    next_km, _ = deterministic_next_due(history, 30_200)
    assert next_km == 50_200  # no meaningful gap -> default interval from last reading


def test_overdue_history_is_due_today() -> None:
    next_km, next_due = deterministic_next_due([_svc(40_000, days_ago=400)], 41_000)
    assert next_km == 60_000
    assert next_due == date.today()  # 400 days > 365 -> due immediately


def test_non_canonical_service_types_still_count_as_history() -> None:
    # "repair" rows were filtered out before AUT-5318, killing the feature.
    next_km, _ = deterministic_next_due([_svc(10_000, 200, service_type="repair")], 12_000)
    assert next_km == 30_000
