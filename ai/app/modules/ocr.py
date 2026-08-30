"""AI module: OCR + document extraction.

Input:  PDF text (`content`) or base64 image (`content_base64`) + content type.
Output: vendor, date, total, tax, line items (parts/labour), warranty,
        next recommended service.
"""

from app.fallbacks.ocr import extract_receipt_fallback
from app.ocr_utils import _IMAGE_TYPES, _tesseract_text
from app.router_client import enhance


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
