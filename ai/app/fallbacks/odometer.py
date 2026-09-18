"""Deterministic odometer-reading fallback (regex over OCR text).

Patterns try to handle common Australian dashboard and receipt formats:
  - bare digits:        123456, 01234567
  - comma-separated:    123,456, 1,234,567
  - with unit labels:   123456 km, 123456.0 km, ODO 123456
  - trip meter variants: 1234.5 (often 5-digit trip, ignore)
"""

import re

# Patterns ordered by confidence (highest first). Each is (compiled_re, label).
# Group 1 = the numeric value (digits only).
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "ODO 123456 km" / "Odometer: 123,456 km" / "123456 km"
    (re.compile(r"(?:odo(?:meter)?\s*[:\-]?\s*)?(\d[\d,]{4,8}\d)\s*(?:km|kilometres?)?", re.I), "label-or-bare"),
    # "123456.0 km" — decimal variant often seen on digital dashes
    (re.compile(r"(\d[\d,]{4,8}\d)\.\d\s*(?:km|kilometres?)?", re.I), "decimal"),
    # Comma-separated: "123,456" (standalone on a line)
    (re.compile(r"\b(\d{1,3}(?:,\d{3}){1,3})\b"), "comma-separated"),
]

# Minimum plausible odometer for AU vehicles (skip very low 5-digit readings
# which are usually trip meters or price fragments).
_MIN_KM = 1_000
_MAX_KM = 9_999_999


def _clean_numeric(raw: str) -> int | None:
    """Strip commas/spaces, parse int, return None if out of range."""
    cleaned = raw.replace(",", "").replace(" ", "")
    try:
        val = int(cleaned)
    except (ValueError, TypeError):
        return None
    if _MIN_KM <= val <= _MAX_KM:
        return val
    return None


def _odometer_fallback(text: str) -> dict:
    """Scan OCR text for a plausible odometer reading (6-7 digit number).

    Tries multiple regex patterns, picks the highest-confidence match.
    Returns best reading with a confidence score. When no pattern matches
    the reading is None with confidence 0.
    """
    best: int | None = None

    for pattern, _label in _PATTERNS:
        for m in pattern.finditer(text):
            val = _clean_numeric(m.group(1))
            if val is None:
                continue
            # Prefer the highest plausible value (odometers only go up).
            if best is None or val > best:
                best = val
        if best is not None:
            break  # first pattern that matches wins

    # Fallback: scan for any bare 6-7 digit sequence if labelled patterns failed.
    if best is None:
        digits_only = re.sub(r"[^\d]", "", text)
        for m in re.finditer(r"\d{6,7}", digits_only):
            val = _clean_numeric(m.group())
            if val is not None:
                best = val

    return {
        "odometer_km": best,
        "confidence": 0.95 if best is not None else 0.0,
        "model": "rule-based-fallback",
    }