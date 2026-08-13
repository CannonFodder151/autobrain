# AutoBrain Payments & Subscription Plan (Stripe)

Sanitised public mirror of the internal Finance doc. No secrets, no internal links. Hosted instance: `hosted.autobrainservice.app`.

## Plans & pricing

Two paid tiers plus a free tier. Prices in AUD (AUT-523); source of truth is `scripts/stripe-setup.py` and the `STRIPE_PRICE_*` env on the hosted stack.

| Plan | Monthly | Yearly | Max vehicles |
|---|---|---|---|
| Free | $0 | — | 1 |
| Enthusiast | $9 | $84 | 1 |
| Garage | $19 | $168 | 5 |

- Free tier: 1 vehicle, AI features and rego lookup disabled (server-side 403), exports still available.
- Paid access via active subscription promotes the account; lapse/cancel demotes back to free.
- Stripe lookup keys: `autobrain-enthusiast-monthly`, `autobrain-enthusiast-yearly`, `autobrain-garage-monthly`, `autobrain-garage-yearly`.

## Early-adopter sale (EARLY40)

- Coupon `autobrain_early_adopter_40`: 40% off the first 3 months, capped at 100 redemptions, redeemable within a 6-month window from launch.
- Promotion code **EARLY40**. Auto-applied to **monthly** checkouts while the window is open; yearly gets no discount; unknown codes rejected.
- Sale-priced monthly: Enthusiast $5.40, Garage $11.40.

## Billing flow

- Checkout: `POST /billing/checkout` → Stripe Checkout session (subscription mode); find-or-create customer by email.
- Customer portal: `POST /billing/portal` → change/cancel subscription.
- Cancel: at period end; access kept until the period ends.
- Webhook: `POST /billing/webhook` (signature verified via `STRIPE_WEBHOOK_SECRET`). Source of truth for tier changes — promotes on active, demotes on cancel/lapse.
- Statuses granting access: `active`, `trialing`, `past_due`. `unpaid`/`canceled` do not.
- Upgrade overlap: a newly completed subscription auto-cancels a previous one (no double billing).
- Admin re-upgrade grants paid benefits without a Stripe subscription; sponsored accounts are blocked from buying a licence.
- Billing endpoints return **503** until `STRIPE_SECRET_KEY` is set.

## Configuration (env)

`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ENTHUSIAST_MONTHLY/YEARLY`, `STRIPE_PRICE_GARAGE_MONTHLY/YEARLY`, `STRIPE_PROMO_EARLY_ADOPTER`, `STRIPE_PROMO_EARLY_ADOPTER_CODE`, `STRIPE_SALE_ENDS_AT`. Hosted stack sets `LICENSE_ENABLED=true`; demo/default keep it off. Provisioning script: `scripts/stripe-setup.py` (idempotent; run in test mode first, then live).

## References

- `scripts/stripe-setup.py`, `backend/app/services/billing.py`, `backend/app/api/v1/billing.py`
- `docker-compose.hosted.yml` (Stripe env), `.env.example` (Stripe block)
