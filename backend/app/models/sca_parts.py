"""Cached Supercheap Auto parts-guide results.

One row per (make, model, year) key — the resolved vehicle identity drives
a deterministic, 24h-stable parts categorisation so repeated lookups don't
re-hit the SCA site or re-run the 9Router tidy pass needlessly.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SCAPartsCache(Base):
    __tablename__ = "sca_parts_cache"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_sca_cache_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, auto_increment=True)
    cache_key: Mapped[str] = mapped_column(String(255), index=True)  # make|model|year
    parts_json: Mapped[str] = mapped_column(Text)  # JSON list of Inventory-shaped parts
    category_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
