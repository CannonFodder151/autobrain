# AutoBrain Payments & Subscription Plan (Stripe)

Sanitised public mirror of the internal Finance doc. No secrets, no internal links. Hosted instance: `hosted.autobrainservice.app`.

## Plans & pricing

Two paid tiers plus a free tier. Prices in AUD (AUT-523); source of truth is `scripts/stripe-setup.py` and the `STRIPE_PRICE_*` env on the hosted stack.

| Plan | Monthly | Yearly | Max vehicles |
|---|---|---|---|
| Free | $0 | — | 1 |
| Enthusiast | $5.90 | $59 | 1 |
| Garage | $11.90 | $119 | 5 |

- Free tier: 1 vehicle, AI features and rego lookup disabled (server-side 403), exports still available.
- Paid access via active subscription promotes the account; lapse/cancel demotes back to free.
- Stripe lookup keys: `autobrain-enthusiast-monthly`, `autobrain-enthusiast-yearly`, `autobrain-garage-monthly`, `autobrain-garage-yearly`.

## Early-adopter sale (EARLY40) — sunset

- Coupon `autobrain_early_adopter_40`: 40% off the first 3 months, capped at 100 redemptions, redeemable within a 6-month window from launch.
- Promotion code **EARLY40**. Sunset in AUT-1164: no longer auto-applied to monthly checkouts and no longer surfaced in `/billing/pricing`; the coupon stays in Stripe and is only honoured if a customer enters the code explicitly at checkout.

## Billing flow

- Checkout: `POST /billing/checkout` → Stripe Checkout session (subscription mode); find-or-create customer by email.
- Customer portal: `POST /billing/portal` → change/cancel subscription.
- Cancel: at period end; access kept until the period ends.
- Webhook: `POST /billing/webhook` (signature verified via `STRIPE_WEBHOOK_SECRET`). Source of truth for tier changes — promotes on active, demotes on cancel/lapse.
- Statuses granting access: `active`, `trialing`, `past_due`. `unpaid`/`canceled` do not.
- Licence state: `/auth/me` exposes `license_status` (`active` / `pending` / `free`). A subscription stuck in `incomplete`/`incomplete_expired`/`unpaid` (checkout started, not paid) or a granted-but-unpaid account is reported `pending`; nothing shows `active` without a paid entitlement. The License screen renders `pending` orange.
- A user with a pending (incomplete/unpaid) checkout can retry paying; only sponsored accounts with no subscription record are blocked from buying a licence.
- Upgrade overlap: a newly completed subscription auto-cancels a previous one (no double billing).
- Admin re-upgrade grants paid benefits without a Stripe subscription; sponsored accounts are blocked from buying a licence.
- Billing endpoints return **503** until `STRIPE_SECRET_KEY` is set.

## Store-native IAP (mobile store builds)

The store builds of the mobile app sell the same licences through Apple App Store / Google Play (AUT-610/617). Product ids (same on both stores): `com.autobrainservice.app.{enthusiast,garage}.{monthly,yearly}`.

- Catalogue: `GET /billing/iap/catalog` (public) → `{enabled, products}`; `enabled` is false until IAP credentials are set, and the mobile app then falls back to the Stripe browser path.
- Verify: `POST /billing/iap/verify` (auth) verifies the store transaction server-side and grants the plan; purchases are recorded on the user (`iap_*` fields) and durable across reinstall/re-login.
- Renewal model: verify-on-refresh — `GET /auth/me` re-validates the stored purchase token against the store API when the entitlement is expired or within `IAP_REFRESH_WINDOW_DAYS` of expiry (no webhooks needed). Webhooks (`POST /billing/iap/webhook/apple|google`) are also accepted and act as refresh triggers when the store teams configure them.
- Rate limiting: `POST /billing/iap/verify` is rate-limited per user (in-process sliding window, 10 hits/60s). The limiter is process-local — correct for the single-uvicorn hosted deploy (`docker-compose.hosted.yml`), but it is invalidated if the backend ever scales to multiple workers/instances; move the window to a shared store (e.g. Redis) before scaling out (N4).
- Entitlement: `plan_for_user` and `/auth/me` treat an active IAP entitlement as paid (`subscription_status` + `iap_status` fields). Upgrading replaces the prior store entitlement (no double grant); expiry/revocation demotes back to the free tier (or keeps a still-active Stripe plan).

## Configuration (env)

`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ENTHUSIAST_MONTHLY/YEARLY`, `STRIPE_PRICE_GARAGE_MONTHLY/YEARLY`, `STRIPE_PROMO_EARLY_ADOPTER`, `STRIPE_PROMO_EARLY_ADOPTER_CODE`, `STRIPE_SALE_ENDS_AT`. Hosted stack sets `LICENSE_ENABLED=true`; demo/default keep it off. Provisioning script: `scripts/stripe-setup.py` (idempotent; run in test mode first, then live).

IAP env (empty = disabled): `IAP_GOOGLE_SERVICE_ACCOUNT_JSON`, `IAP_GOOGLE_PACKAGE_NAME`, `IAP_APPLE_ISSUER_ID`, `IAP_APPLE_KEY_ID`, `IAP_APPLE_PRIVATE_KEY`, `IAP_APPLE_BUNDLE_ID`, `IAP_REFRESH_WINDOW_DAYS`, `IAP_GOOGLE_PUBSUB_AUDIENCE`. Credentials are secrets — set them on the deployment env, never commit.

## References

- `scripts/stripe-setup.py`, `backend/app/services/billing.py`, `backend/app/services/iap.py`, `backend/app/api/v1/billing.py`
- `docker-compose.hosted.yml` (Stripe env), `.env.example` (Stripe + IAP blocks)
