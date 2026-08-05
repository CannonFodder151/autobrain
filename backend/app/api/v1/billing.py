"""Billing routes: Stripe Checkout, customer portal, and webhooks.

The webhook is the source of truth for tier changes — it promotes an account
when a subscription becomes active and demotes it back to the free tier when
the subscription is cancelled or lapses. Webhook signature verification is
mandatory (STRIPE_WEBHOOK_SECRET); events are rejected when it is unset.
"""

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import CheckoutRequest, CheckoutResponse, PortalResponse
from app.services import billing as svc

router = APIRouter(prefix="/billing", tags=["billing"])

_NOT_CONFIGURED = "Billing is not configured on this server"


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CheckoutResponse:
    """Create a Stripe Checkout session for a subscription and return its URL."""
    try:
        url = await svc.create_checkout_session(db, user, payload.plan, payload.billing)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    return CheckoutResponse(url=url)


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
