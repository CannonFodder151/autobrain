"""Receipt and OCR schemas."""

from datetime import datetime

from pydantic import BaseModel


class ReceiptOut(BaseModel):
    id: str
    vehicle_id: str
    original_name: str | None
    ocr_status: str
    extracted: str | None
    vendor: str | None
    total: float | None
    tax: float | None
    currency: str
    invoice_date: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractionResult(BaseModel):
    vendor: str | None = None
    invoice_date: str | None = None
    total: float | None = None
    tax: float | None = None
    currency: str = "AUD"
    items: list[dict]
    next_recommended_service: str | None = None
    warranty_notes: str | None = None


class ApplyToServiceRequest(BaseModel):
    service_type: str = "custom"
    service_date: str | None = None
    workshop: str | None = None
    notes: str | None = None
    add_parts_to_inventory: bool = True
