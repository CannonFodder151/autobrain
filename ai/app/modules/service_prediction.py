"""AI module: service prediction.

Input:  make/model/year, current odometer, last service km/date.
Output: next service due (km + date), interval, confidence.
"""

from app.fallbacks import predict_service_fallback
from app.router_client import route


async def run(payload: dict) -> dict:
    result = await route("service-prediction", payload)
    if result is not None and isinstance(result, dict):
        result.setdefault("model", "9router")
        return result
    return predict_service_fallback(payload)
