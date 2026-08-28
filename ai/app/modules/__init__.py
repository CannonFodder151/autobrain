"""AI module registry."""

from app.modules import condition, diagnostics, fuel_ocr, mod_impact, ocr, odometer, parts_format, resale, service_prediction, social_image

MODULES = {
    "diagnostics": diagnostics.run,
    "service-prediction": service_prediction.run,
    "condition": condition.run,
    "ocr": ocr.run,
    "fuel-ocr": fuel_ocr.run,
    "odometer": odometer.run,
    "resale": resale.run,
    "mod-impact": mod_impact.run,
    "social-image": social_image.run,
    "parts-format": parts_format.run,
}

__all__ = ["MODULES"]
