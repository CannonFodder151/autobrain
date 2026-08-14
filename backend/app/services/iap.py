"""Store-native in-app purchase verification (Apple App Store / Google Play).

The store builds of the mobile app (AUT-610) sell the Enthusiast/Garage
licences through the App Store / Play Store and send the store transaction to
POST /billing/iap/verify. This module verifies it against the store APIs and
grants the same entitlement the Stripe path grants (see app.services.billing).

Renewal model (self-hosted friendly, AUT-617):
- Purchases are recorded server-side (iap_* fields on the user), durable across
  reinstall/re-login — the licence is validated by the AutoBrain backend.
- Verify-on-refresh: GET /auth/me re-validates the stored purchase token
  against the store API when the entitlement is expired or within
  IAP_REFRESH_WINDOW_DAYS of expiry, so renewals and refunds propagate without
  webhooks (Google Play RTDN requires a GCP Pub/Sub subscription, which is
  infeasible on the self-hosted deploy until the store teams provision it).
- Webhooks (POST /billing/iap/webhook/{apple,google}) are accepted when the
  store teams configure them. They act as refresh triggers matched to the user;
  the authoritative state always comes from re-verifying against the store API,
  so a forged notification can neither grant nor revoke anything the store
  disagrees with.
"""

import base64
import json
import logging
import time
import urllib.parse
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import httpx
from cryptography.exceptions import InvalidSignature
from jose import jwk as jose_jwk
from jose import jws as jose_jws
from jose import jwt as jose_jwt
from sqlalchemy import select

from app.core.config import settings
from app.models.user import User
from app.services import billing

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_APIS_BASE = "https://androidpublisher.googleapis.com"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_API_BASE = "https://api.storekit.itunes.apple.com"

# Google Play purchaseState: 0 purchased (active), 1 cancelled, 2 pending.
_GOOGLE_ACTIVE_STATE = 0

# Apple subscription statuses that still grant access (1 active, 3 billing
# retry, 4 billing grace period, 7 in grace period). Anything else (expired,
# revoked, ...) demotes.
_APPLE_ACTIVE_STATUSES = frozenset({1, 3, 4, 7})

# Public Apple Root CA - G3 (expires 2039). App Store Server Notifications v2
# signedPayloads are JWS with an x5c chain that terminates here.
APPLE_ROOT_CA_G3 = (
    "-----BEGIN CERTIFICATE-----\n"
    "MIICQzCCAcmgAwIBAgIILcX8iNLFS5UwCgYIKoZIzj0EAwMwZzEbMBkGA1UEAwwS\n"
    "QXBwbGUgUm9vdCBDQSAtIEczMSYwJAYDVQQLDB1BcHBsZSBDZXJ0aWZpY2F0aW9u\n"
    "IEF1dGhvcml0eTETMBEGA1UECgwKQXBwbGUgSW5jLjELMAkGA1UEBhMCVVMwHhcN\n"
    "MTQwNDMwMTgxOTA2WhcNMzkwNDMwMTgxOTA2WjBnMRswGQYDVQQDDBJBcHBsZSBS\n"
    "b290IENBIC0gRzMxJjAkBgNVBAsMHUFwcGxlIENlcnRpZmljYXRpb24gQXV0aG9y\n"
    "aXR5MRMwEQYDVQQKDApBcHBsZSBJbmMuMQswCQYDVQQGEwJVUzB2MBAGByqGSM49\n"
    "AgEGBSuBBAAiA2IABJjpLz1AcqTtkyJygRMc3RCV8cWjTnHcFBbZDuWmBSp3ZHtf\n"
    "TjjTuxxEtX/1H7YyYl3J6YRbTzBPEVoA/VhYDKX1DyxNB0cTddqXl5dvMVztK517\n"
    "IDvYuVTZXpmkOlEKMaNCMEAwHQYDVR0OBBYEFLuw3qFYM4iapIqZ3r6966/ayySr\n"
    "MA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgEGMAoGCCqGSM49BAMDA2gA\n"
    "MGUCMQCD6cHEFl4aXTQY2e3v9GwOAEZLuN+yRhHFD/3meoyhpmvOwgPUnPWTxnS4\n"
    "at+qIxUCMG1mihDK1A3UT82NQz60imOlM27jbdoXt2QfyFMm+YhidDkLF1vLUagM\n"
    "6BgD56KyKA==\n"
    "-----END CERTIFICATE-----\n"
)


