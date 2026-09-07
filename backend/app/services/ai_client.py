"""Client for the AI inference layer.

The backend never talks to a model directly for AI features — it calls the
AI gateway service (ai) which in turn routes through AI_ROUTER_URL (9Router).
A 503 from the gateway surfaces as a clean error, never a crash.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

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


async def format_sca_parts(payload: dict) -> dict | None:
    return await _call("parts-guide", payload)


# --- AI Advisor (AUT-2450) -------------------------------------------------
# 24h in-process cache keyed by (vehicle_id, stable module-outputs hash).
# Same inputs = same answer for 24h so the router is never called twice for
# the same state. Cache is per-process; restart-eviction is acceptable
# because the cache only optimises repeat calls, not correctness.

_ADVISOR_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_ADVISOR_CACHE_TTL_SECONDS = 24 * 60 * 60
_ADVISOR_CACHE_MAX_ENTRIES = 1024


def _advisor_cache_key(vehicle_id: str | None, modules: dict[str, Any]) -> str:
    canonical = json.dumps(modules or {}, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{(vehicle_id or '')}|{digest}"


def _advisor_cache_get(key: str) -> dict[str, Any] | None:
    entry = _ADVISOR_CACHE.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at < time.time():
        _ADVISOR_CACHE.pop(key, None)
        return None
    return value


def _advisor_cache_put(key: str, value: dict[str, Any]) -> None:
    if len(_ADVISOR_CACHE) >= _ADVISOR_CACHE_MAX_ENTRIES:
        cutoff = time.time()
        stale = [k for k, (exp, _) in _ADVISOR_CACHE.items() if exp < cutoff]
        for k in stale[: max(1, len(_ADVISOR_CACHE) - _ADVISOR_CACHE_MAX_ENTRIES + 1)]:
            _ADVISOR_CACHE.pop(k, None)
        if len(_ADVISOR_CACHE) >= _ADVISOR_CACHE_MAX_ENTRIES:
            for k in list(_ADVISOR_CACHE.keys())[: len(_ADVISOR_CACHE) - _ADVISOR_CACHE_MAX_ENTRIES + 1]:
                _ADVISOR_CACHE.pop(k, None)
    _ADVISOR_CACHE[key] = (time.time() + _ADVISOR_CACHE_TTL_SECONDS, value)


async def run_advisor_ai(
    vehicle_id: str | None,
    modules: dict[str, Any],
) -> dict[str, Any] | None:
    """Call the AI gateway for the Ownership Advisor (AUT-2450).

    Returns the parsed decision payload, or ``None`` when the gateway is
    unreachable. The caller (``compute_advisor_recommendation``) renders
    a deterministic fallback so the route always answers.
    """
    payload = {"question": (modules or {}).get("question"), **{k: v for k, v in (modules or {}).items() if k != "question"}}
    cache_key = _advisor_cache_key(vehicle_id, modules or {})
    cached = _advisor_cache_get(cache_key)
    if cached is not None:
        return cached
    result = await _call("advisor", payload)
    if not isinstance(result, dict):
        return None
    _advisor_cache_put(cache_key, result)
    return result


# --- AI Car Check (AUT-2651) -----------------------------------------------
# Same 24h in-process cache as run_advisor_ai.

_CAR_CHECK_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CAR_CHECK_CACHE_TTL_SECONDS = 24 * 60 * 60
_CAR_CHECK_CACHE_MAX_ENTRIES = 1024


def _car_check_cache_key(vehicle_id: str | None, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload or {}, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{(vehicle_id or '')}|{digest}"


def _car_check_cache_get(key: str) -> dict[str, Any] | None:
    entry = _CAR_CHECK_CACHE.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at < time.time():
        _CAR_CHECK_CACHE.pop(key, None)
        return None
    return value


def _car_check_cache_put(key: str, value: dict[str, Any]) -> None:
    if len(_CAR_CHECK_CACHE) >= _CAR_CHECK_CACHE_MAX_ENTRIES:
        cutoff = time.time()
        stale = [k for k, (exp, _) in _CAR_CHECK_CACHE.items() if exp < cutoff]
        for k in stale[: max(1, len(_CAR_CHECK_CACHE) - _CAR_CHECK_CACHE_MAX_ENTRIES + 1)]:
            _CAR_CHECK_CACHE.pop(k, None)
        if len(_CAR_CHECK_CACHE) >= _CAR_CHECK_CACHE_MAX_ENTRIES:
            for k in list(_CAR_CHECK_CACHE.keys())[: len(_CAR_CHECK_CACHE) - _CAR_CHECK_CACHE_MAX_ENTRIES + 1]:
                _CAR_CHECK_CACHE.pop(k, None)
    _CAR_CHECK_CACHE[key] = (time.time() + _CAR_CHECK_CACHE_TTL_SECONDS, value)


async def run_car_check_ai(
    vehicle_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Call the AI gateway for the Car Check (AUT-2651).

    Input: ``{deal_score, listing: {price, year, odometer_km, make,
    model, listing_url, title}}`` — the deterministic deal score + parsed
    listing from the backend car-check service.

    Returns the parsed result dict (summary / red_flags / green_flags), or
    ``None`` when the gateway is unreachable. The caller renders the
    deterministic fallback (``app.services.car_check.car_check_fallback``)
    so the route always answers.
    """
    cache_key = _car_check_cache_key(vehicle_id, payload or {})
    cached = _car_check_cache_get(cache_key)
    if cached is not None:
        return cached
    result = await _call("car-check", payload or {})
    if not isinstance(result, dict):
        return None
    _car_check_cache_put(cache_key, result)
    return result
