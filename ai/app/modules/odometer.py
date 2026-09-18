"""AI module: odometer reading from a dashboard photo.

Input:  base64 image (`content_base64`) + content type.
Output: odometer_km, confidence.

Deterministic-only: local Tesseract + regex scan, no router call. Odometer
reads are ~95% accurate with the deterministic engine, so AI adds nothing.
"""

from app.fallbacks.odometer import _odometer_fallback
from app.ocr_utils import _IMAGE_TYPES, _tesseract_text


def _clamp(data: dict) -> dict:
    """Coerce odometer_km to int and confidence to float in [0,1]."""
    out = dict(data)
    odo = out.get("odometer_km")
    if odo is not None:
        try:
            out["odometer_km"] = int(float(odo))
        except (TypeError, ValueError):
            out["odometer_km"] = None
    conf = out.get("confidence")
    if conf is not None:
        try:
            out["confidence"] = max(0.0, min(1.0, float(conf)))
        except (TypeError, ValueError):
            out["confidence"] = 0.0
    return out


async def run(payload: dict) -> dict:
    text = ""
    if payload.get("content_base64") and payload.get("content_type") in _IMAGE_TYPES:
        text = _tesseract_text(payload["content_base64"])
    return _odometer_fallback(text)
