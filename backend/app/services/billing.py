"""Billing + entitlement: Stripe subscriptions and store-native IAP (AUT-610/617).

The hosted instance grants plan access through Stripe subscriptions (web
/ self-hosted builds) and, for the store builds of the mobile app, through
Apple App Store / Google Play purchases. A valid subscription or an active
IAP entitlement promotes the account (free_account=False + per-plan vehicle
cap); cancelling, lapsing or being revoked demotes back to the free tier.

IAP purchase verification lives in app/services/iap.py; this module owns the
entitlement mapping (what a product grants) so plan_for_user treats an active
IAP entitlement exactly like a Stripe subscription.
"""

import logging
from datetime import datetime, timezone

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
    "enthusiast": {"monthly": 590, "yearly": 5900},
    "garage": {"monthly": 1190, "yearly": 11900},
}

# Early-adopter sale (AUT-93): 40% off the first 3 months, capped at 100
# subscribers for 6 months after launch. Sunset in AUT-1164 — no longer
# auto-applied; the coupon stays in Stripe for explicit code entry only.
SALE_PERCENT_OFF = 40
SALE_DURATION_MONTHS = 3
SALE_CAP = 100

# 7-day free trial (AUT-1195): one trial per account, granted on monthly
# checkouts only (yearly takes no trial). Replaces the EARLY40 sale on monthly
# — a promo-code checkout (EARLY40 entered explicitly) never carries a trial.
TRIAL_PERIOD_DAYS = 7

# Stripe statuses that still grant paid access (past_due keeps access while
# Stripe retries the card; unpaid/canceled do not).
ACTIVE_STATUSES = frozenset({"active", "trialing", "past_due"})

# Stripe statuses for a checkout that was started but not paid yet (3DS
# pending, failed cards in dunning, or abandoned before payment). The user has
# no paid access but the licence is "pending" until the check completes.
PENDING_STATUSES = frozenset({"incomplete", "incomplete_expired", "unpaid"})

# Store-native IAP product ids (AUT-610/617). The store teams configure these
# exact ids in App Store Connect / Play Console; both stores use the same ids.
# Each maps to the plan + billing interval it grants.
# Note: enthusiast FQN ids (com.autobrainservice.app.enthusiast.{monthly,yearly})
# exceed Google Play's 40-char product ID limit; using short ids instead.
IAP_PRODUCTS: dict[str, tuple[str, str]] = {
    "enthusiast_monthly": ("enthusiast", "monthly"),
    "enthusiast_yearly": ("enthusiast", "yearly"),
    "com.autobrainservice.app.garage.monthly": ("garage", "monthly"),
    "com.autobrainservice.app.garage.yearly": ("garage", "yearly"),
}

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
    """EARLY40 is sunset (AUT-1164) — always inactive in the app so pricing
    stops advertising it and checkouts never auto-apply it. The Stripe coupon
    itself stays untouched and remains redeemable if entered explicitly."""
    return False


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
            "trial_days": {"monthly": TRIAL_PERIOD_DAYS, "yearly": 0},
        }
        if sale["active"]:
            entry["sale_monthly"] = _discounted(amounts["monthly"], SALE_PERCENT_OFF)
        plans.append(entry)
    return {"currency": CURRENCY, "sale": sale, "plans": plans}


def _discounted(amount_cents: int, percent_off: int) -> int:
    return round(amount_cents * (100 - percent_off) / 100)


def _promo_discounts(promo_code: str | None, billing: str) -> list[dict] | None:
    """Stripe `discounts` to attach to the checkout session, or None.

    Applies the early-adopter promotion code only when the customer explicitly
    enters it (AUT-1164: the sale is sunset — no auto-apply on monthly
    checkouts, and the coupon no longer surfaces in /billing/pricing). An
    entered code must match the configured sale code (the only promo AutoBrain
    issues); anything else is rejected locally rather than guessed at —
    Stripe's promotion codes are validated at checkout when
    allow_promotion_codes is set.
    """
    code = settings.STRIPE_PROMO_EARLY_ADOPTER_CODE.upper()
    entered = (promo_code or "").strip().upper()
    if entered and entered != code:
        raise ValueError("Unknown promo code")
    promo_id = settings.STRIPE_PROMO_EARLY_ADOPTER
    if entered == code and promo_id:
        return [{"promotion_code": promo_id}]
    return None


def plan_for_iap_product(product_id: str | None) -> str | None:
    """Plan key granted by a store IAP product id, or None."""
    info = IAP_PRODUCTS.get(product_id) if product_id else None
    return info[0] if info else None


def iap_status(user: User) -> str | None:
    """Effective IAP entitlement state, or None when never bought via a store.

    "active" while the last-known state is not revoked and iap_expires_at is in
    the future; "expired" once the period has passed; "revoked" on refund/revoke.
    """
    if not user.iap_product_id or not user.iap_transaction_id:
        return None
    if user.iap_status == "revoked":
        return "revoked"
    expires = user.iap_expires_at
    if expires is None:
        return "active"
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return "active" if expires > datetime.now(timezone.utc) else "expired"


def apply_iap(
    user: User,
    product_id: str,
    platform: str,
    transaction_id: str,
    purchase_token: str,
    expires_at,
    original_transaction_id: str | None = None,
) -> None:
    """Grant the plan entitlement a store IAP product maps to.

    Replaces any prior IAP entitlement — there is a single store slot per
    account, so upgrading (enthusiast → garage) or switching products never
    double-grants. Raises ValueError for unknown product ids.
    """
    plan_key = plan_for_iap_product(product_id)
    if not plan_key:
        raise ValueError("Unknown IAP product")
    apply_plan(user, plan_key)
    user.iap_platform = platform
    user.iap_product_id = product_id
    user.iap_transaction_id = transaction_id
    user.iap_original_transaction_id = original_transaction_id
    user.iap_purchase_token = purchase_token
    user.iap_expires_at = expires_at
    user.iap_status = "active"


