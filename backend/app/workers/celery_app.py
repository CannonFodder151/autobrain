"""Celery application."""

from celery import Celery

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
    timezone="UTC",
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
    },
)
