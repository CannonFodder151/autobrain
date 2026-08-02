"""Database bootstrap.

Runs Alembic migrations when available; falls back to metadata create_all
during initial bring-up (before the first migration is authored). Keeps both
paths idempotent.
"""

import asyncio
import os
import subprocess
import sys

from app.core.logging import get_logger

logger = get_logger(__name__)


def bootstrap() -> None:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=base,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("alembic_migrations_applied")
            return
        logger.warning(
            "alembic_unavailable_falling_back_to_create_all",
            stderr=result.stderr[-500:],
        )
    except FileNotFoundError:
        pass
    from app.db.session import init_db

    asyncio.run(init_db())
    logger.info("create_all_fallback_done")


if __name__ == "__main__":
    bootstrap()
