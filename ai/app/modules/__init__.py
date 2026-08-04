"""AI module registry."""

from app.modules import diagnostics, fuel_ocr, mod_impact, ocr, odometer, resale, service_prediction

MODULES = {
    "diagnostics": diagnostics.run,
    "service-prediction": service_prediction.run,
    "ocr": ocr.run,
    "fuel-ocr": fuel_ocr.run,
    "odometer": odometer.run,
    "resale": resale.run,
    "mod-impact": mod_impact.run,
}

__all__ = ["MODULES"]
