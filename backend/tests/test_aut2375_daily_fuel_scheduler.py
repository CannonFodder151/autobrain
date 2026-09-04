"""AUT-2375 — minimal scheduler + history contract tests (DB-free, no model init).

These tests intentionally avoid importing ``app.models`` (which on main is
broken by the pre-existing AUT-2277 duplicate ``FuelPrice`` table claim —
tracked separately). They verify only the parts of the change that don't
require a Postgres-backed SQLAlchemy import.

Run with: pytest tests/test_aut2375_daily_fuel_scheduler.py -x
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


def test_celery_app_beat_uses_sydney_timezone_for_off_peak_cron() -> None:
    """AUT-2375: 02:00 AEST off-peak window means the Celery timezone must be
    Australia/Sydney, not UTC. Without this, the cron would fire at 02:00 UTC
    = 13:00 AEST and miss the off-peak window."""
    from app.workers.celery_app import celery_app

    assert celery_app.conf.timezone == "Australia/Sydney"


def test_celery_app_daily_fuel_ingest_is_a_cron_at_02_00() -> None:
    """The daily schedule entry must be a crontab(hour=2, minute=0) — NOT the
    6-hour fixed interval we previously had (60*60*6), which would re-hit the
    upstream fuel APIs every 6h for no UX gain (server serves cached rows)."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "fuel-ingest-all-daily" in schedule
    entry = schedule["fuel-ingest-all-daily"]
    assert entry["task"] == "app.workers.tasks.ingest_fuel_all"
    sched = entry["schedule"]
    assert hasattr(sched, "hour") and hasattr(sched, "minute"), (
        f"expected celery.schedules.crontab, got {type(sched).__name__}"
    )
    assert (sched.hour, sched.minute) == ({2}, {0})  # crontab wraps in sets


def test_per_source_tasks_are_registered_for_manual_retry() -> None:
    """Operators must be able to ``.delay()`` a per-state ingest for retries
    without re-running the whole sweep."""
    from app.workers import tasks as worker_tasks

    for source in ("wa", "nsw", "qld"):
        fn = getattr(worker_tasks, f"ingest_fuel_{source}", None)
        assert fn is not None, f"missing ingest_fuel_{source}"
        # Celery @shared_task adds .delay / .apply_async.
        assert hasattr(fn, "delay"), f"ingest_fuel_{source} not a Celery task"


def test_fuel_feeds_exposes_30_day_retention_constant() -> None:
    """The /history endpoint's 30-day window comes from this constant, so the
    retention is the same everywhere (no magic numbers)."""
    from app.services.fuel_feeds import PRICE_HISTORY_DAYS

    assert PRICE_HISTORY_DAYS == 30