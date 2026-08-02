"""AI module registry."""

from app.modules import diagnostics, mod_impact, ocr, resale, service_prediction

MODULES = {
    "diagnostics": diagnostics.run,
    "service-prediction": service_prediction.run,
    "ocr": ocr.run,
    "resale": resale.run,
    "mod-impact": mod_impact.run,
}

__all__ = ["MODULES"]
