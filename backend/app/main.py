"""AutoBrain backend — FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import authenticate_ws
from app.api.v1 import api_router
from app.api.v1.fuel_servo import router as fuel_servo_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.storage import ensure_bucket
from app.db.session import get_db, init_db
from app.middleware.rate_limit import RateLimitMiddleware
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
    version=settings.APP_VERSION,
    description="AI-powered car enthusiast companion. REST + WebSocket.",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
# Servo Spy fuel map: premium-gated, mounted at /api/fuel (not /api/v1) per the
# AUT-1813 feature contract.
app.include_router(fuel_servo_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "autobrain-backend", "version": settings.APP_VERSION}


# Kubernetes-style alias for the boot-probe used by the Flutter app
# (AppConfig.validate -> ${apiOrigin}/healthz). Same handler, no extra
# surface. AUT-2284 N1.
@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return await health()


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    ws: WebSocket,
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await authenticate_ws(ws, db)
    if user is None or user.id != user_id:
        await ws.close(code=4401)
        return
    await manager.connect(user.id, ws)
    try:
        await ws.send_text('{"event":"connected","payload":{}}')
        while True:
            await ws.receive_text()  # keep-alive; server pushes events
    except WebSocketDisconnect:
        manager.disconnect(user.id, ws)
    except Exception:
        manager.disconnect(user.id, ws)
