"""AI module: OCR + document extraction.

Input:  file bytes metadata + optional raw text preview.
Output: vendor, date, total, tax, line items (parts/labour), warranty,
        next recommended service.
"""

import base64
import io

from app.fallbacks import extract_receipt_fallback
from app.router_client import route

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff"}


def _tesseract_text(content_base64: str) -> str:
    """Local OCR via tesseract when no router and no pre-extracted text."""
    try:
        import pytesseract
        from PIL import Image

        raw = base64.b64decode(content_base64)
        return pytesseract.image_to_string(Image.open(io.BytesIO(raw)))
    except Exception:
        return ""


async def run(payload: dict) -> dict:
    result = await route("ocr", payload)
    if result is not None and isinstance(result, dict):
        result.setdefault("model", "9router")
        return result

    text = payload.get("content", "") or ""
    content_type = payload.get("content_type", "")
    if not text and payload.get("content_base64") and content_type in _IMAGE_TYPES:
        text = _tesseract_text(payload["content_base64"])
    return extract_receipt_fallback(text, content_type)