class VerificationError(Exception):
    """A store verification failed or the transaction is invalid."""


class SubscriptionNotActive(VerificationError):
    """The store definitively says the subscription is no longer active.

    `status` is the entitlement state to settle to ("revoked" for a store-side
    cancellation, "expired" for a lapsed period). Subclasses VerificationError so
    a first-time verify still rejects; refresh_entitlement uses it to demote.
    """

    def __init__(self, status: str, *args: object) -> None:
        super().__init__(*args)
        self.status = status


def _b64decode(data: str) -> bytes:
    """Decode base64/base64url with padding tolerance."""
    data = data.replace("-", "+").replace("_", "/")
    data += "=" * (-len(data) % 4)
    return base64.b64decode(data)


# --- Feature flag / catalogue -------------------------------------------------


def google_configured() -> bool:
    return bool(settings.IAP_GOOGLE_SERVICE_ACCOUNT_JSON)


def apple_configured() -> bool:
    return bool(
        settings.IAP_APPLE_ISSUER_ID
        and settings.IAP_APPLE_KEY_ID
        and settings.IAP_APPLE_PRIVATE_KEY
    )


def enabled() -> bool:
    """True when any store IAP is configured — the mobile app then uses the
    store-native purchase path instead of falling back to Stripe."""
    return google_configured() or apple_configured()


def catalog() -> dict:
    """Deterministic product catalogue for GET /billing/iap/catalog."""
    products = []
    for product_id, (plan, billing_interval) in billing.IAP_PRODUCTS.items():
        products.append(
            {"product_id": product_id, "platform": "android", "plan": plan, "billing": billing_interval}
        )
        products.append(
            {"product_id": product_id, "platform": "ios", "plan": plan, "billing": billing_interval}
        )
    return {"enabled": enabled(), "products": products}


# Verify-endpoint rate limit (F4): in-process sliding window per user so a
# logged-in client cannot spam store verification calls (each hit = external
# store API round-trips).
IAP_VERIFY_WINDOW_SECONDS = 60
IAP_VERIFY_LIMIT_PER_WINDOW = 10
_verify_hits: dict[str, deque[float]] = defaultdict(deque)


