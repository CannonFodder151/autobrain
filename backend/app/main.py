"""AutoBrain backend — FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.storage import ensure_bucket
from app.db.session import init_db
from app.ws.manager import manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting", environment=settings.ENVIRONMENT)
    if settings.ENVIRONMENT == "development":
        await init_db()
    try:
        await ensure_bucket()
    except Exception as exc:  # MinIO may be warming up; Celery retries later
        logger.warning("minio_unavailable_at_startup", error=str(exc))
    yield
    logger.info("shutdown")


app = FastAPI(
    title="AutoBrain API",
    version="0.2.0",
    description="AI-powered car enthusiast companion. REST + WebSocket.",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT != "production" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "autobrain-backend", "version": "0.2.0"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(ws: WebSocket, user_id: str) -> None:
    await manager.connect(user_id, ws)
    try:
        await ws.send_text('{"event":"connected","payload":{}}')
        while True:
            await ws.receive_text()  # keep-alive; server pushes events
    except WebSocketDisconnect:
        manager.disconnect(user_id, ws)
    except Exception:
        manager.disconnect(user_id, ws)
