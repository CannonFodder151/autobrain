"""Stripe billing: plans, checkout sessions, customer portal, webhook handling.

The hosted instance uses Stripe subscriptions to grant plan access. A valid
subscription promotes the account (free_account=False + per-plan vehicle cap);
cancelling or letting it lapse demotes back to the free tier. Everything is
driven by price IDs held in the environment (STRIPE_PRICE_*).
"""

import logging

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

FREE_PLAN = "free"

# plan_key -> what a subscription to that plan grants
PLANS: dict[str, dict] = {
    "enthusiast": {"name": "Enthusiast", "max_vehicles": 1},
    "garage": {"name": "Garage", "max_vehicles": 5},
}

# Stripe statuses that still grant paid access (past_due keeps access while
# Stripe retries the card; unpaid/canceled do not).
ACTIVE_STATUSES = frozenset({"active", "trialing", "past_due"})

_client: stripe.StripeClient | None = None


def get_client() -> stripe.StripeClient:
    global _client
    if _client is None:
        if not settings.STRIPE_SECRET_KEY:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured")
        _client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
    return _client


def price_for(plan_key: str, billing: str) -> str | None:
    """Stripe price ID for a plan + billing interval ('' when unset)."""
    table = {
        "enthusiast": {
            "monthly": settings.STRIPE_PRICE_ENTHUSIAST_MONTHLY,
            "yearly": settings.STRIPE_PRICE_ENTHUSIAST_YEARLY,
        },
        "garage": {
            "monthly": settings.STRIPE_PRICE_GARAGE_MONTHLY,
            "yearly": settings.STRIPE_PRICE_GARAGE_YEARLY,
        },
    }
    return table.get(plan_key, {}).get(billing) or None


def plan_for_price(price_id: str) -> str | None:
    for plan_key in PLANS:
        if price_for(plan_key, "monthly") == price_id or price_for(plan_key, "yearly") == price_id:
            return plan_key
    return None


def plan_for_user(user: User) -> str:
    """Resolve the current plan key from a user's subscription state."""
    if not user.free_account:
        if user.stripe_price_id and user.stripe_subscription_status in ACTIVE_STATUSES:
            return plan_for_price(user.stripe_price_id) or FREE_PLAN
        return FREE_PLAN  # admin-granted access without a Stripe sub
    return FREE_PLAN


def has_paid_subscription(user: User) -> bool:
    return (
        bool(user.stripe_subscription_id)
        and user.stripe_subscription_status in ACTIVE_STATUSES
    )


def apply_plan(user: User, plan_key: str) -> None:
    plan = PLANS[plan_key]
    user.free_account = False
    user.max_vehicles = plan["max_vehicles"]


def apply_free(user: User) -> None:
    user.free_account = True
    user.max_vehicles = 1


async def create_checkout_session(
    db: AsyncSession, user: User, plan_key: str, billing: str
) -> str:
    """Find-or-create the Stripe customer and open a Checkout subscription."""
    if plan_key not in PLANS:
        raise ValueError("Unknown plan")
    price_id = price_for(plan_key, billing)
    if not price_id:
        raise ValueError("Billing is not configured for that plan")
    client = get_client()

    customer_id = user.stripe_customer_id
    if not customer_id:
        existing = client.customers.list(params={"email": user.email, "limit": 1})
        customer_id = existing.data[0].id if existing.data else None
        if not customer_id:
            customer_id = client.customers.create(
                params={
                    "email": user.email,
                    "name": user.display_name,
                    "metadata": {"user_id": user.id},
                }
            ).id
        user.stripe_customer_id = customer_id
        await db.commit()

    base = settings.APP_BASE_URL.rstrip("/")
    session = client.checkout.sessions.create(
        params={
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": user.id,
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": f"{base}/?checkout=success",
            "cancel_url": f"{base}/",
            "metadata": {"plan": plan_key, "billing": billing},
        }
    )
    return session.url


async def create_portal_session(user: User) -> str:
    """Customer portal URL so users can change/cancel the subscription."""
    if not user.stripe_customer_id:
        raise ValueError("No billing account on file")
    base = settings.APP_BASE_URL.rstrip("/")
    session = get_client().billing_portal.sessions.create(
        params={
            "customer": user.stripe_customer_id,
            "return_url": f"{base}/?billing=done",
        }
    )
    return session.url


def construct_event(payload: bytes, sig_header: str):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )


async def handle_event(db: AsyncSession, event) -> None:
    # StripeObject supports []/attr access but not .get(); normalise to dicts.
    event = event.to_dict() if hasattr(event, "to_dict") else event
    etype = event.get("type")
    obj = event.get("data", {}).get("object", {})
    if etype == "checkout.session.completed":
        await _on_checkout_completed(db, obj)
    elif etype in ("customer.subscription.created", "customer.subscription.updated"):
        await _on_subscription_event(db, obj)
    elif etype == "customer.subscription.deleted":
        await _on_subscription_event(db, obj)
    else:
        logger.info("stripe_event_ignored", extra={"type": etype})


async def _on_subscription_event(db: AsyncSession, sub) -> None:
    user = await _user_by_customer_or_id(db, sub.get("customer"), None)
    if user:
        await _apply_subscription(db, user, sub)


async def _on_checkout_completed(db: AsyncSession, session) -> None:
    if session.get("mode") != "subscription" or not session.get("subscription"):
        return
    sub_id = session["subscription"]
    try:
        sub = get_client().subscriptions.retrieve(sub_id).to_dict()
    except stripe.StripeError:
        logger.exception("stripe_subscription_retrieve_failed", extra={"sub": sub_id})
        return
    user = await _user_by_customer_or_id(db, sub.get("customer"), session.get("client_reference_id"))
    if not user:
        return
    old_sub_id = user.stripe_subscription_id
    await _apply_subscription(db, user, sub)
    # Upgrades: a newly completed subscription must replace any previous one,
    # otherwise the account is double-billed during the overlap.
    if old_sub_id and old_sub_id != sub_id:
        try:
            old = get_client().subscriptions.retrieve(old_sub_id)
            if old.status in ACTIVE_STATUSES:
                get_client().subscriptions.cancel(old_sub_id)
                logger.info("stripe_previous_subscription_cancelled", extra={"sub": old_sub_id})
        except stripe.StripeError:
            logger.warning("stripe_previous_subscription_cancel_failed", extra={"sub": old_sub_id})


async def _user_by_customer_or_id(
    db: AsyncSession, customer_id: str | None, user_id_fallback: str | None
) -> User | None:
    user = None
    if customer_id:
        user = await db.scalar(select(User).where(User.stripe_customer_id == customer_id))
    if not user and user_id_fallback:
        user = await db.get(User, str(user_id_fallback))
    if not user:
        logger.warning("stripe_subscription_no_user", extra={"customer": customer_id})
    return user


async def _apply_subscription(db: AsyncSession, user: User, sub) -> None:
    customer_id = sub.get("customer")
    user.stripe_subscription_id = sub.get("id")
    user.stripe_customer_id = customer_id
    user.stripe_subscription_status = sub.get("status")
    items = sub.get("items", {}).get("data", []) if sub.get("items") else []
    price_id = items[0].get("price", {}).get("id") if items else None
    user.stripe_price_id = price_id

    if sub.get("status") in ACTIVE_STATUSES and price_id and plan_for_price(price_id):
        apply_plan(user, plan_for_price(price_id))
    else:
        apply_free(user)
    await db.commit()
    logger.info(
        "stripe_subscription_applied",
        extra={"user": user.id, "status": sub.get("status"), "price": price_id},
    )
