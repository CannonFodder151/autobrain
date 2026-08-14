"""Store-native IAP (Apple/Google) tests: catalogue, entitlement, verification.

Run (no Postgres needed):
    cd backend && python3 -m pytest tests/test_iap.py -q
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ.setdefault("ENVIRONMENT", "development")

import base64  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import billing as svc  # noqa: E402
from app.services import iap  # noqa: E402

PRODUCT_MONTHLY = "com.autobrainservice.app.enthusiast.monthly"
PRODUCT_GARAGE = "com.autobrainservice.app.garage.yearly"


class _FakeDB:
    def __init__(self, scalar_result=None) -> None:
        self._result = scalar_result

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def scalar(self, *args, **kwargs):
        return self._result


def _user(**kw) -> User:
    defaults = dict(
        id=str(uuid.uuid4()),
        email="u@example.com",
        display_name="U",
        hashed_password="x",
        role="user",
        max_vehicles=1,
        free_account=True,
    )
    defaults.update(kw)
    return User(**defaults)


@pytest.fixture(autouse=True)
def clean_iap_config(monkeypatch):
    monkeypatch.setattr(settings, "IAP_GOOGLE_SERVICE_ACCOUNT_JSON", "")
    monkeypatch.setattr(settings, "IAP_GOOGLE_PACKAGE_NAME", "com.autobrainservice.app")
    monkeypatch.setattr(settings, "IAP_APPLE_ISSUER_ID", "")
    monkeypatch.setattr(settings, "IAP_APPLE_KEY_ID", "")
    monkeypatch.setattr(settings, "IAP_APPLE_PRIVATE_KEY", "")
    monkeypatch.setattr(settings, "IAP_APPLE_BUNDLE_ID", "com.autobrainservice.app")
    monkeypatch.setattr(settings, "IAP_REFRESH_WINDOW_DAYS", 2)
    return None


def _google_json() -> str:
    return json.dumps({"client_email": "sa@test.iam.gserviceaccount.com", "private_key": "x"})


def _expires_ms(days=30) -> int:
    return int((time.time() + days * 86400) * 1000)


def _expires_at(days=30):
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) + timedelta(days=days)


# --- catalogue ----------------------------------------------------------------


def test_catalog_disabled_by_default() -> None:
    data = iap.catalog()
    assert data["enabled"] is False
    assert len(data["products"]) == 8  # 4 product ids x 2 platforms


def test_catalog_enabled_with_google(monkeypatch) -> None:
    monkeypatch.setattr(settings, "IAP_GOOGLE_SERVICE_ACCOUNT_JSON", _google_json())
    data = iap.catalog()
    assert data["enabled"] is True
    ids = {(p["product_id"], p["platform"]) for p in data["products"]}
    assert ("com.autobrainservice.app.enthusiast.monthly", "android") in ids
    assert ("com.autobrainservice.app.enthusiast.monthly", "ios") in ids
    by_id = {p["product_id"]: p for p in data["products"]}
    assert by_id[PRODUCT_GARAGE]["plan"] == "garage"
    assert by_id[PRODUCT_GARAGE]["billing"] == "yearly"


def test_catalog_endpoint_public() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    import anyio

    async def _go():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/v1/billing/iap/catalog")

    resp = anyio.run(_go)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


# --- entitlement --------------------------------------------------------------


def test_plan_for_iap_product() -> None:
    assert svc.plan_for_iap_product(PRODUCT_MONTHLY) == "enthusiast"
    assert svc.plan_for_iap_product(PRODUCT_GARAGE) == "garage"
    assert svc.plan_for_iap_product("com.nope") is None


def test_apply_iap_grants_plan_and_fields() -> None:
    u = _user()
    svc.apply_iap(u, PRODUCT_MONTHLY, "android", "txn-1", "tok-1", _expires_at())
    assert u.free_account is False
    assert u.max_vehicles == 1  # enthusiast cap
    assert u.iap_platform == "android"
    assert u.iap_product_id == PRODUCT_MONTHLY
    assert u.iap_transaction_id == "txn-1"
    assert u.iap_status == "active"
    assert svc.iap_status(u) == "active"
    assert svc.plan_for_user(u) == "enthusiast"


def test_apply_iap_upgrade_replaces_without_double_grant() -> None:
    u = _user()
    svc.apply_iap(u, PRODUCT_MONTHLY, "ios", "txn-1", "tok-1", _expires_at())
    svc.apply_iap(u, PRODUCT_GARAGE, "ios", "txn-2", "tok-2", _expires_at())
    assert u.iap_transaction_id == "txn-2"
    assert u.max_vehicles == 5  # garage cap, not stacked
    assert svc.plan_for_user(u) == "garage"


def test_apply_iap_unknown_product() -> None:
    with pytest.raises(ValueError):
        svc.apply_iap(_user(), "com.nope", "android", "t", "p", _expires_at())


def test_iap_status_lifecycle() -> None:
    u = _user()
    assert svc.iap_status(u) is None
    assert svc.plan_for_user(u) == "free"

    svc.apply_iap(u, PRODUCT_MONTHLY, "android", "t1", "p1", _expires_at(days=5))
    assert svc.iap_status(u) == "active"

    u.iap_expires_at = _expires_at(days=-1)
    assert svc.iap_status(u) == "expired"
    assert svc.plan_for_user(u) == "free"

    u.iap_status = "revoked"
    assert svc.iap_status(u) == "revoked"


def test_iap_status_expired_does_not_count_as_paid() -> None:
    u = _user(free_account=True)
    svc.apply_iap(u, PRODUCT_MONTHLY, "ios", "t1", "p1", _expires_at(days=-2))
    assert svc.plan_for_user(u) == "free"
    assert svc.has_paid_subscription(u) is False


def test_clear_iap_demotes_but_keeps_stripe_plan(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STRIPE_PRICE_ENTHUSIAST_MONTHLY", "price_enth_m")
    monkeypatch.setattr(settings, "STRIPE_PRICE_GARAGE_YEARLY", "price_gar_y")
    u = _user()
    svc.apply_iap(u, PRODUCT_GARAGE, "android", "t1", "p1", _expires_at(days=-1))
    svc.clear_iap(u)
    assert u.free_account is True
    assert u.max_vehicles == 1
    assert svc.plan_for_user(u) == "free"

    # A still-active Stripe sub keeps the paid plan when IAP lapses.
    u2 = _user()
    u2.stripe_subscription_id = "sub_1"
    u2.stripe_customer_id = "cus_1"
    u2.stripe_subscription_status = "active"
    u2.stripe_price_id = "price_enth_m"
    svc.apply_plan(u2, "enthusiast")
    svc.apply_iap(u2, PRODUCT_GARAGE, "android", "t1", "p1", _expires_at(days=-1))
    svc.clear_iap(u2)
    assert u2.free_account is False
    assert svc.plan_for_user(u2) == "enthusiast"


def test_iap_grant_counts_as_paid_subscription() -> None:
    u = _user()
    svc.apply_iap(u, PRODUCT_MONTHLY, "ios", "t1", "p1", _expires_at(days=3))
    assert svc.has_paid_subscription(u) is True


# --- google verification ------------------------------------------------------


@pytest.fixture()
def google_cfg(monkeypatch):
    monkeypatch.setattr(settings, "IAP_GOOGLE_SERVICE_ACCOUNT_JSON", _google_json())
    return None


@pytest.mark.asyncio
async def test_verify_and_grant_android(google_cfg, monkeypatch) -> None:
    async def _token(client):
        return "access-1"

    async def _sub(client, token, product_id, purchase_token):
        assert token == "access-1"
        return {"productId": PRODUCT_MONTHLY, "purchaseState": 0, "expiryTimeMillis": str(_expires_ms())}

    monkeypatch.setattr(iap, "_google_access_token", _token)
    monkeypatch.setattr(iap, "_google_subscription", _sub)

    u = _user()
    result = await iap.verify_and_grant(_FakeDB(), u, "android", PRODUCT_MONTHLY, "txn-1", "tok-1")
    assert result == {"status": "active", "plan": "enthusiast", "max_vehicles": 1, "free_account": False}
    assert u.iap_platform == "android"
    assert u.iap_purchase_token == "tok-1"


@pytest.mark.asyncio
async def test_verify_and_grant_android_cancelled(google_cfg, monkeypatch) -> None:
    async def _token(client):
        return "access-1"

    monkeypatch.setattr(iap, "_google_access_token", _token)

    def _handler(request):
        return httpx.Response(200, json={"productId": PRODUCT_MONTHLY, "purchaseState": 1})

    real_client = httpx.AsyncClient

    def _client(**kw):
        return real_client(transport=httpx.MockTransport(_handler))

    monkeypatch.setattr(iap.httpx, "AsyncClient", _client)

    with pytest.raises(iap.VerificationError):
        await iap.verify_and_grant(_FakeDB(), _user(), "android", PRODUCT_MONTHLY, "txn-1", "tok-1")


@pytest.mark.asyncio
async def test_verify_android_unconfigured() -> None:
    with pytest.raises(iap.VerificationError):
        await iap.verify_and_grant(_FakeDB(), _user(), "android", PRODUCT_MONTHLY, "txn-1", "tok-1")


@pytest.mark.asyncio
async def test_verify_unknown_product(google_cfg, monkeypatch) -> None:
    async def _token(client):
        return "access-1"

    async def _sub(client, token, product_id, purchase_token):
        return {"productId": "com.nope", "purchaseState": 0, "expiryTimeMillis": str(_expires_ms())}

    monkeypatch.setattr(iap, "_google_access_token", _token)
    monkeypatch.setattr(iap, "_google_subscription", _sub)

    with pytest.raises(iap.VerificationError):
        await iap.verify_and_grant(_FakeDB(), _user(), "android", "com.nope", "txn-1", "tok-1")


# --- apple verification -------------------------------------------------------


@pytest.fixture()
def apple_cfg(monkeypatch):
    monkeypatch.setattr(settings, "IAP_APPLE_ISSUER_ID", "issuer-1")
    monkeypatch.setattr(settings, "IAP_APPLE_KEY_ID", "key-1")
    monkeypatch.setattr(settings, "IAP_APPLE_PRIVATE_KEY", "-----BEGIN EC PRIVATE KEY-----test-----END EC PRIVATE KEY-----")
    return None


@pytest.mark.asyncio
async def test_verify_and_grant_ios(apple_cfg, monkeypatch) -> None:
    async def _txn(client, transaction_id):
        return {
            "productId": PRODUCT_MONTHLY,
            "bundleId": "com.autobrainservice.app",
            "transactionId": "txn-1",
            "originalTransactionId": "orig-1",
            "expiresDate": str(_expires_ms()),
        }

    monkeypatch.setattr(iap, "_apple_transaction", _txn)

    u = _user()
    result = await iap.verify_and_grant(_FakeDB(), u, "ios", PRODUCT_MONTHLY, "txn-1", "signed-jws")
    assert result["plan"] == "enthusiast"
    assert result["free_account"] is False
    assert u.iap_original_transaction_id == "orig-1"
    assert svc.plan_for_user(u) == "enthusiast"


@pytest.mark.asyncio
async def test_verify_ios_product_mismatch(apple_cfg, monkeypatch) -> None:
    async def _txn(client, transaction_id):
        return {"productId": PRODUCT_GARAGE, "bundleId": "com.autobrainservice.app"}

    monkeypatch.setattr(iap, "_apple_transaction", _txn)

    with pytest.raises(iap.VerificationError):
        await iap.verify_and_grant(_FakeDB(), _user(), "ios", PRODUCT_MONTHLY, "txn-1", "jws")


@pytest.mark.asyncio
async def test_verify_ios_revoked(apple_cfg, monkeypatch) -> None:
    async def _txn(client, transaction_id):
        return {"productId": PRODUCT_MONTHLY, "bundleId": "com.autobrainservice.app", "revocationDate": "2026-01-01"}

    monkeypatch.setattr(iap, "_apple_transaction", _txn)

    with pytest.raises(iap.VerificationError):
        await iap.verify_and_grant(_FakeDB(), _user(), "ios", PRODUCT_MONTHLY, "txn-1", "jws")


# --- refresh ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_renews_expired_google(google_cfg, monkeypatch) -> None:
    async def _token(client):
        return "access-1"

    async def _sub(client, token, product_id, purchase_token):
        return {"productId": product_id, "purchaseState": 0, "expiryTimeMillis": str(_expires_ms(30))}

    monkeypatch.setattr(iap, "_google_access_token", _token)
    monkeypatch.setattr(iap, "_google_subscription", _sub)

    u = _user()
    svc.apply_iap(u, PRODUCT_MONTHLY, "android", "t1", "tok-1", _expires_at(days=-1))
    assert svc.iap_status(u) == "expired"

    await iap.refresh_entitlement(_FakeDB(), u)
    assert svc.iap_status(u) == "active"
    assert svc.plan_for_user(u) == "enthusiast"


@pytest.mark.asyncio
async def test_refresh_google_expired_demotes(google_cfg, monkeypatch) -> None:
    async def _token(client):
        return "access-1"

    async def _sub(client, token, product_id, purchase_token):
        return {"productId": product_id, "purchaseState": 0, "expiryTimeMillis": str(int(time.time() * 1000) - 1000)}

    monkeypatch.setattr(iap, "_google_access_token", _token)
    monkeypatch.setattr(iap, "_google_subscription", _sub)

    u = _user()
    svc.apply_iap(u, PRODUCT_GARAGE, "android", "t1", "tok-1", _expires_at(days=-1))
    await iap.refresh_entitlement(_FakeDB(), u)
    assert svc.iap_status(u) == "expired"
    assert svc.plan_for_user(u) == "free"


@pytest.mark.asyncio
async def test_refresh_transient_failure_keeps_state(google_cfg, monkeypatch) -> None:
    async def _token(client):
        raise iap.VerificationError("boom")

    monkeypatch.setattr(iap, "_google_access_token", _token)

    u = _user()
    svc.apply_iap(u, PRODUCT_MONTHLY, "android", "t1", "tok-1", _expires_at(days=1))
    await iap.refresh_entitlement(_FakeDB(), u)
    assert svc.iap_status(u) == "active"


@pytest.mark.asyncio
async def test_refresh_skipped_while_comfortably_active(google_cfg, monkeypatch) -> None:
    called = []

    async def _token(client):
        called.append(True)
        return "access-1"

    async def _sub(client, token, product_id, purchase_token):
        called.append(True)
        return {}

    monkeypatch.setattr(iap, "_google_access_token", _token)
    monkeypatch.setattr(iap, "_google_subscription", _sub)

    u = _user()
    svc.apply_iap(u, PRODUCT_MONTHLY, "android", "t1", "tok-1", _expires_at(days=30))
    assert iap.should_refresh(u) is False
    await iap.refresh_entitlement(_FakeDB(), u)
    assert called == []


# --- apple webhook signature verification -------------------------------------


def _test_root_leaf() -> tuple:
    """Generate a throwaway root + leaf cert chain and a JWS signed by it.

    Returns (root_pem, signed, root_key, root_cert).
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from jose import jwt as jose_jwt

    now = datetime.datetime.now(datetime.timezone.utc)

    def _mk(name, parent=None):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        issuer = subject if parent is None else x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, parent["name"])])
        signing = parent["key"] if parent else key
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(2)
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365))
            .sign(signing, hashes.SHA256())
        )
        return {"key": key, "cert": cert, "name": name}

    root = _mk("Apple Root CA - G3")
    leaf = _mk("leaf", root)
    root_pem = root["cert"].public_bytes(serialization.Encoding.PEM).decode()
    x5c = [
        base64.b64encode(leaf["cert"].public_bytes(serialization.Encoding.DER)).decode(),
        base64.b64encode(root["cert"].public_bytes(serialization.Encoding.DER)).decode(),
    ]
    signed = jose_jwt.encode(
        {"notificationType": "EXPIRED", "data": {}},
        leaf["key"],
        algorithm="ES256",
        headers={"alg": "ES256", "x5c": x5c},
    )
    return root_pem, signed, root["key"], root["cert"]


