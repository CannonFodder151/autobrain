"""Async SQLAlchemy engine and session.

The engine and SessionLocal are created lazily and re-created when DATABASE_URL
changes so test modules can each set their own database (AUT-296 follow-up).
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Optional

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

_engine: Optional[object] = None
_SessionLocal: Optional[async_sessionmaker] = None
_engine_url: Optional[str] = None

def _current_db_url() -> str:
    return os.environ.get("DATABASE_URL") or settings.sqlalchemy_database_uri

def _get_engine():
    global _engine, _SessionLocal, _engine_url
    url = _current_db_url()
    if _engine is not None and _engine_url != url:
        # Dispose the old engine before creating a new one. pytest runs test
        # modules sequentially so the old engine is no longer in use.
        try:
            asyncio.run(_engine.dispose())
        except Exception:
            pass
        _engine = None
        _SessionLocal = None
    if _engine is None:
        engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
        if not url.startswith("sqlite"):
            engine_kwargs.update(pool_size=10, max_overflow=20)
        _engine = create_async_engine(url, **engine_kwargs)
        _engine_url = url
    return _engine

def _get_session_maker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = async_sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _SessionLocal

class _EngineProxy:
    def __getattr__(self, name):
        return getattr(_get_engine(), name)
    async def __aenter__(self):
        return await _get_engine().__aenter__()
    async def __aexit__(self, *exc):
        return await _get_engine().__aexit__(*exc)

class _SessionProxy:
    def __call__(self, *args, **kwargs):
        return _get_session_maker()(*args, **kwargs)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _get_session_maker()() as session:
        yield session

async def init_db() -> None:
    """Create tables (dev only; prod uses Alembic)."""
    from app import models  # noqa: F401
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

engine = _EngineProxy()
SessionLocal = _SessionProxy()
