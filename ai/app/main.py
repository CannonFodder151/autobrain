"""AutoBrain AI inference gateway.

Exposes /v1/{module}. Each module reads AI_ROUTER_URL at runtime; the router
is tried first and a rule-based fallback keeps the service available offline.

Security: /v1/* inference requires the shared gateway key (AI_GATEWAY_API_KEY,
the same value the backend sends as a Bearer token) and bodies are capped at
AI_GATEWAY_MAX_BODY_BYTES. When the key is unset the gateway logs a warning
and stays open for local dev only.
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

GATEWAY_API_KEY = os.getenv("AI_GATEWAY_API_KEY", "")
MAX_BODY_BYTES = int(os.getenv("AI_GATEWAY_MAX_BODY_BYTES", "1000000"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(
        "ai_gateway_started",
        router_url=router_url(),
        router_enabled=router_enabled(),
        auth_enabled=bool(GATEWAY_API_KEY),
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
    if not GATEWAY_API_KEY:
        logger.warning("ai_gateway_auth_disabled_no_key_configured")
        return
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {GATEWAY_API_KEY}"):
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
async def list_modules() -> dict:
    return {"modules": list(MODULES.keys())}


@app.post("/v1/{module}")
async def infer(module: str, body: InferenceRequest, _: None = Depends(require_gateway_key)) -> dict:
    handler = MODULES.get(module)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module}")
    result = await handler(body.payload)
    return {"result": result}
