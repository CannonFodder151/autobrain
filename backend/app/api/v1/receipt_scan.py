from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class ReceiptOut(BaseModel):
    text: str
    total: Optional[float] = None
    litres: Optional[float] = None
    method: str = "deterministic_fallback"

@router.post("/scan", response_model=ReceiptOut)
async def scan_receipt(file: UploadFile = File(...)):
    # Deterministic fallback: no OCR engine wired; return placeholder.
    return ReceiptOut(text="", total=None, litres=None, method="deterministic_fallback")
