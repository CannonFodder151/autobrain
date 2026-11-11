"""Developer API v1: API key management, webhooks, and public access (AUT-423)."""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.models.webhook import Webhook, WebhookDelivery, WebhookEventType, WebhookStatus
from app.schemas.developer import (
    ApiKeyCreate,
    ApiKeyOut,
    ApiKeyUpdate,
    WebhookCreate,
    WebhookOut,
    WebhookUpdate,
    WebhookDeliveryOut,
    WebhookTestRequest,
)
from app.services.api_keys import (
    DEFAULT_SCOPES,
    generate_key,
    hash_key,
    key_prefix,
    normalize_scopes,
    serialize_key,
    VALID_SCOPES,
)
from app.services.webhooks import (
    generate_secret,
    process_delivery,
    serialize_delivery,
    serialize_webhook,
    trigger_event,
)
from app.services.rate_limit import _client as _redis_client
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/developer", tags=["developer"])


# --- API Key Management ---

@router.get("/keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List all API keys for the current user."""
    rows = await db.scalars(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()))
    return [serialize_key(k) for k in rows]


@router.post("/keys", response_model=ApiKeyOut, status_code=201)
async def create_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Create a new API key. Returns the key value only once."""
    raw_key = generate_key()
    scopes = normalize_scopes(payload.scopes or DEFAULT_SCOPES)

    key = ApiKey(
        user_id=user.id,
        label=payload.label,
        api_key_prefix=key_prefix(raw_key),
        api_key_hash=hash_key(raw_key),
        scopes=json.dumps(scopes),
        rate_limit=payload.rate_limit,
        rate_window_seconds=payload.rate_window_seconds,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)

    data = serialize_key(key)
    data["key"] = raw_key  # Only returned once!
    return data


@router.get("/keys/{key_id}", response_model=ApiKeyOut)
async def get_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Get a specific API key (without the raw key)."""
    key = await db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="API key not found")
    return serialize_key(key)


@router.patch("/keys/{key_id}", response_model=ApiKeyOut)
async def update_api_key(
    key_id: str,
    payload: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Update an API key (label, scopes, rate limits). Cannot change the key value."""
    key = await db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="API key not found")

    data = payload.model_dump(exclude_unset=True)
    if "scopes" in data:
        data["scopes"] = json.dumps(normalize_scopes(data["scopes"]))
    for field, value in data.items():
        setattr(key, field, value)

    await db.commit()
    await db.refresh(key)
    return serialize_key(key)


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Revoke (soft-delete) an API key."""
    key = await db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="API key not found")

    key.revoked_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/scopes", response_model=list[str])
async def list_valid_scopes() -> list[str]:
    """List all valid scope strings for API keys."""
    return sorted(VALID_SCOPES)


# --- Webhook Management ---

