"""Merch store tests (AUT-1540): catalogue, checkout validation, webhook order
recording with shipping details."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import json  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402

from app.models.user import User  # noqa: E402
from app.services import billing as billing_svc  # noqa: E402
from app.services import merch as svc  # noqa: E402


def _user() -> User:
    return User(
        id=str(uuid.uuid4()),
        email="u@example.com",
        display_name="U",
        hashed_password="x",
        role="user",
        max_vehicles=1,
        free_account=True,
    )


class _FakeSessions:
    def __init__(self, capture: dict):
        self._capture = capture

    def create(self, params):
        self._capture.update(params)
        return type("S", (), {"url": "https://checkout.stripe.com/x"})()


class _FakeClient:
    def __init__(self, capture: dict):
        self.checkout = type("C", (), {"sessions": _FakeSessions(capture)})()


@pytest.fixture()
def fake_stripe(monkeypatch):
    capture: dict = {}
    monkeypatch.setattr(billing_svc, "get_client", lambda: _FakeClient(capture))
    monkeypatch.setattr(svc, "get_client", lambda: _FakeClient(capture))
    async def _ensure(db, user):
        user.stripe_customer_id = "cus_test"
        return "cus_test"
    monkeypatch.setattr(svc, "ensure_customer", _ensure)
    return capture


def test_catalog_deterministic() -> None:
    a, b = svc.catalog(), svc.catalog()
    assert a == b
    ids = [p["id"] for p in a["products"]]
    assert "beanie" in ids
    beanie = next(p for p in a["products"] if p["id"] == "beanie")
    assert beanie["amount"] > 0 and beanie["name"]


def test_checkout_collects_shipping(fake_stripe) -> None:
    import asyncio

    u = _user()
    url = asyncio.run(svc.create_checkout_session(None, u, "beanie", 2))
    assert url.startswith("https://checkout.stripe.com/")
    assert fake_stripe["mode"] == "payment"
    assert fake_stripe["shipping_address_collection"]["allowed_countries"]
    assert fake_stripe["shipping_options"][0]["shipping_rate_data"]["fixed_amount"]["amount"] == svc.SHIPPING_FLAT_CENTS
    assert fake_stripe["phone_number_collection"] == {"enabled": True}
    assert fake_stripe["metadata"]["kind"] == "merch"
    assert fake_stripe["line_items"][0]["quantity"] == 2
    assert fake_stripe["line_items"][0]["price_data"]["unit_amount"] == 2500


def test_checkout_validation(fake_stripe) -> None:
    import asyncio

    u = _user()
    with pytest.raises(ValueError):
        asyncio.run(svc.create_checkout_session(None, u, "nope", 1))
    with pytest.raises(ValueError):
        asyncio.run(svc.create_checkout_session(None, u, "beanie", 99))


def test_shipping_from_session_variants() -> None:
    full = {
        "collected_information": {
            "shipping_details": {
                "name": "Nathan",
                "address": {
                    "line1": "1 St",
                    "city": "Melbourne",
                    "state": "VIC",
                    "postal_code": "3000",
                    "country": "AU",
                },
            }
        },
        "customer_details": {"phone": "+61400000000"},
    }
    got = svc.shipping_from_session(full)
    assert got == {
        "name": "Nathan",
        "phone": "+61400000000",
        "line1": "1 St",
        "city": "Melbourne",
        "state": "VIC",
        "postal_code": "3000",
        "country": "AU",
    }
    assert svc.shipping_from_session({}) is None


class _FakeResult:
    def __init__(self, value=None):
        self._value = value

    def scalar(self, *a, **k):
        return None

    def scalars(self, *a, **k):
        return []


class _FakeDB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def scalar(self, *a, **k):
        return None


def test_record_paid_session_idempotent_shape() -> None:
    session = {
        "id": "cs_test_1",
        "mode": "payment",
        "client_reference_id": str(uuid.uuid4()),
        "amount_total": 2595,
        "currency": "aud",
        "metadata": {"kind": "merch", "product_id": "beanie", "quantity": "1"},
        "collected_information": {
            "shipping_details": {"name": "Nat", "address": {"line1": "1 St", "country": "AU"}}
        },
    }
    db = _FakeDB()
    import asyncio

    asyncio.run(svc.record_paid_session(db, dict(session)))
    assert len(db.added) == 1
    order = db.added[0]
    assert order.product_id == "beanie"
    assert order.amount_total == 2595
    shipping = json.loads(order.shipping_address)
    assert shipping["name"] == "Nat" and shipping["country"] == "AU"

    # Non-merch and non-payment sessions are ignored.
    for mutated in (
        {**session, "mode": "subscription"},
        {**session, "metadata": {"kind": "subscription"}},
    ):
        db2 = _FakeDB()
        asyncio.run(svc.record_paid_session(db2, mutated))
        assert db2.added == []
