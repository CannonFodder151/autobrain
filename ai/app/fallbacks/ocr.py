"""Deterministic receipt OCR fallback."""

import re

from app.ocr_utils import _extract_date

_VENDOR_HINTS = ["autobarn", "supercheap", "repco", "bunnings", "kmart", "harley davidson",
                 "toyota", "ford", "nissan", "mitsubishi", "penrite", "castrol"]

_ITEM_HINTS = {
    "oil": ("Oil", "part", 0.0), "filter": ("Filter", "part", 25.0),
    "brake": ("Brake pad", "part", 120.0), "rotor": ("Brake rotor", "part", 260.0),
    "battery": ("Battery", "part", 220.0), "wiper": ("Wiper blades", "part", 30.0),
    "spark": ("Spark plugs", "part", 90.0), "coolant": ("Coolant", "part", 45.0),
    "labour": ("Labour", "labour", 0.0), "service": ("Service", "labour", 150.0),
    "diagnostic": ("Diagnostic fee", "labour", 90.0),
}


def extract_receipt_fallback(text: str, content_type: str = "") -> dict:
    vendor = None
    for v in _VENDOR_HINTS:
        if v.lower() in text.lower():
            vendor = v.title()
            break

    items: list[dict] = []
    total = tax = None
    for line in text.splitlines():
        low = line.lower()
        for hint, (name, kind, cost) in _ITEM_HINTS.items():
            if hint in low and name.lower() not in [i["name"].lower() for i in items]:
                qty = 1
                cost_val = cost
                m = re.search(r"(\d+(?:\.\d{2})?)\s*$", line)
                if m:
                    cost_val = float(m.group(1))
                items.append({"kind": kind, "name": name, "quantity": qty, "unit_cost": cost_val})
                break
        m = re.search(r"total\s*[:\$]?\s*(\d+(?:\.\d{2})?)", low)
        if m and total is None:
            total = float(m.group(1))

    if not items and total:
        items.append({"kind": "labour", "name": "Service items", "quantity": 1, "unit_cost": total})

    next_service = "Routine scheduled service"
    if "oil" in text.lower() and "filter" in text.lower():
        next_service = "Oil and filter service"

    confidence = round(min(0.4 + 0.12 * len(items), 0.95), 2) if items else 0.4

    return {
        "vendor": vendor,
        "invoice_date": _extract_date(text),
        "total": total,
        "tax": tax,
        "currency": "AUD",
        "confidence": confidence,
        "items": items,
        "next_recommended_service": next_service,
        "warranty_notes": "Parts warranty: 12 months on new components" if any(
            i["kind"] == "part" for i in items
        ) else None,
        "model": "rule-based-fallback",
    }

