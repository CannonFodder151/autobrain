"""AI module: odometer reading from a dashboard photo.

Input:  base64 image (`content_base64`) + content type.
Output: odometer_km, confidence.

Deterministic-only: local Tesseract + regex scan, no router call. Odometer
reads are ~95% accurate with the deterministic engine, so AI adds nothing.
"""

from app.fallbacks.odometer import _odometer_fallback
from app.ocr_utils import _IMAGE_TYPES, _tesseract_text


async def run(payload: dict) -> dict:
    text = ""
    if payload.get("content_base64") and payload.get("content_type") in _IMAGE_TYPES:
        text = _tesseract_text(payload["content_base64"])
    return _odometer_fallback(text)
