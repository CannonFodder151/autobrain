"""Webhook delivery service (AUT-423).

Handles signing payloads, delivering webhooks with retry/backoff,
and tracking delivery status.
"""

import hmac
import hashlib
import json
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import Webhook, WebhookDelivery, WebhookEventType, WebhookStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# Retry schedule: exponential backoff in minutes (1, 2, 4, 10, 20)
RETRY_SCHEDULE_MINUTES = [1, 2, 4, 10, 20]
DEFAULT_TIMEOUT_SECONDS = 10


def generate_secret() -> str:
    """Generate a webhook signing secret."""
    return secrets.token_hex(32)


def sign_payload(payload: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for a payload."""
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def verify_signature(payload: bytes, secret: str, signature: str) -> bool:
    """Verify a webhook signature in constant time."""
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(signature, expected)


def build_webhook_payload(
    event_type: str,
    data: dict[str, Any],
    vehicle_id: str | None = None,
    delivery_id: str | None = None,
) -> dict[str, Any]:
    """Build the standard webhook payload envelope."""
    envelope = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    if vehicle_id:
        envelope["vehicle_id"] = vehicle_id
    if delivery_id:
        envelope["delivery_id"] = delivery_id
    return envelope


async def enqueue_delivery(
    db: AsyncSession,
    webhook: Webhook,
    event_type: str,
    data: dict[str, Any],
    vehicle_id: str | None = None,
) -> WebhookDelivery:
    """Create a WebhookDelivery record for async processing."""
    payload_dict = build_webhook_payload(event_type, data, vehicle_id)
    payload_json = json.dumps(payload_dict, separators=(",", ":"))
    payload_bytes = payload_json.encode("utf-8")
    signature = sign_payload(payload_bytes, webhook.secret)

    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event_type=event_type,
        payload=payload_json,
        attempts=0,
    )
    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)

    # Add delivery_id to payload for idempotency
    payload_dict["delivery_id"] = delivery.id
    delivery.payload = json.dumps(payload_dict, separators=(",", ":"))
    await db.commit()

    logger.info(
        "webhook_enqueued",
        webhook_id=webhook.id,
        delivery_id=delivery.id,
        event_type=event_type,
    )
    return delivery


async def deliver_one(
    db: AsyncSession,
    delivery: WebhookDelivery,
    webhook: Webhook,
    http_client,
) -> tuple[bool, Optional[str]]:
    """Attempt a single delivery. Returns (success, error_message)."""
    payload_bytes = delivery.payload.encode("utf-8")
    signature = sign_payload(payload_bytes, webhook.secret)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"AutoBrain-Webhooks/{settings.APP_VERSION}",
        "X-Autobrain-Signature": signature,
        "X-Autobrain-Event": delivery.event_type,
        "X-Autobrain-Delivery": delivery.id,
    }

    try:
        resp = await http_client.post(
            webhook.url,
            content=payload_bytes,
            headers=headers,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        http_status = resp.status_code
        delivery.http_status = http_status

        if 200 <= http_status < 300:
            return True, None
        else:
            error = f"HTTP {http_status}: {resp.text[:500]}"
            return False, error

    except Exception as exc:
        error = str(exc)
        logger.warning(
            "webhook_delivery_exception",
            delivery_id=delivery.id,
            webhook_id=webhook.id,
            error=error,
        )
        return False, error


async def process_delivery(
    db: AsyncSession,
    delivery: WebhookDelivery,
    http_client,
) -> None:
    """Process a single delivery with retry logic."""
    webhook = await db.get(Webhook, delivery.webhook_id)
    if not webhook:
        delivery.error = "Webhook not found"
        await db.commit()
        return

    # Check if webhook is still active
    if webhook.status != WebhookStatus.ACTIVE.value:
        delivery.error = f"Webhook status is {webhook.status}"
        await db.commit()
        return

    success, error = await deliver_one(db, delivery, webhook, http_client)
    delivery.attempts += 1

    if success:
        delivery.delivered_at = datetime.now(timezone.utc)
        delivery.error = None
        webhook.consecutive_failures = 0
        webhook.last_delivered_at = datetime.now(timezone.utc)
        webhook.last_failure_reason = None
        logger.info(
            "webhook_delivered",
            delivery_id=delivery.id,
            webhook_id=webhook.id,
            event_type=delivery.event_type,
        )
    else:
        delivery.error = error
        webhook.consecutive_failures += 1
        webhook.last_failed_at = datetime.now(timezone.utc)
        webhook.last_failure_reason = error[:500]

        # Schedule retry if under max_retries
        if delivery.attempts <= webhook.max_retries:
            delay_min = RETRY_SCHEDULE_MINUTES[min(delivery.attempts - 1, len(RETRY_SCHEDULE_MINUTES) - 1)]
            delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=delay_min)
            logger.info(
                "webhook_retry_scheduled",
                delivery_id=delivery.id,
                webhook_id=webhook.id,
                attempt=delivery.attempts,
                next_retry=delivery.next_retry_at.isoformat(),
            )
        else:
            # Max retries exceeded - pause webhook
            delivery.next_retry_at = None
            webhook.status = WebhookStatus.PAUSED.value
            logger.warning(
                "webhook_paused_max_retries",
                webhook_id=webhook.id,
                delivery_id=delivery.id,
                attempts=delivery.attempts,
            )

    await db.commit()


async def process_pending_deliveries(db: AsyncSession, http_client) -> int:
    """Process all deliveries that are due for retry. Returns count processed."""
    now = datetime.now(timezone.utc)
    stmt = select(WebhookDelivery).where(
        (WebhookDelivery.next_retry_at != None) & (WebhookDelivery.next_retry_at <= now)
    )
    deliveries = list((await db.scalars(stmt)).all())

    processed = 0
    for delivery in deliveries:
        await process_delivery(db, delivery, http_client)
        processed += 1

    return processed


async def trigger_event(
    db: AsyncSession,
    http_client,
    event_type: str,
    data: dict[str, Any],
    vehicle_id: str | None = None,
    user_id: str | None = None,
) -> int:
    """Trigger a webhook event for all matching active webhooks.

    If user_id is provided, only webhooks owned by that user are triggered.
    Returns the number of deliveries enqueued.
    """
    stmt = select(Webhook).where(
        Webhook.status == WebhookStatus.ACTIVE.value,
    )
    if user_id:
        stmt = stmt.where(Webhook.user_id == user_id)

    webhooks = list((await db.scalars(stmt)).all())
    if not webhooks:
        return 0

    enqueued = 0
    for webhook in webhooks:
        try:
            events = json.loads(webhook.events or "[]")
        except (json.JSONDecodeError, TypeError):
            continue

        if event_type not in events:
            continue

        await enqueue_delivery(db, webhook, event_type, data, vehicle_id)
        enqueued += 1

    return enqueued


def serialize_webhook(webhook: Webhook, *, include_secret: bool = False) -> dict:
    """Serialize a Webhook for API responses."""
    try:
        events = json.loads(webhook.events or "[]")
    except (json.JSONDecodeError, TypeError):
        events = []

    data = {
        "id": webhook.id,
        "label": webhook.label,
        "url": webhook.url,
        "events": events,
        "secret_prefix": webhook.secret_prefix if not include_secret else webhook.secret,
        "status": webhook.status,
        "max_retries": webhook.max_retries,
        "consecutive_failures": webhook.consecutive_failures,
        "last_delivered_at": webhook.last_delivered_at.isoformat() if webhook.last_delivered_at else None,
        "last_failed_at": webhook.last_failed_at.isoformat() if webhook.last_failed_at else None,
        "last_failure_reason": webhook.last_failure_reason,
        "created_at": webhook.created_at.isoformat() if webhook.created_at else None,
        "updated_at": webhook.updated_at.isoformat() if webhook.updated_at else None,
    }
    if include_secret:
        data["secret"] = webhook.secret
    return data


def serialize_delivery(delivery: WebhookDelivery) -> dict:
    """Serialize a WebhookDelivery for API responses."""
    return {
        "id": delivery.id,
        "webhook_id": delivery.webhook_id,
        "event_type": delivery.event_type,
        "payload": json.loads(delivery.payload) if delivery.payload else None,
        "http_status": delivery.http_status,
        "error": delivery.error,
        "attempts": delivery.attempts,
        "next_retry_at": delivery.next_retry_at.isoformat() if delivery.next_retry_at else None,
        "created_at": delivery.created_at.isoformat() if delivery.created_at else None,
        "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
    }