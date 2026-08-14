"""Billing routes: Stripe Checkout, customer portal, webhooks, and store-native
IAP (Apple App Store / Google Play) for the mobile store builds.

The Stripe webhook is the source of truth for web tier changes; store IAP
purchases are verified against the store APIs by /billing/iap/verify and
recorded server-side (verify-on-refresh keeps renewals/refunds propagating on
GET /auth/me — see app/services/iap.py).
"""

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import (
    CheckoutRequest,
    CheckoutResponse,
    IapVerifyRequest,
    IapVerifyResponse,
    PortalResponse,
)
from app.services import billing as svc
from app.services import iap

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

_NOT_CONFIGURED = "Billing is not configured on this server"
_IAP_NOT_CONFIGURED = "In-app purchases are not configured on this server"


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CheckoutResponse:
    """Create a Stripe Checkout session for a subscription and return its URL."""
    try:
        url = await svc.create_checkout_session(
            db, user, payload.plan, payload.billing, payload.promo_code
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("billing_checkout_failed")
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    return CheckoutResponse(url=url)


@router.get("/pricing")
async def pricing() -> dict:
    """Public price catalogue + early-adopter sale info (no auth)."""
    return svc.pricing()


@router.post("/portal", response_model=PortalResponse)
async def customer_portal(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PortalResponse:
    """Customer portal URL to change/cancel the subscription."""
    try:
        url = await svc.create_portal_session(user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    return PortalResponse(url=url)


@router.post("/cancel")
async def cancel_subscription(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Cancel the subscription — access stays until the end of the paid period."""
    try:
        svc.cancel_subscription(user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    return {
        "message": "Subscription cancelled — you keep full access until the end of the billing period."
    }


@router.post("/webhook")
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Stripe webhook endpoint — verifies the signature then applies the event."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = svc.construct_event(payload, sig)
    except RuntimeError:
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")
    await svc.handle_event(db, event)
    return {"received": True}


# --- Store-native IAP (Apple App Store / Google Play) ---


@router.get("/iap/catalog")
async def iap_catalog() -> dict:
    """Public IAP product catalogue for the store builds of the mobile app.

    `enabled` is false until IAP credentials are configured — the mobile app
    then falls back to the Stripe browser purchase path (AUT-610).
    """
    return iap.catalog()


@router.post("/iap/verify", response_model=IapVerifyResponse)
async def iap_verify(
    payload: IapVerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IapVerifyResponse:
    """Verify a store transaction against Apple/Google and grant the plan."""
    if not iap.enabled():
        raise HTTPException(status_code=503, detail=_IAP_NOT_CONFIGURED)
    try:
        return await iap.verify_and_grant(
            db,
            user,
            payload.platform,
            payload.product_id,
            payload.transaction_id,
            payload.purchase_token,
        )
    except iap.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/iap/webhook/apple")
async def iap_webhook_apple(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """App Store Server Notifications v2 (JWS-signed signedPayload)."""
    if not iap.apple_configured():
        raise HTTPException(status_code=503, detail=_IAP_NOT_CONFIGURED)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    signed = body.get("signedPayload")
    if not signed:
        raise HTTPException(status_code=400, detail="Missing signedPayload")
    try:
        return await iap.handle_apple_webhook(db, signed)
    except iap.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/iap/webhook/google")
async def iap_webhook_google(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Play Real-time Developer Notification delivered via Pub/Sub push.

    The Pub/Sub push subscription must authenticate with an OIDC token whose
    audience is this endpoint (default: APP_BASE_URL + /api/v1/billing/iap/webhook/google).
    """
    if not iap.google_configured():
        raise HTTPException(status_code=503, detail=_IAP_NOT_CONFIGURED)
    try:
        envelope = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        await iap.verify_google_push_auth(request.headers.get("authorization", ""))
        return await iap.handle_google_webhook(db, envelope)
    except iap.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
