"""Deterministic odometer-reading fallback (regex over OCR text)."""

import re


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
