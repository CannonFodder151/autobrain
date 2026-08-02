"""9Router integration client.

Every AI module reads AI_ROUTER_URL at runtime and POSTs its inference request
to `{AI_ROUTER_URL}/v1/{module}`. If the router is unreachable, misconfigured,
or returns a non-200, each module falls back to a deterministic rule-based
implementation so AutoBrain never goes down with the router.

Environment variables:
  AI_ROUTER_URL      e.g. http://your-9router-instance:port  (required)
  AI_ROUTER_API_KEY  optional bearer key
  AI_ROUTER_TIMEOUT_SECONDS
"""

import os

import httpx

from app.logging import get_logger

logger = get_logger(__name__)


def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://your-9router-instance:port").rstrip("/")


def router_enabled() -> bool:
    url = router_url()
    return bool(url) and "your-9router-instance" not in url


async def route(module: str, payload: dict) -> dict | None:
    """POST inference to 9Router. Returns parsed JSON or None on failure."""
    if not router_enabled():
        logger.info("router_disabled_using_fallback", module=module)
        return None
    url = f"{router_url()}/v1/{module}"
    timeout = int(os.getenv("AI_ROUTER_TIMEOUT_SECONDS", "60"))
    headers = {}
    api_key = os.getenv("AI_ROUTER_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json={"payload": payload}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            logger.info("router_response", module=module, status=resp.status_code)
            return data.get("result") if isinstance(data, dict) and "result" in data else data
    except httpx.HTTPStatusError as exc:
        logger.warning("router_http_error", module=module, status=exc.response.status_code)
        return None
    except Exception as exc:
        logger.warning("router_unreachable_using_fallback", module=module, error=str(exc))
        return None
