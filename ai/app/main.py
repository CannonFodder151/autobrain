"""AutoBrain AI inference gateway.

Exposes /v1/{module}. Each module reads AI_ROUTER_URL at runtime; the router
is tried first and a rule-based fallback keeps the service available offline.

Security: /v1/* requires the shared gateway key (AI_GATEWAY_API_KEY, the same
value the backend sends as a Bearer token) and bodies are capped at
AI_GATEWAY_MAX_BODY_BYTES. Auth FAILS CLOSED: when the key is unset the
gateway rejects /v1 calls with 401 unless the explicit development opt-out is
set (AI_GATEWAY_AUTH_DISABLED=1 or AI_ENV=development).
"""

import hmac
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.logging import get_logger, setup_logging
from app.modules import MODULES
from app.router_client import router_enabled, router_url

logger = get_logger(__name__)

MAX_BODY_BYTES = int(os.getenv("AI_GATEWAY_MAX_BODY_BYTES", "1000000"))


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
    version=os.environ.get("APP_VERSION", "0.3.5"),  # bump-version.sh keeps this in sync
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


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "autobrain-ai",
        "version": os.environ.get("APP_VERSION", "0.3.5"),
        "router_url": router_url(),
        "router_enabled": router_enabled(),
    }


@app.get("/v1/modules")
async def list_modules(_: None = Depends(require_gateway_key)) -> dict:
    return {"modules": list(MODULES.keys())}


@app.post("/v1/{module}")
async def infer(module: str, body: InferenceRequest, _: None = Depends(require_gateway_key)) -> dict:
    handler = MODULES.get(module)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module}")
    result = await handler(body.payload)
    return {"result": result}
