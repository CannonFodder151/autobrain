"""Receipt / parts invoice scan records."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    file_key: Mapped[str] = mapped_column(String(500))  # MinIO key
    original_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(80))
    ocr_status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending/processing/done/failed
    extracted: Mapped[dict | None] = mapped_column(Text)  # full AI extraction JSON
    vendor: Mapped[str | None] = mapped_column(String(255))
    total: Mapped[float | None] = mapped_column(Float)
    tax: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="AUD")
    invoice_date: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractedItem(Base):
    __tablename__ = "extracted_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    receipt_id: Mapped[str] = mapped_column(String(36), ForeignKey("receipts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # part/labour
    name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(default=1)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    warranty_months: Mapped[int | None] = mapped_column()
    applied_to_service: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