def clear_iap(user: User, status: str = "expired") -> None:
    """Demote an IAP entitlement (expired, revoked or refunded).

    The purchase record is kept so verify-on-refresh can re-check a lapsed or
    renewed subscription, but the account tier is recomputed: a still-active
    Stripe subscription keeps the paid plan, otherwise the account returns to
    the free tier.
    """
    if user.iap_product_id:
        user.iap_status = status
    if has_paid_subscription(user):
        plan_key = plan_for_price(user.stripe_price_id) if user.stripe_price_id else None
        if plan_key:
            apply_plan(user, plan_key)
            return
    apply_free(user)


def plan_for_user(user: User) -> str:
    """Resolve the current plan key from a user's subscription state.

    An active store IAP entitlement is treated exactly like a paid subscription.
    """
    if iap_status(user) == "active":
        plan_key = plan_for_iap_product(user.iap_product_id)
        if plan_key:
            return plan_key
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
    if iap_status(user) == "active":
        return True
    return (
        bool(user.stripe_subscription_id)
        and user.stripe_subscription_status in ACTIVE_STATUSES
    )


def license_status(user: User) -> str:
    """Effective licence lifecycle state, one of `active` | `pending` | `free`.

    - `active`: a paid entitlement (Stripe sub in an active status or a live
      store IAP grant).
    - `pending`: a licence is expected but not paid yet — either a Stripe
      subscription whose checkout is incomplete/unpaid, or a non-free account
      with no paid subscription (admin-granted/re-upgraded access that has not
      actually been paid for).
    - `free`: no licence, no pending payment, plain free tier.

    Drives the License screen badge (green / orange / blue). An account is
    never reported `active` without a paid entitlement, so a non-paying user
    cannot show as "registered".
    """
    if has_paid_subscription(user):
        return "active"
    if user.stripe_subscription_status in PENDING_STATUSES:
        return "pending"
    if not user.free_account:
        return "pending"
    return "free"


def apply_plan(user: User, plan_key: str) -> None:
    plan = PLANS[plan_key]
    user.free_account = False
    user.max_vehicles = plan["max_vehicles"]


def apply_free(user: User) -> None:
    user.free_account = True
    user.max_vehicles = 1


async def ensure_customer(db: AsyncSession, user: User) -> str:
    """Find-or-create the Stripe customer for an account and cache its id."""
    if user.stripe_customer_id:
        return user.stripe_customer_id
    client = get_client()
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
    return customer_id


async def create_checkout_session(
    db: AsyncSession, user: User, plan_key: str, billing: str, promo_code: str | None = None
) -> str:
    """Find-or-create the Stripe customer and open a Checkout subscription."""
    if plan_key not in PLANS:
        raise ValueError("Unknown plan")
    # Sponsored/re-upgraded accounts (paid benefits, no Stripe subscription)
    # cannot buy a licence — the admin has already granted them access.
    # A subscription record in a pending status is NOT granted access: it is an
    # unfinished/failed checkout, so the user may retry paying for it.
    if (
        not user.free_account
        and not has_paid_subscription(user)
        and not user.stripe_subscription_id
    ):
        raise ValueError("Licence upgrades are disabled on this account")
    price_id = price_for(plan_key, billing)
    if not price_id:
        raise ValueError("Billing is not configured for that plan")
    client = get_client()

    customer_id = await ensure_customer(db, user)

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
    # AUT-1195: a monthly checkout grants a 7-day trial unless a promo code
    # enters the flow — trial replaces the sale for monthly; yearly never
    # takes a trial. One trial per account, so repeat attempts are blocked.
    trial_days = TRIAL_PERIOD_DAYS if (billing == "monthly" and not discounts) else None
    if trial_days and user.has_had_trial:
        raise ValueError("You have already used your 7-day free trial")
    if discounts:
        # Stripe forbids discounts + allow_promotion_codes together, so promo
        # is applied via the code and other codes are typed at checkout.
        params["discounts"] = discounts
    elif trial_days:
        # Trial replaces the sale for monthly: no promo codes at checkout so a
        # discount cannot stack on top of the free trial.
        params["allow_promotion_codes"] = False
    else:
        params["allow_promotion_codes"] = True
    if trial_days:
        params["subscription_data"] = {"trial_period_days": trial_days}
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
        # Lazy import: merch imports this module for the Stripe client.
        from app.services.merch import record_paid_session

        if obj.get("mode") == "payment":
            await record_paid_session(db, obj)
            return
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
    # AUT-1195/1211: trial consumption is handled inside _apply_subscription
    # so the flag is claimed on whichever webhook lands first.
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

    if sub.get("status") == "trialing":
        # AUT-1211: claim the account's one free trial here (webhook path,
        # committed atomically with the plan grant) so neither a lost
        # checkout.session.completed nor two racing checkouts can yield a
        # second 7-day trial.
        if user.has_had_trial:
            # Duplicate/racing subscription: end this trial immediately.
            try:
                sub = get_client().subscriptions.update(
                    sub["id"], params={"trial_end": "now"}
                ).to_dict()
                logger.info(
                    "stripe_duplicate_trial_ended",
                    extra={"user": user.id, "sub": sub.get("id")},
                )
            except stripe.StripeError:
                logger.exception("stripe_trial_end_failed", extra={"sub": sub.get("id")})
        user.has_had_trial = True

    # Assigned after the trial block: ending a duplicate trial rewrites `sub`
    # (trial_end=now), so the local status must reflect Stripe's response.
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
