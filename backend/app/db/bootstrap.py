"""Database bootstrap.

Runs Alembic migrations when available; falls back to metadata create_all
during initial bring-up (before the first migration is authored). Then seeds
the bootstrap admin account. All async DB work shares a single event loop so
the SQLAlchemy engine pool never binds across loops.
"""

import asyncio
import os
import subprocess

from app.core.logging import get_logger

logger = get_logger(__name__)


async def _seed_admin() -> None:
    from app.db.seed import seed_admin

    await seed_admin()


def bootstrap() -> None:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    migrated = False
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=base,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("alembic_migrations_applied")
            migrated = True
        else:
            logger.warning(
                "alembic_failed_falling_back_to_create_all",
                stderr=result.stderr[-500:],
            )
    except FileNotFoundError:
        pass

    async def _run() -> None:
        if not migrated:
            from app.db.session import init_db

            await init_db()
            logger.info("create_all_fallback_done")
        await _seed_admin()

    asyncio.run(_run())


if __name__ == "__main__":
    bootstrap()
