"""Dongle Server application factory: mounts routers, templates, static, lifecycle.

Merged into backend container as sub-app on :8002 (AUT-3153 pattern).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import device, internal, web
from .db import create_all
from .storage import get_storage

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    yield

app = FastAPI(title="autobrain-dongle-server", lifespan=lifespan)

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

app.include_router(internal, prefix="/_internal")
app.include_router(device)
app.include_router(web)

_static = Path(__file__).resolve().parent / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")