"""Workshop (tenant) and WorkshopUser models."""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SubscriptionTier(str, PyEnum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class WorkshopRole(str, PyEnum):
    OWNER = "owner"
    MANAGER = "manager"
    TECH = "tech"
    ADMIN = "admin"


class Workshop(Base):
    __tablename__ = "workshops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    postcode: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2), default="AU", nullable=False)
    abn: Mapped[str | None] = mapped_column(String(20), index=True)  # Australian Business Number
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier, native_enum=False), default=SubscriptionTier.STARTER, nullable=False
    )
    subscription_status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, past_due, cancelled, trialing
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64))
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    max_users: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_vehicles: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    ai_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    users: Mapped[list["WorkshopUser"]] = relationship(
        "WorkshopUser", back_populates="workshop", cascade="all, delete-orphan"
    )


class WorkshopUser(Base):
    __tablename__ = "workshop_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workshop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[WorkshopRole] = mapped_column(
        Enum(WorkshopRole, native_enum=False), default=WorkshopRole.TECH, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    mfa_enabled: Mapped[bool] = mapped_column(default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    workshop: Mapped["Workshop"] = relationship("Workshop", back_populates="users")

    __table_args__ = (
        UniqueConstraint("workshop_id", "email", name="uq_workshop_user_email"),
    )