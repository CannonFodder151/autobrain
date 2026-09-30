"""Deterministic rule-based engines (one module per domain).

These run whenever the 9Router is unreachable, keeping AutoBrain functional
offline. Each fallback produces the same output schema as the router path so
callers cannot tell the difference.

The patterns are deliberately simple heuristics (keyword rules, manufacturer
schedules, depreciation curves). They are the *fallback*, not the primary
model — the router path is used whenever it is available.
"""

from ..fallbacks.car_check import car_check_fallback, validate_car_check_response
from ..fallbacks.condition import estimate_condition
from ..fallbacks.diagnose import diagnose_fallback
from ..fallbacks.fuel_ocr import _fuel_receipt_fallback
from ..fallbacks.mod_impact import mod_impact_fallback
from ..fallbacks.ocr import extract_receipt_fallback
from ..ocr_utils import _extract_date
from ..fallbacks.odometer import _odometer_fallback
from ..fallbacks.resale import estimate_value_fallback, rrp_for
from ..fallbacks.service_prediction import predict_service_fallback

__all__ = [
    "car_check_fallback",
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
    "validate_car_check_response",
]
