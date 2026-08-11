"""User account model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)  # admin/user
    max_vehicles: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    # Invited/self-signed-up but never completed registration (set a password).
    # Cleared when the invite token is consumed; purged after retention window.
    pending: Mapped[bool] = mapped_column(default=False)
    free_account: Mapped[bool] = mapped_column(default=False)  # disables AI and rego lookup
    obd_enabled: Mapped[bool] = mapped_column(default=False)  # admin-granted OBD access
    obd_auto_connect: Mapped[bool] = mapped_column(default=False)  # auto-connect Bluetooth OBD
    # Token lifecycle: bump to revoke ALL outstanding access + refresh tokens
    # (logout, password change). Tokens carry `ver` = version at issue time.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    mfa_enabled: Mapped[bool] = mapped_column(default=False)
    # Stripe billing (hosted subscriptions). Populated by the billing webhook.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64))
    stripe_subscription_status: Mapped[str | None] = mapped_column(String(32))
    stripe_price_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
