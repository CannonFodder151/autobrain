"""Merch webhook recording (order persistence only).

AUT-1567 (board): merch is NOT sold in the AutoBrain app — the beanie and any
future merch live only on the autobrainservice.app website merch section
(see docs/product-rules.md PR-2). There is no in-app catalogue, checkout, or
orders API. This module only records completed Stripe payment-mode checkouts
(kind=merch metadata, e.g. from the website flow) so order history is not lost;
recording is idempotent by Stripe session id.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merch import MerchOrder
from app.services.billing import CURRENCY

logger = logging.getLogger(__name__)


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