def test_apple_webhook_rejects_bad_signature() -> None:
    with pytest.raises(iap.VerificationError):
        iap._verify_apple_signed_payload("not-a-jws")


@pytest.mark.asyncio
async def test_apple_webhook_valid_signature_ignores_unknown_user(monkeypatch) -> None:
    root_pem, signed, _root_key, _root_cert = _test_root_leaf()
    monkeypatch.setattr(iap, "APPLE_ROOT_CA_G3", root_pem)

    result = await iap.handle_apple_webhook(_FakeDB(), signed)
    assert result == {"received": True}


@pytest.mark.asyncio
async def test_apple_webhook_refreshes_matched_user(monkeypatch) -> None:
    root_pem, signed, root_key, _root_cert = _test_root_leaf()
    monkeypatch.setattr(iap, "APPLE_ROOT_CA_G3", root_pem)

    # Build a payload with a real transaction info so a user is matched.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from jose import jwt as jose_jwt

    now = datetime.datetime.now(datetime.timezone.utc)
    key = ec.generate_private_key(ec.SECP256R1())
    root_cert = x509.load_pem_x509_certificate(root_pem.encode())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "leaf2")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(root_cert.subject)
        .public_key(key.public_key())
        .serial_number(3)
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(root_key, hashes.SHA256())
    )
    x5c = [
        base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode(),
        base64.b64encode(root_cert.public_bytes(serialization.Encoding.DER)).decode(),
    ]
    txn_info = {"originalTransactionId": "orig-9", "productId": PRODUCT_MONTHLY}
    signed = jose_jwt.encode(
        {
            "notificationType": "DID_RENEW",
            "data": {"signedTransactionInfo": jose_jwt.encode(txn_info, key, algorithm="ES256")},
        },
        key,
        algorithm="ES256",
        headers={"alg": "ES256", "x5c": x5c},
    )

    refreshed = []

    async def _refresh(db, user, force=False):
        refreshed.append(user.id)

    monkeypatch.setattr(iap, "refresh_entitlement", _refresh)

    u = _user()
    u.iap_original_transaction_id = "orig-9"
    u.iap_product_id = PRODUCT_MONTHLY
    u.iap_purchase_token = "jws"
    u.iap_transaction_id = "t1"

    db = _FakeDB(scalar_result=u)

    result = await iap.handle_apple_webhook(db, signed)
    assert result == {"received": True}
    assert refreshed == [u.id]


# --- google webhook -----------------------------------------------------------


@pytest.mark.asyncio
async def test_google_webhook_pubsub_envelope(google_cfg, monkeypatch) -> None:
    refreshed = []

    async def _refresh(db, user, force=False):
        refreshed.append(user.id)

    monkeypatch.setattr(iap, "refresh_entitlement", _refresh)

    notification = {
        "version": "1.0",
        "packageName": "com.autobrainservice.app",
        "subscriptionNotification": {
            "notificationType": 2,
            "subscriptionId": PRODUCT_MONTHLY,
            "purchaseToken": "tok-42",
        },
    }
    envelope = {"message": {"data": base64.b64encode(json.dumps(notification).encode()).decode()}}

    u = _user()
    u.iap_purchase_token = "tok-42"
    db = _FakeDB(scalar_result=u)

    result = await iap.handle_google_webhook(db, envelope)
    assert result == {"received": True}
    assert refreshed == [u.id]
