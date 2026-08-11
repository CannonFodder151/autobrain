"""Deterministic rule-based engines (one module per domain).

These run whenever the 9Router is unreachable, keeping AutoBrain functional
offline. Each fallback produces the same output schema as the router path so
callers cannot tell the difference.

The patterns are deliberately simple heuristics (keyword rules, manufacturer
schedules, depreciation curves). They are the *fallback*, not the primary
model — the router path is used whenever it is available.
"""

from app.fallbacks.condition import estimate_condition
from app.fallbacks.diagnose import diagnose_fallback
from app.fallbacks.fuel_ocr import _fuel_receipt_fallback
from app.fallbacks.mod_impact import mod_impact_fallback
from app.fallbacks.ocr import extract_receipt_fallback
from app.ocr_utils import _extract_date
from app.fallbacks.odometer import _odometer_fallback
from app.fallbacks.resale import estimate_value_fallback, rrp_for
from app.fallbacks.service_prediction import predict_service_fallback

__all__ = [
    "diagnose_fallback",
    "estimate_condition",
    "estimate_value_fallback",
    "extract_receipt_fallback",
    "mod_impact_fallback",
    "predict_service_fallback",
    "rrp_for",
    "_extract_date",
    "_fuel_receipt_fallback",
    "_odometer_fallback",
]
