"""Database bootstrap.

Runs Alembic migrations when available; falls back to metadata create_all
during initial bring-up (before the first migration is authored). Then seeds
the bootstrap admin account. All async DB work shares a single event loop so
the SQLAlchemy engine pool never binds across loops.

AUT-5137: the create_all fallback used to swallow *any* alembic failure and
carry on. ``create_all`` never alters an existing table, so a migration that
only adds a column (or a bad DDL, a truncation, a permission error, a stale
revision id, or a forked head) silently did nothing while boot proceeded and
the deploy reported success — the schema drift only surfaced hours later as
an application error far from the deploy.

The fallback now applies only to a genuinely fresh database (no tables at
all, therefore nothing to drift from). Every other failure aborts startup:
the structured ``migration_failed_startup_aborted`` log line is emitted and
the ops webhook (``BOOT_ALERT_WEBHOOK_URL``) is pinged before the raise,
so a broken migration is distinguishable from a good deploy.
"""

import asyncio
import json
import os
import subprocess
import urllib.request

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MigrationError(RuntimeError):
    """Alembic could not bring the database to head; startup is aborted."""


async def _database_is_empty() -> bool:
    """True when the target schema holds no tables at all.

    That is the only state create_all is a sound substitute for the
    migration chain: there is no existing table whose missing column it
    could silently fail to add.
    """
    from app.db.session import engine

    async with engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        )
    return int(count or 0) == 0


async def _seed_admin() -> None:
    from app.db.seed import seed_admin

    await seed_admin()


async def _seed_demo() -> None:
    from app.db.seed import reset_demo, seed_demo

    if settings.DEMO_RESET:
        await reset_demo()
    else:
        await seed_demo()


def _run_alembic() -> tuple[bool, str]:
    """Attempt ``alembic upgrade head``.

    Returns ``(migrated, error)``. ``error`` carries the last stderr so
    the caller can decide between create_all (fresh DB) and a hard failure.
    ``heads`` is retried after ``head`` because alembic refuses
    ``upgrade head`` when the script tree has more than one head, while
    ``upgrade heads`` legitimately walks all of them.
    """
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    error = ""
    for target in ("head", "heads"):
        try:
            result = subprocess.run(
                ["alembic", "upgrade", target],
                cwd=base,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            # Alembic is not installed in this image.
            return False, "alembic executable not found"
        if result.returncode == 0:
            logger.info("alembic_migrations_applied", target=target)
            return True, ""
        error = (result.stderr or result.stdout or "")[-2000:]
        logger.warning("alembic_failed_trying_next", target=target, stderr=error[-500:])
    return False, error


def _alert(payload: dict) -> None:
    """Fire the ops webhook. Best-effort: never raises, never delays the abort."""
    url = settings.BOOT_ALERT_WEBHOOK_URL
    if not url:
        return
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
    except Exception as exc:  # noqa: BLE001 — alerting must not mask the abort
        logger.warning("boot_alert_failed", error=str(exc))


def _abort(error: str) -> MigrationError:
    """Log, alert, and return the fatal error for a failed migration."""
    payload = {
        "event": "migration_failed_startup_aborted",
        "service": "autobrain-backend",
        "environment": settings.ENVIRONMENT,
        "error": error,
    }
    logger.error(**payload)
    _alert(payload)
    return MigrationError(
        "alembic upgrade failed against a non-empty database; refusing to fall "
        "back to create_all, which cannot add columns to existing tables and "
        "would hide the drift. Fix the migration chain or repair alembic_version, "
        "then redeploy. "
        f"Last error: {error}"
    )


def bootstrap() -> None:
    migrated, error = _run_alembic()

    async def _run() -> None:
        if not migrated:
            try:
                fresh = await _database_is_empty()
            except Exception as exc:
                # Cannot even verify the database state: fail closed.
                raise _abort(f"{error}\n(could not verify database state: {exc})") from exc
            if fresh:
                from app.db.session import init_db

                await init_db()
                logger.info("create_all_fallback_fresh_db")
            else:
                raise _abort(error)
        await _seed_admin()
        await _seed_demo()

    asyncio.run(_run())


if __name__ == "__main__":
    bootstrap()
