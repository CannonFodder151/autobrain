"""Deterministic fuel-receipt OCR fallback."""

import re

from app.fallbacks.utils import to_float as _num
from app.ocr_utils import _extract_date

# AU fuel vendors — comprehensive list.
_FUEL_VENDORS = [
    "shell", "caltex", "ampol", "bp ", "united", "7-eleven", "7 eleven",
    "coles express", "woolworths", "costco", "liberty", "petro",
    "gull", "puma", "arrow", "viva", "opie", "fuelplus", "speedway",
    "northshore", "independent", "fuel", "star fuel", "racv",
]

# Regex patterns for litres, matching common AU receipt formats:
_LITRES_PATTERNS = [
    re.compile(r"(\d{1,3}(?:[.,]\d{2})?)\s*(?:L|LT|Litres?|Litros)\b", re.I),
    re.compile(r"(?:Qty|Quantity|Litres)\s*[:\-]?\s*(\d{1,3}(?:[.,]\d{2})?)", re.I),
]

# Price per litre: "@ $2.09"  "$2.09/L"  "209.9 c/L"
_PRICE_PL_PATTERNS = [
    re.compile(r"(\d+[.,]\d{1,3})\s*(?:/L|c/L|per\s*litre)", re.I),
    re.compile(r"[@]\s*\$?\s*(\d+[.,]\d{1,3})", re.I),
    re.compile(r"\$(\d+[.,]\d{1,3})\s*/\s*L", re.I),
    re.compile(r"(\d+\.\d{3})\s*/\s*L", re.I),
]


def _fuel_receipt_fallback(text: str) -> dict:
    litres = price_pl = total = None

    # Litres
    for pat in _LITRES_PATTERNS:
        m = pat.search(text)
        if m:
            litres = _num(m.group(1))
            if litres is not None:
                break

    # Price per litre
    for pat in _PRICE_PL_PATTERNS:
        m = pat.search(text)
        if m:
            price_pl = _num(m.group(1).replace(",", "."))
            if price_pl is not None:
                break

    # Total — multiple formats
    m = re.search(r"total\s*[:\$]?\s*(\d+(?:[.,]\d{2})?)", text.lower())
    if m:
        total = _num(m.group(1).replace(",", "."))
    if total is None:
        m = re.search(r"(?:amount|subtotal)\s*[:\$]?\s*(\d+(?:[.,]\d{2})?)", text.lower())
        if m:
            total = _num(m.group(1).replace(",", "."))

    # Cross-validate: if litres and price_per_litre are both present, total
    # should be approximately litres * price_per_litre. If total is missing,
    # compute it. If total is wildly off, use the computed value.
    if litres is not None and price_pl is not None:
        computed = round(litres * price_pl, 2)
        if total is None:
            total = computed
        elif abs(total - computed) / max(computed, 0.01) > 0.15:
            total = computed

    # Vendor detection
    vendor = None
    low_text = text.lower()
    for v in _FUEL_VENDORS:
        if v in low_text:
            vendor = v.strip().title()
            if vendor.lower() in ("7-eleven", "7 eleven"):
                vendor = "7-Eleven"
            elif v.strip() == "bp ":
                vendor = "BP"
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
