"""AI module registry."""

from app.modules import (
    advisor,
    car_check,
    condition,
    diagnostics,
    fuel_ocr,
    health_score,
    mod_impact,
    ocr,
    odometer,
    parts_guide,
    resale,
    service_prediction,
    social_image,
)

MODULES = {
    "advisor": advisor.run,
    "car-check": car_check.run,
    "diagnostics": diagnostics.run,
    "health-score": health_score.run,
    "service-prediction": service_prediction.run,
    "condition": condition.run,
    "ocr": ocr.run,
    "fuel-ocr": fuel_ocr.run,
    "odometer": odometer.run,
    "resale": resale.run,
    "mod-impact": mod_impact.run,
    "parts-guide": parts_guide.run,
    "social-image": social_image.run,
}

__all__ = ["MODULES"]
