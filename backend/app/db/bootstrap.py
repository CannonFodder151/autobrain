"""Database bootstrap.

Runs Alembic migrations when available; falls back to metadata create_all
during initial bring-up (before the first migration is authored). Then seeds
the bootstrap admin account. All async DB work shares a single event loop so
the SQLAlchemy engine pool never binds across loops.
"""

import asyncio
import os
import subprocess

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _seed_admin() -> None:
    from app.db.seed import seed_admin

    await seed_admin()


async def _seed_demo() -> None:
    from app.db.seed import reset_demo, seed_demo

    if settings.DEMO_RESET:
        await reset_demo()
    else:
        await seed_demo()


async def _ensure_missing_columns() -> None:
    """Add columns that Alembic migrations may have missed (AUT-3317).

    ``create_all`` only creates tables that don't exist — it never alters
    existing ones.  When the migration graph has multiple heads and
    ``alembic upgrade`` fails, the bootstrap falls back to ``create_all``,
    leaving any *new* columns on *existing* tables absent.  This function
    patches that gap for critical columns that the current codebase
    requires.

    Each check is idempotent: SELECT the column list, add if missing.
    """
    from sqlalchemy import text
    from app.db.session import engine

    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'fuel_prices'"
            )
        )
        cols = {row[0] for row in result.fetchall()}

        if "source_id" not in cols:
            logger.warning("patching_missing_column", table="fuel_prices", column="source_id")
            await conn.execute(text('ALTER TABLE fuel_prices ADD COLUMN source_id VARCHAR(16)'))
        if "arbitration_score" not in cols:
            logger.warning("patching_missing_column", table="fuel_prices", column="arbitration_score")
            await conn.execute(text('ALTER TABLE fuel_prices ADD COLUMN arbitration_score DOUBLE PRECISION'))

        # Ensure fuel_price_arbitrations table exists (aut2386).
        tbl = await conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = 'fuel_price_arbitrations'")
        )
        if not tbl.first():
            logger.warning("patching_missing_table", table="fuel_price_arbitrations")
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS fuel_price_arbitrations ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  station_id VARCHAR(36) NOT NULL REFERENCES fuel_stations(id),"
                "  fuel_type VARCHAR(16) NOT NULL,"
                "  day TIMESTAMPTZ NOT NULL,"
                "  source_id VARCHAR(16) NOT NULL,"
                "  price DOUBLE PRECISION NOT NULL,"
                "  arbitration_score DOUBLE PRECISION NOT NULL,"
                "  candidate_count INTEGER NOT NULL DEFAULT 1,"
                "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
                "  UNIQUE (station_id, fuel_type, day)"
                ")"
            ))


def bootstrap() -> None:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    migrated = False
    for target in ("head", "heads"):
        try:
            result = subprocess.run(
                ["alembic", "upgrade", target],
                cwd=base,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info("alembic_migrations_applied", target=target)
                migrated = True
                break
            logger.warning(
                "alembic_failed_trying_next",
                target=target,
                stderr=result.stderr[-500:],
            )
        except FileNotFoundError:
            break

    async def _run() -> None:
        if not migrated:
            from app.db.session import init_db

            await init_db()
            logger.info("create_all_fallback_done")
        await _ensure_missing_columns()
        await _seed_admin()
        await _seed_demo()

    asyncio.run(_run())


if __name__ == "__main__":
    bootstrap()
