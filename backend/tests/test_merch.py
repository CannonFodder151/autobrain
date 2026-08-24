"""Merch webhook-recording tests (AUT-1567): in-app merch sale is banned
(docs/product-rules.md PR-2); only order recording from Stripe webhooks exists."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import json  # noqa: E402
import uuid  # noqa: E402

from app.api.v1 import api_router  # noqa: E402
from app.services import merch as svc  # noqa: E402


def test_pr2_no_merch_sale_surface_in_app() -> None:
    """Guard: the app API must never expose a merch catalogue/checkout/orders."""
    paths = {route.path for route in api_router.routes}
    merch_paths = [p for p in paths if "/merch" in p]
    assert merch_paths == [], f"In-app merch surface must not exist: {merch_paths}"
    assert not hasattr(svc, "PRODUCTS"), "No in-code merch catalogue allowed"
    assert not hasattr(svc, "create_checkout_session"), "No in-app merch checkout allowed"


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
        "amount_total": 5500,
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
    assert order.amount_total == 5500
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
