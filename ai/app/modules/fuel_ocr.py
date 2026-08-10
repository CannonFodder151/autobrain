"""AI module: fuel receipt OCR.

Input:  PDF text (`content`) or base64 image (`content_base64`) + content type.
Output: vendor, date, litres, price_per_litre, total_cost, currency.
"""

from app.fallbacks.fuel_ocr import _fuel_receipt_fallback
from app.modules.ocr import _tesseract_text, _IMAGE_TYPES
from app.router_client import enhance


async def run(payload: dict) -> dict:
    text = payload.get("content", "") or ""
    content_type = payload.get("content_type", "")
    if not text and payload.get("content_base64") and content_type in _IMAGE_TYPES:
        text = _tesseract_text(payload["content_base64"])

    baseline = _fuel_receipt_fallback(text)

    # Router only fills missing optional fields; litres/price/vendor/date/total
    # are measured deterministically and never overridden.
    router_payload = {k: v for k, v in payload.items() if k != "content_base64"}
    router_payload["text"] = text
    return await enhance("fuel-ocr", router_payload, baseline)