def check_verify_rate_limit(user_id: str) -> None:
    """Raise HTTPException 429 when the user exceeds the verify window."""
    from fastapi import HTTPException

    now = time.monotonic()
    q = _verify_hits[user_id]
    while q and now - q[0] > IAP_VERIFY_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= IAP_VERIFY_LIMIT_PER_WINDOW:
        retry_after = max(1, int(IAP_VERIFY_WINDOW_SECONDS - (now - q[0])) + 1)
        raise HTTPException(
            status_code=429,
            detail="Too many purchase verifications. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
    q.append(now)


# --- Google Play --------------------------------------------------------------


def _load_service_account() -> dict:
    if not settings.IAP_GOOGLE_SERVICE_ACCOUNT_JSON:
        raise VerificationError("Google Play IAP is not configured")
    return json.loads(settings.IAP_GOOGLE_SERVICE_ACCOUNT_JSON)


async def _google_access_token(client: httpx.AsyncClient) -> str:
    """Short-lived OAuth token from the Play service-account JWT assertion."""
    sa = _load_service_account()
    now = int(time.time())
    assertion = jose_jwt.encode(
        {
            "iss": sa["client_email"],
            "scope": "https://www.googleapis.com/auth/androidpublisher",
            "aud": GOOGLE_TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        },
        sa["private_key"],
        algorithm="RS256",
    )
    resp = await client.post(
        GOOGLE_TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
    )
    if resp.status_code != 200:
        logger.warning("google_token_exchange_failed", extra={"status": resp.status_code})
        raise VerificationError("Google Play authentication failed")
    return resp.json()["access_token"]


async def _google_subscription(
    client: httpx.AsyncClient, access_token: str, product_id: str, purchase_token: str
) -> dict:
    url = (
        f"{GOOGLE_APIS_BASE}/androidpublisher/v3/applications/"
        f"{urllib.parse.quote(settings.IAP_GOOGLE_PACKAGE_NAME)}/purchases/subscriptions/"
        f"{urllib.parse.quote(product_id)}/tokens/{urllib.parse.quote(purchase_token)}"
    )
    resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code == 404:
        raise VerificationError("Purchase not found by Google Play")
    if resp.status_code != 200:
        logger.warning("google_purchase_verify_failed", extra={"status": resp.status_code})
        raise VerificationError("Google Play verification failed")
    data = resp.json()
    state = data.get("purchaseState")
    expiry_ms = data.get("expiryTimeMillis")
    if state is not None and state != _GOOGLE_ACTIVE_STATE:
        # 0 active, 1 cancelled, 2 pending. A definitive non-active state means
        # the entitlement is gone; the caller settles "revoked" vs "expired".
        raise SubscriptionNotActive("revoked" if state == 1 else "expired")
    if expiry_ms is not None and int(expiry_ms) <= int(time.time() * 1000):
        raise SubscriptionNotActive("expired")
    return data


def _google_expiry_ms(data: dict) -> str | None:
    return data.get("expiryTimeMillis")


# --- Apple App Store ----------------------------------------------------------


def _apple_bearer() -> str:
    """Short-lived ES256 JWT signed with the App Store Connect API key."""
    now = int(time.time())
    return jose_jwt.encode(
        {
            "iss": settings.IAP_APPLE_ISSUER_ID,
            "iat": now,
            "exp": now + 1200,
            "aud": "appstoreconnect-v1",
            "bid": settings.IAP_APPLE_BUNDLE_ID,
        },
        settings.IAP_APPLE_PRIVATE_KEY,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": settings.IAP_APPLE_KEY_ID},
    )


def _decode_signed_transaction(signed: str) -> dict:
    """Decode the (untrusted-envelope) signedTransaction JWS claims."""
    return jose_jwt.get_unverified_claims(signed)


async def _apple_transaction(client: httpx.AsyncClient, transaction_id: str) -> dict:
    resp = await client.get(
        f"{APPLE_API_BASE}/inApps/v1/transactions/{urllib.parse.quote(transaction_id)}",
        headers={"Authorization": f"Bearer {_apple_bearer()}"},
    )
    if resp.status_code != 200:
        logger.warning("apple_transaction_verify_failed", extra={"status": resp.status_code})
        raise VerificationError("App Store verification failed")
    signed = resp.json().get("signedTransaction")
    if not signed:
        raise VerificationError("App Store response missing transaction")
    return _decode_signed_transaction(signed)


async def _apple_subscription(
    client: httpx.AsyncClient, original_transaction_id: str
) -> tuple[str | None, int | None]:
    """Latest subscription status + expiry for an originalTransactionId."""
    resp = await client.get(
        f"{APPLE_API_BASE}/inApps/v1/subscriptions/{urllib.parse.quote(original_transaction_id)}",
        headers={"Authorization": f"Bearer {_apple_bearer()}"},
    )
    if resp.status_code != 200:
        logger.warning("apple_subscription_verify_failed", extra={"status": resp.status_code})
        raise VerificationError("App Store verification failed")
    for group in resp.json().get("data", []):
        for last in group.get("lastTransactions", []):
            signed = last.get("signedTransactionInfo") or ""
            if not signed:
                continue
            info = _decode_signed_transaction(signed)
            if info.get("originalTransactionId") == original_transaction_id:
                return info.get("expiresDate"), last.get("status")
    return None, None


# --- Webhook signature verification -------------------------------------------


def _chain_verified(certs, trusted_root) -> bool:
    """Every cert is signed by its successor; the last cert is the trusted root
    or signed directly by it; all certs are within their validity window."""
    try:
        now = time.time()
        for cert in certs:
            if now < cert.not_valid_before_utc.timestamp() or now > cert.not_valid_after_utc.timestamp():
                return False
        for i in range(len(certs) - 1):
            certs[i].verify_directly_issued_by(certs[i + 1])
        # The terminal cert must be signed by the trusted root's own key —
        # never short-circuit on the subject string. A self-signed root, a root
        # that really is the final cert, and an intermediate signed by the root
        # all pass; a forged "root" that merely copies the subject fails (F1).
        certs[-1].verify_directly_issued_by(trusted_root)
    except (ValueError, InvalidSignature):
        return False
    return True


def _verify_apple_signed_payload(signed: str) -> dict:
    """Verify an App Store Server Notification v2 signedPayload (JWS with x5c
    chain terminating at Apple Root CA - G3) and return its claims."""
    from jose import JWTError
    from jose import exceptions as jose_exc

    try:
        header = jose_jws.get_unverified_header(signed)
        x5c = header.get("x5c")
        if not x5c:
            raise VerificationError("Notification is missing its certificate chain")
        from cryptography import x509

        certs = [x509.load_der_x509_certificate(base64.b64decode(c)) for c in x5c]
        root = x509.load_pem_x509_certificate(APPLE_ROOT_CA_G3.encode())
        if not _chain_verified(certs, root):
            raise VerificationError("Notification certificate chain is untrusted")
        payload = jose_jws.verify(signed, certs[0].public_key(), algorithms=["ES256"])
        return json.loads(payload)
    except (JWTError, jose_exc.JWSError, ValueError, TypeError, InvalidSignature):
        raise VerificationError("Notification JWS could not be verified")


async def verify_google_push_auth(auth_header: str) -> None:
    """Verify the Pub/Sub push OIDC bearer token (see _verify_google_push_auth)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        await _verify_google_push_auth(client, auth_header)


# Google OIDC token issuers for Pub/Sub push authentication (F6).
_GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
_JWKS_CACHE: dict = {"fetched_at": 0.0, "keys": []}


async def _google_jwks(client: httpx.AsyncClient, kid: str):
    """JWKS for Google's signing keys, cached ~24h and refetched on unknown kid."""
    cache = _JWKS_CACHE
    keys = cache["keys"]
    if time.time() - cache["fetched_at"] > 86400 or not any(k.get("kid") == kid for k in keys):
        resp = await client.get(GOOGLE_JWKS_URL)
        if resp.status_code != 200:
            raise VerificationError("Google JWKS unavailable")
        cache["keys"] = resp.json().get("keys", [])
        cache["fetched_at"] = time.time()
    for key in cache["keys"]:
        if key.get("kid") == kid:
            return jose_jwk.construct(key, algorithm="RS256")
    return None


async def _verify_google_push_auth(client: httpx.AsyncClient, auth_header: str) -> None:
    """Verify the Pub/Sub push OIDC bearer token against Google's JWKS.

    The token's audience defaults to the push endpoint URL; operators may
    override via IAP_GOOGLE_PUBSUB_AUDIENCE.
    """
    from jose import JWTError

    if not auth_header.startswith("Bearer "):
        raise VerificationError("Missing Google Pub/Sub auth token")
    token = auth_header[len("Bearer ") :]
    try:
        unverified = jose_jwt.get_unverified_claims(token)
    except JWTError:
        raise VerificationError("Google Pub/Sub auth token is malformed")
    expected_aud = (
        settings.IAP_GOOGLE_PUBSUB_AUDIENCE
        or settings.APP_BASE_URL.rstrip("/") + settings.API_V1_PREFIX + "/billing/iap/webhook/google"
    )
    if unverified.get("aud") != expected_aud:
        raise VerificationError("Google Pub/Sub token audience mismatch")
    if unverified.get("iss") not in _GOOGLE_ISSUERS:
        raise VerificationError("Google Pub/Sub token issuer mismatch")
    exp = unverified.get("exp")
    if isinstance(exp, int) and exp < int(time.time()):
        raise VerificationError("Google Pub/Sub token has expired")
    kid = jose_jwt.get_unverified_header(token).get("kid")
    signing_key = await _google_jwks(client, kid)
    if signing_key is None:
        raise VerificationError("Google Pub/Sub signing key not found")
    try:
        jose_jwt.decode(token, signing_key, algorithms=["RS256"], audience=expected_aud)
    except JWTError:
        raise VerificationError("Google Pub/Sub token signature is invalid")


# --- Top-level verify + refresh -----------------------------------------------


async def _purchase_owner(db, platform: str, transaction_id: str, original_txn, purchase_token: str):
    """User currently holding this purchase, or None."""
    if platform == "android":
        return await db.scalar(select(User).where(User.iap_purchase_token == purchase_token))
    if original_txn:
        return await db.scalar(
            select(User).where(
                (User.iap_transaction_id == transaction_id) | (User.iap_original_transaction_id == original_txn)
            )
        )
    return await db.scalar(select(User).where(User.iap_transaction_id == transaction_id))


async def verify_and_grant(
    db, user: User, platform: str, product_id: str, transaction_id: str, purchase_token: str
) -> dict:
    """Verify a store transaction server-side and grant the entitlement.

    Raises VerificationError when the platform is unconfigured, the transaction
    cannot be verified, or the product id does not match.
    """
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if platform == "android":
            if not google_configured():
                raise VerificationError("Google Play IAP is not configured")
            token = await _google_access_token(client)
            data = await _google_subscription(client, token, product_id, purchase_token)
            # Cross-check the store-returned product/package, mirroring iOS (F5).
            if data.get("productId") and data.get("productId") != product_id:
                raise VerificationError("Product mismatch")
            if data.get("packageName") and data.get("packageName") != settings.IAP_GOOGLE_PACKAGE_NAME:
                raise VerificationError("Package mismatch")
            original_txn = None
            expires_at = _expires_at_from_ms(_google_expiry_ms(data))
        elif platform == "ios":
            if not apple_configured():
                raise VerificationError("App Store IAP is not configured")
            info = await _apple_transaction(client, transaction_id)
            original_txn = info.get("originalTransactionId")
            expires_at = _expires_at_from_ms(info.get("expiresDate"))
            _validate_apple_info(info, product_id, transaction_id)
        else:
            raise VerificationError("Unsupported platform")

    # Replay protection (F2): one store purchase must not be granted to a
    # second account. Same-user re-verification (retry after a partial failure)
    # is allowed; ownership of the purchase elsewhere is rejected.
    owner = await _purchase_owner(db, platform, transaction_id, original_txn, purchase_token)
    if owner is not None and owner.id != user.id:
        raise VerificationError("This purchase is already linked to another account")

    if billing.plan_for_iap_product(product_id) is None:
        raise VerificationError("Unknown product id")

    billing.apply_iap(
        user, product_id, platform, transaction_id, purchase_token, expires_at, original_txn
    )
    await db.commit()
    return {
        "status": "active",
        "plan": billing.plan_for_iap_product(product_id),
        "max_vehicles": user.max_vehicles,
        "free_account": user.free_account,
    }


def _validate_apple_info(info: dict, product_id: str, transaction_id: str) -> None:
    if info.get("productId") != product_id:
        raise VerificationError("Product mismatch")
    if info.get("bundleId") and info.get("bundleId") != settings.IAP_APPLE_BUNDLE_ID:
        raise VerificationError("Bundle id mismatch")
    if info.get("transactionId") and info.get("transactionId") != transaction_id:
        raise VerificationError("Transaction id mismatch")
    if info.get("status") == 2 or info.get("revocationDate"):
        raise VerificationError("Transaction was revoked by Apple")


def _expires_at_from_ms(ms) -> datetime | None:
    if not ms:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)


