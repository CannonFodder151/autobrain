"""Merch store orders (AUT-1540)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

def _uuid() -> str:
    return str(uuid.uuid4())

class MerchOrder(Base):
    __tablename__ = "merch_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount_total: Mapped[int] = mapped_column(Integer)  # cents incl. shipping
    currency: Mapped[str] = mapped_column(String(8), default="aud")
    # paid only for now; refunds arrive via future webhook handling
    status: Mapped[str] = mapped_column(String(20), default="paid")
    stripe_session_id: Mapped[str] = mapped_column(String(255), unique=True)
    # JSON blob from Stripe collected_information.shipping_details
    shipping_address: Mapped[dict | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
