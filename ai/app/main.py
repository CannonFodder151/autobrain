"""AutoBrain AI inference gateway.

Exposes /v1/{module}. Each module reads AI_ROUTER_URL at runtime; the router
is tried first and a rule-based fallback keeps the service available offline.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.logging import get_logger, setup_logging
from app.modules import MODULES
from app.router_client import router_enabled, router_url

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("ai_gateway_started", router_url=router_url(), router_enabled=router_enabled())
    yield


app = FastAPI(
    title="AutoBrain AI Gateway",
    version="0.1.0",
    description="Inference layer. Routes through 9Router via AI_ROUTER_URL.",
    lifespan=lifespan,
)


class InferenceRequest(BaseModel):
    payload: dict


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "autobrain-ai",
        "router_url": router_url(),
        "router_enabled": router_enabled(),
    }


@app.get("/v1/modules")
async def list_modules() -> dict:
    return {"modules": list(MODULES.keys())}


@app.post("/v1/{module}")
async def infer(module: str, body: InferenceRequest) -> dict:
    handler = MODULES.get(module)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module}")
    result = await handler(body.payload)
    return {"result": result}