@router.get("/webhooks", response_model=list[WebhookOut])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List all webhooks for the current user."""
    rows = await db.scalars(select(Webhook).where(Webhook.user_id == user.id).order_by(Webhook.created_at.desc()))
    return [serialize_webhook(w) for w in rows]


@router.post("/webhooks", response_model=WebhookOut, status_code=201)
async def create_webhook(
    payload: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Create a new webhook registration."""
    secret = generate_secret()
    events = json.dumps(payload.events)

    webhook = Webhook(
        user_id=user.id,
        label=payload.label,
        url=payload.url,
        events=events,
        secret=secret,
        secret_prefix=secret[:8],
        max_retries=payload.max_retries or 5,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    data = serialize_webhook(webhook, include_secret=True)
    return data


@router.get("/webhooks/{webhook_id}", response_model=WebhookOut)
async def get_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Get a specific webhook."""
    webhook = await db.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return serialize_webhook(webhook, include_secret=True)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: str,
    payload: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Update a webhook (label, URL, events, status, max_retries)."""
    webhook = await db.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    data = payload.model_dump(exclude_unset=True)
    if "events" in data:
        data["events"] = json.dumps(data["events"])
    for field, value in data.items():
        setattr(webhook, field, value)

    webhook.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(webhook)
    return serialize_webhook(webhook, include_secret=True)


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a webhook and its delivery history."""
    webhook = await db.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Delete associated deliveries first
    await db.execute(select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id).delete())
    await db.delete(webhook)
    await db.commit()


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookDeliveryOut)
async def test_webhook(
    webhook_id: str,
    payload: Optional[WebhookTestRequest] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Send a test payload to the webhook endpoint."""
    import httpx

    webhook = await db.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if webhook.status != WebhookStatus.ACTIVE.value:
        raise HTTPException(status_code=400, detail=f"Webhook is {webhook.status}; must be active to test")

    test_data = payload.model_dump() if payload else {
        "message": "This is a test webhook from AutoBrain",
        "test": True,
    }

    # Enqueue and immediately process
    delivery = await enqueue_test_delivery(db, webhook, "webhook.test", test_data)

    async with httpx.AsyncClient() as client:
        await process_delivery(db, delivery, webhook, client)

    await db.refresh(delivery)
    return serialize_delivery(delivery)


async def enqueue_test_delivery(
    db: AsyncSession,
    webhook: Webhook,
    event_type: str,
    data: dict,
) -> WebhookDelivery:
    """Enqueue a test delivery (bypasses trigger_event user check)."""
    from app.services.webhooks import build_webhook_payload, sign_payload

    payload_dict = build_webhook_payload(event_type, data)
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

    payload_dict["delivery_id"] = delivery.id
    delivery.payload = json.dumps(payload_dict, separators=(",", ":"))
    await db.commit()
    return delivery


@router.get("/webhooks/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_webhook_deliveries(
    webhook_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List recent deliveries for a webhook."""
    webhook = await db.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    rows = list((await db.scalars(stmt)).all())
    return [serialize_delivery(d) for d in rows]


# --- Webhook event types reference ---

@router.get("/webhooks/events", response_model=list[str])
async def list_webhook_events() -> list[str]:
    """List all available webhook event types."""
    return sorted([e.value for e in WebhookEventType])


# --- Public API Access via API Key ---

async def get_user_from_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate a request via X-API-Key header.

    Returns the owning User if valid. Raises 401 if invalid/missing.
    """
    from app.services.api_keys import find_key_by_raw, touch_last_used, has_scope

    supplied = request.headers.get("X-API-Key", "")
    if not supplied:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key = await find_key_by_raw(db, supplied)
    if not key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Check rate limit for this specific key
    await check_api_key_rate_limit(db, key)

    # Update last_used_at
    await touch_last_used(db, key)

    # Get the user
    user = await db.get(User, key.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Attach key info to request state for scope checks
    request.state.api_key = key
    return user


async def check_api_key_rate_limit(db: AsyncSession, key: ApiKey) -> None:
    """Enforce per-key rate limit using Redis."""
    if not key.rate_limit or not key.rate_window_seconds:
        return  # No limit configured

    from app.core.config import settings
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    r = _redis_client()
    try:
        now = int(datetime.now(timezone.utc).timestamp())
        window_key = f"apikey:{key.id}:{now // key.rate_window_seconds}"
        pipe = r.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, key.rate_window_seconds * 2)
        count = int((await pipe.execute())[0])

        if count > key.rate_limit:
            logger.warning("api_key_rate_limit_exceeded", key_id=key.id, count=count, limit=key.rate_limit)
            raise HTTPException(
                status_code=429,
                detail=f"API key rate limit exceeded ({key.rate_limit} requests per {key.rate_window_seconds}s)",
                headers={"Retry-After": str(key.rate_window_seconds)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("api_key_rate_limit_unavailable", key_id=key.id, error=str(exc))
        # Fail open for rate limit (don't block legitimate traffic if Redis is down)
    finally:
        await r.aclose()


def require_scope(scope: str):
    """Dependency factory to require a specific scope on the API key."""
    async def _check(
        request: Request,
        user: User = Depends(get_user_from_api_key),
    ) -> User:
        from app.services.api_keys import has_scope
        key = getattr(request.state, "api_key", None)
        if not key or not has_scope(key, scope):
            raise HTTPException(
                status_code=403,
                detail=f"API key missing required scope: {scope}",
            )
        return user
    return _check