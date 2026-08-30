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


def _clamp(result: dict) -> dict:
    try:
        odo = int(result["odometer_km"])
        result["odometer_km"] = max(0, min(odo, 9_999_999))
    except (KeyError, TypeError, ValueError):
        result["odometer_km"] = None
    try:
        result["confidence"] = float(result.get("confidence") or 0.0)
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    result.setdefault("model", "rule-based-fallback")
    return result
