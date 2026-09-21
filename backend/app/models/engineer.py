"""Engineer marketplace models (AUT-3661).

Engineers are certified mechanics/specialists available for vehicle services.
Search supports: geospatial (postcode/radius), specialty multi-select,
minimum rating, price range, availability window.
"""

import uuid
from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.vehicle import Vehicle


def _uuid() -> str:
    return str(uuid.uuid4())


class Engineer(Base):
    __tablename__ = "engineers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Identity
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Location (geospatial search)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Professional details
    specialties: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    certifications: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    years_experience: Mapped[int | None] = mapped_column(nullable=True)

    # Marketplace metrics
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    review_count: Mapped[int] = mapped_column(default=0, nullable=False)
    price_per_hour: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    price_per_job_min: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    price_per_job_max: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    # Availability: JSON array of {day: 0-6, start: "HH:MM", end: "HH:MM", timezone: "Australia/Sydney"}
    availability: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, verified, rejected

    # Embedding for semantic search on specialties/description
    embedding: Mapped[list[float] | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_engineers_active_rating", "is_active", "rating"),
        Index("ix_engineers_active_price", "is_active", "price_per_hour"),
        Index("ix_engineers_active_verified", "is_active", "is_verified"),
        Index("ix_engineers_postcode_active", "postcode", "is_active"),
    )


class EngineerReview(Base):
    __tablename__ = "engineer_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engineers.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    vehicle_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vehicles.id"), nullable=True, index=True
    )

    rating: Mapped[int] = mapped_column(nullable=False)  # 1-5
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Service context
    service_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engineer: Mapped["Engineer"] = relationship(back_populates="reviews")

    __table_args__ = (
        Index("ix_engineer_reviews_engineer_created", "engineer_id", "created_at"),
    )


# Back-reference for Engineer
Engineer.reviews: Mapped[list["EngineerReview"]] = relationship(
    back_populates="engineer", lazy="selectin", cascade="all, delete-orphan"
)