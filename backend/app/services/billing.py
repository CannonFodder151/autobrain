"""Stripe billing: plans, checkout sessions, customer portal, webhook handling.

The hosted instance uses Stripe subscriptions to grant plan access. A valid
subscription promotes the account (free_account=False + per-plan vehicle cap);
cancelling or letting it lapse demotes back to the free tier. Everything is
driven by price IDs held in the environment (STRIPE_PRICE_*).
"""

import logging
from datetime import date

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

# Display amounts in AUD cents — the approved prices (AUT-93 plan c36be7d;
# AUD per AUT-523). The Stripe price objects created by scripts/stripe-setup.py
# are the source of truth at checkout; these mirror them for the
# /billing/pricing endpoint so the frontend renders prices without a live
# Stripe round-trip.
CURRENCY = "aud"
PLAN_AMOUNTS: dict[str, dict[str, int]] = {
    "enthusiast": {"monthly": 900, "yearly": 8400},
    "garage": {"monthly": 1900, "yearly": 16800},
}

# Early-adopter sale (AUT-93): 40% off the first 3 months, capped at 100
# subscribers for 6 months after launch. Stripe enforces the cap + window via
# the coupon's max_redemptions/redeem_by; the app auto-applies it to monthly
# checkouts so the discounted price ($5.40 / $11.40) shows without a code.
SALE_PERCENT_OFF = 40
SALE_DURATION_MONTHS = 3
SALE_CAP = 100

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


def sale_active() -> bool:
    """True while the early-adopter sale window is open and wired up."""
    if not settings.STRIPE_PROMO_EARLY_ADOPTER:
        return False
    if not settings.STRIPE_SALE_ENDS_AT:
        return True
    return date.today() <= date.fromisoformat(settings.STRIPE_SALE_ENDS_AT)


def pricing() -> dict:
    """Deterministic price catalogue for the /billing/pricing endpoint."""
    sale = {"active": False, "code": "", "percent_off": 0, "months": 0, "cap": 0}
    if sale_active():
        sale = {
            "active": True,
            "code": settings.STRIPE_PROMO_EARLY_ADOPTER_CODE,
            "percent_off": SALE_PERCENT_OFF,
            "months": SALE_DURATION_MONTHS,
            "cap": SALE_CAP,
            "ends_at": settings.STRIPE_SALE_ENDS_AT or None,
        }
    plans = []
    for key, plan in PLANS.items():
        amounts = PLAN_AMOUNTS[key]
        entry = {
            "key": key,
            "name": plan["name"],
            "max_vehicles": plan["max_vehicles"],
            "monthly": amounts["monthly"],
            "yearly": amounts["yearly"],
        }
        if sale["active"]:
            entry["sale_monthly"] = _discounted(amounts["monthly"], SALE_PERCENT_OFF)
        plans.append(entry)
    return {"currency": CURRENCY, "sale": sale, "plans": plans}


def _discounted(amount_cents: int, percent_off: int) -> int:
    return round(amount_cents * (100 - percent_off) / 100)


def _promo_discounts(promo_code: str | None, billing: str) -> list[dict] | None:
    """Stripe `discounts` to attach to the checkout session, or None.

    Auto-applies the early-adopter promotion code to monthly checkouts while
    the sale is active. An explicit promo code must match the configured sale
    code (the only promo AutoBrain issues); anything else is rejected locally
    rather than guessed at — Stripe's promotion codes are validated at checkout
    when allow_promotion_codes is set.
    """
    promo_id = settings.STRIPE_PROMO_EARLY_ADOPTER
    code = settings.STRIPE_PROMO_EARLY_ADOPTER_CODE.upper()
    entered = (promo_code or "").strip().upper()
    if entered and entered != code:
        raise ValueError("Unknown promo code")
    if not promo_id:
        return None
    if entered == code or (billing == "monthly" and sale_active()):
        return [{"promotion_code": promo_id}]
    return None


def plan_for_user(user: User) -> str:
    """Resolve the current plan key from a user's subscription state."""
    if not user.free_account:
        if user.stripe_price_id and user.stripe_subscription_status in ACTIVE_STATUSES:
            return plan_for_price(user.stripe_price_id) or _plan_from_entitlement(user)
        return FREE_PLAN  # admin-granted access without a Stripe sub
    return FREE_PLAN


def _plan_from_entitlement(user: User) -> str:
    """Best-effort plan for an active subscription on a price this deploy does
    not recognise (e.g. a grandfathered pre-AUT-523 price that was archived in
    Stripe). The persisted entitlement was set when the sub was created, so
    infer the plan from it rather than demoting someone who is still billed."""
    if user.max_vehicles >= PLANS["garage"]["max_vehicles"]:
        return "garage"
    return "enthusiast"


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
    db: AsyncSession, user: User, plan_key: str, billing: str, promo_code: str | None = None
) -> str:
    """Find-or-create the Stripe customer and open a Checkout subscription."""
    if plan_key not in PLANS:
        raise ValueError("Unknown plan")
    # Sponsored/re-upgraded accounts (paid benefits, no Stripe subscription)
    # cannot buy a licence — the admin has already granted them access.
    if not user.free_account and not has_paid_subscription(user):
        raise ValueError("Licence upgrades are disabled on this account")
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
    params: dict = {
        "mode": "subscription",
        "customer": customer_id,
        "client_reference_id": user.id,
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{base}/?checkout=success",
        "cancel_url": f"{base}/",
        "metadata": {"plan": plan_key, "billing": billing},
    }
    discounts = _promo_discounts(promo_code, billing)
    if discounts:
        # Stripe forbids discounts + allow_promotion_codes together, so promo
        # is applied via the code and other codes are typed at checkout.
        params["discounts"] = discounts
    else:
        params["allow_promotion_codes"] = True
    session = client.checkout.sessions.create(params=params)
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


def cancel_subscription(user: User) -> None:
    """Cancel the active subscription at the end of its current period.
    The account keeps paid access until then; the webhook demotes it when the
    period ends (customer.subscription.deleted)."""
    if not user.stripe_subscription_id:
        raise ValueError("No active subscription")
    if user.stripe_subscription_status not in ACTIVE_STATUSES:
        raise ValueError("No active subscription")
    get_client().subscriptions.cancel(
        user.stripe_subscription_id, params={"at_period_end": True}
    )


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

    if sub.get("status") in ACTIVE_STATUSES:
        plan = plan_for_price(price_id) if price_id else None
        if plan:
            apply_plan(user, plan)
        else:
            # Active subscription on a price this deploy doesn't recognise (e.g.
            # a grandfathered pre-AUT-523 price archived in Stripe). Stripe keeps
            # billing it, so preserve the user's entitlement instead of silently
            # demoting a paying member to the free tier.
            logger.info(
                "stripe_subscription_preserved_unknown_price",
                extra={"user": user.id, "status": sub.get("status"), "price": price_id},
            )
    else:
        apply_free(user)
    await db.commit()
    logger.info(
        "stripe_subscription_applied",
        extra={"user": user.id, "status": sub.get("status"), "price": price_id},
    )
