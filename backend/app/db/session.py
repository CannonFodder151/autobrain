"""Async SQLAlchemy engine and session."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
if not settings.sqlalchemy_database_uri.startswith("sqlite"):
    engine_kwargs.update(pool_size=10, max_overflow=20)
engine = create_async_engine(settings.sqlalchemy_database_uri, **engine_kwargs)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables (dev only; prod uses Alembic)."""
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
