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
        await _seed_admin()
        await _seed_demo()

    asyncio.run(_run())


if __name__ == "__main__":
    bootstrap()
