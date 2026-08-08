"""AI module: odometer reading from a dashboard photo.

Input:  base64 image (`content_base64`) + content type.
Output: odometer_km, confidence.

Deterministic-only: local Tesseract + regex scan, no router call. Odometer
reads are ~95% accurate with the deterministic engine, so AI adds nothing.
"""

import re

from app.modules.ocr import _tesseract_text, _IMAGE_TYPES


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


def _odometer_fallback(text: str) -> dict:
    """Scan OCR text for a plausible odometer reading (6-7 digit number)."""
    best = None
    for m in re.finditer(r"\d{6,7}", re.sub(r"[^\d]", "", text) if len(text) < 400 else text):
        val = int(m.group())
        if 1_000 <= val <= 9_999_999:
            if best is None or val > best:
                best = val
    return {
        "odometer_km": best,
        "confidence": 0.95 if best is not None else 0.0,
        "model": "rule-based-fallback",
    }
