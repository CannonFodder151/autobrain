#!/usr/bin/env python3
"""Idempotent Stripe provisioning for AutoBrain paid tiers (AUT-111).

Creates or verifies, in the account owning STRIPE_SECRET_KEY:
  * Enthusiast prices  A$9/mo, A$84/yr
  * Garage prices      A$19/mo, A$168/yr
  * Early-adopter sale (AUT-93, plan c36be7d): coupon EARLY40 = 40% off the
    first 3 months, capped at 100 redemptions, redeemable for 6 months from
    launch, plus its promotion code.

All prices are in AUD (AUT-523); the script archives any wrong-currency price
found under the same lookup key and creates an AUD replacement.

Run in Stripe test mode first (sk_test_...), then again with the live key.
Prints the env values to wire into the hosted stack; do not run against an
account with existing conflicting prices.

Usage:
    STRIPE_SECRET_KEY=sk_... python3 scripts/stripe-setup.py
"""

import argparse
import os
import sys
from datetime import date, timedelta

import stripe

CURRENCY = "aud"

PLANS = {
    "enthusiast": {
        "name": "Enthusiast",
        "amounts": {"monthly": 900, "yearly": 8400},
        "lookup": {"monthly": "autobrain-enthusiast-monthly", "yearly": "autobrain-enthusiast-yearly"},
    },
    "garage": {
        "name": "Garage",
        "amounts": {"monthly": 1900, "yearly": 16800},
        "lookup": {"monthly": "autobrain-garage-monthly", "yearly": "autobrain-garage-yearly"},
    },
}

SALE_COUPON_ID = "autobrain_early_adopter_40"
SALE_CODE = "EARLY40"
SALE_PERCENT_OFF = 40
SALE_DURATION_MONTHS = 3
SALE_CAP = 100
SALE_WINDOW_MONTHS = 6


def upsert_price(plan_key: str, billing: str) -> dict:
    plan = PLANS[plan_key]
    lookup = plan["lookup"][billing]
    amount = plan["amounts"][billing]
    existing = stripe.Price.list(lookup_keys=[lookup], limit=1).data
    if existing:
        price = existing[0]
        assert price.unit_amount == amount, (
            f"{plan_key}/{billing}: existing price {price.unit_amount} != {amount}"
        )
        if price.currency == CURRENCY:
            print(f"  verified {plan['name']} {billing}: {price.id}")
            return price
        # Price objects are immutable; a wrong-currency price (e.g. the pre-AUT-523
        # USD prices) must be archived before its lookup key can be reused.
        print(
            f"  archiving wrong-currency {plan['name']} {billing} "
            f"({price.id}, {price.currency})"
        )
        stripe.Price.modify(price.id, active=False)
        existing = stripe.Price.list(lookup_keys=[lookup], limit=1).data
        if existing:
            stripe.Price.modify(existing[0].id, active=False)
    product = stripe.Product.retrieve(plan_key)
    interval = {"monthly": "month", "yearly": "year"}[billing]
    return stripe.Price.create(
        product=product.id,
        unit_amount=amount,
        currency=CURRENCY,
        lookup_key=lookup,
        nickname=f"{plan['name']} {billing}",
        recurring={"interval": interval, "interval_count": 1},
    )


def upsert_coupon() -> dict:
    try:
        coupon = stripe.Coupon.retrieve(SALE_COUPON_ID)
        print(f"  verified coupon {SALE_COUPON_ID}")
        return coupon
    except stripe.error.InvalidRequestError:
        pass
    return stripe.Coupon.create(
        id=SALE_COUPON_ID,
        name="Early-adopter 40% off (first 3 months)",
        percent_off=SALE_PERCENT_OFF,
        duration="repeating",
        duration_in_months=SALE_DURATION_MONTHS,
        max_redemptions=SALE_CAP,
        redeem_by=int((date.today() + timedelta(days=30 * SALE_WINDOW_MONTHS)).strftime("%s")),
        applies_to={"products": list(PLANS.keys())},
    )


def upsert_promo(coupon: dict) -> dict:
    existing = stripe.PromotionCode.list(code=SALE_CODE, limit=1).data
    if existing:
        print(f"  verified promotion code {SALE_CODE}: {existing[0].id}")
        return existing[0]
    return stripe.PromotionCode.create(coupon=coupon.id, code=SALE_CODE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="check prices/coupon/promo exist without creating anything",
    )
    args = parser.parse_args()

    if not os.environ.get("STRIPE_SECRET_KEY"):
        sys.exit("STRIPE_SECRET_KEY is not set")
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    # The account's default API version (2026-07-29.dahlia) rejects the `coupon`
    # param on promotion_codes; pin a stable version that accepts it.
    stripe.api_version = "2024-06-20"

    print("AutoBrain pricing setup")
    for plan_key in PLANS:
        if not args.verify_only:
            stripe.Product.retrieve(plan_key)  # ensure the product exists
        for billing in ("monthly", "yearly"):
            upsert_price(plan_key, billing)

    coupon = upsert_coupon()
    promo = upsert_promo(coupon)

    ends = date.today() + timedelta(days=30 * SALE_WINDOW_MONTHS)
    print("\nWire these into the hosted stack (.env):")
    for plan_key in PLANS:
        for billing in ("monthly", "yearly"):
            price = stripe.Price.list(
                lookup_keys=[PLANS[plan_key]["lookup"][billing]], limit=1
            ).data[0]
            env = f"STRIPE_PRICE_{plan_key.upper()}_{billing.upper()}"
            print(f"{env}={price.id}")
    print(f"STRIPE_PROMO_EARLY_ADOPTER={promo.id}")
    print(f"STRIPE_PROMO_EARLY_ADOPTER_CODE={SALE_CODE}")
    print(f"STRIPE_SALE_ENDS_AT={ends.isoformat()}")


if __name__ == "__main__":
    main()