def should_refresh(user: User) -> bool:
    """True when /auth/me should re-validate the stored entitlement.

    Refresh when the entitlement is expired or within IAP_REFRESH_WINDOW_DAYS of
    expiry; comfortably-active entitlements are served from the cached expiry so
    the store APIs are only hit ~once per billing period.
    """
    status = billing.iap_status(user)
    if status is None or status == "revoked":
        return False
    if status == "expired":
        return True
    if user.iap_expires_at is None:
        return False
    expires = user.iap_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return (expires - datetime.now(timezone.utc)).days <= settings.IAP_REFRESH_WINDOW_DAYS


async def refresh_entitlement(db, user: User, force: bool = False) -> None:
    """Re-validate a stored purchase against the store API and update the
    entitlement. Transient store failures leave the cached state untouched
    (never demote on a network error); a definitive non-active state settles
    the entitlement to expired/revoked (F3). A per-user cooldown bounds how
    often a lapsed user can trigger store calls from /auth/me (F4)."""
    if not user.iap_product_id or not user.iap_purchase_token:
        return
    if not force and not should_refresh(user):
        return
    cooldown = timedelta(minutes=settings.IAP_REFRESH_COOLDOWN_MINUTES)
    last = user.iap_refreshed_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if not force and datetime.now(timezone.utc) - last < cooldown:
            return
    # Record the attempt up-front so a failing store call still cools the
    # account down instead of re-hitting the store on every /auth/me.
    user.iap_refreshed_at = datetime.now(timezone.utc)
    await db.commit()
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if user.iap_platform == "android":
                if not google_configured():
                    return
                token = await _google_access_token(client)
                data = await _google_subscription(
                    client, token, user.iap_product_id, user.iap_purchase_token
                )
                expires_at = _expires_at_from_ms(_google_expiry_ms(data))
            elif user.iap_platform == "ios":
                if not apple_configured() or not user.iap_original_transaction_id:
                    return
                expires_ms, status = await _apple_subscription(
                    client, user.iap_original_transaction_id
                )
                if status is not None and status not in _APPLE_ACTIVE_STATUSES:
                    billing.clear_iap(user, "revoked" if status == 5 else "expired")
                    await db.commit()
                    return
                expires_at = _expires_at_from_ms(expires_ms)
            else:
                return
        except SubscriptionNotActive as exc:
            billing.clear_iap(user, exc.status)
            await db.commit()
            return
        except (VerificationError, httpx.HTTPError):
            logger.warning("iap_refresh_failed", extra={"user": user.id, "platform": user.iap_platform})
            return
    if expires_at is None:
        return
    if expires_at <= datetime.now(timezone.utc):
        billing.clear_iap(user, "expired")
    else:
        # Re-apply: also re-grants if a previous refresh had demoted the account
        # while the store still shows the subscription as active (renewed).
        billing.apply_iap(
            user,
            user.iap_product_id,
            user.iap_platform,
            user.iap_transaction_id,
            user.iap_purchase_token,
            expires_at,
            user.iap_original_transaction_id,
        )
    await db.commit()


