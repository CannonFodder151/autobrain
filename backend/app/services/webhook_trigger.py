"""Background webhook trigger helper (AUT-423).

Fires webhook events after writes in existing routes. Uses a fire-and-forget
pattern so webhook delivery latency never blocks the user-facing response.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


def fire_webhook_event(
    db: AsyncSession,
    event_type: str,
    data: dict[str, Any],
    vehicle_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """Schedule a webhook event to fire in the background.

    Uses asyncio.create_task if a loop is running, otherwise logs a warning.
    """
    from app.services.webhooks import trigger_event

    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(_fire_event(db, event_type, data, vehicle_id, user_id))
    except RuntimeError:
        logger.warning(
            "webhook_event_no_running_loop",
            event_type=event_type,
            user_id=user_id,
        )


async def _fire_event(
    db: AsyncSession,
    event_type: str,
    data: dict[str, Any],
    vehicle_id: Optional[str],
    user_id: Optional[str],
) -> None:
    """Internal: trigger webhook events for matching webhooks."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            await trigger_event(db, client, event_type, data, vehicle_id, user_id)
    except Exception as exc:
        logger.error(
            "webhook_trigger_failed",
            event_type=event_type,
            error=str(exc),
        )


def fire_vehicle_created(db: AsyncSession, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "vehicle.created",
        {"vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_vehicle_updated(db: AsyncSession, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "vehicle.updated",
        {"vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_vehicle_deleted(db: AsyncSession, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "vehicle.deleted",
        {"vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_service_completed(db: AsyncSession, service_id: str, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "service.completed",
        {"service_id": service_id, "vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_service_due(db: AsyncSession, service_id: str, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "service.due",
        {"service_id": service_id, "vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_fuel_entry(db: AsyncSession, fuel_id: str, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "fuel.entry",
        {"fuel_id": fuel_id, "vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_fuel_receipt(db: AsyncSession, receipt_id: str, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "fuel.receipt",
        {"receipt_id": receipt_id, "vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_rego_expiry(db: AsyncSession, vehicle_id: str, user_id: str, expiry_date: str) -> None:
    fire_webhook_event(
        db, "rego.expiry",
        {"vehicle_id": vehicle_id, "expiry_date": expiry_date},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_diagnostic_created(db: AsyncSession, diagnostic_id: str, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "diagnostic.created",
        {"diagnostic_id": diagnostic_id, "vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_diagnostic_resolved(db: AsyncSession, diagnostic_id: str, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "diagnostic.resolved",
        {"diagnostic_id": diagnostic_id, "vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_odometer_updated(db: AsyncSession, vehicle_id: str, user_id: str, odometer_km: int) -> None:
    fire_webhook_event(
        db, "odometer.updated",
        {"vehicle_id": vehicle_id, "odometer_km": odometer_km},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )


def fire_logbook_trip(db: AsyncSession, entry_id: str, vehicle_id: str, user_id: str) -> None:
    fire_webhook_event(
        db, "logbook.trip",
        {"entry_id": entry_id, "vehicle_id": vehicle_id},
        vehicle_id=vehicle_id,
        user_id=user_id,
    )