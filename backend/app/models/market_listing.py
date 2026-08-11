"""Cached used-car market data (CarsGuide/CarSales listings + aggregates).

One row per (make, model, year) search key. Listing prices feed the resale
valuation so consecutive valuations return the same number instead of
re-rolling the AI guess on every call.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MarketListingCache(Base):
    __tablename__ = "market_listing_cache"
    __table_args__ = (UniqueConstraint("make", "model", "year", name="uq_market_make_model_year"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    make: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64), index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="fallback")  # provider | fallback
    listings: Mapped[list | None] = mapped_column(Text)  # JSON list of listings
    median_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
