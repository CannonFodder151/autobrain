"""Client for the AI inference layer.

The backend never talks to a model directly for AI features — it calls the
AI gateway service (ai) which in turn routes through AI_ROUTER_URL (9Router).
A 503 from the gateway surfaces as a clean error, never a crash.
"""

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AIGatewayError(Exception):
    pass


async def _call(module: str, payload: dict) -> dict | None:
    url = f"{settings.AI_LOCAL_BASE_URL.rstrip('/')}/v1/{module}"
    headers = {}
    if settings.AI_GATEWAY_API_KEY:
        headers["Authorization"] = f"Bearer {settings.AI_GATEWAY_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=settings.AI_ROUTER_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json={"payload": payload}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("result") if isinstance(data, dict) and "result" in data else data
    except Exception as exc:
        logger.warning("ai_gateway_call_failed", module=module, error=str(exc))
        return None


async def run_diagnostics(payload: dict) -> dict | None:
    return await _call("diagnostics", payload)


async def predict_service(payload: dict) -> dict | None:
    return await _call("service-prediction", payload)


async def extract_receipt(payload: dict) -> dict | None:
    return await _call("ocr", payload)


async def extract_fuel_receipt(payload: dict) -> dict | None:
    return await _call("fuel-ocr", payload)


async def read_odometer(payload: dict) -> dict | None:
    return await _call("odometer", payload)


async def estimate_value(payload: dict) -> dict | None:
    return await _call("resale", payload)


async def mod_impact(payload: dict) -> dict | None:
    return await _call("mod-impact", payload)

async def estimate_condition(payload: dict) -> dict | None:
    return await _call("condition", payload)

async def format_parts(payload: dict) -> dict | None:
    return await _call("parts-format", payload)
