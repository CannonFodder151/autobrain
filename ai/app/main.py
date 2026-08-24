"""AutoBrain AI inference gateway.

Exposes /v1/{module}. Each module reads AI_ROUTER_URL at runtime; the router
is tried first and a rule-based fallback keeps the service available offline.

Security: /v1/* requires the shared gateway key (AI_GATEWAY_API_KEY, the same
value the backend sends as a Bearer token) and bodies are capped at
AI_GATEWAY_MAX_BODY_BYTES. Auth FAILS CLOSED: when the key is unset the
gateway rejects /v1 calls with 401 unless the explicit development opt-out is
set (AI_GATEWAY_AUTH_DISABLED=1 or AI_ENV=development).

Cost control: an in-memory fixed-window limiter (per client IP + global)
rejects with 429 when authenticated traffic exceeds
AI_GATEWAY_RATE_LIMIT_PER_WINDOW (per IP) or
AI_GATEWAY_GLOBAL_RATE_LIMIT_PER_WINDOW within AI_GATEWAY_RATE_WINDOW_SECONDS.
Defaults are set well above the daily fleet-valuation refresh (same shared key)
so legit bursts pass; this is a coarse ceiling for runaway/compromised callers.
Per-user precision lives in the backend (AUT-302).
"""

import hmac
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.logging import get_logger, setup_logging
from app.modules import MODULES
from app.router_client import router_enabled, router_url

logger = get_logger(__name__)

MAX_BODY_BYTES = int(os.getenv("AI_GATEWAY_MAX_BODY_BYTES", "1000000"))

def _window_seconds() -> int:
    return int(os.getenv("AI_GATEWAY_RATE_WINDOW_SECONDS", "60"))

def _per_ip_limit() -> int:
    return int(os.getenv("AI_GATEWAY_RATE_LIMIT_PER_WINDOW", "600"))

def _global_limit() -> int:
    return int(os.getenv("AI_GATEWAY_GLOBAL_RATE_LIMIT_PER_WINDOW", "6000"))

# In-memory fixed-window counters. Single-process uvicorn; a hard ceiling (not
# a rate-accurate store) is the point — the backend owns precise per-user caps.
_rate_windows: dict[str, tuple[int, int]] = {}


def _gateway_key() -> str:
    return os.environ.get("AI_GATEWAY_API_KEY", "")


def _auth_disabled() -> bool:
    return (
        os.environ.get("AI_GATEWAY_AUTH_DISABLED") == "1"
        or os.environ.get("AI_ENV") == "development"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(
        "ai_gateway_started",
        router_url=router_url(),
        router_enabled=router_enabled(),
        auth_enabled=bool(_gateway_key()),
    )
    yield


app = FastAPI(
    title="AutoBrain AI Gateway",
    version=os.environ.get("APP_VERSION", "0.3.130"),  # bump-version.sh keeps this in sync
    description="Inference layer. Routes through 9Router via AI_ROUTER_URL.",
    lifespan=lifespan,
)


class InferenceRequest(BaseModel):
    payload: dict


@app.middleware("http")
async def enforce_payload_size(request: Request, call_next):
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Payload too large"})
    return await call_next(request)


def require_gateway_key(authorization: str | None = Header(default=None)) -> None:
    if _auth_disabled():
        return
    expected = _gateway_key()
    if not expected:
        raise HTTPException(
            status_code=401,
            detail="AI gateway not configured: AI_GATEWAY_API_KEY must be set",
        )
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _window_allows(key: str, limit: int, window: int) -> bool:
    bucket = int(time.time()) // window
    if len(_rate_windows) > 10_000:
        _rate_windows.clear()
    current = _rate_windows.get(key)
    if current is None or current[0] != bucket:
        _rate_windows[key] = (bucket, 1)
        return True
    if current[1] >= limit:
        return False
    _rate_windows[key] = (bucket, current[1] + 1)
    return True


def enforce_gateway_rate_limit(request: Request) -> None:
    """Per-IP + global fixed-window cap on authenticated /v1 inference calls."""
    client_ip = request.client.host if request.client else "unknown"
    window = _window_seconds()
    if not _window_allows(f"ip:{client_ip}", _per_ip_limit(), window):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    if not _window_allows("global", _global_limit(), window):
        raise HTTPException(status_code=429, detail="Global rate limit exceeded. Try again later.")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "autobrain-ai",
        "version": os.environ.get("APP_VERSION", "0.3.130"),
        "router_url": router_url(),
        "router_enabled": router_enabled(),
    }


@app.get("/v1/modules")
async def list_modules(_: None = Depends(require_gateway_key)) -> dict:
    return {"modules": list(MODULES.keys())}


@app.post("/v1/{module}")
async def infer(
    module: str,
    body: InferenceRequest,
    _: None = Depends(require_gateway_key),
    _rl: None = Depends(enforce_gateway_rate_limit),
) -> dict:
    handler = MODULES.get(module)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module}")
    result = await handler(body.payload)
    return {"result": result}
