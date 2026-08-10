"""Deterministic fuel-receipt OCR fallback."""

import re

from app.fallbacks.ocr import _extract_date


def _num(s) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _fuel_receipt_fallback(text: str) -> dict:
    litres = price_pl = total = None
    m = re.search(r"(\d{1,3}(?:[.,]\d{2})?)\s*(?:L|LT|Litres?|Litros)\b", text, re.IGNORECASE)
    if m:
        litres = _num(m.group(1))
    m = re.search(r"(\d+[.,]\d{1,3})\s*(?:/L|c/L|per\s*litre)", text, re.IGNORECASE)
    if m:
        price_pl = _num(m.group(1).replace(",", "."))
    if price_pl is None:
        # Fuel receipts often format the unit price as "@ 2.09" or "$2.09".
        m = re.search(r"[@]\s*\$?\s*(\d+[.,]\d{1,3})", text)
        if m:
            price_pl = _num(m.group(1).replace(",", "."))
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