# --- Webhook handlers ---------------------------------------------------------


async def handle_apple_webhook(db, signed_payload: str) -> dict:
    """App Store Server Notifications v2 (JWS-signed). Matches the account by
    originalTransactionId, then re-verifies against the App Store API so the
    authoritative subscription state drives the entitlement."""
    try:
        payload = _verify_apple_signed_payload(signed_payload)
    except VerificationError as exc:
        raise VerificationError(f"Invalid App Store notification: {exc}")
    txn_info = None
    data = payload.get("data") or {}
    bundle_id = data.get("bundleId")
    if bundle_id and bundle_id != settings.IAP_APPLE_BUNDLE_ID:
        raise VerificationError("Notification bundle id mismatch")
    if data.get("signedTransactionInfo"):
        txn_info = _decode_signed_transaction(data["signedTransactionInfo"])
    original_txn = (txn_info or {}).get("originalTransactionId")
    if not original_txn:
        return {"received": True}  # e.g. TEST notification — nothing to do
    user = await db.scalar(
        select(User).where(User.iap_original_transaction_id == original_txn)
    )
    if user is None:
        return {"received": True}  # renewal/refund for an entitlement we never granted
    await refresh_entitlement(db, user, force=True)
    return {"received": True}


async def handle_google_webhook(db, envelope: dict) -> dict:
    """Play Real-time Developer Notification delivered via Pub/Sub push."""
    if not google_configured():
        raise VerificationError("Google Play IAP is not configured")
    message = envelope.get("message") or {}
    raw = message.get("data")
    if not raw:
        return {"received": True}
    try:
        notification = json.loads(_b64decode(raw))
    except Exception:
        return {"received": True}
    purchase_token = None
    sub = notification.get("subscriptionNotification")
    otp = notification.get("oneTimeProductNotification")
    if sub:
        purchase_token = sub.get("purchaseToken")
    elif otp:
        purchase_token = otp.get("purchaseToken")
    if not purchase_token:
        return {"received": True}
    user = await db.scalar(select(User).where(User.iap_purchase_token == purchase_token))
    if user is None:
        return {"received": True}
    await refresh_entitlement(db, user, force=True)
    return {"received": True}
