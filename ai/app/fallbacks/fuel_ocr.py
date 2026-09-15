"""Deterministic fuel-receipt OCR fallback."""

import re

from app.ocr_utils import _extract_date


def _num(s) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _fuel_receipt_fallback(text: str) -> dict:
    litres = price_pl = total = None
    m = re.search(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:L|LT|Litres?|Litros)\b", text, re.IGNORECASE)
    if m:
        litres = _num(m.group(1))
    # Price per litre: "2.09/L", "209.9 c/L", "per litre 2.099", "@ $2.09"
    for pat in [
        r"(\d+[.,]\d{1,3})\s*(?:/L|c/L)",
        r"per\s*litre\s*[:\$]?\s*(\d+[.,]\d{1,3})",
        r"(\d+[.,]\d{1,3})\s*per\s*litre",
        r"[@]\s*\$?\s*(\d+[.,]\d{1,3})",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            price_pl = _num(m.group(1).replace(",", "."))
            break
    m = re.search(r"total\s*[:\$]?\s*(\d+(?:[.,]\d{2})?)", text.lower())
    if m:
        total = _num(m.group(1).replace(",", "."))

    vendor = None
    for v in ["shell", "caltex", "bp ", "ampol", "united", "7-eleven", "coles express", "woolworths", "costco", "liberty"]:
        if v in text.lower():
            vendor = v.strip().title()
            break

    return {
        "vendor": vendor,
        "date": _extract_date(text),
        "litres": litres,
        "price_per_litre": price_pl,
        "total_cost": total,
        "currency": "AUD",
        "notes": None,
        "model": "rule-based-fallback",
    }
