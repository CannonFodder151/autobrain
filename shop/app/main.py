"""AutoBrain Shop — FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.storage import ensure_bucket
from app.db.session import get_db, init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting", environment=settings.ENVIRONMENT)
    if settings.ENVIRONMENT == "development":
        await init_db()
    try:
        await ensure_bucket()
    except Exception as exc:
        logger.warning("minio_unavailable_at_startup", error=str(exc))
    yield
    logger.info("shutdown")


app = FastAPI(
    title="AutoBrain Shop API",
    version=settings.APP_VERSION,
    description="Multi-tenant workshop management for AutoBrain.",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "autobrain-shop-backend",
        "version": settings.APP_VERSION,
        "env": settings.ENVIRONMENT,
    }


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return await health()