"""AI Gateway client module contract.

This module defines the public interface for AI inference calls.
All AI features route through the ai gateway service, which goes through 9Router.

Actual implementation lives in:
- app.services.ai_client (HTTP client, caching, router calls)

Usage:
    from app.modules.ai_client import extract_fuel_receipt, run_diagnostics
"""

from __future__ import annotations

__all__ = [
    "run_diagnostics",
    "predict_service",
    "extract_receipt",
    "extract_fuel_receipt",
    "read_odometer",
    "estimate_value",
    "mod_impact",
    "estimate_condition",
    "format_sca_parts",
    "run_advisor_ai",
    "run_car_check_ai",
]


def __getattr__(name: str):
    if name in __all__:
        from app.services.ai_client import (
            run_diagnostics, predict_service, extract_receipt,
            extract_fuel_receipt, read_odometer, estimate_value,
            mod_impact, estimate_condition, format_sca_parts,
            run_advisor_ai, run_car_check_ai,
        )
        globals().update({
            "run_diagnostics": run_diagnostics,
            "predict_service": predict_service,
            "extract_receipt": extract_receipt,
            "extract_fuel_receipt": extract_fuel_receipt,
            "read_odometer": read_odometer,
            "estimate_value": estimate_value,
            "mod_impact": mod_impact,
            "estimate_condition": estimate_condition,
            "format_sca_parts": format_sca_parts,
            "run_advisor_ai": run_advisor_ai,
            "run_car_check_ai": run_car_check_ai,
        })
        return globals()[name]
    raise AttributeError(f"module 'app.modules.ai_client' has no attribute '{name}'")