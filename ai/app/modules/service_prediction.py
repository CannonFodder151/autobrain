"""AI module: service prediction.

Input:  make/model/year, current odometer, last service km/date.
Output: next service due (km + date), interval, confidence.
"""

from datetime import date, timedelta

from app.fallbacks import predict_service_fallback
from app.router_client import route

_INT_FIELDS = ("interval_km", "interval_months", "due_in_km", "due_in_days", "next_due_km")


def _normalize(result: dict) -> dict:
    """Coerce LLM output to the required schema (LLMs occasionally emit nulls)."""
    today = date.today()
    months = int(result.get("interval_months") or 12)

    if not result.get("next_due_date"):
        result["next_due_date"] = (today + timedelta(days=months * 30)).isoformat()

    try:
        next_due = date.fromisoformat(str(result["next_due_date"]))
    except ValueError:
        next_due = today + timedelta(days=months * 30)
        result["next_due_date"] = next_due.isoformat()

    if result.get("due_in_days") is None:
        result["due_in_days"] = max((next_due - today).days, 0)

    for key in _INT_FIELDS:
        if result.get(key) is not None:
            result[key] = int(result[key])

    if result.get("confidence") is not None:
        result["confidence"] = float(result["confidence"])

    return result


async def run(payload: dict) -> dict:
    result = await route("service-prediction", payload)
    if result is not None and isinstance(result, dict):
        return _normalize(result)
    return predict_service_fallback(payload)
