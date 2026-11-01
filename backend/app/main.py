from fastapi import FastAPI
from app.api.v1 import health_score

app = FastAPI(
    title="Vehicle Health API",
    description="API for vehicle health monitoring and scoring",
    version="1.0.0",
)

app.include_router(health_score.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy"}


@app.get("/api", tags=["api"])
async def api_root():
    return {
        "service": "Vehicle Health API",
        "version": "1.0.0",
        "status": "operational",
    }