"""AI module: service prediction.

Input:  make/model/year, current odometer, last service km/date.
Output: next service due (km + date), interval, confidence.

Deterministic-first: manufacturer schedules + measured intervals from history
produce the baseline; 9Router only supplies supplementary interval adjustment.
"""

from app.fallbacks import predict_service_fallback
from app.router_client import enhance


async def run(payload: dict) -> dict:
    baseline = predict_service_fallback(payload)
    return await enhance("service-prediction", payload, baseline)
