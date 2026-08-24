"""Merch store: catalogue, Stripe payment checkouts with shipping collection,
and order history (AUT-1540).

The catalogue is a deterministic in-code dict — merch products are few and
change rarely, so there is no merch table to manage. Orders themselves are
persisted when the Stripe webhook reports checkout.session.completed
(mode=payment); the session id makes recording idempotent against replays.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merch import MerchOrder
from app.models.user import User
from app.core.config import settings
from app.services.billing import CURRENCY, ensure_customer, get_client

logger = logging.getLogger(__name__)

# Optional flat-rate shipping added at checkout; products with free_shipping
# skip it entirely (address still collected via shipping_address_collection).
SHIPPING_FLAT_CENTS = 995
SHIPPING_COUNTRIES = ["AU", "NZ", "US", "GB", "CA"]

PRODUCTS: dict[str, dict] = {
    "beanie": {
        "name": "AutoBrain Beanie",
        "description": "Embroidered AutoBrain beanie. One size.",
        "amount": 5500,  # AUD cents
        "free_shipping": True,
    },
}

MAX_QTY = 10


def catalog() -> dict:
    """Deterministic catalogue for GET /merch/catalog."""
    return {
        "currency": CURRENCY,
        "shipping_flat_cents": SHIPPING_FLAT_CENTS,
        "products": [
            {"id": pid, **prod} for pid, prod in PRODUCTS.items()
        ],
    }


def _validate(product_id: str, quantity: int) -> str:
    if product_id not in PRODUCTS:
        raise ValueError("Unknown product")
    if not isinstance(quantity, int) or quantity < 1 or quantity > MAX_QTY:
        raise ValueError(f"Quantity must be between 1 and {MAX_QTY}")
    return product_id


async def create_checkout_session(
    db: AsyncSession, user: User, product_id: str, quantity: int
) -> str:
    """Open a Stripe Checkout (payment mode) that collects the shipping address."""
    product_id = _validate(product_id, quantity)
    product = PRODUCTS[product_id]
    client = get_client()
    customer_id = await ensure_customer(db, user)

    base = settings.APP_BASE_URL.rstrip("/")
    params: dict = {
        "mode": "payment",
        "customer": customer_id,
        "client_reference_id": user.id,
        "line_items": [
            {
                "quantity": quantity,
                "price_data": {
                    "currency": CURRENCY,
                    "unit_amount": product["amount"],
                    "product_data": {
                        "name": product["name"],
                        "description": product["description"],
                    },
                },
            }
        ],
        # AUT-1540: physical goods — Stripe must collect where to ship them.
        "shipping_address_collection": {"allowed_countries": SHIPPING_COUNTRIES},
        "phone_number_collection": {"enabled": True},
        "success_url": f"{base}/?checkout=merch-success",
        "cancel_url": f"{base}/",
        "metadata": {"kind": "merch", "product_id": product_id, "quantity": quantity},
        "payment_intent_data": {
            "metadata": {"kind": "merch", "product_id": product_id}
        },
    }
    if not product.get("free_shipping"):
        params["shipping_options"] = [
            {
                "shipping_rate_data": {
                    "type": "fixed_amount",
                    "fixed_amount": {"amount": SHIPPING_FLAT_CENTS, "currency": CURRENCY},
                    "display_name": "Standard shipping",
                }
            }
        ]
    session = client.checkout.sessions.create(params=params)
    logger.info(
        "merch_checkout_created",
        extra={"user": user.id, "product": product_id, "qty": quantity},
    )
    return session.url


def _dig(obj: dict, *path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def shipping_from_session(session: dict) -> dict | None:
    """Normalise the shipping details Stripe collected at checkout."""
    details = (
        _dig(session, "collected_information", "shipping_details")
        or _dig(session, "shipping_details")
        or {}
    )
    name = details.get("name") or _dig(session, "customer_details", "name")
    addr = details.get("address") or _dig(session, "customer_details", "address") or {}
    phone = (
        (_dig(session, "collected_information", "phone_numbers") or [None])[0]
        or _dig(session, "customer_details", "phone")
    )
    if not any([name, addr]):
        return None
    out = {"name": name, "phone": phone}
    for src, dst in (
        ("line1", "line1"), ("line2", "line2"), ("city", "city"),
        ("state", "state"), ("postal_code", "postal_code"), ("country", "country"),
    ):
        if addr.get(src):
            out[dst] = addr[src]
    return out


async def record_paid_session(db: AsyncSession, session: dict) -> None:
    """Persist an order from a completed merch checkout (idempotent)."""
    if session.get("mode") != "payment":
        return
    metadata = session.get("metadata") or {}
    if metadata.get("kind") != "merch":
        return
    session_id = session.get("id")
    existing = await db.scalar(select(MerchOrder).where(MerchOrder.stripe_session_id == session_id))
    if existing:
        return
    user_id = session.get("client_reference_id") or _dig(session, "customer_details", "client_reference_id")
    if not user_id:
        logger.warning("merch_order_no_user", extra={"session": session_id})
        return
    order = MerchOrder(
        user_id=str(user_id),
        product_id=metadata.get("product_id", "unknown"),
        quantity=int(metadata.get("quantity") or 1),
        amount_total=session.get("amount_total") or 0,
        currency=session.get("currency") or CURRENCY,
        status="paid",
        stripe_session_id=session_id,
        shipping_address=(json.dumps(shipping) if (shipping := shipping_from_session(session)) else None),
    )
    db.add(order)
    await db.commit()
    logger.info("merch_order_recorded", extra={"session": session_id, "user": order.user_id})


def order_view(order: MerchOrder) -> dict:
    product = PRODUCTS.get(order.product_id, {})
    return {
        "id": order.id,
        "product_id": order.product_id,
        "product_name": product.get("name", order.product_id),
        "quantity": order.quantity,
        "amount_total": order.amount_total,
        "currency": order.currency,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "shipping_address": json.loads(order.shipping_address) if order.shipping_address else None,
    }


async def list_orders(db: AsyncSession, user: User) -> list[dict]:
    rows = await db.scalars(
        select(MerchOrder)
        .where(MerchOrder.user_id == user.id)
        .order_by(MerchOrder.created_at.desc())
    )
    return [order_view(o) for o in rows]
