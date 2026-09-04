"""Celery application."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "autobrain",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Australia/Sydney",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "refresh-valuations-daily": {
            "task": "app.workers.tasks.refresh_valuations",
            "schedule": 60 * 60 * 24,
        },
        "daily-notification-checks": {
            "task": "app.workers.tasks.run_daily_notification_checks",
            "schedule": 60 * 60 * 6,
        },
        "scheduled-backup": {
            "task": "app.workers.tasks.scheduled_backup",
            "schedule": 60 * 60 * 24,
        },
        "embedding-backfill": {
            "task": "app.workers.tasks.backfill_entity_embeddings",
            "schedule": 60 * 60 * 24,
        },
        "purge-stale-pending-accounts": {
            "task": "app.workers.tasks.purge_stale_pending_accounts",
            "schedule": 60 * 60 * 6,
        },
        # AUT-2375: once-per-day fuel ingest — server hits each upstream feed
        # ONCE per day and serves cached DB rows to /fuel/stations and
        # /fuel/stations/{id}/history. Off-peak 02:00 AEST (16:00 UTC the day
        # before); the per-source tasks remain triggerable by hand for retries.
        "fuel-ingest-all-daily": {
            "task": "app.workers.tasks.ingest_fuel_all",
            "schedule": crontab(hour=2, minute=0),
        },
        # AUT-2375: deprecated — replaced by fuel-ingest-all-daily above.
        "ingest-fuel-prices": {
            "task": "app.workers.tasks.ingest_fuel_all",
            "schedule": crontab(hour=2, minute=0),
        },
        "poll-nsw-fuel-prices": {
            "task": "app.workers.tasks.poll_nsw_fuel_prices",
            "schedule": 60 * 60 * 24,
        },
        "refresh-sca-parts-cache": {
            "task": "app.workers.tasks.refresh_sca_parts_cache",
            "schedule": crontab(hour=0, minute=0),
        },
    },
)