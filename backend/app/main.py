import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.api.v1 import health_score
from app.api.v1 import admin
from app.api.v1 import engineering_helper
from app.api.v1 import fuel_price
from app.api.v1 import demo_request
from app.api.v1 import track
from app.api.v1 import ownership_advisor
from app.api.v1 import vass
from app.api.v1 import issues
from app.api.v1 import social
from app.api.v1 import fuel_service
from app.api.v1 import fuel_watchlist
from app.api.v1 import workshop
from app.core.middleware import SecurityMiddleware, ErrorHandlerMiddleware

_CHECK_INTERVAL_SECONDS = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_watchlist_poll_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _watchlist_poll_loop():
    from app.api.v1.fuel_watchlist import run_check_all_users
    while True:
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
        try:
            await run_check_all_users()
        except Exception:
            pass


app = FastAPI(
    title="Vehicle Health API",
    description="API for vehicle health monitoring and scoring",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(health_score.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(engineering_helper.router, prefix="/api/v1")
app.include_router(fuel_price.router, prefix="/api/v1")
app.include_router(demo_request.router, prefix="/api/v1")
app.include_router(track.router, prefix="/api/track")
app.include_router(ownership_advisor.router, prefix="/api/v1")
app.include_router(vass.router, prefix="/api/v1/vass")
app.include_router(issues.router, prefix="/api/v1")
app.include_router(social.router, prefix="/api/v1")
app.include_router(fuel_service.router, prefix="/api/v1/fuel-service")
app.include_router(fuel_watchlist.router, prefix="/api/v1")
app.include_router(workshop.router, prefix="/api/v1")

app.add_middleware(SecurityMiddleware)
app.add_middleware(ErrorHandlerMiddleware)

@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy"}

@app.get("/api", tags=["api"])
async def api_root():
    return {
        "service": "Vehicle Health API",
        "status": "operational",
    }