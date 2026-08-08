"""AI module: OCR + document extraction.

Input:  PDF text (`content`) or base64 image (`content_base64`) + content type.
Output: vendor, date, total, tax, line items (parts/labour), warranty,
        next recommended service.
"""

import base64
import io

from app.fallbacks import extract_receipt_fallback
from app.router_client import enhance

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
    text = payload.get("content", "") or ""
    content_type = payload.get("content_type", "")
    if not text and payload.get("content_base64") and content_type in _IMAGE_TYPES:
        text = _tesseract_text(payload["content_base64"])

    baseline = extract_receipt_fallback(text, content_type)

    # Router gets only the extracted text — never raw image bytes. It can only
    # polish line-item classification; vendor/total/tax/items stay deterministic.
    router_payload = {
        k: v for k, v in payload.items() if k != "content_base64"
    }
    router_payload["text"] = text
    return await enhance("ocr", router_payload, baseline)
